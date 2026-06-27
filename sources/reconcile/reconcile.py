"""
reconcile.py - the deterministic, fail-closed, vendor-neutral reconciler.

Mirrors test-dlocal/audit_dlocal_test.py: it READS two already-produced things -
my computed statements and the ERP's native statements (the answer key) - and
diffs them line by line. It never computes a figure and never fetches anything;
it only compares. Structural checks run first (key alignment, each trial balance
self-balances), then a per-line tolerance compare. Any break -> result['pass'] is
False and the caller exits non-zero. Nothing is ever absorbed silently.

Both inputs are the SAME vendor-neutral shape:
    {
      "pnl":     {revenue, cogs, gross, opex, operating_income, net_income},
      "balance": {total_assets, total_liabilities, total_equity, cash, ar, ap},
      "trial_balance": {<canonical_code>: {"debit": x, "credit": y}, ...},
    }

Backbone = the trial balance: every canonical account's closing balance (mine vs
the ERP's TB) must tie. If the TB ties, the statements derive by construction; the
statement-level lines are an extra cross-check.
"""

TOLERANCE_USD = 0.01   # absolute, cent-level rounding (documented in the README)

PNL_LINES = ("revenue", "cogs", "gross", "opex", "operating_income", "net_income")
BALANCE_LINES = ("total_assets", "total_liabilities", "total_equity", "cash", "ar", "ap")


def _num(x):
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return None


def _statement_lines(stmt):
    """Fixed statement-level lines (must be present on both sides)."""
    out = {}
    for k in PNL_LINES:
        out[f"pnl.{k}"] = _num((stmt.get("pnl") or {}).get(k))
    for k in BALANCE_LINES:
        out[f"balance.{k}"] = _num((stmt.get("balance") or {}).get(k))
    return out


def _tb_lines(stmt):
    """Per-code trial-balance lines (debit + credit). Codes are unioned across the
    two sides by the caller; an account present on one side only surfaces as a
    value break, never absorbed."""
    out = {}
    for code, dc in (stmt.get("trial_balance") or {}).items():
        out[f"tb.{code}.debit"] = _num((dc or {}).get("debit", 0.0))
        out[f"tb.{code}.credit"] = _num((dc or {}).get("credit", 0.0))
    return out


def _tb_totals(stmt):
    tb = stmt.get("trial_balance") or {}
    debit = round(sum(float((dc or {}).get("debit", 0.0)) for dc in tb.values()), 2)
    credit = round(sum(float((dc or {}).get("credit", 0.0)) for dc in tb.values()), 2)
    return debit, credit


def reconcile(computed, native, tolerance=TOLERANCE_USD, statements_independent=False):
    """Return {pass, structural, rows, n_pass, n_fail, tolerance}. Pure; no I/O.

    `statements_independent` marks whether the P&L/Balance lines are an
    independent cross-check (the compute side was derived differently from the
    native reports, e.g. ERPNext recomputed from the GL) or a regression guard
    (the canonical P&L/Balance share the ERP's report derivation, e.g.
    QuickBooks). The trial-balance lines are always an independent cross-report
    check. This only affects the honest label on each row, never the diff."""
    structural = []

    mine_s, their_s = _statement_lines(computed), _statement_lines(native)
    # statement lines must be present (numeric) on both sides
    for label, d in (("computed", mine_s), ("native", their_s)):
        bad = sorted(k for k, v in d.items() if v is None)
        if bad:
            structural.append(f"{label} statements missing/non-numeric lines: {bad}")

    # each trial balance must self-balance (a TB that does not is itself a break:
    # an unrouted/dropped account or an inconsistent report)
    for label, stmt in (("computed", computed), ("native", native)):
        debit, credit = _tb_totals(stmt)
        if abs(debit - credit) > tolerance:
            structural.append(
                f"{label} trial balance does not self-balance: debits {debit:,.2f} vs credits {credit:,.2f}")

    if structural:
        return {"pass": False, "structural": structural, "rows": [],
                "n_pass": 0, "n_fail": len(structural), "tolerance": tolerance}

    # union all lines (statement + per-code TB); absent on a side -> 0.0 so a
    # one-sided balance surfaces as a delta rather than disappearing.
    mine = {**mine_s, **_tb_lines(computed)}
    their = {**their_s, **_tb_lines(native)}
    keys = sorted(set(mine) | set(their))

    rows, n_pass, n_fail = [], 0, 0
    for key in keys:
        m = mine.get(key, 0.0)
        t = their.get(key, 0.0)
        delta = round(m - t, 4)
        ok = abs(delta) <= tolerance
        rows.append({"line": key, "mine": m, "native": t, "delta": delta,
                     "status": "PASS" if ok else "FAIL",
                     "kind": _line_kind(key, statements_independent)})
        n_pass += ok
        n_fail += (not ok)

    n_cross = sum(1 for r in rows if r["kind"] == "cross-report")
    return {"pass": n_fail == 0, "structural": [], "rows": rows,
            "n_pass": n_pass, "n_fail": n_fail, "tolerance": tolerance,
            "n_cross_report": n_cross, "n_regression_guard": len(rows) - n_cross}


def _line_kind(key, statements_independent=False):
    """Honest labelling. Trial-balance lines are always an INDEPENDENT cross-report
    check. P&L/Balance lines are independent too when the compute side was derived
    differently from the native reports (ERPNext: recomputed from the GL); for a
    source whose canonical P&L/Balance are built from the ERP's own P&L/Balance
    reports (QuickBooks) they are a REGRESSION GUARD that ties by construction
    unless the mapping or finance_core drifts."""
    if key.startswith("tb."):
        return "cross-report"
    return "cross-report" if statements_independent else "regression-guard"


def render_table(result):
    """Aligned PASS/FAIL table (dLocal style)."""
    if result["structural"]:
        lines = ["STRUCTURAL CHECK FAILED:"]
        lines += [f"  - {p}" for p in result["structural"]]
        return "\n".join(lines)
    header = ["line", "mine", "native", "delta", "status", "check"]
    table = [header] + [[r["line"], f"{r['mine']:,.2f}", f"{r['native']:,.2f}",
                         f"{r['delta']:,.2f}", r["status"],
                         "independent" if r["kind"] == "cross-report" else "regression-guard"]
                        for r in result["rows"]]
    w = [max(len(row[i]) for row in table) for i in range(len(header))]
    rightcols = {1, 2, 3}

    def render(row):
        return " | ".join((v.rjust(w[i]) if i in rightcols else v.ljust(w[i]))
                          for i, v in enumerate(row))

    out = [render(table[0]), "-+-".join("-" * x for x in w)]
    out += [render(row) for row in table[1:]]
    out.append("")
    out.append(f"PASS: {result['n_pass']}    FAIL: {result['n_fail']}    "
               f"(tolerance {result['tolerance']} USD)")
    out.append(f"  {result.get('n_cross_report', 0)} trial-balance lines are an INDEPENDENT "
               "cross-report check (my TB vs the ERP's separate TrialBalance report);")
    out.append(f"  {result.get('n_regression_guard', 0)} P&L/Balance lines are a regression "
               "guard (canonical P&L/Balance share the ERP's P&L/Balance derivation).")
    return "\n".join(out)
