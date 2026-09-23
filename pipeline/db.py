"""
Talking to the Supabase database.

Supabase automatically gives every table a REST API (a service called
PostgREST). Instead of writing SQL, we send HTTP requests:

    GET    /rest/v1/articles?...     -> read rows     (SQL: SELECT)
    POST   /rest/v1/articles         -> add rows      (SQL: INSERT)
    PATCH  /rest/v1/pipeline_runs?.. -> change rows   (SQL: UPDATE)

Filters go in the URL, e.g.  run_id=eq.5  means  WHERE run_id = 5.

The pipeline uses the SECRET key, which is allowed to write. (The public
website will use a read-only key; Row Level Security blocks it from writing.)
"""

from datetime import datetime, timezone

import requests

from pipeline import config
from pipeline.extract import Lookups


class DatabaseError(Exception):
    """A request to Supabase failed."""


# ---------------------------------------------------------------------
# Low-level helper: every database call goes through here
# ---------------------------------------------------------------------

def _request(method, table, params=None, json=None, prefer=None):
    """Send one HTTP request to Supabase's REST API and return the reply."""
    key = config.SUPABASE_SECRET_KEY
    headers = {"apikey": key, "Content-Type": "application/json"}

    # New-style keys (sb_secret_...) go only in the "apikey" header.
    # Old-style keys (long JWT "service_role" keys) also need this header:
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"

    # "Prefer" tells Supabase extra things, e.g. "send back the rows you saved".
    if prefer:
        headers["Prefer"] = prefer

    url = f"{config.SUPABASE_URL}/rest/v1/{table}"
    try:
        response = requests.request(method, url, params=params, json=json,
                                    headers=headers, timeout=config.HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise DatabaseError(f"could not reach Supabase: {error}") from error

    if not response.ok:
        raise DatabaseError(f"{method} {table} failed "
                            f"(HTTP {response.status_code}): {response.text[:300]}")
    return response


def _in_list(values):
    """
    Build a filter meaning "value is one of these", e.g.  in.("a","b").
    Each value is wrapped in double quotes because URLs and titles
    contain commas and brackets, which would otherwise break the list.
    """
    quoted = ['"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"' for v in values]
    return "in.(" + ",".join(quoted) + ")"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------
# pipeline_runs — the diary of each run
# ---------------------------------------------------------------------

def start_run():
    """Create a pipeline_runs row with status 'running' and return its run_id."""
    response = _request("POST", "pipeline_runs",
                        json={"status": "running"},
                        prefer="return=representation")   # send the new row back
    return response.json()[0]["run_id"]


def finish_run(run_id, status, articles_fetched, articles_new,
               disruptions_found=0, error_message=None):
    """Fill in the results and end time of a run."""
    _request("PATCH", "pipeline_runs",
             params={"run_id": f"eq.{run_id}"},              # WHERE run_id = ...
             json={
                 "status": status,
                 "finished_at": _now(),
                 "articles_fetched": articles_fetched,
                 "articles_new": articles_new,
                 "disruptions_found": disruptions_found,
                 "error_message": error_message,
             })


# ---------------------------------------------------------------------
# articles — duplicate checks and inserts
# ---------------------------------------------------------------------

def find_existing_urls(urls_normalized):
    """Return the subset of these normalized URLs that are already stored."""
    existing = set()
    urls = list(urls_normalized)
    batch_size = 25   # ask about 25 URLs per request, to keep request URLs short
    for start in range(0, len(urls), batch_size):
        batch = urls[start:start + batch_size]
        response = _request("GET", "articles", params={
            "select": "url_normalized",
            "url_normalized": _in_list(batch),
        })
        existing.update(row["url_normalized"] for row in response.json())
    return existing


def find_recent_titles(since):
    """Return normalized titles of stored articles published on/after `since`."""
    titles = set()
    page_size = 1000   # Supabase returns at most 1000 rows per request
    offset = 0
    while True:
        response = _request("GET", "articles", params={
            "select": "title_normalized",
            "published_at": f"gte.{since.isoformat()}",
            "order": "article_id",
            "limit": page_size,
            "offset": offset,
        })
        rows = response.json()
        titles.update(row["title_normalized"] for row in rows)
        if len(rows) < page_size:        # last page reached
            return titles
        offset += page_size


def insert_articles(rows):
    """
    Save new articles and return how many were actually inserted.

    Safety net: "on_conflict=url_normalized" + "ignore-duplicates" means that if
    an article somehow slipped past the duplicate checks, the database's UNIQUE
    rule quietly skips it instead of failing the whole insert.
    """
    if not rows:
        return 0
    response = _request("POST", "articles",
                        params={"on_conflict": "url_normalized",
                                "select": "article_id"},
                        json=rows,
                        prefer="resolution=ignore-duplicates,return=representation")
    return len(response.json())    # only rows really inserted are sent back


# ---------------------------------------------------------------------
# Gemini extraction — lookups, work queue, results
# ---------------------------------------------------------------------

def load_lookups():
    """Read the allowed regions, disruption types and countries from the database."""
    regions = _request("GET", "regions", params={"select": "region_id,name",
                                                 "order": "region_id"}).json()
    types = _request("GET", "disruption_types",
                     params={"select": "disruption_type_id,name,description",
                             "order": "disruption_type_id"}).json()
    countries = _request("GET", "countries", params={"select": "country_code,region_id"}).json()
    return Lookups(
        region_ids={r["name"]: r["region_id"] for r in regions},
        type_ids={t["name"]: t["disruption_type_id"] for t in types},
        type_descriptions={t["name"]: t["description"] for t in types},
        country_regions={c["country_code"]: c["region_id"] for c in countries},
    )


def get_articles_to_extract(limit):
    """
    Articles waiting for Gemini: status 'pending' first, then 'failed'
    (an earlier Gemini call went wrong, so try again), oldest first.
    """
    return _request("GET", "articles", params={
        "select": "article_id,title,description,source_name,published_at,status",
        "status": "in.(pending,failed)",
        "order": "status.desc,article_id.asc",    # 'pending' sorts after 'failed', so desc
        "limit": limit,
    }).json()


def save_disruption(row):
    """
    Insert Gemini's result. If this article already has a result (e.g. an
    earlier run saved it but crashed before updating the article's status),
    the UNIQUE rule on article_id quietly skips it.
    """
    _request("POST", "disruptions",
             params={"on_conflict": "article_id"},
             json=row,
             prefer="resolution=ignore-duplicates")


def set_article_status(article_id, status):
    """Record Gemini's verdict on the article: disruption / not_disruption / failed."""
    _request("PATCH", "articles",
             params={"article_id": f"eq.{article_id}"},
             json={"status": status})
