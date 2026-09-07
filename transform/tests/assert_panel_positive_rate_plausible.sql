-- A canary on the join, not a statistical claim.
--
-- The observed rate is ~0.55% of pipe-years. If a future change reintroduces a
-- fanout (the ROADSEGMENTID bug produced a 3.9x row explosion) or drops the
-- inventory negatives, this rate moves by an order of magnitude and the build
-- fails on that run instead of six weeks later in a model postmortem.

with rate as (

    select
        avg(case when broke_in_year then 1.0 else 0.0 end) as positive_rate,
        count(*) as n_rows
    from {{ ref('fct_pipe_year') }}
    where is_complete_year

)

select * from rate
where positive_rate not between 0.002 and 0.02
   or n_rows < 100000
