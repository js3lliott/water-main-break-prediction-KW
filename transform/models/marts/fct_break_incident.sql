-- One row per confirmed main break, with its inventory match status.
--
-- Kept at incident grain for the historical analysis and the app's map of
-- where breaks have actually happened. It is NOT the training table --
-- fct_pipe_year is, because this table contains no negative examples.

select
    break_incident_id,
    arcgis_object_id,
    global_id,

    watmainid,
    match_status,
    road_segment_id,

    incident_date,
    incident_year,
    incident_month,
    case
        when incident_month in (12, 1, 2) then 'WINTER'
        when incident_month in (3, 4, 5) then 'SPRING'
        when incident_month in (6, 7, 8) then 'SUMMER'
        else 'FALL'
    end                                             as incident_season,

    break_type,
    status,
    break_nature,
    break_apparent_cause,
    break_categorization,

    street,
    civic_number,

    pipe_install_year,
    pipe_material,
    pipe_diameter_mm,
    age_at_break_years,

    reported_diameter_mm,
    reported_material,
    reported_install_year,
    asset_still_exists,

    geometry_wkt,
    extracted_at

from {{ ref('int_breaks_matched') }}
