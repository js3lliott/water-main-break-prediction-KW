-- Break history for each pipe-year, computed strictly AS OF 1 January of the
-- panel year.
--
-- The `< panel_year` bound is the leakage guard for the whole project. Every
-- aggregate here must be knowable before the year starts; a `<=` anywhere in
-- this file would let the model see the outcome it is predicting.

with spine as (

    select watmainid, panel_year from {{ ref('int_pipe_year_spine') }}

),

breaks as (

    select
        watmainid,
        incident_year,
        break_incident_id,
        match_status
    from {{ ref('int_breaks_matched') }}
    where match_status in ('matched', 'predecessor_asset')

),

prior as (

    select
        spine.watmainid,
        spine.panel_year,
        -- Breaks on THIS pipe. A predecessor's failures are deliberately not
        -- counted here: the PVC segment installed in 2010 has never broken,
        -- and telling the model otherwise would teach it that new PVC fails
        -- constantly.
        count(breaks.break_incident_id)
            filter (where breaks.match_status = 'matched')  as prior_break_count,
        max(breaks.incident_year)
            filter (where breaks.match_status = 'matched')  as last_break_year,
        min(breaks.incident_year)
            filter (where breaks.match_status = 'matched')  as first_break_year,

        -- Breaks at this LOCATION on the pipe that was here before. Distinct
        -- signal -- it describes the ground, not the asset -- so it is exposed
        -- separately rather than merged into the count above.
        count(breaks.break_incident_id)
            filter (where breaks.match_status = 'predecessor_asset') as predecessor_break_count
    from spine
    left join breaks
        on breaks.watmainid = spine.watmainid
       and breaks.incident_year < spine.panel_year   -- as-of guard
    group by 1, 2

)

select
    watmainid,
    panel_year,
    prior_break_count,
    prior_break_count > 0                           as has_prior_break,
    predecessor_break_count,
    predecessor_break_count > 0                     as location_had_earlier_pipe_break,
    last_break_year,
    first_break_year,
    panel_year - last_break_year                    as years_since_last_break,

    -- Breaks in the three years before the panel year: recent failures carry
    -- more signal than a break three decades ago.
    least(prior_break_count, 3)                     as prior_break_count_capped

from prior
