-- =====================================================================
-- 7. What kinds of disruption are we finding?
-- =====================================================================
-- Exactly query 6, grouped by a different column. Once group by makes
-- sense, you can slice the data by anything.
-- =====================================================================

select disruption_type,
       count(*) as signals
from disruption_feed
where published_at >= now() - interval '30 days'
group by disruption_type
order by signals desc;

-- Expect: something like Tariff / policy 3, Geopolitical 2, ...
--
-- Good README material: it shows what kind of risk the news is actually
-- reporting, rather than what you assumed it would report.
