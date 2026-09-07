-- Neighbourhood break pressure per pipe-year, as of 1 January.
--
-- Same as-of discipline as int_pipe_year_history: the year bound is strictly
-- `<`, so nothing here can see the year being predicted.

with spine as (

    select watmainid, panel_year from {{ ref('int_pipe_year_spine') }}

),

neighbour_breaks as (

    select * from {{ ref('int_pipe_neighbour_breaks') }}

),

static_neighbourhood as (

    select * from {{ ref('int_pipe_neighbourhood') }}

),

windowed as (

    select
        spine.watmainid,
        spine.panel_year,

        coalesce(sum(neighbour_breaks.neighbour_breaks), 0)  as neighbour_breaks_prior_all,

        coalesce(sum(neighbour_breaks.neighbour_breaks) filter (
            where neighbour_breaks.incident_year >= spine.panel_year - 5
        ), 0)                                               as neighbour_breaks_prior_5y

    from spine
    left join neighbour_breaks
        on neighbour_breaks.watmainid = spine.watmainid
       and neighbour_breaks.incident_year < spine.panel_year   -- as-of guard
    group by 1, 2

)

select
    windowed.watmainid,
    windowed.panel_year,
    windowed.neighbour_breaks_prior_all,
    windowed.neighbour_breaks_prior_5y,

    coalesce(static_neighbourhood.neighbour_pipe_km, 0)     as neighbour_pipe_km,
    coalesce(static_neighbourhood.neighbour_pipe_count, 0)  as neighbour_pipe_count,

    -- Normalised local burden: nearby breaks per km of nearby pipe. Six breaks
    -- around a dense downtown block is a different signal from six around a
    -- single suburban run.
    case
        when coalesce(static_neighbourhood.neighbour_pipe_km, 0) > 0.1
            then round(
                windowed.neighbour_breaks_prior_5y / static_neighbourhood.neighbour_pipe_km, 4
            )
    end                                                     as neighbour_breaks_per_km_5y

from windowed
left join static_neighbourhood
    on static_neighbourhood.watmainid = windowed.watmainid
