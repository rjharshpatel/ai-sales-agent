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

from sales_engine import load_and_clean, calculate_kpis, SchemaResolutionNeeded
from ai_insights import get_insights
from report_builder import build_pdf_report
from schema_mapper import CANONICAL_FIELDS

st.set_page_config(page_title="AI Sales Data Analyst Agent", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Sidebar: data input + AI config
# ---------------------------------------------------------------------------
st.sidebar.title("📊 AI Sales Analyst Agent")
st.sidebar.markdown("Upload **any** daily sales CSV — columns are auto-detected — or use the bundled demo data.")

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

manual_mapping = st.session_state.get("manual_mapping")

try:
    with st.spinner("Detecting columns and cleaning data..."):
        df, report = load_and_clean(data_source, manual_mapping=manual_mapping)
        st.session_state.pop("manual_mapping_pending", None)
except SchemaResolutionNeeded as e:
    st.warning(
        f"Couldn't automatically recognize these fields: **{', '.join(e.unmapped)}**. "
        "Map them to the matching columns from your file below."
    )
    raw_df_preview = pd.read_csv(data_source, nrows=5)
    st.dataframe(raw_df_preview, use_container_width=True)

    with st.form("manual_mapping_form"):
        new_mapping = {}
        # Pre-fill anything that auto-detection already got right
        already_known = {f: f for f in CANONICAL_FIELDS if f not in e.unmapped and f in raw_df_preview.columns}
        for field_name in CANONICAL_FIELDS:
            if field_name in already_known:
                new_mapping[field_name] = already_known[field_name]
                continue
            options = ["(none)"] + e.available_columns
            choice = st.selectbox(f"Which column is **{field_name}**?", options, key=f"map_{field_name}")
            if choice != "(none)":
                new_mapping[field_name] = choice
        submitted = st.form_submit_button("Apply mapping")
        if submitted:
            # Revenue is derivable, so don't hard-require it
            required_for_submit = [f for f in CANONICAL_FIELDS if f != "Revenue"]
            missing_after_manual = [f for f in required_for_submit if f not in new_mapping]
            if missing_after_manual:
                st.error(f"Still missing: {missing_after_manual}. Please map every field.")
            else:
                st.session_state["manual_mapping"] = new_mapping
                st.rerun()
    st.stop()
except ValueError as e:
    st.error(f"Could not process this file: {e}")
    st.stop()

kpis_unfiltered = calculate_kpis(df)

if report.column_mapping_used and not manual_mapping:
    with st.expander("🔎 Auto-detected column mapping"):
        st.json(report.column_mapping_used)
        if report.revenue_was_derived:
            st.caption("Revenue was derived as Quantity × UnitPrice (not present in source file).")

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
# Interactive filters — everything below (KPIs, charts, AI insights, PDF)
# respects this filtered view, not just the charts.
# ---------------------------------------------------------------------------
st.subheader("🔍 Filters")
f1, f2, f3 = st.columns([2, 1, 1])

min_date, max_date = df["OrderDate"].min().date(), df["OrderDate"].max().date()
with f1:
    date_range = st.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
with f2:
    region_options = sorted(df["Region"].unique().tolist())
    selected_regions = st.multiselect("Region", region_options, default=region_options)
with f3:
    product_options = sorted(df["Product"].unique().tolist())
    selected_products = st.multiselect("Product", product_options, default=product_options)

# Apply filters
filtered_df = df.copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered_df = filtered_df[
        (filtered_df["OrderDate"].dt.date >= start) & (filtered_df["OrderDate"].dt.date <= end)
    ]
if selected_regions:
    filtered_df = filtered_df[filtered_df["Region"].isin(selected_regions)]
if selected_products:
    filtered_df = filtered_df[filtered_df["Product"].isin(selected_products)]

if filtered_df.empty:
    st.warning("No rows match the current filters. Adjust your selection above.")
    st.stop()

kpis = calculate_kpis(filtered_df)
st.caption(f"Showing {len(filtered_df):,} of {len(df):,} rows based on current filters.")

st.divider()

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

    anomalies = kpis.get("anomalies", [])
    if anomalies:
        anomaly_df = pd.DataFrame(anomalies)
        anomaly_df["date"] = pd.to_datetime(anomaly_df["date"])
        colors = anomaly_df["direction"].map({"spike": "green", "drop": "red"})
        fig_trend.add_scatter(
            x=anomaly_df["date"], y=anomaly_df["revenue"], mode="markers",
            marker=dict(size=12, color=colors, symbol="star"),
            name="Anomaly", showlegend=True,
        )
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
# Drill-down: inspect the actual transactions behind any product or region
# ---------------------------------------------------------------------------
st.subheader("🔬 Drill Down")
dd1, dd2 = st.columns(2)
with dd1:
    drill_product = st.selectbox("Inspect a product", ["(all)"] + sorted(filtered_df["Product"].unique().tolist()))
with dd2:
    drill_region = st.selectbox("Inspect a region", ["(all)"] + sorted(filtered_df["Region"].unique().tolist()))

drill_df = filtered_df.copy()
if drill_product != "(all)":
    drill_df = drill_df[drill_df["Product"] == drill_product]
if drill_region != "(all)":
    drill_df = drill_df[drill_df["Region"] == drill_region]

dd_c1, dd_c2, dd_c3 = st.columns(3)
dd_c1.metric("Matching orders", f"{len(drill_df):,}")
dd_c2.metric("Revenue", f"{drill_df['Revenue'].sum():,.0f}")
dd_c3.metric("Avg order value", f"{drill_df['Revenue'].mean():,.0f}" if len(drill_df) else "—")

st.dataframe(
    drill_df.sort_values("OrderDate", ascending=False).head(200),
    use_container_width=True,
    height=250,
)
if len(drill_df) > 200:
    st.caption(f"Showing most recent 200 of {len(drill_df):,} matching rows.")

st.divider()

# ---------------------------------------------------------------------------
# AI Insights
# ---------------------------------------------------------------------------
st.subheader("🤖 AI-Generated Insights")

def _get_secret_api_key():
    """Safely read ANTHROPIC_API_KEY from secrets.toml if it exists.
    st.secrets raises StreamlitSecretNotFoundError if no secrets file
    exists at all (not just if the key is missing), so this must be
    wrapped in try/except rather than using a plain .get()."""
    try:
        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None

effective_key = api_key_input or _get_secret_api_key()

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
                except KeyError:
                    st.error("SMTP credentials not configured in Streamlit secrets.")
                except Exception as e:
                    st.error(f"Email failed: {e}")

st.divider()
st.caption("Built with Python, pandas, Streamlit, Plotly, and Claude AI.")
