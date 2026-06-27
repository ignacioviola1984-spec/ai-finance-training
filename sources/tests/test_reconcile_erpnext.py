"""test_reconcile_erpnext.py - the independent ERP tie-out for ERPNext, offline
against the recorded fixture. Per company, MY statements are recomputed from the
GL (blind) and must reproduce ERPNext's own P&L / BalanceSheet / TrialBalance
reports. Because the compute side comes from the GL and the answer key from the
reports, EVERY line (P&L, Balance and TB) is an independent cross-check here.
Tampering the GL must make the reconciler FAIL (fail-closed)."""

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fixture_erpnext
from _fixture_erpnext import load_raw, PERIOD
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reconcile"))
import run_reconcile
import connector as connector_mod


class _FakeAdapter:
    class _Cfg:
        site_label = "demo.frappe.cloud"
        base_url = "https://demo.frappe.cloud"
        companies = []
    def __init__(self, raw):
        self.raw = raw
        self.config = self._Cfg()
    def extract_raw(self, period):
        return self.raw


def _conn(raw):
    return connector_mod.ERPNextConnector(_FakeAdapter(raw))


def _run(raw):
    tmp = tempfile.mkdtemp(prefix="erp_reconcile_")
    return run_reconcile.reconcile_connector(
        _conn(raw), PERIOD, source="erpnext", out_dir=os.path.join(tmp, "active"),
        snapshot_base=os.path.join(tmp, "snap"), now_iso="2026-05-31T12:00:00+00:00")


class ReconcileErpNextTest(unittest.TestCase):
    def test_gl_reproduces_native_reports_per_company(self):
        result, snap_dir = _run(load_raw())
        self.assertTrue(result["pass"], result["structural"]
                        or [r for r in result["rows"] if r["status"] == "FAIL"])
        # two companies reconciled independently
        self.assertEqual(len(result["units"]), 2)
        self.assertEqual(result["n_fail"], 0)
        # for ERPNext, the P&L/Balance lines are independent (GL-derived), not a guard
        self.assertEqual(result["n_regression_guard"], 0)
        self.assertGreater(result["n_cross_report"], 0)
        self.assertTrue(os.path.exists(os.path.join(snap_dir, "manifest.json")))

    def test_tampered_gl_breaks_the_tie_out(self):
        raw = load_raw()
        for g in raw["gl_entries"]:
            if g["company"] == "Lumen UK Ltd." and g["account"].startswith("Cash"):
                g["debit"] = float(g["debit"]) + 10000.0   # GL no longer matches the reports
        result, _ = _run(raw)
        self.assertFalse(result["pass"])
        self.assertGreater(result["n_fail"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
