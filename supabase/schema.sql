-- =====================================================================
-- Supply Chain Disruption Monitor — database schema
-- =====================================================================
-- What this file does:
--   1. Creates the 6 tables described in DATA_MODEL.md
--   2. Fills in the two small fixed lists (regions, disruption types)
--   3. Creates one saved query (a "view") that the feed uses
--   4. Locks the database so the public website can only READ
--
-- How to run it (once, on a new empty Supabase project):
--   Supabase dashboard → SQL Editor → New query → paste this file → Run
--
-- The country list is loaded separately (supabase/seed_countries.sql),
-- generated from the world-map file so every map_id matches a map shape.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LOOKUP TABLES — fixed lists that keep categories consistent
-- ---------------------------------------------------------------------

-- Regions shown in the chart, filters and feed.
create table regions (
    region_id    smallint generated always as identity primary key,  -- auto-number
    name         text    not null unique,                            -- "East Asia"
    show_on_map  boolean not null default true                       -- false only for "Global"
);

-- Countries on the world map. Each belongs to exactly one region.
create table countries (
    country_code char(2)  primary key,                          -- ISO code: "US", "CN"
    name         text     not null,                             -- display name
    map_id       char(3)  unique,                               -- ISO numeric id used by the map file: "840"
    region_id    smallint not null references regions (region_id)
);

-- The allowed disruption categories. The description is also given to
-- Gemini in the prompt so it classifies articles consistently.
create table disruption_types (
    disruption_type_id smallint generated always as identity primary key,
    name               text not null unique,
    description        text
);


-- ---------------------------------------------------------------------
-- 2. PIPELINE LOG — one row every time the daily job runs
-- ---------------------------------------------------------------------

create table pipeline_runs (
    run_id            bigint generated always as identity primary key,
    started_at        timestamptz not null default now(),
    finished_at       timestamptz,                    -- empty while still running
    status            text not null default 'running'
                      check (status in ('running', 'success', 'failed')),
    articles_fetched  integer,                        -- returned by the news API
    articles_new      integer,                        -- left after removing duplicates
    disruptions_found integer,                        -- flagged by Gemini as real
    error_message     text                            -- what went wrong, if anything
);


-- ---------------------------------------------------------------------
-- 3. ARTICLES — every unique article fetched (real disruption or not)
-- ---------------------------------------------------------------------

create table articles (
    article_id       bigint generated always as identity primary key,
    run_id           bigint not null references pipeline_runs (run_id),
    url              text   not null,                -- original link for "Open source article"
    url_normalized   text   not null unique,         -- cleaned URL; UNIQUE blocks duplicates
    title            text   not null,                -- headline on the feed card
    title_normalized text   not null,                -- cleaned headline for the 7-day duplicate check
    source_name      text,                           -- "Reuters"
    description      text,                           -- short snippet; title + snippet go to Gemini
    search_keyword   text,                           -- which keyword found it
    published_at     timestamptz not null,           -- publisher's date (used by charts and cards)
    fetched_at       timestamptz not null default now(),
    status           text not null default 'pending'
                     check (status in ('pending', 'disruption', 'not_disruption', 'failed'))
);


-- ---------------------------------------------------------------------
-- 4. DISRUPTIONS — Gemini's structured result, only for real disruptions
-- ---------------------------------------------------------------------

create table disruptions (
    disruption_id      bigint   generated always as identity primary key,
    article_id         bigint   not null unique                 -- one result per article
                                references articles (article_id) on delete cascade,
    region_id          smallint not null references regions (region_id),
    country_code       char(2)  references countries (country_code),   -- optional
    disruption_type_id smallint not null references disruption_types (disruption_type_id),
    severity           text     not null
                                check (severity in ('low', 'medium', 'high')),
    summary            text     not null,                       -- one plain-English sentence
    model_name         text     not null,                       -- which Gemini model produced it
    extracted_at       timestamptz not null default now()
);


-- ---------------------------------------------------------------------
-- 5. STARTING DATA for the fixed lists
-- ---------------------------------------------------------------------

insert into regions (name, show_on_map) values
    ('East Asia',        true),
    ('South Asia',       true),
    ('Middle East',      true),
    ('Europe',           true),
    ('North America',    true),
    ('Latin America',    true),
    ('Africa & Oceania', true),
    ('Global',           false);   -- worldwide events; no single place on the map

insert into disruption_types (name, description) values
    ('Labour action',         'Strikes, walkouts, lockouts or labour disputes that stop or slow work.'),
    ('Weather event',         'Storms, typhoons, floods, drought, low water levels or other natural events.'),
    ('Tariff / policy',       'New tariffs, export controls, sanctions, customs rules or trade regulations.'),
    ('Geopolitical',          'Conflict, security threats or political instability affecting trade routes.'),
    ('Supplier shortage',     'A supplier or input material cannot meet demand.'),
    ('Port / shipping delay', 'Port congestion, vessel delays, canal restrictions or freight backlogs.'),
    ('Other',                 'A real supply chain disruption that fits none of the categories above.');


-- ---------------------------------------------------------------------
-- 6. FEED VIEW — joins everything the feed card needs into one place,
--    so the website makes one simple request instead of five joins.
--    security_invoker = the view follows the same read rules as the tables.
-- ---------------------------------------------------------------------

create view disruption_feed
with (security_invoker = true) as
select
    d.disruption_id,
    d.severity,
    d.summary,
    d.model_name,
    d.extracted_at,
    a.title,
    a.url,
    a.source_name,
    a.published_at,
    r.region_id,
    r.name  as region,
    c.country_code,
    c.name  as country,
    t.disruption_type_id,
    t.name  as disruption_type
from disruptions d
join articles         a on a.article_id         = d.article_id
join regions          r on r.region_id          = d.region_id
join disruption_types t on t.disruption_type_id = d.disruption_type_id
left join countries   c on c.country_code       = d.country_code;   -- left join: country is optional


-- ---------------------------------------------------------------------
-- 7. SECURITY — Row Level Security (RLS)
--    The website uses the public "anon" key → may only SELECT (read).
--    The pipeline uses the secret "service role" key → bypasses RLS and
--    is the only thing that can insert or update.
-- ---------------------------------------------------------------------

alter table regions          enable row level security;
alter table countries        enable row level security;
alter table disruption_types enable row level security;
alter table pipeline_runs    enable row level security;
alter table articles         enable row level security;
alter table disruptions      enable row level security;

create policy "public read" on regions          for select to anon, authenticated using (true);
create policy "public read" on countries        for select to anon, authenticated using (true);
create policy "public read" on disruption_types for select to anon, authenticated using (true);
create policy "public read" on pipeline_runs    for select to anon, authenticated using (true);
create policy "public read" on articles         for select to anon, authenticated using (true);
create policy "public read" on disruptions      for select to anon, authenticated using (true);

-- Make sure the website's key is allowed to read these tables and the view
-- (read only — no insert/update/delete is granted).
grant select on regions, countries, disruption_types, pipeline_runs,
                articles, disruptions, disruption_feed
      to anon, authenticated;
