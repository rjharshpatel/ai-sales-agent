"""
ai_insights.py
---------------
Turns a KPI dict (numbers only) into a narrative business insight.

DESIGN PRINCIPLE: the LLM never sees raw transaction rows. It only
sees the already-computed KPI summary. This is both cheaper (small
prompt) and more reliable (the LLM explains numbers pandas already
verified, instead of trying to "calculate" from a wall of CSV text).

Two paths:
  1. generate_ai_insights()   -> calls Claude API
  2. generate_fallback_insights() -> rule-based, zero dependencies,
     used automatically if no ANTHROPIC_API_KEY is configured or
     the API call fails for any reason. This keeps a public demo
     from ever showing a broken screen.
"""

import os
import json


def _format_kpi_prompt(kpis: dict) -> str:
    """Builds a compact, numbers-only prompt. No raw data, just the
    aggregates — this is what keeps token cost low and output reliable."""
    return f"""You are a sales data analyst. Based ONLY on the KPI data below,
write a concise business insight report. Do not invent numbers not given here.

KPI DATA:
{json.dumps(kpis, indent=2, default=str)}

Write your response in exactly this structure, using plain text (no markdown headers):

SUMMARY: (2 sentences on overall performance)
KEY WINS: (2 bullet points, each starting with "- ")
AREAS OF CONCERN: (2 bullet points, each starting with "- ")
RECOMMENDATION: (1-2 sentences, actionable, specific to the data shown)
"""


def generate_ai_insights(kpis: dict, api_key: str | None = None) -> dict:
    """
    Calls Claude API (claude-haiku-4-5) to generate narrative insights.
    Returns {"source": "ai", "text": "..."} on success.
    Raises on failure — caller is expected to catch and fall back.
    """
    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("No API key configured")

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": _format_kpi_prompt(kpis)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return {"source": "ai", "text": text.strip()}


def generate_fallback_insights(kpis: dict) -> dict:
    """
    Rule-based insight generator. No API, no network, no cost.
    Mirrors the same SUMMARY / KEY WINS / CONCERNS / RECOMMENDATION
    structure so the dashboard rendering code doesn't need branching logic.
    Now references real statistical anomalies and trend direction, not
    just static top/bottom rankings.
    """
    growth = kpis.get("wow_growth_pct")
    trend = kpis.get("trend_pct_per_day")
    anomalies = kpis.get("anomalies", [])
    top_products = kpis.get("top_products", {})
    by_region = kpis.get("by_region", {})

    top_product_name = next(iter(top_products), "N/A")
    top_region_name = next(iter(by_region), "N/A")
    # Exclude "Unknown" (imputed missing-data bucket) from actionable
    # recommendations — it's a data quality artifact, not a real region
    # to deprioritize.
    actionable_regions = {k: v for k, v in by_region.items() if k != "Unknown"}
    weakest_region = list(actionable_regions.items())[-1] if actionable_regions else ("N/A", 0)

    growth_line = (
        f"Revenue moved {growth:+.1f}% week-over-week."
        if growth is not None else
        "Not enough weekly history yet to calculate week-over-week growth."
    )
    trend_line = ""
    if trend is not None:
        direction = "trending up" if trend > 0.05 else "trending down" if trend < -0.05 else "roughly flat"
        trend_line = f" The overall daily trend is {direction} ({trend:+.2f}%/day)."

    summary = (
        f"Total revenue across the period was {kpis.get('total_revenue', 0):,.2f} "
        f"from {kpis.get('total_orders', 0):,} orders. {growth_line}{trend_line}"
    )

    key_wins = [
        f"- {top_product_name} is the top-performing product by revenue.",
        f"- {top_region_name} is the strongest performing region.",
    ]

    concerns = [
        f"- {weakest_region[0]} region is trailing the others in total revenue.",
    ]
    if anomalies:
        spike_days = [a for a in anomalies if a["direction"] == "spike"]
        drop_days = [a for a in anomalies if a["direction"] == "drop"]
        if drop_days:
            worst = min(drop_days, key=lambda a: a["z_score"])
            concerns.append(
                f"- Unusual revenue drop detected on {worst['date']} "
                f"({worst['revenue']:,.2f}, {abs(worst['z_score']):.1f} std dev below normal) — worth investigating."
            )
        if spike_days:
            best = max(spike_days, key=lambda a: a["z_score"])
            key_wins.append(
                f"- Notable revenue spike on {best['date']} ({best['revenue']:,.2f}, "
                f"{best['z_score']:.1f} std dev above normal)."
            )
    else:
        concerns.append(
            f"- Average order value is {kpis.get('avg_order_value', 0):,.2f}; "
            f"watch for declines if this trends down over time."
        )

    recommendation = (
        f"Consider reallocating marketing or staffing focus toward {weakest_region[0]} "
        f"region, and investigate what's driving {top_product_name}'s performance to "
        f"replicate it across other product lines."
    )
    if anomalies:
        recommendation += " Review the flagged anomaly date(s) above for a root cause before adjusting strategy."

    text = (
        f"SUMMARY: {summary}\n\n"
        f"KEY WINS:\n" + "\n".join(key_wins) + "\n\n"
        f"AREAS OF CONCERN:\n" + "\n".join(concerns) + "\n\n"
        f"RECOMMENDATION: {recommendation}"
    )
    return {"source": "rule-based", "text": text}


def get_insights(kpis: dict, api_key: str | None = None) -> dict:
    """
    Single entry point the dashboard calls. Tries AI first, falls back
    silently on any failure (missing key, network error, rate limit, etc.)
    so the live demo is never one API hiccup away from looking broken.
    """
    try:
        return generate_ai_insights(kpis, api_key=api_key)
    except Exception:
        return generate_fallback_insights(kpis)
