"""
Offline tests for the ingestion pipeline — no API keys or internet needed.
NewsAPI and Supabase are replaced with fakes ("mocks").

Run from the project folder:
    python -m unittest discover tests -v
"""

import unittest
from unittest import mock

from pipeline import dedupe, run_pipeline
from pipeline.db import _in_list
from pipeline.news_client import NewsAPIError, to_article_row
from pipeline.normalize import normalize_title, normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_same_article_different_links(self):
        a = normalize_url("http://www.Reuters.com/world/port-strike/?utm_source=x&utm_medium=y#top")
        b = normalize_url("https://www.reuters.com/world/port-strike")
        self.assertEqual(a, b)

    def test_keeps_meaningful_query_params(self):
        self.assertEqual(normalize_url("https://site.com/story?id=42&fbclid=abc"),
                         "https://site.com/story?id=42")

    def test_param_order_does_not_matter(self):
        self.assertEqual(normalize_url("https://site.com/s?b=2&a=1"),
                         normalize_url("https://site.com/s?a=1&b=2"))

    def test_path_case_is_kept(self):
        # Paths can be case-sensitive, so only the domain is lower-cased.
        self.assertNotEqual(normalize_url("https://site.com/A"), normalize_url("https://site.com/a"))


class NormalizeTitleTests(unittest.TestCase):
    def test_source_suffix_punctuation_and_case(self):
        a = normalize_title("Port strike halts ships - Reuters", "Reuters")
        b = normalize_title("Port Strike Halts Ships!", "Yahoo News")
        self.assertEqual(a, b)
        self.assertEqual(a, "port strike halts ships")

    def test_suffix_only_removed_when_it_is_the_source(self):
        self.assertEqual(normalize_title("Rates rise - analysts", "Reuters"), "rates rise analysts")

    def test_curly_quotes(self):
        self.assertEqual(normalize_title("“Tariffs” bite"), normalize_title('"Tariffs" bite'))


def row(url, title):
    return {"url_normalized": url, "title_normalized": title}


class DedupeTests(unittest.TestCase):
    def test_batch_duplicates_by_url_or_title(self):
        rows = [row("u1", "t1"), row("u1", "t2"), row("u2", "t1"), row("u3", "t3")]
        self.assertEqual(dedupe.remove_batch_duplicates(rows), [row("u1", "t1"), row("u3", "t3")])

    def test_empty_titles_never_match_each_other(self):
        rows = [row("u1", ""), row("u2", "")]
        self.assertEqual(len(dedupe.remove_batch_duplicates(rows)), 2)

    def test_stored_duplicates(self):
        rows = [row("u1", "t1"), row("u2", "t2"), row("u3", "t3")]
        result = dedupe.remove_stored_duplicates(rows, existing_urls={"u1"}, recent_titles={"t2"})
        self.assertEqual(result, [row("u3", "t3")])


class ArticleRowTests(unittest.TestCase):
    RAW = {"source": {"id": None, "name": "Reuters"}, "title": "Port strike - Reuters",
           "description": "Snippet", "url": "https://reuters.com/a/?utm_source=x",
           "publishedAt": "2026-09-20T14:05:00Z"}

    def test_converts_fields(self):
        r = to_article_row(self.RAW, "port strike")
        self.assertEqual(r["url"], self.RAW["url"])                 # original kept
        self.assertEqual(r["url_normalized"], "https://reuters.com/a")
        self.assertEqual(r["title_normalized"], "port strike")
        self.assertEqual(r["source_name"], "Reuters")
        self.assertEqual(r["search_keyword"], "port strike")
        self.assertEqual(r["published_at"], "2026-09-20T14:05:00Z")

    def test_skips_removed_and_incomplete(self):
        self.assertIsNone(to_article_row({**self.RAW, "title": "[Removed]"}, "k"))
        self.assertIsNone(to_article_row({**self.RAW, "url": None}, "k"))
        self.assertIsNone(to_article_row({**self.RAW, "publishedAt": None}, "k"))


class InListTests(unittest.TestCase):
    def test_quotes_values_with_commas_and_quotes(self):
        self.assertEqual(_in_list(['a,b', 'say "hi"']), 'in.("a,b","say \\"hi\\"")')


def article(n):
    return {"url": f"https://x.com/{n}", "url_normalized": f"https://x.com/{n}",
            "title": f"T{n}", "title_normalized": f"t{n}", "source_name": "X",
            "description": None, "search_keyword": "k", "published_at": "2026-09-20T00:00:00Z"}


class RunPipelineTests(unittest.TestCase):
    """The whole run with NewsAPI and Supabase replaced by fakes."""

    KEYWORDS = [{"label": "k1", "query": "q1"}, {"label": "k2", "query": "q2"},
                {"label": "k3", "query": "q3"}]

    def run_with(self, fetch_results, existing_urls=(), existing_urls_error=None):
        """Run main() once. fetch_results = what each keyword's fetch returns/raises."""
        find_urls = mock.Mock(return_value=set(existing_urls), side_effect=existing_urls_error)
        with (
            mock.patch.object(run_pipeline.config, "missing_settings", return_value=[]),
            mock.patch.object(run_pipeline.config, "SEARCH_KEYWORDS", self.KEYWORDS),
            mock.patch.object(run_pipeline, "fetch_articles", side_effect=fetch_results) as fetch,
            mock.patch.object(run_pipeline.db, "start_run", return_value=7),
            mock.patch.object(run_pipeline.db, "find_existing_urls", find_urls),
            mock.patch.object(run_pipeline.db, "find_recent_titles", return_value=set()),
            mock.patch.object(run_pipeline.db, "insert_articles",
                              side_effect=lambda rows: len(rows)) as insert,
            mock.patch.object(run_pipeline.db, "finish_run") as finish,
            mock.patch.object(run_pipeline, "extract_step", return_value=(0, True)),
            mock.patch("builtins.print"),
        ):
            exit_code = run_pipeline.main([])
        return exit_code, fetch, insert, finish

    def test_happy_path_inserts_new_articles_as_pending(self):
        batches = [[article(1), article(2)], [article(2), article(3)], []]
        code, _, insert, finish = self.run_with(batches, existing_urls={"https://x.com/1"})
        self.assertEqual(code, 0)
        inserted = insert.call_args[0][0]
        self.assertEqual([r["url"] for r in inserted], ["https://x.com/2", "https://x.com/3"])
        self.assertTrue(all(r["status"] == "pending" and r["run_id"] == 7 for r in inserted))
        finish.assert_called_once_with(7, "success", 4, 2, disruptions_found=0, error_message=None)

    def test_one_keyword_failing_does_not_stop_the_others(self):
        code, fetch, _, finish = self.run_with(
            [[article(1)], NewsAPIError("boom", code="unexpectedError"), [article(2)]])
        self.assertEqual(code, 0)
        self.assertEqual(fetch.call_count, 3)
        finish.assert_called_once_with(7, "success", 2, 2, disruptions_found=0,
                                       error_message="k2: boom")

    def test_bad_api_key_stops_fetching_and_fails_run(self):
        code, fetch, _, finish = self.run_with(
            [NewsAPIError("Your API key is invalid", code="apiKeyInvalid")])
        self.assertEqual(code, 1)
        self.assertEqual(fetch.call_count, 1)
        finish.assert_called_once_with(7, "failed", 0, 0, disruptions_found=0,
                                       error_message="k1: Your API key is invalid")

    def test_database_error_mid_run_is_recorded(self):
        code, _, insert, finish = self.run_with(
            [[article(1)], [], []],
            existing_urls_error=run_pipeline.db.DatabaseError("down"))
        self.assertEqual(code, 1)
        insert.assert_not_called()
        finish.assert_called_once_with(7, "failed", 0, 0, disruptions_found=0,
                                       error_message="unexpected error: down")

    def test_missing_settings_stops_before_touching_anything(self):
        with (
            mock.patch.object(run_pipeline.config, "missing_settings",
                              return_value=["NEWSAPI_KEY"]),
            mock.patch.object(run_pipeline.db, "start_run") as start,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(run_pipeline.main([]), 1)
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
