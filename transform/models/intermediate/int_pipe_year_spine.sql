-- The panel skeleton: one row per pipe per year it was in the ground and at
-- risk. This is the grain change the whole project turns on -- it is what
-- supplies the ~99.4% of rows where nothing broke.
--
-- Three boundary rules:
--   * History starts at `panel_start_year` (1997). Only 10 break records
--     predate it, so earlier years would encode "no record" as "no break".
--   * A pipe enters the panel the year AFTER installation, so no row carries a
--     partial year of exposure.
--   * The panel runs one year PAST the current year. That forecast year has no
--     outcome and never will until it arrives -- it exists so the scoring
--     pipeline has rows to score. An inspection list is for the year ahead;
--     ranking the current year is half-pointless once it is half over.

{% set current_year = "cast(extract(year from current_date) as integer)" %}

with pipes as (

    select
        watmainid,
        install_year,
        length_m,
        length_km
    from {{ ref('stg_water_mains') }}
    where install_year is not null

),

years as (

    select unnest(
        generate_series({{ var('panel_start_year') }}, {{ current_year }} + 1)
    ) as panel_year

)

select
    pipes.watmainid,
    years.panel_year,
    pipes.install_year,
    pipes.length_m,
    pipes.length_km,

    years.panel_year - pipes.install_year           as age_years,

    -- The forecast year: features are as-of its 1 January, outcome unknown.
    -- Excluded from training and from every rate table by is_complete_year.
    years.panel_year > {{ current_year }}           as is_forecast_year,

    -- The current year is still accruing breaks. Training must exclude it or
    -- it drags the observed positive rate down; the flag makes that explicit
    -- rather than leaving it to whoever writes the training query.
    years.panel_year < {{ current_year }}           as is_complete_year

from pipes
cross join years
where years.panel_year > pipes.install_year
