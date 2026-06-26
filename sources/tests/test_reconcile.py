"""test_reconcile.py - the independent ERP tie-out, offline against the recorded
QuickBooks fixture. My canonical + finance_core must REPRODUCE QuickBooks' own
P&L / BalanceSheet / TrialBalance reports (PASS); tampering a canonical account
must make the reconciler FAIL with a non-zero result (fail-closed).

The compute path (finance_core) is blind to the native reports; only the
reconciler reads both."""

import copy
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fixture
from _fixture import load_raw, ENTITY_ID, ENTITY_NAME, PERIOD
# the reconciler lives in sources/reconcile (not on the default test sys.path)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reconcile"))
import run_reconcile   # sets up sys.path for canonical/quickbooks/snapshots/reconcile


class _FixtureConnector:
    """A QuickBooks connector backed by the recorded fixture (no network). The
    optional `tamper` mutates the canonical AFTER the mapper, to simulate a
    pipeline break that must surface against the unchanged native reports."""
    name = "quickbooks"

    def __init__(self, raw, tamper=None):
        self.raw = raw
        self.tamper = tamper

    def extract_raw(self, period):
        return self.raw

    def canonical_tables(self, period=None):
        import mapper
        tables = mapper.build_canonical(self.raw, ENTITY_ID, ENTITY_NAME, period)
        if self.tamper:
            self.tamper(tables)
        return tables

    def fetch_native_statements(self, period, company=None):
        import mapper
        return mapper.map_native_statements(self.raw, ENTITY_ID, period)


def _run(connector):
    tmp = tempfile.mkdtemp(prefix="reconcile_")
    return run_reconcile.reconcile_connector(
        connector, PERIOD, source="quickbooks", out_dir=os.path.join(tmp, "active"),
        snapshot_base=os.path.join(tmp, "snap"), now_iso="2026-05-31T12:00:00+00:00")


class ReconcileTest(unittest.TestCase):
    def test_clean_canonical_reproduces_the_native_reports(self):
        result, snap_dir = _run(_FixtureConnector(load_raw()))
        self.assertTrue(result["pass"], [r for r in result["rows"] if r["status"] == "FAIL"]
                        or result["structural"])
        self.assertEqual(result["n_fail"], 0)
        self.assertGreater(result["n_pass"], 12)        # statement lines + per-code TB
        # the backbone (every canonical code's TB) is in the comparison
        tb_lines = [r for r in result["rows"] if r["line"].startswith("tb.")]
        self.assertGreaterEqual(len(tb_lines), 24)      # 12 codes x debit/credit
        # and the snapshot carries the reconciliation result
        self.assertTrue(os.path.exists(os.path.join(snap_dir, "manifest.json")))

    def test_tampered_account_breaks_the_tie_out(self):
        def tamper(tables):
            for r in tables["balance_sheet"]:
                if r["account_code"] == "1000":          # inflate cash by 10,000
                    r["amount_local"] = float(r["amount_local"]) + 10000.0
        result, _ = _run(_FixtureConnector(load_raw(), tamper=tamper))
        self.assertFalse(result["pass"])
        self.assertGreater(result["n_fail"], 0)

    def test_synthetic_source_has_no_native_statements(self):
        # the tie-out only applies to sources that expose native ERP reports
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "canonical"))
        from connector import SyntheticConnector
        with self.assertRaises(NotImplementedError):
            SyntheticConnector().fetch_native_statements(PERIOD)


if __name__ == "__main__":
    unittest.main(verbosity=2)
