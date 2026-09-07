-- Break-level reconciliation.
--
-- Every matched break should appear in the panel, except the two documented
-- boundary cases: breaks before the panel start year, and breaks in the pipe's
-- own installation year (the panel begins the year after install). Anything
-- else going missing means breaks are being silently dropped by a join.

with expected as (

    select count(*) as n
    from {{ ref('int_breaks_matched') }} as breaks
    join {{ ref('dim_pipe') }} as dim on breaks.watmainid = dim.watmainid
    where breaks.match_status = 'matched'
      and breaks.incident_year >= {{ var('panel_start_year') }}
      and breaks.incident_year > dim.install_year

),

actual as (

    select cast(sum(break_count) as bigint) as n from {{ ref('fct_pipe_year') }}

)

select expected.n as expected_breaks, actual.n as breaks_in_panel
from expected cross join actual
where expected.n != actual.n
