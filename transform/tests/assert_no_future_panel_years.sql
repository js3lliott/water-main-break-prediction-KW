-- The panel must not extend past the current year.

select panel_year, count(*) as n
from {{ ref('fct_pipe_year') }}
where panel_year > cast(extract(year from current_date) as integer)
group by 1
