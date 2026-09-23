-- =====================================================================
-- 4. The live feed (what the dashboard shows)
-- =====================================================================
-- disruption_feed is a VIEW: a saved query that behaves like a table.
-- It already joins disruptions + articles + regions + countries + types,
-- so you can simply select from it.
-- =====================================================================

select published_at,
       severity,
       region,
       country,
       disruption_type,
       title,
       summary,
       source_name
from disruption_feed
order by published_at desc
limit 20;

-- Expect: one row per real disruption, newest first.
--
-- Try it: only the serious ones - add before "order by" --
--   where severity = 'high'
