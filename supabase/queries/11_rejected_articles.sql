-- =====================================================================
-- 11. What did the AI throw away?
-- =====================================================================
-- Worth checking now and then. If real disruptions appear in this list,
-- the rules in pipeline/prompt.py need adjusting. This is how you keep
-- the AI honest instead of trusting it blindly.
-- =====================================================================

select published_at::date as published,
       search_keyword,
       source_name,
       title
from articles
where status = 'not_disruption'
order by published_at desc
limit 30;

-- Expect: mostly market commentary, company news and unrelated stories.
-- Spotting a genuine supply chain event here IS a finding - note it down.
