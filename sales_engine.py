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


# ---------------------------------------------------------------------------
# 1. ETL / CLEANING
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = ["OrderDate", "Product", "Region", "SalesRep", "Quantity", "UnitPrice", "Revenue"]


@dataclass
class CleaningReport:
    """Tracks what the cleaning step actually did, so the dashboard
    can show 'we fixed X issues' instead of cleaning silently."""
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    missing_filled: dict = field(default_factory=dict)
    date_parse_failures: int = 0


def load_and_clean(file_obj_or_path) -> tuple[pd.DataFrame, CleaningReport]:
    """
    Loads a raw CSV and applies a defensible cleaning pipeline:
      1. Validate required columns exist
      2. Strip whitespace from text fields
      3. Parse OrderDate (handles mixed YYYY-MM-DD and DD/MM/YYYY formats)
      4. Coerce numeric columns, drop unparseable rows
      5. Fill missing Region with 'Unknown' (categorical -> safe default)
      6. Impute missing Quantity/UnitPrice using product-level median
         (better than dropping rows or using a single global average)
      7. Recompute Revenue where it's missing or inconsistent with Qty*Price
      8. Drop exact duplicate rows
    """
    report = CleaningReport()

    df = pd.read_csv(file_obj_or_path)
    report.rows_in = len(df)

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"CSV is missing required columns: {missing_cols}")

    # --- text cleanup ---
    for col in ["Product", "Region", "SalesRep"]:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": np.nan})

    # --- date parsing: try multiple formats, mixed within the same column ---
    parsed = pd.to_datetime(df["OrderDate"], format="%Y-%m-%d", errors="coerce")
    still_missing = parsed.isna()
    parsed_alt = pd.to_datetime(df.loc[still_missing, "OrderDate"], format="%d/%m/%Y", errors="coerce")
    parsed.loc[still_missing] = parsed_alt
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

    return {
        "total_revenue": round(total_revenue, 2),
        "total_orders": total_orders,
        "total_units": total_units,
        "avg_order_value": round(avg_order_value, 2),
        "wow_growth_pct": wow_growth_pct,
        "top_products": by_product.head(5).round(2).to_dict(),
        "bottom_products": by_product.tail(3).round(2).to_dict(),
        "by_region": by_region.round(2).to_dict(),
        "by_rep": by_rep.round(2).to_dict(),
        "date_range": [str(df["OrderDate"].min().date()), str(df["OrderDate"].max().date())],
        "daily_revenue": {str(k): round(v, 2) for k, v in daily_revenue.items()},
    }
