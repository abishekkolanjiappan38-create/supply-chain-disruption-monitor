-- =====================================================================
-- 2. How many articles are there, and what happened to each?
-- =====================================================================
-- count(*)  counts rows.
-- group by  makes one row per different value - here, one row per status.
-- The database forms the groups first, then counts inside each one.
-- =====================================================================

select status,
       count(*) as articles
from articles
group by status
order by articles desc;

-- Expect: one row per status.
--   pending        = waiting for Gemini
--   not_disruption = Gemini judged it irrelevant
--   disruption     = a real signal (details live in the disruptions table)
--   failed         = something went wrong; the next run retries it
--
-- Rule worth remembering: every column in the select must either appear in
-- the group by, or sit inside a function like count() / sum() / max().
