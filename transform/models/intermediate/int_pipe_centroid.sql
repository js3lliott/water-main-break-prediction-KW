-- Pipe and break locations in a local metric frame.
--
-- Geometry arrives in EPSG:4326 (degrees) because GeoJSON mandates it. Rather
-- than depend on a reprojection, distances use an equirectangular
-- approximation anchored at Kitchener's latitude. Over a city-sized extent and
-- a 250 m radius the error is well under a percent -- far below the precision
-- the neighbourhood feature needs.

{% set lat0 = 43.45 %}
{% set m_per_deg_lat = 111132.0 %}
{% set m_per_deg_lon = 80814.0 %}  {# 111320 * cos(43.45 deg) #}

with pipes as (

    select
        watmainid,
        length_km,
        ST_Centroid(ST_GeomFromText(geometry_wkt)) as centroid
    from {{ ref('dim_pipe') }}
    where geometry_wkt is not null

)

select
    watmainid,
    length_km,
    ST_X(centroid)                                          as longitude,
    ST_Y(centroid)                                          as latitude,
    ST_X(centroid) * {{ m_per_deg_lon }}                    as x_m,
    (ST_Y(centroid) - {{ lat0 }}) * {{ m_per_deg_lat }}     as y_m
from pipes
