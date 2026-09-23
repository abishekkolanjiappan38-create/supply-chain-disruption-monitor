-- =====================================================================
-- Give the pipeline permission to write — run once, after schema.sql.
--
-- Why this is needed:
--   The pipeline connects with the SECRET key, which acts as the
--   "service_role" database role. That role skips Row Level Security,
--   but it still needs ordinary table permissions (GRANTs). Newer Supabase
--   projects no longer add these automatically for new tables, and
--   schema.sql only granted READ access to the website's roles.
--
-- Error this fixes:
--   permission denied for table pipeline_runs  (code 42501)
--
-- The public website's roles (anon, authenticated) are NOT changed:
-- they stay read-only.
-- =====================================================================

grant select, insert, update, delete
    on regions, countries, disruption_types, pipeline_runs, articles, disruptions
    to service_role;

grant select on disruption_feed to service_role;

-- The auto-numbering counters behind the ID columns.
grant usage, select on all sequences in schema public to service_role;


-- Check: every row should say true.
select t as table_name,
       has_table_privilege('service_role', 'public.' || t, 'INSERT') as pipeline_can_insert,
       has_table_privilege('service_role', 'public.' || t, 'UPDATE') as pipeline_can_update,
       not has_table_privilege('anon', 'public.' || t, 'INSERT')     as website_still_read_only
from unnest(array['regions', 'countries', 'disruption_types',
                  'pipeline_runs', 'articles', 'disruptions']) as t;
