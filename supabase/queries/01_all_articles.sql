-- =====================================================================
-- 1. Look at some articles
-- =====================================================================
-- The simplest query there is:   select COLUMNS from TABLE
--   *      = every column
--   limit  = stop after this many rows (always use it while exploring)
-- =====================================================================

select *
from articles
limit 5;

-- Expect: 5 rows showing every column of the articles table.
--
-- Try it: ask for only the columns you care about --
--   select title, source_name, status from articles limit 5;
