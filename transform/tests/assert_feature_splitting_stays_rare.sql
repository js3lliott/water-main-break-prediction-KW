-- Multi-feature mains must stay the exception.
--
-- OBJECTID identifies a GIS feature, WATMAINID identifies the main, and the
-- city occasionally splits one main into several features that share a
-- WATMAINID. stg_water_mains collapses them -- summing length, taking
-- attributes from the longest piece -- because WATMAINID has to remain the
-- grain: it is the key break records join on.
--
-- That collapse is safe while splitting is rare. If it became the norm, taking
-- one feature's attributes for the whole main would start discarding real
-- variation, and the right answer would be a separate feature-grain model
-- rather than a quiet aggregation. This fails the build at 1% so that decision
-- gets made deliberately instead of by default.

with split_rate as (

    select
        count(*) filter (where feature_count > 1)            as multi_feature_mains,
        count(*)                                             as total_mains,
        count(*) filter (where feature_count > 1) * 1.0 / count(*) as share
    from {{ ref('stg_water_mains') }}

)

select * from split_rate where share > 0.01
