-- The pipe inventory: one row per water main segment currently in the network.
--
-- This is the model that supplies the panel's negative examples. The original
-- pipeline never used it, so every training row was a pipe that had already
-- broken.

with raw_mains as (

    select * from {{ source('raw', 'water_mains') }}

),

-- Each extract run writes a new partition. Keep only the newest so the model
-- is idempotent however many partitions have accumulated.
latest as (

    select * from raw_mains
    where _extracted_at = (select max(_extracted_at) from raw_mains)

),

cleaned as (

    select
        "WATMAINID"                                 as watmainid,
        "OBJECTID"                                  as arcgis_object_id,
        "ROADSEGMENTID"                             as road_segment_id,
        "STATUS"                                    as status,
        "PRESSURE_ZONE"                             as pressure_zone,
        "CATEGORY"                                  as category,
        "MAP_LABEL"                                 as map_label,

        -- Sentinel codes. The service uses 0 for "no recorded diameter" and
        -- -1 for "not scored"; left as-is they read as a 0 mm pipe and a
        -- worse-than-worst condition.
        nullif("PIPE_SIZE", 0)                      as diameter_mm,
        nullif("CONDITION_SCORE", -1)               as condition_score,
        nullif("CRITICALITY", -1)                   as criticality,

        -- 'XXX' is an unknown-material placeholder, not a material.
        nullif("MATERIAL", 'XXX')                   as material_raw,

        "LINED" = 'YES'                             as is_lined,
        cast("LINED_DATE" as date)                  as lined_date,
        nullif("LINED_MATERIAL", 'NONE')            as lined_material,
        "UNDERSIZED" = 'Y'                          as is_undersized,
        "OVERSIZED" = 'Y'                           as is_oversized,
        "SHALLOW_MAIN" = 'Y'                        as is_shallow,
        "BRIDGE_MAIN" = 'Y'                         as is_bridge_main,
        "CLEANED" = 'Y'                             as is_cleaned,

        -- Source has both 'KITCHENER' and 'Kitchener'.
        upper(trim("OWNERSHIP"))                    as ownership,
        upper(trim("ACQUISITION"))                  as acquisition,
        "REL_CLEANING_AREA"                         as cleaning_area,

        cast("INSTALLATION_DATE" as date)           as install_date,
        cast(extract(year from "INSTALLATION_DATE") as integer) as install_year,

        -- Shape__Length is in the layer's native SR (EPSG:26917), so it is
        -- already metres. Do NOT derive length from geometry_wkt, which the
        -- extractor reprojects to degrees.
        "Shape__Length"                             as length_m,
        "Shape__Length" / 1000.0                    as length_km,

        "geometry_wkt"                              as geometry_wkt,
        _extracted_at                               as extracted_at

    from latest

)

select
    *,

    -- Rare materials (each under ~60 segments) are pooled so one-hot
    -- encodings don't carry near-zero-support columns into the model.
    case
        when material_raw is null then null
        when material_raw in ('PVC', 'DI', 'CI', 'PVCO', 'CPP') then material_raw
        else 'OTHER'
    end as material,

    -- Integer division: `install_year / 10` is float division in DuckDB and
    -- yields labels like '1987.0s'.
    case
        when install_year is null then null
        when install_year < 1900 then 'PRE_1900'
        else cast(cast(floor(install_year / 10.0) * 10 as integer) as varchar) || 's'
    end as install_decade,

    -- The inventory contains 655 segments under a metre, the shortest under a
    -- millimetre. They are GIS connector artifacts rather than real pipe, and
    -- they wreck any length-normalised rate: a 1 cm "segment" with one break
    -- scores 14,000 breaks per 100 km. Flagged rather than deleted, because
    -- they are still valid rows for a per-segment model.
    length_m < 1.0 as is_negligible_length

from cleaned
