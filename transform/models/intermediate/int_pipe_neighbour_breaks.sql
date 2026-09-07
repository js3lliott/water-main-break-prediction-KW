-- Breaks on OTHER pipes near each pipe, by year.
--
-- This is the feature that gives the model something to say about the ~90% of
-- the network that has never broken. Their own break history is all zeroes, so
-- without a neighbourhood signal a cold-start pipe carries only static
-- attributes and the model degenerates toward a material-and-decade lookup.
--
-- Nearby failures transfer real information: adjacent segments share trench,
-- soil, water chemistry, traffic loading and often the same install crew and
-- pipe batch.
--
-- `watmainid <> ` on the join is essential. Including the pipe's own breaks
-- would smuggle prior_break_count back in under a different name, and the
-- cold-start model would no longer be cold-start.

with pipes as (

    select watmainid, x_m, y_m from {{ ref('int_pipe_centroid') }}

),

breaks as (

    select break_incident_id, watmainid, incident_year, x_m, y_m
    from {{ ref('int_break_point') }}

)

select
    pipes.watmainid,
    breaks.incident_year,
    count(*)                                                as neighbour_breaks
from pipes
join breaks
    on breaks.watmainid <> pipes.watmainid
   -- Bounding box first so the quadratic distance test runs on far fewer pairs.
   and breaks.x_m between pipes.x_m - {{ var('neighbour_radius_m') }}
                      and pipes.x_m + {{ var('neighbour_radius_m') }}
   and breaks.y_m between pipes.y_m - {{ var('neighbour_radius_m') }}
                      and pipes.y_m + {{ var('neighbour_radius_m') }}
   and (breaks.x_m - pipes.x_m) * (breaks.x_m - pipes.x_m)
     + (breaks.y_m - pipes.y_m) * (breaks.y_m - pipes.y_m)
       <= {{ var('neighbour_radius_m') }} * {{ var('neighbour_radius_m') }}
group by 1, 2
