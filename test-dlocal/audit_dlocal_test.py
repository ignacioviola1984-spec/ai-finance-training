#!/usr/bin/env python3
"""Deterministic dLocal audit (Step 2, versioned as code).

Joins the code-generated model_output.csv against EXPECTED_from_dLocal_SEC_filings.csv
(the answer key derived from dLocal's public SEC filings) and reports PASS/FAIL per
metric.

Pure Python standard library, no LLM / Anthropic calls, CI-friendly:
  - reads ONLY model_output.csv and EXPECTED_from_dLocal_SEC_filings.csv
  - never recomputes figures from pnl_activity.csv / balance_sheet.csv
  - never modifies any file (read-only; prints to stdout)
  - deterministic output; exits 0 iff every expected row passes, else 1

Tolerances: USD_000 rows pass if |model - expected| <= 1; pct rows pass if
|model - expected| <= 0.1.
"""

import csv
import os
import sys
from collections import Counter

# Resolve paths relative to this file so it runs from repo root (or anywhere).
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "model_output.csv")
EXPECTED_PATH = os.path.join(HERE, "EXPECTED_from_dLocal_SEC_filings.csv")

TOLERANCE = {"USD_000": 1.0, "pct": 0.1}
EPS = 1e-9  # guards the "<=" boundary against floating-point representation error


def load_expected(path):
    """Ordered list of (key, expected_value, unit). Raises on a malformed key file."""
    rows = []
    seen = Counter()
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (r["key"] or "").strip()
            unit = (r["unit"] or "").strip()
            value = float(r["expected_value"])
            if unit not in TOLERANCE:
                raise ValueError(
                    "EXPECTED has unknown unit {!r} for key {!r}".format(unit, key)
                )
            rows.append((key, value, unit))
            seen[key] += 1
    dups = sorted(k for k, c in seen.items() if c > 1)
    if dups:
        raise ValueError("EXPECTED has duplicate keys: {}".format(", ".join(dups)))
    return rows


def load_model_pairs(path):
    """Raw (key, value_string) pairs from model_output.csv, in file order."""
    pairs = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            pairs.append(((r.get("key") or "").strip(), (r.get("value") or "").strip()))
    return pairs


def fmt_num(value, unit):
    """Format a number for the table: integer for USD_000, 1 decimal for pct."""
    if abs(value) < EPS:  # normalise -0.0 -> 0
        value = 0.0
    return "{:.1f}".format(value) if unit == "pct" else "{:.0f}".format(value)


def render_table(results):
    """Render the comparison table as aligned text."""
    header = ["key", "model", "expected", "delta", "unit", "status"]
    table = [header]
    for key, model_v, expected_v, delta, unit, status in results:
        table.append([
            key,
            fmt_num(model_v, unit),
            fmt_num(expected_v, unit),
            fmt_num(delta, unit),
            unit,
            status,
        ])
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    numeric_cols = {1, 2, 3}  # model, expected, delta -> right-align

    def render(row):
        cells = []
        for i, val in enumerate(row):
            cells.append(val.rjust(widths[i]) if i in numeric_cols else val.ljust(widths[i]))
        return " | ".join(cells)

    lines = [render(table[0]), "-+-".join("-" * w for w in widths)]
    lines.extend(render(row) for row in table[1:])
    return "\n".join(lines)


def main():
    expected = load_expected(EXPECTED_PATH)
    expected_keys = [k for k, _, _ in expected]
    expected_set = set(expected_keys)

    pairs = load_model_pairs(MODEL_PATH)
    model_keys = [k for k, _ in pairs]
    counts = Counter(model_keys)
    model_set = set(model_keys)

    # ---- Structural validation (fail before comparison if the file is malformed) ----
    structural = []

    dups = sorted(k for k, c in counts.items() if c > 1)
    if dups:
        structural.append("duplicate keys: {}".format(", ".join(dups)))

    values = {}
    non_numeric = []
    for key, raw in pairs:
        try:
            values[key] = float(raw)
        except ValueError:
            non_numeric.append("{}={!r}".format(key, raw))
    if non_numeric:
        structural.append("non-numeric values: {}".format(", ".join(non_numeric)))

    missing = sorted(expected_set - model_set)
    if missing:
        structural.append("missing keys: {}".format(", ".join(missing)))

    unexpected = sorted(model_set - expected_set)
    if unexpected:
        structural.append("unexpected keys: {}".format(", ".join(unexpected)))

    if structural:
        print("STRUCTURAL CHECK FAILED:")
        for problem in structural:
            print("  - {}".format(problem))
        print()
        print("AUDIT FAILED (model_output.csv did not pass structural validation)")
        sys.exit(1)

    # ---- Row-by-row comparison (expected order is the canonical order) ----
    results = []
    pass_count = 0
    fail_count = 0
    for key, expected_v, unit in expected:
        model_v = values[key]
        delta = model_v - expected_v
        tol = TOLERANCE[unit]
        ok = abs(delta) <= tol + EPS
        status = "PASS" if ok else "FAIL"
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        results.append((key, model_v, expected_v, delta, unit, status))

    print(render_table(results))
    print()
    print("PASS: {}".format(pass_count))
    print("FAIL: {}".format(fail_count))

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
