"""
Talking to the Google Gemini API.

One function call = one request to Gemini's generateContent endpoint,
carrying a batch of up to GEMINI_BATCH_SIZE articles. We ask for JSON that
must follow the schema in prompt.py, so the reply can be read directly with
json.loads().
"""

import json
import re
import time

import requests

from pipeline import config, prompt

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# HTTP codes worth retrying: 429 = too many requests (rate limit),
# 5xx = temporary problem on Google's side.
RETRY_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class GeminiError(Exception):
    """
    A Gemini request failed. `stop_all` = True means every other article
    would fail the same way (bad key, unknown model, daily quota used up),
    so the pipeline should stop calling Gemini for this run.
    """

    def __init__(self, message, stop_all=False):
        super().__init__(message)
        self.stop_all = stop_all


def extract_batch(articles, lookups):
    """
    Send several articles to Gemini in ONE request.

    Returns {article_id: answer_dict}. Answers are matched to articles by
    article_id — never by their position in the list. An article Gemini
    skipped is simply missing from the result; the caller handles that.
    """
    body = {
        "systemInstruction": {"parts": [{"text": prompt.build_system_instruction(lookups)}]},
        "contents": [{"role": "user",
                      "parts": [{"text": prompt.build_user_message(articles)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",          # reply must be JSON...
            "responseSchema": prompt.build_response_schema(lookups),  # ...in this shape
            "temperature": 0,     # least random: the same article gets the same answer
        },
    }
    data = _post_with_retries(body)

    # The JSON text sits at candidates[0].content.parts[0].text
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no answer")
        raise GeminiError(f"Gemini returned no answer ({reason})")

    candidate = candidates[0]
    if candidate.get("finishReason") not in (None, "STOP"):
        raise GeminiError(f"Gemini stopped early ({candidate.get('finishReason')})")

    try:
        text = candidate["content"]["parts"][0]["text"]
        results = json.loads(text)["results"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise GeminiError(f"could not read Gemini's JSON: {error}") from error

    # Link each answer back to its article by article_id.
    sent_ids = {article["article_id"] for article in articles}
    by_id = {}
    for result in results:
        article_id = result.get("article_id") if isinstance(result, dict) else None
        if article_id in sent_ids and article_id not in by_id:   # ignore unknown / repeated ids
            by_id[article_id] = result
    return by_id


def _post_with_retries(body):
    """POST to Gemini, waiting and retrying on rate limits / temporary errors."""
    url = GEMINI_URL.format(model=config.GEMINI_MODEL)
    headers = {"x-goog-api-key": config.GEMINI_API_KEY}   # key in a header, not the URL

    for attempt in range(1, MAX_ATTEMPTS + 1):
        last_try = attempt == MAX_ATTEMPTS

        try:
            response = requests.post(url, json=body, headers=headers, timeout=60)
        except requests.RequestException as error:        # no internet, timeout...
            if last_try:
                raise GeminiError(f"could not reach Gemini: {error}") from error
            time.sleep(5 * attempt)
            continue

        if response.status_code == 200:
            return response.json()

        error = _error_details(response)
        if response.status_code in RETRY_CODES and not last_try:
            wait = _retry_delay(error) or 10 * attempt
            print(f"    Gemini busy (HTTP {response.status_code}), waiting {wait:.0f}s...")
            time.sleep(wait)
            continue

        # Not retryable, or out of retries. These affect every article, so stop:
        #   400 bad request/key, 401/403 not allowed, 404 unknown model,
        #   429 still rate-limited after retries (likely the daily quota).
        stop_all = response.status_code in {400, 401, 403, 404, 429}
        raise GeminiError(f"HTTP {response.status_code}: {error.get('message', response.text[:200])}",
                          stop_all=stop_all)


def _error_details(response):
    """Gemini errors look like {"error": {"code":..., "message":..., "details": [...]}}."""
    try:
        return response.json().get("error") or {}
    except ValueError:
        return {}


def _retry_delay(error):
    """If Gemini says how long to wait (e.g. "retryDelay": "12s"), use it (max 60s)."""
    for detail in error.get("details", []):
        match = re.match(r"([\d.]+)s", str(detail.get("retryDelay", "")))
        if match:
            return min(float(match.group(1)) + 1, 60)
    return None
