"""
Quick test of Gemini on two made-up articles — nothing is saved.

    python -m pipeline.check_gemini

Reads the allowed regions/types from Supabase (read-only), sends the two
samples to Gemini, and prints its raw JSON and the row that WOULD be saved.
Uses 1 Gemini request (both samples are sent as one batch).
"""

import json
import sys

from pipeline import config, db, extract, gemini_client

SAMPLES = [
    {"article_id": 1, "source_name": "Sample Wire", "published_at": "2026-09-20T08:00:00Z",
     "title": "Dockworkers walk out at Savannah and Charleston, halting container traffic",
     "description": "A strike by port workers has stopped vessel unloading at two major US "
                    "East Coast ports, with carriers diverting ships to other terminals."},
    {"article_id": 2, "source_name": "Sample Markets", "published_at": "2026-09-20T09:00:00Z",
     "title": "Tech stocks edge higher as investors await earnings",
     "description": "Shares of large technology companies rose slightly on Monday ahead of "
                    "quarterly results later this week."},
]


def main():
    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY is empty - add it to .env and save the file.")
        return 1

    lookups = db.load_lookups()
    print(f"Model: {config.GEMINI_MODEL}\n")
    try:
        results = gemini_client.extract_batch(SAMPLES, lookups)
    except gemini_client.GeminiError as error:
        print("FAILED:", error)
        return 1

    for sample in SAMPLES:
        print("ARTICLE:", sample["title"])
        result = results.get(sample["article_id"])
        if result is None:
            print("  No result returned for this article\n")
            continue
        print("  Gemini JSON:", json.dumps(result))
        try:
            row = extract.to_disruption_row(result, sample["article_id"], lookups,
                                            config.GEMINI_MODEL)
            print("  Would save:", row if row else "nothing (not a disruption)")
        except extract.InvalidExtraction as error:
            print("  Answer rejected:", error)
        print()
    print("Nothing was saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
