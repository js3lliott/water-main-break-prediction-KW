-- The leakage guard for the whole project, tested by recomputation.
--
-- `prior_break_count` must equal the number of matched breaks strictly BEFORE
-- the panel year. If an `as-of` bound anywhere upstream slipped from `<` to
-- `<=`, the model would see the outcome it is predicting, and this test is what
-- catches it.

with recomputed as (

    select
        panel.watmainid,
        panel.panel_year,
        panel.prior_break_count as reported,
        count(breaks.break_incident_id) as expected
    from {{ ref('fct_pipe_year') }} as panel
    left join {{ ref('int_breaks_matched') }} as breaks
        on breaks.watmainid = panel.watmainid
       and breaks.match_status = 'matched'
       and breaks.incident_year < panel.panel_year
    group by 1, 2, 3

)

select * from recomputed where reported != expected
