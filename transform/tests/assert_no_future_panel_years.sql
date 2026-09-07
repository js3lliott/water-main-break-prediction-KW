-- The panel may run one year past the current year -- that is the forecast row
-- the scoring pipeline ranks -- but no further.

select panel_year, count(*) as n
from {{ ref('fct_pipe_year') }}
where panel_year > cast(extract(year from current_date) as integer) + 1
group by 1
