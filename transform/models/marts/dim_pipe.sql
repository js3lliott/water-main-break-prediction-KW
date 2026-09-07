-- One row per water main segment: the current state of the network.
--
-- Attribute vintage caveat: these are the values as of the latest extract. The
-- snapshot (snap_water_mains) is what will eventually let a pipe-year use the
-- attributes that were true *that year* rather than today's; until it has
-- accumulated history, fct_pipe_year retro-applies current attributes. That is
-- a known and documented limitation, not an oversight.

with mains as (

    select * from {{ ref('stg_water_mains') }}

),

break_summary as (

    select
        watmainid,

        -- Breaks on this pipe, after it went in the ground.
        count(*) filter (where match_status = 'matched')           as lifetime_break_count,
        min(incident_date) filter (where match_status = 'matched') as first_break_date,
        max(incident_date) filter (where match_status = 'matched') as last_break_date,

        -- Breaks recorded against this asset ID that predate this pipe's
        -- installation: the pipe that used to be here. Counting these as this
        -- pipe's own history would credit a 2010 PVC segment with failures
        -- from the cast iron it replaced.
        count(*) filter (where match_status = 'predecessor_asset')           as predecessor_break_count,
        max(incident_date) filter (where match_status = 'predecessor_asset') as last_predecessor_break_date

    from {{ ref('int_breaks_matched') }}
    where match_status in ('matched', 'predecessor_asset')
    group by 1

)

select
    mains.watmainid,
    mains.arcgis_object_id,
    mains.road_segment_id,

    mains.material,
    mains.material_raw,
    mains.diameter_mm,
    mains.length_m,
    mains.length_km,
    mains.is_negligible_length,
    mains.install_date,
    mains.install_year,
    mains.install_decade,
    cast(extract(year from current_date) as integer) - mains.install_year as current_age_years,

    mains.pressure_zone,
    mains.category,
    mains.ownership,
    mains.acquisition,
    mains.cleaning_area,
    mains.criticality,
    mains.condition_score,

    mains.is_lined,
    mains.lined_date,
    mains.lined_material,
    mains.is_undersized,
    mains.is_oversized,
    mains.is_shallow,
    mains.is_bridge_main,
    mains.is_cleaned,

    coalesce(break_summary.lifetime_break_count, 0) as lifetime_break_count,
    coalesce(break_summary.lifetime_break_count, 0) > 0 as has_ever_broken,
    break_summary.first_break_date,
    break_summary.last_break_date,

    coalesce(break_summary.predecessor_break_count, 0) as predecessor_break_count,
    break_summary.last_predecessor_break_date,

    -- A dated replacement event: something at this location failed, and the
    -- pipe here now was installed afterwards. This is the observable edge of
    -- the survivorship bias -- the failure-prone pipes have been progressively
    -- removed from the population the model trains on.
    coalesce(break_summary.predecessor_break_count, 0) > 0 as replaced_after_break,

    mains.geometry_wkt,
    mains.extracted_at

from mains
left join break_summary on mains.watmainid = break_summary.watmainid
