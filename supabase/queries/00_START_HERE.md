# Practice queries

One query per file, in learning order. Each file says what the query does,
what to expect, and teaches one new idea. Every query only **reads** data —
none of them can change or delete anything.

**How to run one:** Supabase -> SQL Editor -> New query -> paste the file -> Run.

| File | New idea | Answers |
|---|---|---|
| `01_all_articles.sql` | `select`, `limit` | What does one row look like? |
| `02_count_by_status.sql` | `count`, `group by` | How many articles, and what happened to them? |
| `03_pipeline_runs.sql` | `order by`, reading a log | Did the daily runs work? |
| `04_the_feed.sql` | reading a view | What the dashboard feed shows |
| `05_kpi_numbers.sql` | subqueries, date filters | The three numbers at the top of the dashboard |
| `06_signals_by_region.sql` | `filter (where ...)` | Which regions have the most signals? |
| `07_signals_by_type.sql` | grouping by another column | What kinds of disruption are we finding? |
| `08_map_colours.sql` | `case`, `max` | How the map picks each country's colour |
| `09_weekly_trend.sql` | `date_trunc` | The trend chart's numbers |
| `10_keyword_quality.sql` | percentages | Which keywords actually find disruptions? |
| `11_rejected_articles.sql` | filtering text columns | What did the AI throw away? |
| `12_find_a_word.sql` | `ilike` and `%` | Searching inside text |

Tip: change one small thing and run it again. That is the fastest way to
learn SQL, and nothing here can break the database.

For the full explanation of the tables themselves, see `SQL_Learning_Guide.pdf`.
