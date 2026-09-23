-- =====================================================================
-- RESET — removes everything schema.sql and seed_countries.sql created,
-- so schema.sql can be run again on a clean project.
--
-- ⚠ Deletes all data in these tables. Only use before real data exists.
--
-- Safe by design:
--   • Names only this project's 1 view + 6 tables — nothing else is touched.
--   • "if exists" = no error if an object was never created (partial run).
--   • No CASCADE: if anything unexpected depends on these tables, Postgres
--     stops with an error instead of silently deleting it.
--   • Wrapped in begin/commit: either everything is removed or nothing is.
--
-- Dropping a table automatically removes what belongs to it: its data,
-- RLS policies, keys, unique/check rules, auto-number sequences and grants.
-- =====================================================================

begin;

-- The view reads from the tables, so it goes first.
drop view if exists public.disruption_feed;

-- Tables in reverse dependency order: a table is dropped only after
-- every table that points to it (via a foreign key) is already gone.
drop table if exists public.disruptions;       -- points to articles, regions, countries, types
drop table if exists public.articles;          -- points to pipeline_runs
drop table if exists public.pipeline_runs;
drop table if exists public.countries;         -- points to regions
drop table if exists public.disruption_types;
drop table if exists public.regions;

commit;

-- Check: should return no rows (nothing from this project is left).
select c.relname as leftover_object, c.relkind as kind
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('disruption_feed', 'disruptions', 'articles', 'pipeline_runs',
                    'countries', 'disruption_types', 'regions');
