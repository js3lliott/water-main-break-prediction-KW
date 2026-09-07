-- Breaks joined to the pipe inventory on the correct key.
--
-- `ASSETID -> WATMAINID` is a true 1:1 lookup: WATMAINID is unique across the
-- inventory. The original pipeline joined on ROADSEGMENTID, which carries up
-- to 45 mains per segment and therefore fanned 2,766 break records out to
-- 10,761 rows with mostly-wrong pipe attributions.
--
-- `match_status` is materialised rather than filtered away, because the
-- non-matching cases are the survivorship bias this project has to quantify:
--
--   orphan_asset       ASSETID is not in the inventory at all (~17%). Mostly
--                      pipes replaced after failing, now gone.
--   predecessor_asset  The break predates the install date of the pipe that
--                      currently holds this ID (~310 records). The asset ID
--                      was carried over to the replacement pipe.
--
-- The `predecessor_asset` case is worth being precise about, because it looks
-- like a data error and is not. For every one of those records, the break's OWN
-- `ASSET_YEAR_INSTALLED` also postdates the incident -- and `reported_material`
-- agrees with the current inventory 98.4% of the time. The break record's
-- ASSET_* columns are therefore a denormalised copy of *today's* inventory,
-- refreshed when the pipe was replaced, not a historical record of the pipe
-- that actually failed.
--
-- Two consequences, both load-bearing:
--   1. reported_material / reported_install_year / reported_diameter_mm are not
--      evidence about the failed pipe and must not be used as features.
--   2. These rows are dated replacement events -- we know a pipe here broke in
--      year X and the pipe here now went in at year Y > X. That is the most
--      direct measurement of the replacement process available in this data.

with breaks as (

    select * from {{ ref('stg_water_main_breaks') }}

),

mains as (

    select watmainid, install_year, material, diameter_mm from {{ ref('stg_water_mains') }}

)

select
    breaks.*,

    case
        when breaks.watmainid is null then 'null_asset_id'
        when mains.watmainid is null then 'orphan_asset'
        when breaks.incident_year < mains.install_year then 'predecessor_asset'
        else 'matched'
    end                                             as match_status,

    mains.install_year                              as pipe_install_year,
    mains.material                                  as pipe_material,
    mains.diameter_mm                               as pipe_diameter_mm,

    -- Age at failure, from the inventory's install year rather than the
    -- incident record's, since the inventory is the system of record.
    case
        when mains.install_year is not null
            then breaks.incident_year - mains.install_year
    end                                             as age_at_break_years

from breaks
left join mains on breaks.watmainid = mains.watmainid
