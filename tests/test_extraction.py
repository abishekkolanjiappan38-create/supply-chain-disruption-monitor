"""
Offline tests for the Gemini extraction step — no API keys or internet needed.
Gemini and Supabase are replaced with fakes ("mocks").

Run from the project folder:
    python -m unittest discover tests -v
"""

import json
import unittest
from unittest import mock

from pipeline import gemini_client, prompt, run_pipeline
from pipeline.extract import InvalidExtraction, Lookups, to_disruption_row

LOOKUPS = Lookups(
    region_ids={"East Asia": 1, "Middle East": 3, "North America": 5, "Global": 8},
    type_ids={"Labour action": 1, "Port / shipping delay": 6},
    type_descriptions={"Labour action": "Strikes.", "Port / shipping delay": "Congestion."},
    country_regions={"US": 5, "CN": 1, "EG": 3},
)

DISRUPTION = {"is_disruption": True, "region": "North America", "country_code": "US",
              "disruption_type": "Labour action", "severity": "high",
              "summary": "  Dockworkers   strike halts US East Coast ports.  "}
NOT_DISRUPTION = {"is_disruption": False, "region": None, "country_code": None,
                  "disruption_type": None, "severity": None, "summary": None}


def answer(article_id, base):
    """One Gemini result for one article (the batch format includes article_id)."""
    return {"article_id": article_id, **base}


# ---------------------------------------------------------------------
# Validation of ONE answer (unchanged by batching)
# ---------------------------------------------------------------------

class ToDisruptionRowTests(unittest.TestCase):
    def test_not_a_disruption_gives_no_row(self):
        self.assertIsNone(to_disruption_row(NOT_DISRUPTION, 1, LOOKUPS, "m"))

    def test_valid_disruption(self):
        row = to_disruption_row(DISRUPTION, 42, LOOKUPS, "gemini-x")
        self.assertEqual(row, {"article_id": 42, "region_id": 5, "country_code": "US",
                               "disruption_type_id": 1, "severity": "high",
                               "summary": "Dockworkers strike halts US East Coast ports.",
                               "model_name": "gemini-x"})

    def test_region_comes_from_country_when_they_disagree(self):
        row = to_disruption_row({**DISRUPTION, "region": "East Asia"}, 1, LOOKUPS, "m")
        self.assertEqual(row["region_id"], 5)          # US -> North America

    def test_unknown_country_is_dropped_and_region_used(self):
        row = to_disruption_row({**DISRUPTION, "country_code": "ZZ", "region": "Middle East"},
                                1, LOOKUPS, "m")
        self.assertIsNone(row["country_code"])
        self.assertEqual(row["region_id"], 3)

    def test_lowercase_country_code_accepted(self):
        self.assertEqual(to_disruption_row({**DISRUPTION, "country_code": "cn"}, 1, LOOKUPS, "m")
                         ["region_id"], 1)

    def test_invalid_answers_are_rejected(self):
        bad = [
            {**DISRUPTION, "is_disruption": "yes"},
            {**DISRUPTION, "severity": "extreme"},
            {**DISRUPTION, "disruption_type": "Aliens"},
            {**DISRUPTION, "country_code": None, "region": "Atlantis"},
            {**DISRUPTION, "summary": "   "},
        ]
        for bad_answer in bad:
            with self.assertRaises(InvalidExtraction, msg=bad_answer):
                to_disruption_row(bad_answer, 1, LOOKUPS, "m")


# ---------------------------------------------------------------------
# Prompt and answer format
# ---------------------------------------------------------------------

class PromptTests(unittest.TestCase):
    def test_schema_is_a_list_of_results_with_article_id(self):
        schema = prompt.build_response_schema(LOOKUPS)
        item = schema["properties"]["results"]["items"]
        self.assertEqual(schema["properties"]["results"]["type"], "ARRAY")
        self.assertIn("article_id", item["required"])
        self.assertEqual(item["properties"]["region"]["enum"],
                         ["East Asia", "Middle East", "North America", "Global"])
        self.assertEqual(item["properties"]["disruption_type"]["enum"],
                         ["Labour action", "Port / shipping delay"])
        self.assertEqual(item["properties"]["severity"]["enum"], ["low", "medium", "high"])

    def test_system_instruction_lists_types_regions_and_batch_rule(self):
        text = prompt.build_system_instruction(LOOKUPS)
        self.assertIn("- Labour action: Strikes.", text)
        self.assertIn("East Asia, Middle East, North America, Global", text)
        self.assertIn("exactly ONE result per article", text)

    def test_user_message_labels_every_article_with_its_id(self):
        text = prompt.build_user_message([
            {"article_id": 3, "title": "A", "source_name": None,
             "published_at": "2026-09-20", "description": None},
            {"article_id": 9, "title": "B", "source_name": "S",
             "published_at": "2026-09-21", "description": "d"},
        ])
        self.assertIn("article_id: 3\nHeadline: A", text)
        self.assertIn("article_id: 9\nHeadline: B", text)
        self.assertIn("Description: (none)", text)
        self.assertIn("Source: unknown", text)


# ---------------------------------------------------------------------
# Gemini client (one request per batch)
# ---------------------------------------------------------------------

def fake_response(status, body):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    response.text = json.dumps(body)
    return response


def gemini_ok(results):
    text = json.dumps({"results": results})
    return fake_response(200, {"candidates": [{"finishReason": "STOP",
                                               "content": {"parts": [{"text": text}]}}]})


def make_articles(*ids):
    return [{"article_id": i, "title": f"T{i}", "description": "D",
             "source_name": "S", "published_at": "2026-09-20T00:00:00Z"} for i in ids]


class GeminiClientTests(unittest.TestCase):
    def call(self, responses, articles=None):
        articles = articles or make_articles(1)
        with mock.patch.object(gemini_client.requests, "post", side_effect=responses) as post, \
             mock.patch.object(gemini_client.time, "sleep") as sleep, \
             mock.patch("builtins.print"):
            try:
                return gemini_client.extract_batch(articles, LOOKUPS), post, sleep
            except gemini_client.GeminiError as error:
                return error, post, sleep

    def test_one_request_for_the_whole_batch(self):
        results, post, _ = self.call(
            [gemini_ok([answer(1, DISRUPTION), answer(2, NOT_DISRUPTION), answer(3, DISRUPTION)])],
            make_articles(1, 2, 3))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(set(results), {1, 2, 3})
        body = post.call_args.kwargs["json"]
        self.assertIn("article_id: 3", body["contents"][0]["parts"][0]["text"])
        self.assertIn("x-goog-api-key", post.call_args.kwargs["headers"])

    def test_answers_matched_by_id_not_position(self):
        # Gemini returns the answers in a different order than the articles were sent.
        results, _, _ = self.call([gemini_ok([answer(2, NOT_DISRUPTION), answer(1, DISRUPTION)])],
                                  make_articles(1, 2))
        self.assertTrue(results[1]["is_disruption"])
        self.assertFalse(results[2]["is_disruption"])

    def test_unknown_and_repeated_ids_are_ignored(self):
        results, _, _ = self.call([gemini_ok([answer(1, DISRUPTION), answer(1, NOT_DISRUPTION),
                                              answer(99, DISRUPTION)])],
                                  make_articles(1, 2))
        self.assertEqual(set(results), {1})               # 99 wasn't sent; 2 is missing
        self.assertTrue(results[1]["is_disruption"])      # first answer for #1 wins

    def test_rate_limit_is_retried_using_retry_delay(self):
        limited = fake_response(429, {"error": {"code": 429, "message": "slow down",
                                                "details": [{"retryDelay": "7s"}]}})
        results, post, sleep = self.call([limited, gemini_ok([answer(1, NOT_DISRUPTION)])])
        self.assertEqual(set(results), {1})
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(8.0)

    def test_rate_limit_that_never_clears_stops_all(self):
        limited = fake_response(429, {"error": {"code": 429, "message": "quota"}})
        error, post, _ = self.call([limited] * 3)
        self.assertIsInstance(error, gemini_client.GeminiError)
        self.assertTrue(error.stop_all)
        self.assertEqual(post.call_count, 3)

    def test_bad_key_stops_all_without_retry(self):
        error, post, _ = self.call([fake_response(400, {"error": {"message": "API key not valid"}})])
        self.assertTrue(error.stop_all)
        self.assertEqual(post.call_count, 1)

    def test_blocked_request_fails_only_this_batch(self):
        error, _, _ = self.call([fake_response(200, {"promptFeedback": {"blockReason": "SAFETY"}})])
        self.assertIsInstance(error, gemini_client.GeminiError)
        self.assertFalse(error.stop_all)
        self.assertIn("SAFETY", str(error))

    def test_malformed_json_is_an_error(self):
        bad = fake_response(200, {"candidates": [{"finishReason": "STOP",
                                                  "content": {"parts": [{"text": '{"oops": 1}'}]}}]})
        error, _, _ = self.call([bad])
        self.assertIsInstance(error, gemini_client.GeminiError)
        self.assertFalse(error.stop_all)


# ---------------------------------------------------------------------
# extract_step: batches in, separate records out
# ---------------------------------------------------------------------

class ExtractStepTests(unittest.TestCase):
    def run_step(self, n_articles, batch_results, batch_size=10):
        """batch_results: one item per expected Gemini request (a dict of answers, or an error)."""
        articles = make_articles(*range(1, n_articles + 1))
        errors = []
        with mock.patch.object(run_pipeline.db, "load_lookups", return_value=LOOKUPS), \
             mock.patch.object(run_pipeline.db, "get_articles_to_extract", return_value=articles), \
             mock.patch.object(run_pipeline.db, "save_disruption") as save, \
             mock.patch.object(run_pipeline.db, "set_article_status") as set_status, \
             mock.patch.object(run_pipeline.gemini_client, "extract_batch",
                               side_effect=batch_results) as extract_batch, \
             mock.patch.object(run_pipeline.config, "GEMINI_BATCH_SIZE", batch_size), \
             mock.patch.object(run_pipeline.time, "sleep"), \
             mock.patch("builtins.print"):
            found, ok = run_pipeline.extract_step(errors)
        statuses = {c.args[0]: c.args[1] for c in set_status.call_args_list}
        saved_ids = [c.args[0]["article_id"] for c in save.call_args_list]
        return found, ok, saved_ids, statuses, errors, extract_batch

    def test_articles_are_split_into_batches(self):
        _, _, _, _, _, extract_batch = self.run_step(
            25, [{i: answer(i, NOT_DISRUPTION) for i in range(a, b)}
                 for a, b in [(1, 11), (11, 21), (21, 26)]])
        sizes = [len(c.args[0]) for c in extract_batch.call_args_list]
        self.assertEqual(sizes, [10, 10, 5])              # 25 articles -> 3 requests

    def test_each_article_in_a_batch_is_handled_separately(self):
        results = {
            1: answer(1, DISRUPTION),
            2: answer(2, NOT_DISRUPTION),
            3: answer(3, {**DISRUPTION, "severity": "extreme"}),   # invalid -> only #3 fails
            # 4 missing: Gemini skipped it -> only #4 fails
            5: answer(5, {**DISRUPTION, "country_code": "CN"}),
        }
        found, ok, saved_ids, statuses, errors, _ = self.run_step(5, [results])
        self.assertEqual((found, ok), (2, True))
        self.assertEqual(saved_ids, [1, 5])               # one disruptions row per real disruption
        self.assertEqual(statuses, {1: "disruption", 2: "not_disruption", 3: "failed",
                                    4: "failed", 5: "disruption"})
        self.assertIn("2 article(s) failed", errors[0])
        self.assertIn("no result", errors[0])

    def test_a_failed_request_only_fails_its_own_batch(self):
        found, ok, saved_ids, statuses, _, _ = self.run_step(
            4, [gemini_client.GeminiError("blocked"), {3: answer(3, DISRUPTION), 4: answer(4, NOT_DISRUPTION)}],
            batch_size=2)
        self.assertEqual((found, ok), (1, True))
        self.assertEqual(statuses, {1: "failed", 2: "failed", 3: "disruption", 4: "not_disruption"})
        self.assertEqual(saved_ids, [3])

    def test_stop_all_leaves_articles_pending_and_stops(self):
        found, ok, saved_ids, statuses, errors, extract_batch = self.run_step(
            25, [gemini_client.GeminiError("API key not valid", stop_all=True)])
        self.assertEqual((found, ok), (0, False))
        self.assertEqual(extract_batch.call_count, 1)     # no further requests
        self.assertEqual(saved_ids, [])
        self.assertEqual(statuses, {})                     # nothing marked failed; all stay 'pending'
        self.assertIn("API key not valid", errors[0])

    def test_nothing_waiting_is_fine(self):
        found, ok, saved_ids, statuses, errors, extract_batch = self.run_step(0, [])
        self.assertEqual((found, ok, saved_ids, statuses, errors), (0, True, [], {}, []))
        extract_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
