"""
Quick test of NewsAPI on its own — no Supabase needed, nothing is saved.

    python -m pipeline.check_newsapi

Only NEWSAPI_KEY has to be set in .env. Uses one NewsAPI request per
keyword (6 of the free plan's 100 per day).
"""

import sys

from pipeline import config
from pipeline.news_client import NewsAPIError, fetch_articles


def main():
    if not config.NEWSAPI_KEY:
        print("NEWSAPI_KEY is empty - add it to .env and save the file.")
        return 1

    total, failed = 0, 0
    for keyword in config.SEARCH_KEYWORDS:
        try:
            rows = fetch_articles(keyword)
        except NewsAPIError as error:
            failed += 1
            print(f"[{keyword['label']}] FAILED: {error} (code: {error.code})")
            if error.stop_all:
                print("Stopping - the remaining requests would fail the same way.")
                break
            continue

        total += len(rows)
        print(f"[{keyword['label']}] {len(rows)} articles")
        for row in rows[:3]:                    # show a few examples
            print(f"    {row['published_at'][:10]}  {row['source_name']}: {row['title'][:90]}")

    print(f"\nTotal: {total} articles, {failed} keyword(s) failed. Nothing was saved.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
