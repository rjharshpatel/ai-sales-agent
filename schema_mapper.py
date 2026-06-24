"""
schema_mapper.py
-----------------
Solves the "only works with my exact column names" brittleness.

Real sales exports use wildly different column names for the same
concept (Date / OrderDate / Order Date / Transaction Date / order_dt
all mean the same thing). This module auto-detects the best match
for each canonical field using normalized string comparison against
a synonym list, and reports anything it couldn't confidently map so
the caller (Streamlit UI) can ask the user to pick manually instead
of just throwing an error.
"""

import re
from dataclasses import dataclass, field

CANONICAL_FIELDS = ["OrderDate", "Product", "Region", "SalesRep", "Quantity", "UnitPrice", "Revenue"]

# Known synonyms per canonical field, lowercased/normalized (spaces, underscores,
# hyphens stripped) for matching against normalized CSV headers.
SYNONYMS = {
    "OrderDate": ["orderdate", "date", "transactiondate", "saledate", "orderdt", "invoicedate", "day"],
    "Product": ["product", "productname", "item", "itemname", "sku", "productid"],
    "Region": ["region", "area", "territory", "zone", "market", "location"],
    "SalesRep": ["salesrep", "rep", "salesperson", "agent", "employee", "seller"],
    "Quantity": ["quantity", "qty", "units", "unitssold", "amountsold", "count"],
    "UnitPrice": ["unitprice", "price", "unitcost", "rate", "priceperunit"],
    "Revenue": ["revenue", "totalrevenue", "totalsales", "sales", "totalamount", "amount", "total"],
}

# Fields that can be derived if missing, rather than treated as fatal.
DERIVABLE = {"Revenue"}  # Revenue = Quantity * UnitPrice if both present


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass
class SchemaMapping:
    mapping: dict = field(default_factory=dict)       # canonical -> actual column name
    unmapped: list = field(default_factory=list)       # canonical fields with no confident match
    can_derive_revenue: bool = False

    @property
    def is_complete(self) -> bool:
        missing = [f for f in self.unmapped if f not in DERIVABLE or not self.can_derive_revenue]
        return len(missing) == 0


def detect_schema(columns: list[str]) -> SchemaMapping:
    """
    Given the actual column headers from an uploaded CSV, returns the
    best-guess mapping to canonical field names. Does not raise —
    callers should check `.unmapped` and `.is_complete`.
    """
    result = SchemaMapping()
    normalized_actual = {_normalize(c): c for c in columns}

    for canonical in CANONICAL_FIELDS:
        match = None
        for synonym in SYNONYMS[canonical]:
            if synonym in normalized_actual:
                match = normalized_actual[synonym]
                break
        if match:
            result.mapping[canonical] = match
        else:
            result.unmapped.append(canonical)

    if "Revenue" in result.unmapped and "Quantity" in result.mapping and "UnitPrice" in result.mapping:
        result.can_derive_revenue = True

    return result


def apply_mapping(df, mapping: dict):
    """Renames df columns according to the resolved mapping (canonical -> actual).
    Returns a new DataFrame with canonical column names."""
    rename_map = {actual: canonical for canonical, actual in mapping.items()}
    return df.rename(columns=rename_map)
