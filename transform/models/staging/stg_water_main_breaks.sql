-- Recorded break incidents, one row per incident.
--
-- Two filters are applied here rather than silently downstream, because both
-- change what "a break" means:
--
--   * BREAK_TYPE = 'MAIN'  -- the file also carries service-line breaks, which
--     are a different asset class on a different failure mechanism.
--   * STATUS <> 'CANCELLED' -- cancelled call-outs are not confirmed breaks.
--
-- Both are driven by dbt vars so the choice is visible and reversible.

with raw_breaks as (

    select * from {{ source('raw', 'water_main_breaks') }}

),

latest as (

    select * from raw_breaks
    where _extracted_at = (select max(_extracted_at) from raw_breaks)

),

cleaned as (

    select
        "WATBREAKINCIDENTID"                        as break_incident_id,
        "OBJECTID"                                  as arcgis_object_id,
        "GLOBALID"                                  as global_id,

        -- The join key to the inventory. The original pipeline joined on
        -- ROADSEGMENTID, which carries up to 45 mains per segment.
        "ASSETID"                                   as watmainid,
        "ROADSEGMENTID"                             as road_segment_id,

        cast("INCIDENT_DATE" as date)               as incident_date,
        cast(extract(year from "INCIDENT_DATE") as integer)  as incident_year,
        cast(extract(month from "INCIDENT_DATE") as integer) as incident_month,

        "BREAK_TYPE"                                as break_type,
        "STATUS"                                    as status,
        coalesce("BREAK_NATURE", 'UNKNOWN')         as break_nature,
        coalesce("BREAK_APPARENT_CAUSE", 'UNKNOWN') as break_apparent_cause,
        coalesce("BREAK_CATEGORIZATION", 'UNKNOWN') as break_categorization,

        "STREET"                                    as street,
        "CIVIC_NUMBER"                              as civic_number,

        -- Asset attributes as recorded on the incident. These are kept for
        -- reconciliation against the inventory, NOT as model features -- the
        -- inventory is the system of record for pipe attributes.
        nullif("ASSET_SIZE", 0)                     as reported_diameter_mm,
        nullif("ASSET_MATERIAL", 'XXX')             as reported_material,
        try_cast("ASSET_YEAR_INSTALLED" as integer) as reported_install_year,

        -- ASSET_EXISTS is an OUTCOME, not a predictor: rows flagged 'N' have a
        -- median install year ~45 years later than 'Y', which is the signature
        -- of post-break replacement. Carried for the survivorship analysis and
        -- excluded from features.
        "ASSET_EXISTS" = 'Y'                        as asset_still_exists,

        "geometry_wkt"                              as geometry_wkt,
        _extracted_at                               as extracted_at

    from latest
    where "BREAK_TYPE" in ({% for t in var('break_types') %}'{{ t }}'{% if not loop.last %}, {% endif %}{% endfor %})
      and "STATUS" not in ({% for s in var('excluded_break_statuses') %}'{{ s }}'{% if not loop.last %}, {% endif %}{% endfor %})

)

select * from cleaned
