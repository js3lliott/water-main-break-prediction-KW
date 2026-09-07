-- THE TRAINING TABLE. One row per pipe segment per year at risk.
--
-- Grain: (watmainid, panel_year) -- enforced by a composite uniqueness test.
--
-- Every feature is as-of 1 January of panel_year. The outcome columns
-- (broke_in_year, break_count) are the only things here that describe the year
-- itself; anything else that did would be leakage.
--
-- Known limitation: static pipe attributes are the CURRENT inventory values
-- retro-applied to historical years. Once snap_water_mains has accumulated
-- history, this should join point-in-time-correct attributes instead. Material
-- and diameter rarely change; condition_score does, which is one more reason
-- to treat it carefully as a feature.

with spine as (

    select * from {{ ref('int_pipe_year_spine') }}

),

history as (

    select * from {{ ref('int_pipe_year_history') }}

),

outcomes as (

    select * from {{ ref('int_pipe_year_breaks') }}

),

winter as (

    select * from {{ ref('int_winter_severity') }}

),

pipe as (

    select
        watmainid,
        material,
        diameter_mm,
        pressure_zone,
        install_decade,
        ownership,
        category,
        criticality,
        condition_score,
        is_lined,
        is_undersized,
        is_oversized,
        is_shallow,
        is_bridge_main,
        is_cleaned,
        is_negligible_length
    from {{ ref('dim_pipe') }}

)

select
    -- ---- grain ----
    spine.watmainid,
    spine.panel_year,

    -- ---- outcome ----
    coalesce(outcomes.break_count, 0)               as break_count,
    coalesce(outcomes.break_count, 0) > 0           as broke_in_year,
    coalesce(outcomes.winter_break_count, 0)        as winter_break_count,
    outcomes.first_break_date,

    -- ---- exposure ----
    -- A 300 m main is not the same risk as a 12 m main. Rate models take
    -- log(length_km) as an offset; classifiers take length_m as a feature.
    spine.length_m,
    spine.length_km,

    -- ---- as-of-year-start features ----
    spine.age_years,
    spine.install_year,
    history.prior_break_count,
    history.prior_break_count_capped,
    history.has_prior_break,
    history.years_since_last_break,
    history.last_break_year,

    -- Location history, kept separate from this pipe's own history. See
    -- int_breaks_matched for why conflating them would poison the material
    -- coefficient.
    history.predecessor_break_count,
    history.location_had_earlier_pipe_break,

    pipe.material,
    pipe.diameter_mm,
    pipe.pressure_zone,
    pipe.install_decade,
    pipe.ownership,
    pipe.category,
    pipe.criticality,
    pipe.condition_score,
    pipe.is_lined,
    pipe.is_undersized,
    pipe.is_oversized,
    pipe.is_shallow,
    pipe.is_bridge_main,
    pipe.is_cleaned,

    -- Sub-metre GIS connector artifacts. Harmless per-segment, but they must be
    -- excluded from any length-normalised rate.
    pipe.is_negligible_length,

    -- ---- winter severity (weather-sensitivity model only; see model doc) ----
    winter.freeze_thaw_days,
    winter.freezing_degree_days,
    winter.coldest_7day_mean_c,
    winter.avg_mean_temp_c                          as winter_avg_mean_temp_c,
    winter.has_adequate_coverage                    as winter_has_adequate_coverage,

    -- ---- flags ----
    spine.is_complete_year

from spine
left join history
    on spine.watmainid = history.watmainid
   and spine.panel_year = history.panel_year
left join outcomes
    on spine.watmainid = outcomes.watmainid
   and spine.panel_year = outcomes.panel_year
left join winter
    on spine.panel_year = winter.panel_year
left join pipe
    on spine.watmainid = pipe.watmainid
