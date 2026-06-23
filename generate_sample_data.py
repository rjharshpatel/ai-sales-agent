"""
generate_sample_data.py
------------------------
Produces a synthetic daily-sales CSV with realistic messiness:
duplicate rows, missing values, inconsistent date formats, and
stray whitespace in text columns. This gives the cleaning module
real problems to solve, and gives the live demo something to show
on first load without requiring a user upload.

Run: python generate_sample_data.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)

PRODUCTS = ["Laptop", "Mouse", "Keyboard", "Monitor", "Headphones", "Webcam", "USB-C Hub"]
REGIONS = ["North", "South", "East", "West"]
REPS = ["A. Kumar", "S. Singh", "P. Sharma", "R. Gupta", "M. Verma"]

N_DAYS = 90
N_ROWS_PER_DAY = 12

def random_date_string(d: datetime) -> str:
    """Mimic real-world messiness: two different date formats mixed in the same file."""
    if np.random.rand() < 0.5:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%d/%m/%Y")

def generate():
    rows = []
    start = datetime(2024, 1, 1)
    base_price = {p: np.random.randint(15, 900) for p in PRODUCTS}

    for day in range(N_DAYS):
        current_date = start + timedelta(days=day)
        # weekday seasonality: weekends sell less
        weekday_factor = 0.6 if current_date.weekday() >= 5 else 1.0
        n_rows = max(1, int(np.random.poisson(N_ROWS_PER_DAY * weekday_factor)))

        for _ in range(n_rows):
            product = np.random.choice(PRODUCTS)
            qty = np.random.randint(1, 15)
            price = base_price[product] * np.random.uniform(0.92, 1.08)
            rows.append({
                "OrderDate": random_date_string(current_date),
                "Product": product if np.random.rand() > 0.03 else f"  {product}  ",  # stray whitespace
                "Region": np.random.choice(REGIONS),
                "SalesRep": np.random.choice(REPS),
                "Quantity": qty,
                "UnitPrice": round(price, 2),
                "Revenue": round(qty * price, 2),
            })

    df = pd.DataFrame(rows)

    # Inject missing values (realistic % of nulls)
    for col in ["Quantity", "UnitPrice", "Region"]:
        mask = np.random.rand(len(df)) < 0.02
        df.loc[mask, col] = np.nan

    # Inject duplicate rows (common in daily-export systems)
    dupes = df.sample(frac=0.015, random_state=1)
    df = pd.concat([df, dupes], ignore_index=True)

    # Shuffle so duplicates aren't suspiciously adjacent
    df = df.sample(frac=1, random_state=2).reset_index(drop=True)

    return df

if __name__ == "__main__":
    df = generate()
    out_path = "data/sales_data.csv"
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df)} rows -> {out_path}")
    print(df.head(8).to_string())
