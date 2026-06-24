"""
report_builder.py
-------------------
Builds a one-page PDF report from KPIs + insight text using fpdf2
(pure Python, no system dependencies — important for Streamlit Cloud,
which has a restricted/no system package install step).
"""

from fpdf import FPDF
from datetime import datetime


class SalesReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "Sales Performance Report", new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(235, 235, 245)
        self.cell(0, 8, _pdf_safe(title), new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(2)

    def kpi_row(self, label: str, value: str):
        self.set_font("Helvetica", "", 10)
        self.cell(70, 7, _pdf_safe(label))
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, _pdf_safe(value), new_x="LMARGIN", new_y="NEXT")

    def body_text(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 6, _pdf_safe(text))
        self.ln(2)


# Helvetica (a core PDF font) only supports latin-1. AI-generated text and
# our own f-strings can contain Unicode punctuation (em-dash, smart quotes,
# sigma, etc.) that crashes rendering. Rather than fix call sites one
# character at a time, sanitize centrally wherever text reaches the PDF.
_UNICODE_REPLACEMENTS = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2018": "'", "\u2019": "'",   # smart single quotes
    "\u201c": '"', "\u201d": '"',   # smart double quotes
    "\u2026": "...",  # ellipsis
    "\u03c3": "std dev",  # sigma, just in case
    "\u00b1": "+/-",
}


def _pdf_safe(text: str) -> str:
    for bad, good in _UNICODE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    # final safety net: drop anything else outside latin-1 rather than crash
    return text.encode("latin-1", errors="replace").decode("latin-1")


def build_pdf_report(kpis: dict, insights: dict, output_path: str = "outputs/sales_report.pdf") -> str:
    pdf = SalesReportPDF()
    pdf.add_page()

    pdf.section_title("Key Metrics")
    pdf.kpi_row("Total Revenue:", f"{kpis.get('total_revenue', 0):,.2f}")
    pdf.kpi_row("Total Orders:", f"{kpis.get('total_orders', 0):,}")
    pdf.kpi_row("Total Units Sold:", f"{kpis.get('total_units', 0):,}")
    pdf.kpi_row("Avg Order Value:", f"{kpis.get('avg_order_value', 0):,.2f}")
    growth = kpis.get("wow_growth_pct")
    pdf.kpi_row("WoW Growth:", f"{growth:+.1f}%" if growth is not None else "N/A")
    date_range = kpis.get("date_range", ["N/A", "N/A"])
    pdf.kpi_row("Date Range:", f"{date_range[0]}  to  {date_range[1]}")
    pdf.ln(3)

    pdf.section_title("Top Products by Revenue")
    for product, rev in list(kpis.get("top_products", {}).items())[:5]:
        pdf.kpi_row(f"  {product}", f"{rev:,.2f}")
    pdf.ln(3)

    pdf.section_title("Revenue by Region")
    for region, rev in kpis.get("by_region", {}).items():
        pdf.kpi_row(f"  {region}", f"{rev:,.2f}")
    pdf.ln(3)

    pdf.section_title(f"AI-Generated Insights  (source: {insights.get('source', 'n/a')})")
    pdf.body_text(insights.get("text", "No insights available."))

    pdf.output(output_path)
    return output_path
