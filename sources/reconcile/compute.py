"""
compute.py - MY statements, computed BLIND by finance_core from canonical data.

This is the compute path. It reads ONLY the canonical CSVs (via finance_core);
it NEVER reads the ERP's native reports. Independence is the whole point of the
tie-out, so finance_core runs in a subprocess with FINANCE_DATA_DIR isolated
(same pattern as the engine end-to-end tests), and this module imports nothing
from the reconciler's native-statement path.

Returns the vendor-neutral shape the reconciler compares:
    {"pnl": {...}, "balance": {...}, "trial_balance": {<code>: {debit, credit}}}
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ORCH = os.path.join(REPO, "orchestration")

_SCRIPT = (
    "import sys, os, json\n"
    f"sys.path.insert(0, {ORCH!r})\n"
    "import finance_core as fc\n"
    "period = os.environ['RECONCILE_PERIOD']\n"
    "inc = fc.income_statement(period)\n"
    "bs = fc.balance_sheet_statement(period)\n"
    "tb = fc.trial_balance_usd(period)\n"
    "print(json.dumps({'income': inc, 'balance': bs, 'trial_balance': tb}))\n"
)


def compute_statements(canonical_data_dir, period):
    """Run finance_core over the canonical at `canonical_data_dir` and normalize."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["FINANCE_DATA_DIR"] = os.path.abspath(canonical_data_dir)
    env["FINANCE_LATEST_PERIOD"] = period
    env["RECONCILE_PERIOD"] = period
    out = subprocess.run([sys.executable, "-c", _SCRIPT], env=env, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"finance_core compute failed: {out.stderr.strip()}")
    raw = json.loads(out.stdout.strip())
    return _normalize(raw, period)


def _normalize(raw, period):
    inc, bs, tb = raw["income"], raw["balance"], raw["trial_balance"]
    return {
        "period": period,
        "pnl": {
            "revenue": round(inc["revenue"], 2), "cogs": round(inc["cogs"], 2),
            "gross": round(inc["gross"], 2), "opex": round(inc["opex"], 2),
            "operating_income": round(inc["operating_income"], 2),
            "net_income": round(inc["net_income"], 2),
        },
        "balance": {
            "total_assets": round(bs["total_assets"], 2),
            "total_liabilities": round(bs["total_liabilities"], 2),
            "total_equity": round(bs["total_equity"], 2),
            "cash": round(bs["assets"]["cash"], 2),
            "ar": round(bs["assets"]["accounts_receivable"], 2),
            "ap": round(bs["liabilities"]["accounts_payable"], 2),
        },
        "trial_balance": {code: {"debit": round(dc["debit"], 2), "credit": round(dc["credit"], 2)}
                          for code, dc in tb.items()},
    }
