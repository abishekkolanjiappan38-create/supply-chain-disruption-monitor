"""
Cleaning up URLs and headlines so duplicates can be spotted.

Two links or two headlines can look different but mean the same article:

    https://www.Reuters.com/world/port-strike/?utm_source=twitter
    https://www.reuters.com/world/port-strike

    "Port strike halts ships - Reuters"
    "Port Strike Halts Ships!"

These functions turn each one into a single standard ("normalized") form.
The normalized forms are saved in articles.url_normalized and
articles.title_normalized and compared against each other.
"""

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query-string parameters that only track where a click came from.
# They never change which article the link points to, so they are removed.
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ocid", "cmpid", "smid"}


def normalize_url(url):
    """
    Return a cleaned version of a URL, used only for duplicate detection
    (the original URL is still saved and used for the "Open article" link).

    Steps:
      1. http and https are treated the same (both become https)
      2. the domain is lower-cased          Reuters.com  -> reuters.com
      3. tracking parameters are removed    ?utm_source=... , ?fbclid=...
      4. the #anchor is removed             #comments
      5. a trailing slash is removed        /article/    -> /article
    """
    parts = urlsplit(url.strip())

    domain = parts.netloc.lower()

    # Keep only the query parameters that are not tracking tags.
    kept_params = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept_params))   # sorted, so parameter order doesn't matter

    path = parts.path.rstrip("/")

    # urlunsplit puts the pieces back together; "" for the #anchor drops it.
    return urlunsplit(("https", domain, path, query, ""))


def normalize_title(title, source_name=None):
    """
    Return a cleaned version of a headline, used only for duplicate detection.

    Steps:
      1. remove a trailing " - Source Name" that NewsAPI often adds
         ("Port strike halts ships - Reuters" -> "Port strike halts ships"),
         so the same story from two outlets still matches
      2. standardize special characters (curly quotes, accents' encodings)
      3. lower-case everything
      4. replace punctuation with spaces and squeeze repeated spaces
    """
    text = title.strip()

    if source_name:
        suffix = " - " + source_name.strip()
        if text.lower().endswith(suffix.lower()):
            text = text[: -len(suffix)]

    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)       # anything not a letter/digit/space
    text = re.sub(r"\s+", " ", text).strip()   # many spaces -> one space
    return text
