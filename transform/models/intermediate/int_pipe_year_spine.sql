-- The panel skeleton: one row per pipe per year it was in the ground and at
-- risk. This is the grain change the whole project turns on -- it is what
-- supplies the ~99.4% of rows where nothing broke.
--
-- Two boundary rules:
--   * History starts at `panel_start_year` (1997). Only 10 break records
--     predate it, so earlier years would encode "no record" as "no break".
--   * A pipe enters the panel the year AFTER installation, so no row carries a
--     partial year of exposure.

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
        generate_series({{ var('panel_start_year') }}, {{ current_year }})
    ) as panel_year

)

select
    pipes.watmainid,
    years.panel_year,
    pipes.install_year,
    pipes.length_m,
    pipes.length_km,

    years.panel_year - pipes.install_year           as age_years,

    -- The current year is still accruing breaks. Training must exclude it or
    -- it drags the observed positive rate down; the flag makes that explicit
    -- rather than leaving it to whoever writes the training query.
    years.panel_year < {{ current_year }}           as is_complete_year

from pipes
cross join years
where years.panel_year > pipes.install_year
