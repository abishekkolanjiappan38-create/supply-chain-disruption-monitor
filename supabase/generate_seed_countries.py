"""
Generates supabase/seed_countries.sql from two public data files,
so no country code or map ID is ever typed by hand.

Sources (pinned versions, so the output is always the same):
  1. MAP    - world-atlas 2.0.2, countries-110m.json
              The exact file the dashboard's world map draws. Each country
              shape has an "id" (ISO numeric code, e.g. "840") and a "name".
  2. ISO    - lukes/ISO-3166-Countries-with-Regional-Codes 10.0
              Official ISO 3166 list: numeric code -> 2-letter code ("US"),
              plus the United Nations region/sub-region of each country.

Run it (from the project folder):
    python supabase/generate_seed_countries.py
"""

import json
import urllib.request
from pathlib import Path

MAP_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json"
ISO_URL = ("https://cdn.jsdelivr.net/gh/lukes/"
           "ISO-3166-Countries-with-Regional-Codes@10.0/all/all.json")
OUTPUT = Path(__file__).parent / "seed_countries.sql"

# --- Region rule (decision D4 in DATA_MODEL.md) ---------------------------
# Start from the UN sub-region of each country, mapped to our 8 regions...
SUBREGION_TO_REGION = {
    "Eastern Asia": "East Asia",
    "South-eastern Asia": "East Asia",        # v2 puts Vietnam, Thailand here
    "Southern Asia": "South Asia",
    "Central Asia": "South Asia",
    "Western Asia": "Middle East",
    "Northern Europe": "Europe",
    "Western Europe": "Europe",
    "Southern Europe": "Europe",
    "Eastern Europe": "Europe",
    "Northern America": "North America",
    "Latin America and the Caribbean": "Latin America",
    "Northern Africa": "Africa & Oceania",
    "Sub-Saharan Africa": "Africa & Oceania",
    "Australia and New Zealand": "Africa & Oceania",
    "Melanesia": "Africa & Oceania",
    "Micronesia": "Africa & Oceania",
    "Polynesia": "Africa & Oceania",
}
# ...then these named exceptions win.
OVERRIDES = {
    "EG": "Middle East",     # v2 prototype: Egypt (Suez) grouped with Middle East
    "MX": "North America",   # v2 prototype: Mexico grouped with North America
    "IR": "Middle East",     # UN lists Iran under Southern Asia; grouped with Middle East
    "TW": "East Asia",       # ISO list gives Taiwan no UN region
}
SKIP = {"AQ"}                # Antarctica: on the map, but not a supply chain location


def download(url):
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def sql_text(value):
    """Wrap text in single quotes for SQL; a ' inside becomes ''."""
    return "'" + value.replace("'", "''") + "'"


def main():
    shapes = download(MAP_URL)["objects"]["countries"]["geometries"]
    iso_by_numeric = {row["country-code"]: row for row in download(ISO_URL)}

    rows, no_id, skipped = [], [], []
    for shape in shapes:
        map_name = shape["properties"]["name"]
        map_id = shape.get("id")
        if not map_id:                       # shape has no ISO code at all
            no_id.append(map_name)
            continue
        iso = iso_by_numeric[map_id]         # fails loudly if a code is unknown
        code = iso["alpha-2"]
        if code in SKIP:
            skipped.append(map_name)
            continue
        region = OVERRIDES.get(code) or SUBREGION_TO_REGION[iso["sub-region"]]
        rows.append((region, map_name, code, map_id))

    rows.sort()
    region_order = list(dict.fromkeys(SUBREGION_TO_REGION.values()))

    lines = [
        "-- =====================================================================",
        "-- Country list for the world map  (GENERATED - do not edit by hand)",
        "-- Made by supabase/generate_seed_countries.py from:",
        f"--   map shapes : {MAP_URL}",
        f"--   ISO codes  : {ISO_URL}",
        "-- Run AFTER schema.sql (it needs the regions table to be filled).",
        "--",
        f"-- {len(rows)} countries. Not included:",
        f"--   no ISO code on the map (stay grey): {', '.join(sorted(no_id))}",
        f"--   skipped: {', '.join(skipped)}",
        "-- =====================================================================",
        "",
        "insert into countries (country_code, name, map_id, region_id)",
        "select v.country_code, v.name, v.map_id, r.region_id",
        "from (values",
    ]
    values = []
    for region in region_order:
        group = [r for r in rows if r[0] == region]
        if not group:
            continue
        values.append(f"    -- {region} ({len(group)})")
        for reg, name, code, map_id in group:
            values.append(f"    ({sql_text(code)}, {sql_text(name)}, "
                          f"{sql_text(map_id)}, {sql_text(reg)}),")
    values[-1] = values[-1].rstrip(",")      # last row: no trailing comma
    lines += values
    lines += [
        ") as v (country_code, name, map_id, region_name)",
        "join regions r on r.name = v.region_name;",
        "",
        "-- Check: the join above silently drops a row whose region name has no match,",
        f"-- so this should return {len(rows)}:",
        "--   select count(*) from countries;",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {OUTPUT} with {len(rows)} countries")
    for region in region_order:
        print(f"  {region:<17} {sum(1 for r in rows if r[0] == region)}")
    print("No ISO code (not included):", ", ".join(sorted(no_id)))
    print("Skipped:", ", ".join(skipped))


if __name__ == "__main__":
    main()
