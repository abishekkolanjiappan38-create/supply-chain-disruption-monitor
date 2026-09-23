"""
Runs the pipeline once, start to finish.

    python -m pipeline.run_pipeline                  fetch news + extract with Gemini
    python -m pipeline.run_pipeline --extract-only   only process articles already stored

Steps:
  1. Check that all API keys are set
  2. Create a pipeline_runs row                    (status = 'running')
  3. FETCH:   get articles from NewsAPI, drop duplicates, save new ones as 'pending'
  4. EXTRACT: send 'pending' articles to Gemini (10 per request), save real disruptions,
              mark each article 'disruption' / 'not_disruption' / 'failed'
  5. Update the pipeline_runs row                  (counts, status, finished_at)

Exit code: 0 if the run succeeded, 1 if it failed (a scheduler can use this).
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from pipeline import config, db, dedupe, extract, gemini_client
from pipeline.news_client import NewsAPIError, fetch_articles


def main(argv=None):
    parser = argparse.ArgumentParser(description="Supply chain disruption pipeline")
    parser.add_argument("--extract-only", action="store_true",
                        help="skip NewsAPI; only send stored 'pending' articles to Gemini")
    args = parser.parse_args(argv)

    # --- Step 1: settings -------------------------------------------------
    missing = config.missing_settings()
    if missing:
        print("Missing environment variables:", ", ".join(missing))
        print("Add them to your .env file (see .env.example).")
        return 1

    # --- Step 2: open the run diary ---------------------------------------
    # If Supabase can't be reached, there is nowhere to record the run, so stop.
    try:
        run_id = db.start_run()
    except db.DatabaseError as error:
        print("Could not start the run:", error)
        return 1
    print(f"Pipeline run {run_id} started")

    articles_fetched = articles_new = disruptions_found = 0
    errors = []          # problems worth recording in pipeline_runs.error_message
    status = "failed"    # assume failure until we get to the end successfully

    try:
        # --- Step 3: fetch ------------------------------------------------
        fetch_ok = True
        if not args.extract_only:
            articles_fetched, articles_new, fetch_ok = fetch_step(run_id, errors)

        # --- Step 4: extract ----------------------------------------------
        disruptions_found, extract_ok = extract_step(errors)

        status = "success" if fetch_ok and extract_ok else "failed"

    except Exception as error:
        # Anything unexpected (e.g. Supabase went down mid-run): record it
        # instead of crashing without a trace.
        print("Run failed:", error)
        errors.append(f"unexpected error: {error}")
        status = "failed"

    # --- Step 5: close the run diary --------------------------------------
    try:
        db.finish_run(run_id, status, articles_fetched, articles_new,
                      disruptions_found=disruptions_found,
                      error_message="; ".join(errors) or None)
    except db.DatabaseError as error:
        print("Could not update the run record:", error)
        status = "failed"

    print(f"Pipeline run {run_id} finished: {status} ({articles_fetched} fetched, "
          f"{articles_new} new, {disruptions_found} disruptions found)")
    return 0 if status == "success" else 1


def fetch_step(run_id, errors):
    """
    Fetch from NewsAPI, remove duplicates, save new articles as 'pending'.
    Returns (articles_fetched, articles_new, ok). ok = at least one keyword worked.
    """
    print("FETCH")
    fetched_rows = []
    keywords_ok = 0

    # Each keyword is tried separately, so one failed request doesn't stop the others.
    for keyword in config.SEARCH_KEYWORDS:
        try:
            rows = fetch_articles(keyword)
        except NewsAPIError as error:
            print(f"  [{keyword['label']}] failed: {error}")
            errors.append(f"{keyword['label']}: {error}")
            if error.stop_all:       # e.g. bad key or daily limit reached
                print("  Stopping NewsAPI requests - the rest would fail too.")
                break
            continue
        keywords_ok += 1
        fetched_rows.extend(rows)
        print(f"  [{keyword['label']}] {len(rows)} articles")

    # Remove duplicates: within this batch, then against the database.
    unique_rows = dedupe.remove_batch_duplicates(fetched_rows)
    existing_urls = db.find_existing_urls(r["url_normalized"] for r in unique_rows)
    since = datetime.now(timezone.utc) - timedelta(days=config.TITLE_DUPLICATE_WINDOW_DAYS)
    recent_titles = db.find_recent_titles(since)
    new_rows = dedupe.remove_stored_duplicates(unique_rows, existing_urls, recent_titles)
    print(f"  Fetched {len(fetched_rows)}, unique in batch {len(unique_rows)}, "
          f"new {len(new_rows)}")

    for row in new_rows:
        row["run_id"] = run_id
        row["status"] = "pending"    # waiting for Gemini
    articles_new = db.insert_articles(new_rows)

    return len(fetched_rows), articles_new, keywords_ok > 0


def extract_step(errors):
    """
    Send waiting articles to Gemini in batches and save the results.
    Returns (disruptions_found, ok). ok = nothing to do, or at least one
    article was processed successfully.

    One Gemini request covers a whole batch, but every article is still
    validated, saved and given its status ON ITS OWN.
    """
    print("EXTRACT")
    lookups = db.load_lookups()
    articles = db.get_articles_to_extract(config.EXTRACT_MAX_PER_RUN)
    size = config.GEMINI_BATCH_SIZE
    batches = [articles[i:i + size] for i in range(0, len(articles), size)]
    print(f"  {len(articles)} article(s) waiting for Gemini -> {len(batches)} request(s)")

    counts = {"processed": 0, "found": 0, "failed": 0}
    failure_notes = []

    def article_failed(article_id, reason):
        """Mark ONE article 'failed' (a later run retries it) and note why."""
        counts["failed"] += 1
        print(f"  #{article_id} failed: {reason}")
        if len(failure_notes) < 3:
            failure_notes.append(f"#{article_id}: {reason}")
        db.set_article_status(article_id, "failed")

    for number, batch in enumerate(batches, start=1):
        if number > 1:
            time.sleep(config.GEMINI_SECONDS_BETWEEN_CALLS)   # respect the rate limit

        # --- one request for the whole batch ------------------------------
        try:
            results = gemini_client.extract_batch(batch, lookups)
        except gemini_client.GeminiError as error:
            if error.stop_all:
                # A problem for EVERY article (bad key, quota used up): the
                # articles did nothing wrong, so leave them 'pending' and stop.
                print(f"  Batch {number} failed: {error}")
                print("  Stopping Gemini requests - the rest would fail too.")
                counts["failed"] += len(batch)
                failure_notes.append(f"batch {number}: {error}")
                break
            # A problem with THIS request only: its articles are retried later.
            for article in batch:
                article_failed(article["article_id"], f"batch request failed: {error}")
            continue

        # --- then every article on its own --------------------------------
        for article in batch:
            article_id = article["article_id"]
            result = results.get(article_id)
            if result is None:
                article_failed(article_id, "Gemini returned no result for this article")
                continue
            try:
                row = extract.to_disruption_row(result, article_id, lookups, config.GEMINI_MODEL)
            except extract.InvalidExtraction as error:
                article_failed(article_id, error)
                continue

            if row is None:
                db.set_article_status(article_id, "not_disruption")
                print(f"  #{article_id} not a disruption")
            else:
                # Save the result first, then the article's status. If the run
                # crashed in between, the article is simply processed again later.
                db.save_disruption(row)
                db.set_article_status(article_id, "disruption")
                counts["found"] += 1
                print(f"  #{article_id} DISRUPTION ({row['severity']}): {row['summary'][:70]}")
            counts["processed"] += 1

    if counts["failed"]:
        errors.append(f"extraction: {counts['failed']} article(s) failed, will retry next run "
                      f"({'; '.join(failure_notes)})")
    print(f"  Processed {counts['processed']}, disruptions {counts['found']}, "
          f"failed {counts['failed']}")
    return counts["found"], counts["processed"] > 0 or counts["failed"] == 0


if __name__ == "__main__":
    sys.exit(main())
