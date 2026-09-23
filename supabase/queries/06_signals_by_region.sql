-- =====================================================================
-- 6. Which regions have the most disruption signals?
-- =====================================================================
-- The same group-by idea as query 2, applied to the feed view.
-- This is the list shown beside the dashboard's chart.
-- =====================================================================

select region,
       count(*)                                    as signals,
       count(*) filter (where severity = 'high')   as high,
       count(*) filter (where severity = 'medium') as medium,
       count(*) filter (where severity = 'low')    as low
from disruption_feed
where published_at >= now() - interval '30 days'
group by region
order by signals desc;

-- Expect: one row per region that has signals.
--
-- New idea: count(*) filter (where ...) counts only the rows matching that
-- condition, inside each group. It saves writing three separate queries.
