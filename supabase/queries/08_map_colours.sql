-- =====================================================================
-- 8. How the world map picks each country's colour
-- =====================================================================
-- A country is shaded by its WORST severity in the window.
-- Problem: 'high' / 'medium' / 'low' are words, and words sort
-- alphabetically ('high' < 'low' < 'medium') - not what we want.
-- Solution: turn them into numbers, take the largest, turn it back.
-- =====================================================================

select country,
       count(*) as signals,
       case max(case severity when 'high'   then 3
                              when 'medium' then 2
                              else 1 end)           -- word -> number
         when 3 then 'high'
         when 2 then 'medium'
         else 'low'
       end as worst_severity                        -- number -> word
from disruption_feed
where country_code is not null                      -- skip sea routes etc.
  and published_at >= now() - interval '30 days'
group by country
order by signals desc;

-- Expect: one row per country shown in colour on the map.
--
-- New idea: case ... when ... then ... else ... end is SQL's if/else.
-- Read the inner case first, then max(), then the outer case.
