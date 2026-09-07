-- Static neighbourhood exposure: how much other pipe sits near each segment.
--
-- Carried so the model can normalise neighbour break counts. Six nearby breaks
-- means something different in a dense downtown block than along a single
-- suburban run.

with pipes as (

    select watmainid, x_m, y_m from {{ ref('int_pipe_centroid') }}

),

others as (

    select watmainid, x_m, y_m, length_km from {{ ref('int_pipe_centroid') }}

)

select
    pipes.watmainid,
    count(*)                                                as neighbour_pipe_count,
    round(sum(others.length_km), 4)                         as neighbour_pipe_km
from pipes
join others
    on others.watmainid <> pipes.watmainid
   and others.x_m between pipes.x_m - {{ var('neighbour_radius_m') }}
                      and pipes.x_m + {{ var('neighbour_radius_m') }}
   and others.y_m between pipes.y_m - {{ var('neighbour_radius_m') }}
                      and pipes.y_m + {{ var('neighbour_radius_m') }}
   and (others.x_m - pipes.x_m) * (others.x_m - pipes.x_m)
     + (others.y_m - pipes.y_m) * (others.y_m - pipes.y_m)
       <= {{ var('neighbour_radius_m') }} * {{ var('neighbour_radius_m') }}
group by 1
