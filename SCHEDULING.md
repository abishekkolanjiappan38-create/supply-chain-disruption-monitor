# Scheduling — the daily automatic run

The pipeline runs **once a day on GitHub's servers**, so data accumulates
whether or not your computer is on. Nothing is deployed; the dashboard and
database are untouched by this.

| | |
|---|---|
| What runs | `python -m pipeline.run_pipeline` — fetch news → remove duplicates → Gemini → save |
| When | Every day at **06:17 UTC** (11:47 AM IST). GitHub may start it up to ~30 minutes late |
| Where | GitHub Actions, free tier (2,000 minutes/month; this uses about 90) |
| Defined in | [`.github/workflows/daily-pipeline.yml`](.github/workflows/daily-pipeline.yml) |
| Typical cost per run | ~6 NewsAPI requests (of 100/day), 1–5 Gemini requests, 1–3 minutes |

---

## One-time setup

### 1. Create the GitHub repository

In PowerShell, from the project folder:

```powershell
git init
git add .
git commit -m "Supply chain disruption monitor: pipeline, database, dashboard"
gh auth login                      # opens your browser; sign in to GitHub
gh repo create supply-chain-disruption-monitor --public --source . --push
```

`git status` before committing should **not** list `.env`. It is in
`.gitignore`, together with `.venv/` and `__pycache__/`.

> `web/config.js` **is** committed. It holds the Supabase project URL and the
> *publishable* key, which can only read (Row Level Security blocks writes —
> tested: a write attempt returns HTTP 401).

### 2. Add the four secrets

GitHub repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Add these, copying each value from your local `.env`:

| Secret name | Value |
|---|---|
| `NEWSAPI_KEY` | NewsAPI key |
| `SUPABASE_URL` | `https://xxxx.supabase.co` |
| `SUPABASE_SECRET_KEY` | The Supabase **secret** key (`sb_secret_…`) |
| `GEMINI_API_KEY` | Google AI Studio key |

Names must match exactly. Secrets are write-only: GitHub never shows them
again, and masks them in logs. `SUPABASE_PUBLISHABLE_KEY` is **not** needed
here — it is only used to build `web/config.js` locally.

### 3. Test it by hand before trusting the schedule

Repo → **Actions** tab → **Daily pipeline** → **Run workflow**.
Watch the log; it should end with a line like:

```
Pipeline run 6 finished: success (31 fetched, 4 new, 1 disruptions found)
```

---

## Everyday use

- **See past runs:** the **Actions** tab lists every run, green or red, with full logs.
- **Failures:** a failed run turns red and GitHub emails you. The reason is also
  stored in the database: `select * from pipeline_runs order by run_id desc limit 5;`
- **Run it now:** the **Run workflow** button (same as step 3).
- **Change the time:** edit the `cron:` line in the workflow file. It is
  `minute hour day month weekday`, always in **UTC**. IST is UTC + 5:30, so
  `17 6 * * *` = 11:47 AM IST. Commit the change to apply it.
- **Pause collection:** Actions tab → **Daily pipeline** → the `…` menu →
  **Disable workflow**.

---

## Things to know

- **A quiet repo stops the schedule.** GitHub disables scheduled workflows after
  **60 days with no commits**. It emails you first, and the Enable button brings
  it back. For a 2–4 week collection this will not bite, but it matters if you
  leave the project running for months.
- **Timing is approximate.** Scheduled jobs are queued; a few minutes to half an
  hour late is normal. Fine for a daily job.
- **A missed day is not a hole.** Each run looks back 3 days and drops
  duplicates, so a skipped run is picked up by the next one.
- **Gemini's free quota** is the usual reason for a partial run. Articles that
  don't get processed stay `pending` and are picked up the next day.
- **NewsAPI's free plan is licensed for development only.** Running it daily
  from the cloud stretches that, and publishing the results publicly goes
  beyond it. Decide before the dashboard goes live: change news source, or
  document the limitation.

---

## Later: moving the schedule to Vercel

The PRD suggests Vercel Cron. Nothing here blocks that: when the dashboard is
deployed, the same `run_pipeline` entry point can be called by a Vercel cron
job instead, and this workflow can be disabled. Vercel's free plan allows one
run per day with a 5-minute limit, so the job must stay short.
