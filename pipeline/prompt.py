"""
The instructions and output format given to Gemini — kept in one file so
the "rules" the AI follows are easy to read, review and change.

The allowed regions and disruption types are NOT typed here: they are read
from the database's lookup tables, so the AI can only answer with values
the database accepts.
"""

# ---------------------------------------------------------------------
# What counts as a disruption, and how severe it is.
# ⚠ These definitions are the project's working rules (the PRD only names
#   the three severity levels). Adjust them here if you want different rules.
# ---------------------------------------------------------------------

DISRUPTION_RULES = """\
A REAL disruption signal is an actual, ongoing, or officially announced event that
disrupts or directly threatens the flow of goods, materials, or freight. Examples:
port or transport strikes, factory shutdowns, closed or restricted shipping routes,
new tariffs or export controls taking effect, severe weather hitting ports or
transport, shortages of a material or component.

NOT a disruption signal: market or stock commentary, company earnings, opinion
pieces without a concrete event, general politics without a concrete trade or
supply impact, product deals or advertisements, speculation about something that
has not happened or been announced.
"""

SEVERITY_RULES = """\
- low:    limited or local impact, or a credible threat that has not started yet
- medium: active disruption causing delays or higher costs in one country or industry
- high:   major disruption halting a key port, route, or supply source, or affecting
          several countries or a whole industry
"""


def build_system_instruction(lookups):
    """The fixed instructions sent with every batch of articles."""
    type_lines = "\n".join(f"- {name}: {description}"
                           for name, description in lookups.type_descriptions.items())
    region_list = ", ".join(lookups.region_ids)

    return f"""\
You analyse news articles for a supply chain disruption monitor.
You will receive several articles, each starting with its article_id.
Judge every article separately and return exactly ONE result per article,
with the same article_id. Never mix information between articles.
You only see each headline and a short description. Base every answer strictly
on that text. Do not guess facts that are not stated.

Step 1 - decide is_disruption.
{DISRUPTION_RULES}
If is_disruption is false, set every other field to null.

Step 2 - if is_disruption is true, fill in:
- region: the region where the disruption happens. One of: {region_list}.
  Use "Global" only if it is worldwide or spans several regions with no main one.
- country_code: ISO 3166-1 alpha-2 code (e.g. "US", "CN") of the single main
  affected country, or null if there is no single country (e.g. a sea route).
- disruption_type: exactly one of:
{type_lines}
- severity:
{SEVERITY_RULES}
- summary: ONE plain-English sentence (max 30 words) saying what is disrupted,
  where, and why. Facts from the article only.
"""


def build_user_message(articles):
    """All articles of one batch, each labelled with its database article_id."""
    blocks = []
    for article in articles:
        blocks.append(f"article_id: {article['article_id']}\n"
                      f"Headline: {article['title']}\n"
                      f"Source: {article.get('source_name') or 'unknown'}\n"
                      f"Published: {article['published_at']}\n"
                      f"Description: {article.get('description') or '(none)'}")
    return "\n\n---\n\n".join(blocks)


def build_response_schema(lookups):
    """
    The exact JSON shape Gemini must return: {"results": [ one object per article ]}.
    "enum" limits a field to a fixed list, so Gemini cannot invent a region,
    type, or severity. article_id links each result back to its article.
    """
    one_result = {
        "type": "OBJECT",
        "properties": {
            "article_id":      {"type": "INTEGER"},
            "is_disruption":   {"type": "BOOLEAN"},
            "region":          {"type": "STRING", "nullable": True,
                                "enum": list(lookups.region_ids)},
            "country_code":    {"type": "STRING", "nullable": True,
                                "description": "ISO 3166-1 alpha-2 code, e.g. US"},
            "disruption_type": {"type": "STRING", "nullable": True,
                                "enum": list(lookups.type_ids)},
            "severity":        {"type": "STRING", "nullable": True,
                                "enum": ["low", "medium", "high"]},
            "summary":         {"type": "STRING", "nullable": True},
        },
        "required": ["article_id", "is_disruption", "region", "country_code",
                     "disruption_type", "severity", "summary"],
        "propertyOrdering": ["article_id", "is_disruption", "region", "country_code",
                             "disruption_type", "severity", "summary"],
    }
    return {
        "type": "OBJECT",
        "properties": {"results": {"type": "ARRAY", "items": one_result}},
        "required": ["results"],
    }
