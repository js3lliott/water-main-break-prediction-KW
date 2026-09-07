-- Daily climate for Kitchener-Waterloo, spliced across three ECCC stations
-- (see extract/weather.py for why no single station covers the panel period).
--
-- `source_station_name` is carried through deliberately: the splice is a
-- modelling assumption, and anyone reading a winter-severity feature should be
-- able to see which station produced it.

with raw_weather as (

    select * from {{ source('raw', 'weather_daily') }}

),

latest as (

    select * from raw_weather
    where _extracted_at = (select max(_extracted_at) from raw_weather)

)

select
    cast(date as date)                              as weather_date,
    cast(extract(year from date) as integer)        as weather_year,
    cast(extract(month from date) as integer)       as weather_month,

    max_temp_c,
    min_temp_c,
    mean_temp_c,
    total_rain_mm,
    total_snow_cm,
    total_precip_mm,
    snow_on_grnd_cm,

    -- A freeze-thaw day: the ground crosses 0 C in both directions within the
    -- same day. Repeated cycling is what works pipe joints loose.
    (min_temp_c < 0 and max_temp_c > 0)             as is_freeze_thaw_day,

    -- Freezing degree-days accumulate frost depth; the running seasonal total
    -- is the standard proxy for how deep the frost line has driven.
    greatest(-mean_temp_c, 0)                       as freezing_degree_days,

    source_station_id,
    source_station_name,
    _extracted_at                                   as extracted_at

from latest
