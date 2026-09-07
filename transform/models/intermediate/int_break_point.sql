-- Break locations in the same local metric frame as int_pipe_centroid.

{% set lat0 = 43.45 %}
{% set m_per_deg_lat = 111132.0 %}
{% set m_per_deg_lon = 80814.0 %}

with breaks as (

    select
        break_incident_id,
        watmainid,
        incident_year,
        ST_GeomFromText(geometry_wkt) as point
    from {{ ref('int_breaks_matched') }}
    where geometry_wkt like 'POINT%'
      and match_status = 'matched'

)

select
    break_incident_id,
    watmainid,
    incident_year,
    ST_X(point) * {{ m_per_deg_lon }}                       as x_m,
    (ST_Y(point) - {{ lat0 }}) * {{ m_per_deg_lat }}        as y_m
from breaks
