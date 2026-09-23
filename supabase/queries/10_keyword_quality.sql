-- =====================================================================
-- 10. Which search keywords actually find real disruptions?
-- =====================================================================
-- Genuinely useful for the README: it shows which keywords earn their
-- place and which only bring noise.
-- =====================================================================

select search_keyword,
       count(*)                                       as articles_found,
       count(*) filter (where status = 'disruption')  as real_disruptions,
       round(100.0 * count(*) filter (where status = 'disruption')
             / count(*), 1)                           as hit_rate_percent
from articles
group by search_keyword
order by real_disruptions desc, articles_found desc;

-- Expect: one row per keyword, best first.
--
-- New idea: 100.0 * x / y gives a percentage. The ".0" matters - without it
-- Postgres divides whole numbers and throws the decimals away (3/10 = 0).
-- round(..., 1) keeps one decimal place.
