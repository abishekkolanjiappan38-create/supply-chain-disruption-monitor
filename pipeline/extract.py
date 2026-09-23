"""
Checking Gemini's answer and turning it into a row for the `disruptions` table.

Gemini's JSON is never trusted blindly. Every value is checked against the
database's lookup tables before anything is saved. This file only works with
Python values — no API or database calls — so it's easy to test.
"""

import re
from dataclasses import dataclass

SEVERITIES = {"low", "medium", "high"}


@dataclass
class Lookups:
    """The allowed values, loaded from the database's lookup tables."""
    region_ids: dict          # "East Asia"      -> 1
    type_ids: dict            # "Labour action"  -> 1
    type_descriptions: dict   # "Labour action"  -> "Strikes, walkouts, ..."
    country_regions: dict     # "US"             -> region_id of North America


class InvalidExtraction(ValueError):
    """Gemini's answer broke one of the rules (e.g. an unknown region)."""


def to_disruption_row(result, article_id, lookups, model_name):
    """
    Returns:
      None  -> Gemini says this article is NOT a disruption
      dict  -> a row ready to insert into `disruptions`
    Raises InvalidExtraction if the answer can't be used.
    """
    is_disruption = result.get("is_disruption")
    if not isinstance(is_disruption, bool):
        raise InvalidExtraction("is_disruption must be true or false")
    if not is_disruption:
        return None

    # --- severity and type must be from the fixed lists -------------------
    severity = result.get("severity")
    if severity not in SEVERITIES:
        raise InvalidExtraction(f"unknown severity: {severity!r}")

    type_name = result.get("disruption_type")
    if type_name not in lookups.type_ids:
        raise InvalidExtraction(f"unknown disruption type: {type_name!r}")

    # --- country (optional) and region -------------------------------------
    # An unknown country code is dropped rather than failing the article.
    country = (result.get("country_code") or "").strip().upper() or None
    if country not in lookups.country_regions:
        country = None

    if country:
        # When there is a country, its region comes from our countries table,
        # so region and country can never disagree.
        region_id = lookups.country_regions[country]
    else:
        region_name = result.get("region")
        if region_name not in lookups.region_ids:
            raise InvalidExtraction(f"unknown region: {region_name!r}")
        region_id = lookups.region_ids[region_name]

    # --- summary -----------------------------------------------------------
    summary = re.sub(r"\s+", " ", result.get("summary") or "").strip()
    if not summary:
        raise InvalidExtraction("summary is empty")

    return {
        "article_id": article_id,
        "region_id": region_id,
        "country_code": country,
        "disruption_type_id": lookups.type_ids[type_name],
        "severity": severity,
        "summary": summary[:500],
        "model_name": model_name,
    }
