-- =====================================================================
-- 9. The trend chart: signals per week
-- =====================================================================
-- date_trunc('week', a_date) rounds a date down to the Monday of its week,
-- so every article in the same week shares a value and can be grouped.
-- =====================================================================

select date_trunc('week', published_at)::date as week_starting,
       count(*) as signals
from disruption_feed
where published_at >= now() - interval '8 weeks'
group by week_starting
order by week_starting;

-- Expect: one row per week that had signals. Weeks with none are simply
-- missing here; the dashboard draws those as 0.
--
-- New idea: ::date is a CAST - it drops the time, so you see 2026-09-21
-- instead of 2026-09-21 00:00:00+00.
--
-- Try it: add  , region  after "signals" AND to the group by, to get one
-- row per week and region - exactly what the chart draws.
