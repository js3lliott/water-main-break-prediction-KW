-- Winter severity per season, keyed to the panel year the winter falls into.
--
-- A "winter season" runs 1 November of year t-1 through 31 March of year t and
-- is labelled with year t, because that is the calendar year in which most of
-- its breaks land.
--
-- Note for phase 4: these features describe weather that has already happened.
-- A forward-looking inspection list cannot use them (next winter is unknown),
-- so they belong to the weather-sensitivity model, not the structural one.

with daily as (

    select
        *,
        -- Sustained cold drives the frost line down; a single cold night does
        -- not. The 7-day mean is the standard way to capture that.
        avg(mean_temp_c) over (
            order by weather_date
            rows between 6 preceding and current row
        ) as mean_temp_7d

    from {{ ref('stg_weather_daily') }}

),

winter as (

    select
        *,
        case
            when weather_month >= 11 then weather_year + 1
            else weather_year
        end as panel_year
    from daily
    where weather_month in (11, 12, 1, 2, 3)

)

select
    panel_year,
    count(*)                                        as observed_days,
    sum(case when is_freeze_thaw_day then 1 else 0 end) as freeze_thaw_days,
    round(sum(freezing_degree_days), 1)             as freezing_degree_days,
    round(min(mean_temp_c), 1)                      as coldest_daily_mean_c,
    round(min(mean_temp_7d), 1)                     as coldest_7day_mean_c,
    round(avg(mean_temp_c), 2)                      as avg_mean_temp_c,
    max(snow_on_grnd_cm)                            as max_snow_on_grnd_cm,

    -- Seasons are only comparable if they were observed comparably. ROSEVILLE
    -- has gappy years, so this guards against reading a mild winter off a
    -- winter that was simply under-reported.
    count(*) >= 130                                 as has_adequate_coverage

from winter
group by 1
