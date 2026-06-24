"""
test_blind_validation_2026_07.py - External blind-validation regression test.

The 2026-07 fixture (data/2026-07/) is an EXTERNAL blind validation pack with 10
planted hard-control issues. The answer key below is used ONLY here, as a test
reference. It is never imported by the runtime pipeline - the controls re-derive
every failure from the source data with no knowledge of these IDs. This test
locks in that the hardened controls catch all 10 planted issues, by control and
record ID, so the fixes cannot silently regress.
"""

import os
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
O2C = os.path.dirname(TESTS)
for _p in (O2C, os.path.join(O2C, "agents")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import o2c_data_loader as loader
import o2c_core as core
import o2c_controls as controls
import o2c_orchestrator as orch

PERIOD = "2026-07"

# External answer key (test reference only; NOT used by the runtime pipeline).
# seed -> (control_id, [record IDs that must be flagged]).
PLANTED = {
    "S01": ("A_CRM_CLOSED_WON_TO_CONTRACT", ["OPP-014"]),
    "S02": ("B_CONTRACT_TO_ORDER", ["CON-018"]),
    "S03": ("C_ORDER_TO_BILLING_SCHEDULE", ["SO-015"]),
    "S04": ("D_BILLING_COMPLETENESS", ["BS-010"]),
    "S05": ("E_INVOICE_ACCURACY", ["INV-001"]),
    "S06": ("F_PO_REQUIRED_CONTROL", ["INV-009"]),
    "S07": ("G_INVOICE_DUPLICATE_CONTROL", ["INV-002", "INV-003"]),
    "S08": ("I_CASH_RECEIPT_TO_BANK", ["PAY-018"]),
    "S09": ("J_CASH_APPLICATION_COMPLETENESS", ["BR-019"]),
    "S10": ("K_REVENUE_RECOGNITION_CUTOFF", ["RS-022"]),
}


@unittest.skipUnless(
    os.path.exists(os.path.join(loader.period_data_dir(PERIOD), "invoices.csv")),
    f"blind fixture data/{PERIOD}/ not present")
class BlindValidation202607Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dfs = loader.load_o2c_data(period=PERIOD)
        cls.results = controls.run_all_controls(cls.dfs, PERIOD)
        cls.by_id = {r.control_id: r for r in cls.results}

    def test_each_planted_seed_is_detected_by_control_and_id(self):
        for seed, (control_id, rec_ids) in PLANTED.items():
            r = self.by_id[control_id]
            self.assertEqual(r.status, "FAIL", f"{seed}: {control_id} should FAIL")
            self.assertTrue(r.blocks_reporting, f"{seed}: {control_id} should block reporting")
            for rid in rec_ids:
                self.assertIn(rid, r.exception_details,
                              f"{seed}: {control_id} did not flag {rid}")

    def test_failing_hard_controls_are_exactly_the_planted_set(self):
        failing = {r.control_id for r in self.results
                   if r.severity == "HARD" and r.status == "FAIL"}
        expected = {cid for cid, _ in PLANTED.values()}
        self.assertEqual(failing, expected,
                         f"missed: {expected - failing} | unexpected: {failing - expected}")

    def test_all_ten_seeds_covered(self):
        self.assertEqual(len(PLANTED), 10)
        covered = sum(1 for _, (cid, _) in PLANTED.items()
                      if self.by_id[cid].status == "FAIL")
        self.assertEqual(covered, 10)

    def test_orchestrator_blocks_on_blind_fixture(self):
        out = tempfile.mkdtemp(prefix="o2c_blind_")
        ctx, meta = orch.run(period=PERIOD, output_dir=out, fail_on_hard=False, verbose=False)
        self.assertEqual(meta["final_status"], "BLOCKED_HARD_CONTROLS")
        self.assertGreaterEqual(ctx.calc["controls_summary"]["hard_failures"], 10)
        self.assertTrue(os.path.exists(os.path.join(out, "o2c_board_pack.md")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
