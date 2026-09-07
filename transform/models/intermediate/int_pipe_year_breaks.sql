-- The outcome side of the panel: how many breaks each pipe actually had in
-- each year. Joined onto the spine in fct_pipe_year, where pipe-years with no
-- break become explicit zeroes rather than missing rows.

select
    watmainid,
    incident_year                                   as panel_year,
    count(*)                                        as break_count,
    min(incident_date)                              as first_break_date,
    max(incident_date)                              as last_break_date,
    count(*) filter (where incident_month in (12, 1, 2, 3)) as winter_break_count

from {{ ref('int_breaks_matched') }}
where match_status = 'matched'
group by 1, 2
