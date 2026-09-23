# Project Requirements Document
## AI-Powered Supply Chain Risk & Disruption Monitor

**Author:** Abishek Kolanjiappan
**Purpose:** Portfolio project for supply chain analyst job search (target roles: Supply Chain Analyst, Demand Planner, Inventory Planner, Business/Operations Analyst)
**Built with:** Claude Code (author has no prior Python experience — code should be clean, well-commented, and explained step by step so the author can understand and defend it in interviews)

---

## 1. Project Objective

Build a tool that monitors news for supply chain disruption signals (port strikes, tariffs, shipping delays, supplier shortages, weather events, geopolitical incidents), uses an LLM to extract structured risk data from each article, stores the results over time, and visualizes disruption trends by region and category on a live website.

This is a **standalone project**, separate from the author's existing Power BI demand forecasting dashboard and SQL project. No overlap in dataset or purpose — this project demonstrates applied GenAI on unstructured text data, not structured tabular analytics.

---

## 2. Success Criteria

- A working pipeline that pulls real news articles and extracts structured risk data via an LLM API
- At least 2–4 weeks of accumulated data showing real trends (not a one-time snapshot)
- A live, deployed website showing risk by region/category over time
- 2–3 genuine, defensible findings/insights the author can discuss in an interview
- A GitHub repo with a clear README (overview, process, findings, what's next)
- Author understands every major step well enough to explain it without referring to notes

---

## 3. Scope

### In scope
- Pulling news articles via a free news API, filtered by supply-chain-relevant keywords
- LLM-based structured extraction: region, disruption type, severity, one-line summary
- Persistent storage of extracted results (SQLite or a free hosted DB like Supabase)
- Scheduled/repeated runs to accumulate data over time
- A fully interactive website with live API integration, deployed on Vercel
- A GitHub README write-up with findings

### Out of scope
- Real-time/streaming ingestion (batch runs are sufficient)
- Predictive modeling or forecasting (this is a monitoring/extraction tool, not a forecast)
- Paid API tiers — everything should run on free tiers
- Native mobile app

---

## 4. Functional Requirements

1. **News ingestion**
   - Query a news API (NewsAPI.org free tier) using a defined keyword list (e.g., "port strike," "shipping delay," "tariff," "supplier shortage," plus optional industry-specific terms)
   - Capture: headline, source, publish date, article snippet/URL

2. **LLM extraction**
   - Send each article to the Google Gemini API with a structured prompt
   - Extract: affected region, disruption type, severity (low/medium/high), one-sentence plain-English summary
   - Output must be returned as clean, parseable JSON
   - Handle articles that don't contain a real disruption signal (should be flagged/skipped, not forced into a false extraction)

3. **Storage**
   - Store each extracted record with a timestamp in SQLite or a free hosted database (e.g., Supabase)
   - Schema: `date, region, disruption_type, severity, summary, source_url`

4. **Automation**
   - Pipeline runs on a schedule (daily or every few days) via Vercel Cron Jobs, so data accumulates over multiple weeks
   - Should avoid duplicate entries on re-runs (basic dedupe by URL or headline)

5. **Website / Visualization**
   - Live, deployed website (not a static export) showing: disruption count by region, disruption count by type, severity trend over time, and a live feed of recent flagged articles
   - See Section 6 (UI/UX Requirements) for detailed layout and design direction

6. **Documentation**
   - Inline code comments explaining each step in plain language
   - A GitHub README following this structure: Overview → My Process → Key Findings → What I'd Do Next

---

## 5. Non-Functional Requirements

- **Cost:** must run entirely on free-tier API access (NewsAPI free tier, Gemini free tier, Vercel free tier)
- **Simplicity over scale:** favor readable, well-commented code over optimized/production-grade architecture
- **Explainability:** author must be able to walk through the logic of each script unassisted — Claude Code should explain design decisions as it builds, not just output code silently
- **Security:** API keys must never be hardcoded or committed to GitHub — use `.env` + `.gitignore`, and Vercel environment variables in production

---

## 6. UI/UX Requirements

**Design goal:** the insight should be obvious within 5 seconds of landing on the page — this is a portfolio piece a recruiter or interviewer may actually open, not an internal tool.

**Layout:**
- **Top:** a headline stat banner (e.g., "14 active disruptions tracked across 6 regions") plus a "last updated" timestamp, so it's clear the data is live, not a static snapshot
- **Upper section:** a region map or region list, color-coded by current risk level (green = low, yellow = medium, red = high)
- **Middle section:** a trend chart of disruption mentions over time, filterable by region and/or disruption type
- **Lower section / side panel:** a live feed of the most recently flagged articles, each showing its extracted summary, severity tag, and a link to the source — this is what proves the AI extraction is real and working, not just a chart of pre-baked numbers

**Visual style:**
- Dark, data-dashboard aesthetic (dark background, high-contrast accent colors) — reads as a professional monitoring/analytics tool
- Severity color-coding must stay **consistent everywhere** (map, chart, and feed all use the same red/yellow/green scheme)
- Clean, modern typography — avoid default unstyled HTML look

**Suggested implementation:**
- Next.js + Tailwind CSS + shadcn/ui component library (pairs well with Vercel deployment, gives a polished look without needing custom design skills)
- Responsive layout — should be presentable on both desktop and mobile, since a recruiter may open the link on their phone

---

## 7. Suggested Tech Stack

| Component | Tool |
|---|---|
| Backend language | Python (data pipeline) |
| Frontend | Next.js + Tailwind CSS + shadcn/ui |
| News source | NewsAPI.org (free tier) |
| LLM | Google Gemini API (free tier, e.g. Gemini 1.5/2.0 Flash) |
| Storage | SQLite or Supabase (free tier) |
| Hosting | Vercel (frontend + serverless functions + cron jobs) |
| Version control | GitHub |

---

## 8. Reference Sources Needed

Claude Code should pull current documentation from these sources while building — do not rely on memorized knowledge, as API details change:

- **NewsAPI.org** — https://newsapi.org/docs — endpoint structure, query parameters, free-tier rate limits
- **Google AI Studio / Gemini API docs** — https://ai.google.dev/gemini-api/docs — authentication, request format, JSON output mode, free-tier rate limits
- **Python `requests` library docs** — https://requests.readthedocs.io
- **Supabase docs** (if used instead of local SQLite) — https://supabase.com/docs
- **Next.js documentation** — https://nextjs.org/docs
- **Tailwind CSS documentation** — https://tailwindcss.com/docs
- **shadcn/ui documentation** — https://ui.shadcn.com
- **Vercel documentation** — https://vercel.com/docs — deployment, environment variables, Cron Jobs

---

## 9. Milestones

| Milestone | Deliverable |
|---|---|
| 1 | Working news-pulling script returning raw article data |
| 2 | Gemini prompt tested and reliably returning structured JSON on sample articles |
| 3 | Full pipeline run on 30–50 articles, stored in database |
| 4 | Automated to run on a schedule via Vercel Cron; data accumulating |
| 5 | Website built and deployed on Vercel, matching UI/UX requirements in Section 6 |
| 6 | README written with findings; pushed to GitHub |

---

## 10. Open Questions for Claude Code to Ask the Author Before Starting

- Which industry/niche to focus keywords on (electronics, apparel, general/broad)?
- SQLite (simple, local) or Supabase (hosted, needed if the live site reads data directly)?
- Preferred local environment (VS Code, terminal, OS)?
- Any existing GitHub repo/Vercel account already set up, or starting fresh?
