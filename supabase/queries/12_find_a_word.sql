-- =====================================================================
-- 12. Searching inside the text
-- =====================================================================
-- ilike = "is like, ignoring capital letters".
-- %      = "anything can be here", so '%port%' matches any title that
--          contains port.
-- =====================================================================

select published_at::date as published,
       status,
       source_name,
       title
from articles
where title ilike '%tariff%'
order by published_at desc
limit 20;

-- Expect: every stored article whose headline mentions tariff.
--
-- Try it: change the word - '%strike%', '%shortage%', '%port%'.
-- Careful: '%port%' also matches report, important and export. That is
-- exactly the kind of noise our keyword searches have to cope with.
