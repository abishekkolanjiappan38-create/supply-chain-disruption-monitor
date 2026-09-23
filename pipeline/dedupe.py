"""
Deciding which fetched articles are genuinely new.

An article is a duplicate (and is dropped) if:
  1. another article in this same batch already has its URL or headline
     (e.g. one article matched two keywords), or
  2. its normalized URL is already stored in the database (any date), or
  3. its normalized headline matches a stored article published in the
     last 7 days (the same wire story republished at a different link).

This file only compares lists — it never talks to NewsAPI or Supabase —
which makes it easy to test.
"""


def remove_batch_duplicates(rows):
    """Keep only the first article for each URL and each headline in this batch."""
    seen_urls, seen_titles, unique = set(), set(), []
    for row in rows:
        url, title = row["url_normalized"], row["title_normalized"]
        if url in seen_urls or (title and title in seen_titles):
            continue
        seen_urls.add(url)
        if title:                      # an empty title can't identify a story
            seen_titles.add(title)
        unique.append(row)
    return unique


def remove_stored_duplicates(rows, existing_urls, recent_titles):
    """Drop articles whose URL is already stored or whose headline was seen recently."""
    return [
        row for row in rows
        if row["url_normalized"] not in existing_urls
        and not (row["title_normalized"] and row["title_normalized"] in recent_titles)
    ]
