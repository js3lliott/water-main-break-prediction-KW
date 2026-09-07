-- Network failure rates in the unit the water industry actually benchmarks on:
-- breaks per 100 km per year.
--
-- This is the model that answers "is cast iron really the problem?". Raw counts
-- say CI dominates breaks, but CI is a minority of the network by length. Only
-- the length-normalised rate settles it.

with panel as (

    select * from {{ ref('fct_pipe_year') }}
    where is_complete_year

)

select
    panel_year,
    coalesce(material, 'UNKNOWN')                   as material,
    pressure_zone,
    coalesce(install_decade, 'UNKNOWN')             as install_decade,

    count(*)                                        as pipe_years,
    round(sum(length_km), 2)                        as exposure_km,
    sum(break_count)                                as breaks,
    sum(case when broke_in_year then 1 else 0 end)  as pipes_with_a_break,

    -- The headline rate, suppressed below 1 km of exposure. A rate computed
    -- over 10 metres of pipe is not a rate, it is an artifact of the
    -- denominator -- and this cut is fine enough that some cells really do have
    -- almost no pipe in them.
    case
        when sum(length_km) >= 1.0
            then round(100.0 * sum(break_count) / sum(length_km), 2)
    end                                             as breaks_per_100km,

    sum(length_km) >= 1.0                           as has_reportable_exposure,

    round(avg(age_years), 1)                        as mean_age_years

from panel
group by 1, 2, 3, 4
