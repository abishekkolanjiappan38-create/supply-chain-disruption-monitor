-- =====================================================================
-- Verification checks — run AFTER schema.sql and seed_countries.sql.
-- Read-only except for one write test that is expected to be BLOCKED.
-- Output: one table of checks, each marked PASS or FAIL.
-- =====================================================================

-- ---- Security test: act as the public website ("anon") -------------
-- Try to READ (should work) and WRITE (should be blocked by RLS).
drop table if exists _anon_test;
create temp table _anon_test (check_name text, actual text);

do $$
declare n integer;
begin
    -- read test
    begin
        set local role anon;
        select count(*) into n from public.regions;
        reset role;
        insert into _anon_test values ('anon can read regions', n::text);
    exception when others then
        insert into _anon_test values ('anon can read regions', 'error: ' || sqlerrm);
    end;

    -- write test
    begin
        set local role anon;
        insert into public.regions (name) values ('__rls_test__');
        reset role;
        insert into _anon_test values ('anon write is blocked', 'NOT blocked');
    exception when insufficient_privilege then
        insert into _anon_test values ('anon write is blocked', 'blocked');
    end;
end $$;

-- If the write was NOT blocked, remove the test row again.
delete from public.regions where name = '__rls_test__';


-- ---- All checks ------------------------------------------------------
with our_tables(t) as (
    values ('regions'), ('countries'), ('disruption_types'),
           ('pipeline_runs'), ('articles'), ('disruptions')
),
checks(n, check_name, expected, actual) as (

    select 1, 'tables created', '6',
           (select count(*) from pg_tables
             where schemaname = 'public' and tablename in (select t from our_tables))::text

    union all select 2, 'RLS enabled on all tables', '6',
           (select count(*) from pg_class c join pg_namespace s on s.oid = c.relnamespace
             where s.nspname = 'public' and c.relname in (select t from our_tables)
               and c.relrowsecurity)::text

    union all select 3, 'read-only policies', '6',
           (select count(*) from pg_policies
             where schemaname = 'public' and cmd = 'SELECT')::text

    union all select 4, 'policies allowing writes', '0',
           (select count(*) from pg_policies
             where schemaname = 'public' and cmd <> 'SELECT')::text

    union all select 5, 'foreign keys (relationships)', '6',
           (select count(*) from pg_constraint
             where contype = 'f' and connamespace = 'public'::regnamespace)::text

    union all select 6, 'unique rules', '5',
           (select count(*) from pg_constraint
             where contype = 'u' and connamespace = 'public'::regnamespace)::text

    union all select 7, 'allowed-value rules (severity, statuses)', '3',
           (select count(*) from pg_constraint
             where contype = 'c' and connamespace = 'public'::regnamespace)::text

    union all select 8, 'feed view exists and follows RLS', 'true',
           (select coalesce(array_to_string(reloptions, ','), '') like '%security_invoker=true%'
              from pg_class where oid = 'public.disruption_feed'::regclass)::text

    union all select 9, 'feed view is readable by website', 'true',
           has_table_privilege('anon', 'public.disruption_feed', 'SELECT')::text

    union all select 10, 'regions seeded', '8',
           (select count(*) from regions)::text

    union all select 11, 'disruption types seeded', '7',
           (select count(*) from disruption_types)::text

    union all select 12, 'countries seeded', '173',
           (select count(*) from countries)::text

    union all select 13, 'countries per region',
           'East Asia 16, South Asia 12, Middle East 19, Europe 38, North America 4, Latin America 27, Africa & Oceania 57, Global 0',
           (select string_agg(r.name || ' ' || (select count(*) from countries c
                                                 where c.region_id = r.region_id), ', '
                              order by r.region_id)
              from regions r)

    union all select 14, 'spot check: US → North America, map id 840', 'North America 840',
           (select r.name || ' ' || c.map_id from countries c join regions r using (region_id)
             where c.country_code = 'US')

    union all select 15, 'data tables start empty (runs, articles, disruptions)', '0 0 0',
           (select (select count(*) from pipeline_runs) || ' ' ||
                   (select count(*) from articles)      || ' ' ||
                   (select count(*) from disruptions))

    union all select 16, 'anon can read regions', '8',
           (select actual from _anon_test where check_name = 'anon can read regions')

    union all select 17, 'anon write is blocked', 'blocked',
           (select actual from _anon_test where check_name = 'anon write is blocked')
)
select n as "#",
       check_name,
       expected,
       actual,
       case when expected = actual then 'PASS' else 'FAIL' end as result
from checks
order by n;
