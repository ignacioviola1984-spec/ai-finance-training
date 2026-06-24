"""test_o2c_scenarios.py - two-period scenarios, comparison, and docs existence."""

import os
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
O2C = os.path.dirname(TESTS)
REPO = os.path.dirname(os.path.dirname(O2C))
for _p in (O2C, os.path.join(O2C, "agents"), REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import o2c_data_loader as loader
import o2c_orchestrator as orch
import run_o2c_control_tower as tower


def _ensure_data():
    if not os.path.exists(os.path.join(loader.period_data_dir("2026-06"), "invoices.csv")):
        import generate_data
        generate_data.generate_all()


class ScenarioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_data()
        cls.tmp = tempfile.mkdtemp(prefix="o2c_scen_")

    def test_problematic_period_is_blocked(self):
        ctx, meta = orch.run("2026-05", output_dir=os.path.join(self.tmp, "05"),
                             fail_on_hard=False, verbose=False)
        self.assertEqual(meta["final_status"], "BLOCKED_HARD_CONTROLS")
        self.assertGreaterEqual(ctx.calc["controls_summary"]["hard_failures"], 13)
        self.assertEqual(meta["audit_opinion"], "adverse")

    def test_clean_period_passes(self):
        ctx, meta = orch.run("2026-06", output_dir=os.path.join(self.tmp, "06"),
                             fail_on_hard=False, verbose=False)
        self.assertEqual(ctx.calc["controls_summary"]["hard_failures"], 0,
                         "the clean period must have zero hard failures")
        self.assertIn(meta["final_status"], ("PASS", "PASS_WITH_WARNINGS"))
        self.assertEqual(meta["audit_opinion"], "unqualified")

    def test_periods_generate_separate_outputs(self):
        d5 = tempfile.mkdtemp(prefix="o2c_05_")
        d6 = tempfile.mkdtemp(prefix="o2c_06_")
        orch.run("2026-05", output_dir=d5, fail_on_hard=False, verbose=False)
        orch.run("2026-06", output_dir=d6, fail_on_hard=False, verbose=False)
        for d in (d5, d6):
            self.assertTrue(os.path.exists(os.path.join(d, "o2c_executive_summary.md")))
            self.assertTrue(os.path.exists(os.path.join(d, "o2c_board_pack.md")))
        s5 = open(os.path.join(d5, "o2c_executive_summary.md"), encoding="utf-8").read()
        s6 = open(os.path.join(d6, "o2c_executive_summary.md"), encoding="utf-8").read()
        self.assertNotEqual(s5, s6)
        self.assertIn("BLOCKED", s5)

    def test_comparison_run_works(self):
        rows = tower.compare_periods(("2026-05", "2026-06"), do_print=False)
        self.assertEqual(rows["2026-05"]["final_status"], "BLOCKED_HARD_CONTROLS")
        self.assertEqual(rows["2026-06"]["hard_failures"], 0)
        # the clean period is genuinely healthier
        self.assertLess(rows["2026-06"]["dso"], rows["2026-05"]["dso"])
        self.assertLess(rows["2026-06"]["overdue_ar_usd"], rows["2026-05"]["overdue_ar_usd"])

    def test_architecture_docs_exist(self):
        readme = os.path.join(O2C, "README.md")
        self.assertTrue(os.path.exists(readme))
        txt = open(readme, encoding="utf-8").read()
        self.assertIn("Architecture: Agent-First, Human-Led O2C Control Tower", txt)
        self.assertIn("```mermaid", txt)

    def test_interview_script_exists(self):
        path = os.path.join(O2C, "INTERVIEW_SCRIPT.md")
        self.assertTrue(os.path.exists(path))
        txt = open(path, encoding="utf-8").read()
        self.assertIn("60-second", txt)
        self.assertIn("3-minute", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
