-- =====================================================================
-- 3. Did the daily runs work?
-- =====================================================================
-- This table is the pipeline's diary: one row per run.
-- order by ... desc = newest first (desc = descending).
-- =====================================================================

select run_id,
       status,
       articles_fetched,
       articles_new,
       disruptions_found,
       started_at,
       finished_at,
       error_message
from pipeline_runs
order by run_id desc
limit 10;

-- Expect: your most recent runs, status 'success'.
-- error_message is filled in when something went wrong. A run can be
-- 'success' and still have a message, if only part of it failed.
--
-- Try it: show only failed runs by adding this before "order by" --
--   where status = 'failed'
