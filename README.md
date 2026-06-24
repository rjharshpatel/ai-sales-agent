# AI Sales Data Analyst Agent

An autonomous pipeline that takes a raw daily sales CSV and produces cleaned
data, KPIs, AI-generated business insights, an interactive dashboard, and a
downloadable PDF report — with zero manual analysis steps.

**Live demo:** _(add your Streamlit Cloud URL here after deploying — Step 4 below)_

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
    - Claude API narrates the KPI summary, including detected anomalies
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
├── ai_insights.py           # Claude API call + rule-based fallback
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
your own CSV with these columns:

```
OrderDate, Product, Region, SalesRep, Quantity, UnitPrice, Revenue
```

To enable real AI insights instead of the rule-based fallback, either:
- paste your Anthropic API key into the sidebar field at runtime, or
- create `.streamlit/secrets.toml` (copy from the `.example` file) with
  `ANTHROPIC_API_KEY = "sk-ant-..."`

Get a key at [console.anthropic.com](https://console.anthropic.com).

## Deploy it live (Streamlit Community Cloud — free)

This is what makes it "live on anyone's device" — a public URL, no install
required for whoever you share it with.

**Step 1 — Push to GitHub**
```bash
cd ai-sales-agent
git init
git add .
git commit -m "AI Sales Data Analyst Agent"
git branch -M main
git remote add origin https://github.com/<your-username>/ai-sales-agent.git
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
laptop. Put this URL in your resume/portfolio and at the top of this README.

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
