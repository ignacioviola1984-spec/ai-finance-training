#!/usr/bin/env python3
"""Deterministic dLocal FY2025 close runner (Step 1, versioned as code).

Reads ONLY the three public dLocal input CSVs in this folder and writes
model_output.csv. Pure Python standard library, no LLM / Anthropic calls, fully
reproducible: running it again from a clean checkout regenerates an identical
model_output.csv.

By design this script does NOT read:
  - EXPECTED_from_dLocal_SEC_filings.csv  (the answer key)
  - the existing model_output.csv
so the computed numbers can be graded against the answer key without leakage.

Conventions (per the dLocal input files):
  - All amounts are USD thousands.
  - In pnl_activity.csv expenses are ALREADY negative, so every P&L subtotal is a
    plain sum of the relevant account rows (no sign flipping).
  - FY2025 == period 2025-12, FY2024 == period 2024-12.
"""

import csv
import os

# Resolve every path relative to this file so the script works regardless of the
# current working directory (e.g. `py -3 test-dlocal\run_dlocal_test.py` from repo root).
HERE = os.path.dirname(os.path.abspath(__file__))
PNL_PATH = os.path.join(HERE, "pnl_activity.csv")
BS_PATH = os.path.join(HERE, "balance_sheet.csv")
KPI_PATH = os.path.join(HERE, "kpis_reference.csv")
OUT_PATH = os.path.join(HERE, "model_output.csv")

FY2025 = "2025-12"
FY2024 = "2024-12"

# Operating-profit account set (revenue + cost of services + the operating expense lines).
OPERATING_CODES = ["4000", "5000", "6100", "6200", "6300", "6400", "6500"]
# Below-operating, pre-tax items.
FINANCE_CODES = ["7100", "7200", "7300"]

# Exact required output order (17 rows). Guards against accidental drift.
EXPECTED_KEYS = [
    "gross_profit_fy2025",
    "operating_profit_fy2025",
    "profit_before_tax_fy2025",
    "net_income_fy2025",
    "net_income_fy2024",
    "adjusted_ebitda_fy2025",
    "total_assets_fy2025",
    "total_assets_fy2024",
    "total_liabilities_fy2025",
    "total_equity_fy2025",
    "closing_cash_fy2025",
    "gross_margin_fy2025_pct",
    "net_margin_fy2025_pct",
    "adjusted_ebitda_margin_fy2025_pct",
    "revenue_growth_yoy_pct",
    "gross_profit_growth_yoy_pct",
    "net_income_growth_yoy_pct",
]


def load_pnl(path):
    """(account_code, period) -> amount (USD 000), summed over any duplicate rows."""
    pnl = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["account_code"].strip(), row["period"].strip())
            pnl[key] = pnl.get(key, 0.0) + float(row["amount_usd_000"])
    return pnl


def pnl_sum(pnl, codes, period):
    """Plain sum of the given accounts for a period (expenses are already negative)."""
    return sum(pnl.get((code, period), 0.0) for code in codes)


def load_bs(path):
    """Return ((section, period) -> total) and (period -> cash & equivalents)."""
    by_section = {}
    cash = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            section = row["section"].strip()
            period = row["period"].strip()
            amount = float(row["amount_usd_000"])
            sk = (section, period)
            by_section[sk] = by_section.get(sk, 0.0) + amount
            if row["line_item"].strip() == "Cash and cash equivalents":
                cash[period] = cash.get(period, 0.0) + amount
    return by_section, cash


def load_kpi_value(path, metric, column):
    """Read a single KPI cell from kpis_reference.csv by metric name and column."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["metric"].strip() == metric:
                return float(row[column])
    raise KeyError("KPI metric not found: {!r} (column {!r})".format(metric, column))


def fmt_usd(value):
    """USD thousands as a plain integer string, no commas."""
    return str(int(round(value)))


def fmt_pct(numerator, denominator):
    """Percentage rounded to 1 decimal."""
    return "{:.1f}".format(numerator / denominator * 100.0)


def compute_rows():
    pnl = load_pnl(PNL_PATH)
    by_section, cash = load_bs(BS_PATH)

    # --- Revenue (account 4000) ---
    revenue_2025 = pnl_sum(pnl, ["4000"], FY2025)
    revenue_2024 = pnl_sum(pnl, ["4000"], FY2024)

    # --- P&L subtotals (plain sums; expenses already negative) ---
    gross_profit_2025 = pnl_sum(pnl, ["4000", "5000"], FY2025)
    gross_profit_2024 = pnl_sum(pnl, ["4000", "5000"], FY2024)

    operating_profit_2025 = pnl_sum(pnl, OPERATING_CODES, FY2025)
    operating_profit_2024 = pnl_sum(pnl, OPERATING_CODES, FY2024)

    pbt_2025 = operating_profit_2025 + pnl_sum(pnl, FINANCE_CODES, FY2025)
    pbt_2024 = operating_profit_2024 + pnl_sum(pnl, FINANCE_CODES, FY2024)

    net_income_2025 = pbt_2025 + pnl_sum(pnl, ["8000"], FY2025)
    net_income_2024 = pbt_2024 + pnl_sum(pnl, ["8000"], FY2024)

    # --- Adjusted EBITDA: read from the KPI reference (not derived) ---
    adj_ebitda_2025 = load_kpi_value(KPI_PATH, "Adjusted EBITDA (USD 000)", "fy2025")

    # --- Balance sheet (sum by section and period) ---
    total_assets_2025 = by_section[("ASSET", FY2025)]
    total_assets_2024 = by_section[("ASSET", FY2024)]
    total_liabilities_2025 = by_section[("LIABILITY", FY2025)]
    total_equity_2025 = by_section[("EQUITY", FY2025)]
    closing_cash_2025 = cash[FY2025]

    rows = [
        ("gross_profit_fy2025", fmt_usd(gross_profit_2025)),
        ("operating_profit_fy2025", fmt_usd(operating_profit_2025)),
        ("profit_before_tax_fy2025", fmt_usd(pbt_2025)),
        ("net_income_fy2025", fmt_usd(net_income_2025)),
        ("net_income_fy2024", fmt_usd(net_income_2024)),
        ("adjusted_ebitda_fy2025", fmt_usd(adj_ebitda_2025)),
        ("total_assets_fy2025", fmt_usd(total_assets_2025)),
        ("total_assets_fy2024", fmt_usd(total_assets_2024)),
        ("total_liabilities_fy2025", fmt_usd(total_liabilities_2025)),
        ("total_equity_fy2025", fmt_usd(total_equity_2025)),
        ("closing_cash_fy2025", fmt_usd(closing_cash_2025)),
        ("gross_margin_fy2025_pct", fmt_pct(gross_profit_2025, revenue_2025)),
        ("net_margin_fy2025_pct", fmt_pct(net_income_2025, revenue_2025)),
        ("adjusted_ebitda_margin_fy2025_pct", fmt_pct(adj_ebitda_2025, revenue_2025)),
        ("revenue_growth_yoy_pct", fmt_pct(revenue_2025 - revenue_2024, revenue_2024)),
        ("gross_profit_growth_yoy_pct", fmt_pct(gross_profit_2025 - gross_profit_2024, gross_profit_2024)),
        ("net_income_growth_yoy_pct", fmt_pct(net_income_2025 - net_income_2024, net_income_2024)),
    ]

    # Integrity guards: exactly the 17 required keys, in the required order.
    assert [k for k, _ in rows] == EXPECTED_KEYS, "output keys/order drifted from spec"
    return rows


def main():
    rows = compute_rows()

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["key", "value"])
        writer.writerows(rows)

    print("Wrote: {}".format(OUT_PATH))
    print("key,value")
    for key, value in rows:
        print("{},{}".format(key, value))


if __name__ == "__main__":
    main()
