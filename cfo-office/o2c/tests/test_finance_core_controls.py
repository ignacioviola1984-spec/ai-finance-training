"""
test_finance_core_controls.py - finance_core internal controls (the shared
deterministic engine the CFO office runs on). Lives here so the single O2C test
runner (run_tests.py) also exercises it; it imports finance_core from
../../../orchestration.

Covers review finding #5: the FX-completeness control (C2) must validate the FX
rate for EACH balance-sheet row's own period - including the comparative period
the cash flow and audit reconvert - not only the requested reporting period.
"""

import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
O2C = os.path.dirname(TESTS)
CFO_OFFICE = os.path.dirname(O2C)
ROOT = os.path.dirname(CFO_OFFICE)
for _p in (os.path.join(ROOT, "orchestration"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import finance_core as fc


def _c2(period="2026-05"):
    checks = fc.control_checks(period)["checks"]
    return next(c for c in checks if c["id"] == "C2")


class FinanceCoreC2Test(unittest.TestCase):
    def test_c2_passes_on_clean_data(self):
        c2 = _c2("2026-05")
        self.assertEqual(c2["status"], "PASS")

    def test_c2_covers_each_balance_sheet_period(self):
        # Isolate the BS-side fix. The balance sheet carries a comparative period
        # (2026-04) that the cash flow and audit reconvert to USD. On this fixture
        # the P&L spans every period, so the P&L side of C2's needed-set would mask
        # the BS-side change. To prove the fix specifically, construct the one case
        # where the BS rows are the ONLY thing requiring the comparative period's FX:
        # remove that period from the P&L's contribution too, then drop its FX rate.
        # The OLD C2 (BS keyed on the requested period only) would PASS; the fixed
        # C2 (BS keyed on each row's own period) must FAIL.
        bs_periods = sorted({r["period"] for r in fc._BS})
        latest_bs = bs_periods[-1]
        comparative = [p for p in bs_periods if p < latest_bs]
        self.assertTrue(comparative, "fixture needs a comparative balance-sheet period")
        comp = comparative[-1]

        ccy = next(fc._CCY[r["entity_id"]] for r in fc._BS if r["period"] == comp)
        key = (comp, ccy)
        saved_fx = fc._FX.get(key)
        self.assertIsNotNone(saved_fx, "fixture needs an FX rate for the comparative period")

        saved_pnl = fc._PNL
        fc._PNL = [r for r in fc._PNL if r["period"] != comp]   # P&L no longer covers comp
        try:
            del fc._FX[key]
            c2 = _c2(latest_bs)
            # Only the BS-side keying can require (comp, ccy) now; the fixed code does.
            self.assertEqual(c2["status"], "FAIL")
            self.assertIn(comp, str(c2["detail"]))
        finally:
            fc._FX[key] = saved_fx
            fc._PNL = saved_pnl

        # restored: C2 passes again (no test cross-contamination)
        self.assertEqual(_c2(latest_bs)["status"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
