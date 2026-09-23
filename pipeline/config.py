"""
Settings for the pipeline, all in one place.

Secrets (API keys) are NEVER written in code. They are read from
environment variables, which locally come from the .env file
(listed in .gitignore, so it never reaches GitHub) and in production
will come from Vercel's environment variable settings.
"""

import os

from dotenv import load_dotenv

# Read the .env file (if there is one) into environment variables.
load_dotenv()


# ---------------------------------------------------------------------
# Secrets — read from the environment
# ---------------------------------------------------------------------

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
# The base project URL, e.g. https://abcd.supabase.co . If the REST address
# (.../rest/v1/) was pasted instead, trim it — db.py adds /rest/v1 itself.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/").removesuffix("/rest/v1")
# The Supabase *secret* key (sb_secret_...) or legacy "service_role" key.
# It can write to the database, so it must only ever live on the server.
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def missing_settings():
    """Return the names of any required environment variables that are empty."""
    required = {
        "NEWSAPI_KEY": NEWSAPI_KEY,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SECRET_KEY": SUPABASE_SECRET_KEY,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }
    return [name for name, value in required.items() if not value]


# ---------------------------------------------------------------------
# NewsAPI search settings
# ---------------------------------------------------------------------

# How many days back to search each run. Runs overlap on purpose:
# duplicate detection throws away anything we already have.
LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS", "3"))

# One NewsAPI request per keyword, so 6 keywords = 6 requests per run
# (the free plan allows 100 requests per day).
#
#   label -> saved in articles.search_keyword (readable name)
#   query -> sent to NewsAPI. Supports "exact phrases", AND, OR, ( ).
#
# The first four come straight from the PRD's keyword examples. The last two
# cover the PRD's "weather events" and "geopolitical incidents"; they are
# tied to "supply chain" because on their own they match mostly unrelated news.
# The PRD's industry focus is still open, so these are general / broad.
SEARCH_KEYWORDS = [
    {"label": "port strike",
     "query": '"port strike" OR "dockworkers strike" OR "dock strike"'},
    {"label": "shipping delay",
     "query": '"shipping delay" OR "shipping delays"'},
    {"label": "tariff",
     "query": 'tariff AND "supply chain"'},
    {"label": "supplier shortage",
     "query": '"supplier shortage" OR "supply shortage"'},
    {"label": "weather event",
     "query": '"supply chain" AND (storm OR typhoon OR hurricane OR flood OR drought)'},
    {"label": "geopolitical incident",
     "query": '"supply chain" AND (sanctions OR conflict OR "export controls" OR blockade)'},
]

# Only English articles. NewsAPI searches headline, description and article
# text. (Limiting it to headline + description was tested and returned 0
# results for combined queries like  tariff AND "supply chain", because both
# terms rarely appear in such short text. Gemini filters out irrelevant
# articles in the next step anyway.)
NEWS_LANGUAGE = "en"
NEWS_PAGE_SIZE = 100          # the maximum NewsAPI allows per request

# Titles that match a stored title published within this many days are
# treated as the same story (decision D11 in DATA_MODEL.md).
TITLE_DUPLICATE_WINDOW_DAYS = 7

# Seconds to wait for a reply from NewsAPI / Supabase before giving up.
HTTP_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------
# Gemini extraction settings
# ---------------------------------------------------------------------

# Which Gemini model to use (free tier). Saved in disruptions.model_name.
# Flash-Lite: Google's fastest, highest-throughput model — enough for classifying news.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# How many articles go into ONE Gemini request. The free tier limits requests
# per day, so 10 articles per request = 10x more articles for the same quota.
GEMINI_BATCH_SIZE = int(os.getenv("GEMINI_BATCH_SIZE", "10"))

# At most this many articles are sent to Gemini per run (50 = 5 requests).
# Anything left over stays 'pending' and is picked up by the next run.
EXTRACT_MAX_PER_RUN = int(os.getenv("EXTRACT_MAX_PER_RUN", "50"))

# Pause between Gemini requests, to stay under the free tier's
# requests-per-minute limit (4 seconds = at most 15 per minute).
GEMINI_SECONDS_BETWEEN_CALLS = float(os.getenv("GEMINI_SECONDS_BETWEEN_CALLS", "4"))
