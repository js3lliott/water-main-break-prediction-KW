-- A pipe cannot break before it exists.
--
-- This catches the asset-ID-reuse case leaking into the panel: when a segment
-- is replaced, the new pipe inherits the old WATMAINID, and a naive join
-- credits the replacement with its predecessor's failures.

select
    panel.watmainid,
    panel.panel_year,
    panel.break_count,
    dim.install_year

from {{ ref('fct_pipe_year') }} as panel
join {{ ref('dim_pipe') }} as dim on panel.watmainid = dim.watmainid

where panel.break_count > 0
  and panel.panel_year <= dim.install_year
