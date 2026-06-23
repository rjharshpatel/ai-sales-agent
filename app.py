"""
app.py
-------
Streamlit entry point. Run locally with:
    streamlit run app.py

Deployed publicly via Streamlit Community Cloud — see README.md.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import smtplib
from email.message import EmailMessage
from pathlib import Path

from sales_engine import load_and_clean, calculate_kpis
from ai_insights import get_insights
from report_builder import build_pdf_report

st.set_page_config(page_title="AI Sales Data Analyst Agent", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Sidebar: data input + AI config
# ---------------------------------------------------------------------------
st.sidebar.title("📊 AI Sales Analyst Agent")
st.sidebar.markdown("Upload your daily sales CSV, or use the bundled demo data.")

uploaded_file = st.sidebar.file_uploader("Upload sales CSV", type=["csv"])
use_demo = st.sidebar.checkbox("Use demo dataset", value=uploaded_file is None)

st.sidebar.divider()
st.sidebar.subheader("AI Settings")
api_key_input = st.sidebar.text_input(
    "Anthropic API key (optional)",
    type="password",
    help="If left blank, the app uses Streamlit secrets, then falls back "
         "to rule-based insights automatically. Your key is never stored.",
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
data_source = None
if uploaded_file is not None and not use_demo:
    data_source = uploaded_file
elif use_demo:
    data_source = "data/sales_data.csv"

if data_source is None:
    st.info("⬅️ Upload a CSV or check 'Use demo dataset' in the sidebar to begin.")
    st.stop()

try:
    with st.spinner("Cleaning data..."):
        df, report = load_and_clean(data_source)
except ValueError as e:
    st.error(f"Could not process this file: {e}")
    st.caption("Required columns: OrderDate, Product, Region, SalesRep, Quantity, UnitPrice, Revenue")
    st.stop()

kpis = calculate_kpis(df)

# ---------------------------------------------------------------------------
# Header + cleaning report
# ---------------------------------------------------------------------------
st.title("AI Sales Data Analyst Agent")
st.caption("CSV → Clean → KPIs → AI Insights → Dashboard → PDF Report, fully automated.")

with st.expander(f"🧹 Data cleaning report — {report.rows_in} rows in, {report.rows_out} rows out"):
    c1, c2, c3 = st.columns(3)
    c1.metric("Duplicates removed", report.duplicates_removed)
    c2.metric("Date parse failures", report.date_parse_failures)
    c3.metric("Missing values filled", sum(report.missing_filled.values()))
    if report.missing_filled:
        st.caption(f"Filled by column: {report.missing_filled}")

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Revenue", f"{kpis['total_revenue']:,.0f}")
k2.metric("Total Orders", f"{kpis['total_orders']:,}")
k3.metric("Units Sold", f"{kpis['total_units']:,}")
k4.metric("Avg Order Value", f"{kpis['avg_order_value']:,.0f}")
growth = kpis.get("wow_growth_pct")
k5.metric("WoW Growth", f"{growth:+.1f}%" if growth is not None else "N/A",
          delta=f"{growth:+.1f}%" if growth is not None else None)

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    daily = pd.DataFrame(
        {"Date": list(kpis["daily_revenue"].keys()), "Revenue": list(kpis["daily_revenue"].values())}
    )
    daily["Date"] = pd.to_datetime(daily["Date"])
    fig_trend = px.line(daily, x="Date", y="Revenue", title="Daily Revenue Trend", markers=False)
    st.plotly_chart(fig_trend, use_container_width=True)

with chart_col2:
    prod_df = pd.DataFrame(
        {"Product": list(kpis["top_products"].keys()), "Revenue": list(kpis["top_products"].values())}
    )
    fig_prod = px.bar(prod_df, x="Product", y="Revenue", title="Top Products by Revenue")
    st.plotly_chart(fig_prod, use_container_width=True)

chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    region_df = pd.DataFrame(
        {"Region": list(kpis["by_region"].keys()), "Revenue": list(kpis["by_region"].values())}
    )
    fig_region = px.pie(region_df, names="Region", values="Revenue", title="Revenue Share by Region")
    st.plotly_chart(fig_region, use_container_width=True)

with chart_col4:
    rep_df = pd.DataFrame(
        {"SalesRep": list(kpis["by_rep"].keys()), "Revenue": list(kpis["by_rep"].values())}
    )
    fig_rep = px.bar(rep_df, x="SalesRep", y="Revenue", title="Revenue by Sales Rep", orientation="v")
    st.plotly_chart(fig_rep, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# AI Insights
# ---------------------------------------------------------------------------
st.subheader("🤖 AI-Generated Insights")

def _get_secret(key_name):
    try:
        return st.secrets.get(key_name, None)
    except Exception:
        return None

effective_key = api_key_input or _get_secret("ANTHROPIC_API_KEY")

with st.spinner("Generating insights..."):
    insights = get_insights(kpis, api_key=effective_key)

source_label = "✅ Claude AI" if insights["source"] == "ai" else "ℹ️ Rule-based (no API key configured)"
st.caption(f"Insight source: {source_label}")
st.text(insights["text"])

st.divider()

# ---------------------------------------------------------------------------
# Export: PDF + Email
# ---------------------------------------------------------------------------
st.subheader("📤 Export Report")

export_col1, export_col2 = st.columns(2)

with export_col1:
    if st.button("Generate PDF Report", type="primary"):
        Path("outputs").mkdir(exist_ok=True)
        pdf_path = build_pdf_report(kpis, insights)
        with open(pdf_path, "rb") as f:
            st.session_state["pdf_bytes"] = f.read()
        st.success("PDF generated below ⬇️")

    if "pdf_bytes" in st.session_state:
        st.download_button(
            "⬇️ Download PDF Report",
            data=st.session_state["pdf_bytes"],
            file_name="sales_report.pdf",
            mime="application/pdf",
        )

with export_col2:
    with st.expander("📧 Email this report"):
        st.caption(
            "Requires SMTP credentials in Streamlit secrets "
            "(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD). "
            "See README for setup."
        )
        recipient = st.text_input("Recipient email")
        if st.button("Send Email"):
            if "pdf_bytes" not in st.session_state:
                st.warning("Generate the PDF first.")
            elif not recipient:
                st.warning("Enter a recipient email address.")
            else:
                try:
                    smtp_host = st.secrets["SMTP_HOST"]
                    smtp_port = int(st.secrets["SMTP_PORT"])
                    smtp_user = st.secrets["SMTP_USER"]
                    smtp_password = st.secrets["SMTP_PASSWORD"]

                    msg = EmailMessage()
                    msg["Subject"] = "Automated Sales Report"
                    msg["From"] = smtp_user
                    msg["To"] = recipient
                    msg.set_content("Attached is your automated sales report.")
                    msg.add_attachment(
                        st.session_state["pdf_bytes"],
                        maintype="application",
                        subtype="pdf",
                        filename="sales_report.pdf",
                    )

                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_password)
                        server.send_message(msg)

                    st.success(f"Report emailed to {recipient}")
                except Exception as e:
                    if isinstance(e, KeyError) or "secret" in str(e).lower():
                        st.error("SMTP credentials not configured in Streamlit secrets.")
                    else:
                        st.error(f"Email failed: {e}")

st.divider()
st.caption("Built with Python, pandas, Streamlit, Plotly, and Claude AI.")
