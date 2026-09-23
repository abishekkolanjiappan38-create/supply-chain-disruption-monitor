-- =====================================================================
-- 5. The three numbers at the top of the dashboard
-- =====================================================================
-- A query inside another query is a SUBQUERY. Three of them side by side
-- produce one row with three answers.
--
-- now() - interval '30 days'  =  the moment 30 days ago.
-- =====================================================================

select
    (select count(*)
       from articles
      where status in ('disruption', 'not_disruption')   -- judged by the AI
        and published_at >= now() - interval '30 days')   as articles_screened,

    (select count(*)
       from disruption_feed
      where published_at >= now() - interval '30 days')   as disruption_signals,

    (select count(*)
       from disruption_feed
      where severity = 'high'
        and published_at >= now() - interval '30 days')   as high_severity;

-- Expect: one row, three numbers - the same ones on the live dashboard.
--
-- Try it: change '30 days' to '7 days' in all three and compare.
