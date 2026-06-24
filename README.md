# AI Sales Data Analyst Agent

**Built by Harsh Raj**

An autonomous pipeline that takes a raw daily sales CSV and produces cleaned
data, KPIs, AI-generated business insights, an interactive dashboard, and a
downloadable PDF report — with zero manual analysis steps.

**Live demo:** [ai-sales-agent-gytf7zieaa8xczwcxkguwh.streamlit.app](https://ai-sales-agent-gytf7zieaa8xczwcxkguwh.streamlit.app/)
**Source:** [github.com/rjharshpatel/ai-sales-agent](https://github.com/rjharshpatel/ai-sales-agent)

## Architecture

```
CSV Upload (any schema)
    │
    ▼
Schema Auto-Detection (schema_mapper.py)
    - matches synonyms (Date/OrderDate/Transaction Date → OrderDate)
    - derives Revenue from Quantity × UnitPrice if not present
    - falls back to an interactive manual-mapping form if unsure
    │
    ▼
Python ETL & Cleaning (sales_engine.py)
    - mixed date format parsing (7+ formats tried)
    - duplicate removal
    - product-level median imputation for missing values
    │
    ▼
KPI + Anomaly Calculation (sales_engine.py)
    - revenue, growth %, linear trend slope, top products, regional/rep breakdown
    - statistical anomaly detection (z-score > 2 on daily revenue)
    │
    ▼
Interactive Filters (app.py)
    - date range / region / product filters apply to every metric, chart,
      and the AI insight text below — not just the charts
    │
    ▼
AI Insight Generation (ai_insights.py)
    - The AI provider narrates the KPI summary, including detected anomalies
    - Rule-based fallback if no API key / call fails (demo never breaks)
    │
    ▼
Dashboard (app.py — Streamlit + Plotly) + Drill-Down table
    │
    ▼
PDF Report (report_builder.py — fpdf2) + optional Email (smtplib)
```

**Key design decisions:**
- The AI model never sees raw transaction rows — only the already-computed
  KPI dict. pandas computes; the AI explains.
- Column names are auto-detected via synonym matching rather than hardcoded,
  so the app works with CSVs from different sources/companies, not just the
  exact demo schema.
- Anomalies are detected statistically (z-score), not just "lowest day" —
  this surfaces genuinely unusual events rather than restating rankings.

## Project structure

```
ai-sales-agent/
├── app.py                  # Streamlit dashboard (main entry point)
├── sales_engine.py          # ETL, cleaning, KPI + anomaly calculation (no UI deps)
├── schema_mapper.py         # Flexible column auto-detection for any sales CSV
├── ai_insights.py           # AI API call + rule-based fallback
├── report_builder.py        # PDF generation (Unicode-safe)
├── generate_sample_data.py  # Creates the bundled demo dataset
├── data/sales_data.csv      # Demo dataset (generated)
├── requirements.txt
├── .streamlit/
│   └── secrets.toml.example # Template — copy to secrets.toml, fill in, don't commit
└── outputs/                 # Generated PDFs land here (gitignored)
```

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the URL it prints (usually `http://localhost:8501`). Check
**"Use demo dataset"** in the sidebar to see it work immediately, or upload
your own sales CSV.

Columns are **auto-detected** — names like `Date`, `Transaction Date`, or
`Order Date` are all recognized as the order date, and similar synonym
matching applies to product, region, sales rep, quantity, and price columns.
If `Revenue` isn't present, it's calculated automatically as
`Quantity × UnitPrice`. If a column genuinely can't be identified, the app
shows a short form asking you to pick the matching column manually — it
won't just fail.

To enable real AI insights instead of the rule-based fallback, either:
- paste your AI provider's API key into the sidebar field at runtime, or
- create `.streamlit/secrets.toml` (copy from the `.example` file) with
  `ANTHROPIC_API_KEY = "your-key-here"`

(The code currently calls the Anthropic API — get a key at
[console.anthropic.com](https://console.anthropic.com) — but `ai_insights.py`
is a self-contained module, so you can swap it for any other provider's API
without touching the rest of the app.)

## Deploy it live (Streamlit Community Cloud — free)

This is what makes it "live on anyone's device" — a public URL, no install
required for whoever you share it with.

### First-time deployment

**Step 1 — Push to GitHub**
```bash
cd ai-sales-agent
git init
git add .
git commit -m "AI Sales Data Analyst Agent"
git branch -M main
git remote add origin https://github.com/rjharshpatel/ai-sales-agent.git
git push -u origin main
```
(`.gitignore` already excludes secrets and generated PDFs — don't remove that.)

**Step 2 — Create the app**
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **"New app"**, pick your repo, branch `main`, main file `app.py`.
3. Click **Deploy**.

**Step 3 — Add secrets (so the live app uses real AI, not just fallback)**
1. In the app dashboard, open **Settings → Secrets**.
2. Paste the contents of your local `secrets.toml` (your real API key, not
   the `.example` placeholder).
3. Save — the app restarts automatically with the new secrets.

**Step 4 — Share the link**
Streamlit gives you a URL like `https://your-app-name.streamlit.app`. Anyone
with that link gets the live app — no Python, no install, works on phone or
laptop.

### Updating an already-deployed app

Once deployed, you don't repeat any of the steps above. Just push new
commits — Streamlit Cloud watches the repo and auto-redeploys within about
a minute:
```bash
git add .
git commit -m "describe what changed"
git push
```
If `git push` is rejected with "fetch first," someone (or Streamlit's own
devcontainer setup) added something to the GitHub repo that your local copy
doesn't have yet. Run `git pull --no-edit` to merge it in, then `git push`
again — this is normal and doesn't lose any of your changes.

To confirm the update went live, refresh the app URL and check for whatever
changed, or open [share.streamlit.io](https://share.streamlit.io), select
the app, and check its log panel for "Updating..." → "Running".

## Email feature (optional)

The in-app "Email this report" button needs SMTP credentials in secrets:
```toml
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USER = "youremail@gmail.com"
SMTP_PASSWORD = "your-gmail-app-password"   # not your normal password
```
For Gmail, generate an **App Password** under Google Account → Security →
2-Step Verification → App Passwords (regular passwords are blocked by Google
for SMTP since 2022).

## What this project demonstrates (for your resume / interviews)

- **Data engineering**: defensive ETL handling real-world messiness (mixed
  date formats, duplicates, missing values) with a documented, auditable
  cleaning report rather than silent fixes.
- **Analytics**: KPI design (WoW growth, AOV, segment breakdowns) using
  pandas groupby/aggregation.
- **AI integration**: a deliberate pattern — LLM explains pre-computed
  numbers rather than doing arithmetic itself — plus a fallback path so a
  public demo has no single point of failure.
- **Full-stack delivery**: from raw file to a deployed, shareable web app,
  including automated report generation and email delivery.

## Extending this project

Ideas if you want to keep building once this works:
- Swap the CSV upload for a live database connection (this would pair
  naturally with your MySQL/Power BI ER project — same `STR_TO_DATE`-style
  date handling skills apply).
- Add a scheduled job (e.g. GitHub Actions cron) that runs the pipeline daily
  against a fixed data source and emails the report automatically — true
  "automation" rather than on-demand.
- Add authentication (Streamlit supports `streamlit-authenticator`) if you
  want to gate access before sharing the link publicly.

---

**Author:** Harsh Raj
This project was built as part of an ongoing portfolio focused on data
analytics, automation, and AI integration — alongside a parallel Hospital ER
analytics project (MySQL + Power BI).
