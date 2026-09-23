"""
Talking to NewsAPI.org.

One function call = one HTTP request to NewsAPI's /v2/everything endpoint
for one keyword. It returns the articles as simple Python dictionaries
shaped like rows of our `articles` table.
"""

from datetime import datetime, timedelta, timezone

import requests

from pipeline import config
from pipeline.normalize import normalize_title, normalize_url

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# NewsAPI error codes that mean "every further request will fail too",
# so the pipeline should stop asking instead of trying the next keyword.
STOP_ALL_CODES = {"apiKeyInvalid", "apiKeyMissing", "apiKeyDisabled",
                  "apiKeyExhausted", "rateLimited"}


class NewsAPIError(Exception):
    """A request to NewsAPI failed. `code` is NewsAPI's error code, if it sent one."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

    @property
    def stop_all(self):
        return self.code in STOP_ALL_CODES


def fetch_articles(keyword):
    """
    Search NewsAPI for one keyword and return a list of article rows.

    `keyword` is one entry of config.SEARCH_KEYWORDS: {"label": ..., "query": ...}
    Raises NewsAPIError if the request fails.
    """
    oldest = datetime.now(timezone.utc) - timedelta(days=config.LOOKBACK_DAYS)

    params = {
        "q": keyword["query"],
        "language": config.NEWS_LANGUAGE,
        "from": oldest.strftime("%Y-%m-%dT%H:%M:%S"),
        "sortBy": "publishedAt",            # newest first
        "pageSize": config.NEWS_PAGE_SIZE,
    }
    # The key goes in a header rather than the URL, so it never shows up in logs.
    headers = {"X-Api-Key": config.NEWSAPI_KEY}

    # --- Send the request ------------------------------------------------
    try:
        response = requests.get(NEWSAPI_URL, params=params, headers=headers,
                                timeout=config.HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as error:      # no internet, timeout, DNS...
        raise NewsAPIError(f"could not reach NewsAPI: {error}") from error

    # --- Read the reply --------------------------------------------------
    try:
        data = response.json()
    except ValueError:
        raise NewsAPIError(f"NewsAPI sent a non-JSON reply (HTTP {response.status_code})")

    # On failure NewsAPI replies {"status": "error", "code": "...", "message": "..."}
    if response.status_code != 200 or data.get("status") != "ok":
        raise NewsAPIError(data.get("message", f"HTTP {response.status_code}"),
                           code=data.get("code"))

    # --- Turn each raw article into a row for our table ------------------
    rows = []
    for raw in data.get("articles", []):
        row = to_article_row(raw, keyword["label"])
        if row is not None:
            rows.append(row)
    return rows


def to_article_row(raw, search_keyword):
    """
    Convert one article from NewsAPI's format into our `articles` table format.
    Returns None for articles we can't use.
    """
    title = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    published_at = raw.get("publishedAt")
    source_name = (raw.get("source") or {}).get("name")

    # Skip unusable articles: missing essentials, or NewsAPI's placeholder
    # for articles that were taken down ("[Removed]").
    if not title or not url or not published_at or title == "[Removed]":
        return None

    return {
        "url": url,
        "url_normalized": normalize_url(url),
        "title": title,
        "title_normalized": normalize_title(title, source_name),
        "source_name": source_name,
        "description": raw.get("description"),
        "search_keyword": search_keyword,
        "published_at": published_at,    # e.g. "2026-09-20T14:05:00Z" (UTC)
    }
