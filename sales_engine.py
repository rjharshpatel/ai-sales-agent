"""
sales_engine.py
----------------
Pure data-layer module: CSV -> clean DataFrame -> KPI dict.
No Streamlit, no AI calls here. Keeping this layer dependency-free
means you can unit test it, run it in a notebook, or swap the UI
later without touching the analytics logic.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from schema_mapper import detect_schema, apply_mapping, CANONICAL_FIELDS


# ---------------------------------------------------------------------------
# 1. ETL / CLEANING
# ---------------------------------------------------------------------------


@dataclass
class CleaningReport:
    """Tracks what the cleaning step actually did, so the dashboard
    can show 'we fixed X issues' instead of cleaning silently."""
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    missing_filled: dict = field(default_factory=dict)
    date_parse_failures: int = 0
    column_mapping_used: dict = field(default_factory=dict)
    revenue_was_derived: bool = False


class SchemaResolutionNeeded(Exception):
    """Raised when columns can't be auto-mapped and the caller (UI) needs
    to ask the user to manually pick which column means what."""
    def __init__(self, unmapped: list, available_columns: list):
        self.unmapped = unmapped
        self.available_columns = available_columns
        super().__init__(f"Could not auto-detect columns for: {unmapped}")


def load_and_clean(file_obj_or_path, manual_mapping: Optional[dict] = None) -> tuple[pd.DataFrame, CleaningReport]:
    """
    Loads a raw CSV and applies a defensible cleaning pipeline:
      0. Auto-detect column schema (or use manual_mapping if provided),
         derive Revenue from Quantity*UnitPrice if not present
      1. Strip whitespace from text fields
      2. Parse OrderDate (handles mixed YYYY-MM-DD and DD/MM/YYYY formats)
      3. Coerce numeric columns, drop unparseable rows
      4. Fill missing Region with 'Unknown' (categorical -> safe default)
      5. Impute missing Quantity/UnitPrice using product-level median
         (better than dropping rows or using a single global average)
      6. Recompute Revenue where it's missing or inconsistent with Qty*Price
      7. Drop exact duplicate rows

    Raises SchemaResolutionNeeded if columns can't be auto-mapped and no
    manual_mapping was supplied — the UI should catch this and prompt
    the user to map columns manually, rather than failing outright.
    """
    report = CleaningReport()

    df = pd.read_csv(file_obj_or_path)
    report.rows_in = len(df)

    if manual_mapping:
        mapping = manual_mapping
        derive_revenue = "Revenue" not in mapping and "Quantity" in mapping and "UnitPrice" in mapping
    else:
        schema = detect_schema(list(df.columns))
        if not schema.is_complete:
            raise SchemaResolutionNeeded(schema.unmapped, list(df.columns))
        mapping = schema.mapping
        derive_revenue = schema.can_derive_revenue

    df = apply_mapping(df, mapping)
    report.column_mapping_used = mapping

    if derive_revenue:
        df["Revenue"] = pd.NA
        report.revenue_was_derived = True
    elif "Revenue" not in df.columns:
        df["Revenue"] = pd.NA

    # --- text cleanup ---
    for col in ["Product", "Region", "SalesRep"]:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": np.nan})

    # --- date parsing: try several common formats, mixed within the
    #     same column, since real exports are inconsistent ---
    DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%B %d, %Y", "%d %b %Y"]
    parsed = pd.Series(pd.NaT, index=df.index)
    remaining = df["OrderDate"].astype(str)
    for fmt in DATE_FORMATS:
        still_unparsed = parsed.isna()
        if not still_unparsed.any():
            break
        attempt = pd.to_datetime(remaining[still_unparsed], format=fmt, errors="coerce")
        parsed.loc[still_unparsed] = attempt
    # last resort: let pandas infer freely for anything still unparsed
    still_unparsed = parsed.isna()
    if still_unparsed.any():
        parsed.loc[still_unparsed] = pd.to_datetime(remaining[still_unparsed], errors="coerce")
    df["OrderDate"] = parsed

    report.date_parse_failures = int(df["OrderDate"].isna().sum())
    df = df.dropna(subset=["OrderDate"])

    # --- numeric coercion ---
    for col in ["Quantity", "UnitPrice", "Revenue"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- categorical fill ---
    region_missing = int(df["Region"].isna().sum())
    if region_missing:
        df["Region"] = df["Region"].fillna("Unknown")
        report.missing_filled["Region"] = region_missing

    # --- numeric imputation: product-level median is more honest than
    #     a single global fill value, since prices vary a lot by product ---
    for col in ["Quantity", "UnitPrice"]:
        n_missing = int(df[col].isna().sum())
        if n_missing:
            medians = df.groupby("Product")[col].transform("median")
            df[col] = df[col].fillna(medians)
            # last-resort fallback for products with zero non-null values
            df[col] = df[col].fillna(df[col].median())
            report.missing_filled[col] = n_missing

    # --- recompute Revenue consistently ---
    df["Revenue"] = (df["Quantity"] * df["UnitPrice"]).round(2)

    # --- drop exact duplicates ---
    before = len(df)
    df = df.drop_duplicates()
    report.duplicates_removed = before - len(df)

    df = df.reset_index(drop=True)
    report.rows_out = len(df)
    return df, report


# ---------------------------------------------------------------------------
# 2. KPI CALCULATION
# ---------------------------------------------------------------------------

def calculate_kpis(df: pd.DataFrame) -> dict:
    """
    Returns a dict of KPIs the dashboard and AI insight layer both consume.
    Kept as plain Python types (not DataFrames) so it serializes cleanly
    to JSON for the LLM prompt later.
    """
    if df.empty:
        return {"error": "No data after cleaning."}

    df = df.copy()
    df["OrderDate"] = pd.to_datetime(df["OrderDate"])
    df["WeekStart"] = df["OrderDate"] - pd.to_timedelta(df["OrderDate"].dt.weekday, unit="D")

    total_revenue = float(df["Revenue"].sum())
    total_orders = int(len(df))
    total_units = int(df["Quantity"].sum())
    avg_order_value = float(df["Revenue"].mean())

    # Week-over-week comparison (last full week vs. prior week)
    weekly = df.groupby("WeekStart")["Revenue"].sum().sort_index()
    wow_growth_pct = None
    if len(weekly) >= 2:
        last, prev = weekly.iloc[-1], weekly.iloc[-2]
        if prev > 0:
            wow_growth_pct = round((last - prev) / prev * 100, 1)

    by_product = (
        df.groupby("Product")["Revenue"].sum().sort_values(ascending=False)
    )
    by_region = (
        df.groupby("Region")["Revenue"].sum().sort_values(ascending=False)
    )
    by_rep = (
        df.groupby("SalesRep")["Revenue"].sum().sort_values(ascending=False)
    )
    daily_revenue = df.groupby(df["OrderDate"].dt.date)["Revenue"].sum().sort_index()

    # --- Anomaly detection: flag days where revenue is a statistical
    # outlier (z-score beyond 2 std dev), not just "the lowest day" ---
    anomalies = []
    if len(daily_revenue) >= 5:
        mean, std = daily_revenue.mean(), daily_revenue.std()
        if std > 0:
            z_scores = (daily_revenue - mean) / std
            outlier_days = z_scores[z_scores.abs() > 2]
            for day, z in outlier_days.items():
                anomalies.append({
                    "date": str(day),
                    "revenue": round(float(daily_revenue[day]), 2),
                    "z_score": round(float(z), 2),
                    "direction": "spike" if z > 0 else "drop",
                })

    # --- Trend: simple linear regression slope on daily revenue,
    # normalized as % of mean per day, so "trend" means something
    # beyond a single week-over-week comparison ---
    trend_pct_per_day = None
    if len(daily_revenue) >= 7:
        x = np.arange(len(daily_revenue))
        y = daily_revenue.values
        slope = np.polyfit(x, y, 1)[0]
        if daily_revenue.mean() > 0:
            trend_pct_per_day = round(float(slope / daily_revenue.mean() * 100), 3)

    return {
        "total_revenue": round(total_revenue, 2),
        "total_orders": total_orders,
        "total_units": total_units,
        "avg_order_value": round(avg_order_value, 2),
        "wow_growth_pct": wow_growth_pct,
        "trend_pct_per_day": trend_pct_per_day,
        "anomalies": anomalies,
        "top_products": by_product.head(5).round(2).to_dict(),
        "bottom_products": by_product.tail(3).round(2).to_dict(),
        "by_region": by_region.round(2).to_dict(),
        "by_rep": by_rep.round(2).to_dict(),
        "date_range": [str(df["OrderDate"].min().date()), str(df["OrderDate"].max().date())],
        "daily_revenue": {str(k): round(v, 2) for k, v in daily_revenue.items()},
    }
