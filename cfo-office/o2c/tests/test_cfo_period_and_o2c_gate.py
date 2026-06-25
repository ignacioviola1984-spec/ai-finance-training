"""
test_cfo_period_and_o2c_gate.py - the CFO office honors the requested period and
the Order-to-Cash hard controls actually block the consolidated board pack.

Covers two review findings:
  #1 the `period` argument is threaded through stages.run_all -> each stage
     runner -> each agent (no hardcoded 2026-05); and
  #2 when O2C hard controls fail, the CFO cannot sign off the consolidated pack.

The close agents' LLM narration is stubbed, so this needs no ANTHROPIC_API_KEY
(the deterministic numbers come from finance_core, not the model). A dummy key is
set before import only because each agent constructs an Anthropic() client at
import time; no request is ever made.
"""

import os
import sys
import unittest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-not-used")   # construct-only, never called
os.environ["CFO_AUTO_REVIEW"] = "1"                            # non-interactive sign-offs

TESTS = os.path.dirname(os.path.abspath(__file__))
O2C = os.path.dirname(TESTS)
CFO_OFFICE = os.path.dirname(O2C)
ROOT = os.path.dirname(CFO_OFFICE)
for _p in (O2C, os.path.join(O2C, "agents"), CFO_OFFICE, os.path.join(ROOT, "orchestration")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import o2c_data_loader as loader        # noqa: E402
import finance_core as fc               # noqa: E402
from shared_state import CFOContext     # noqa: E402

import cfo_orchestrator as orch         # noqa: E402  (pulls in stages + every close agent)
import controller_agent, treasury_agent, ar_agent, ap_agent, tax_agent          # noqa: E402
import administration_agent, accounting_close_agent, financial_reporting_agent   # noqa: E402
import accounting_reporting_agent, fpa_agent, strategic_finance_agent            # noqa: E402
import internal_controls_agent, audit_agent                                      # noqa: E402

_LLM_MODULES = (controller_agent, treasury_agent, ar_agent, ap_agent, tax_agent,
                administration_agent, accounting_close_agent, financial_reporting_agent,
                accounting_reporting_agent, fpa_agent, strategic_finance_agent,
                internal_controls_agent, audit_agent, orch)


def _ensure_data():
    if not os.path.exists(os.path.join(loader.period_data_dir("2026-05"), "invoices.csv")):
        import generate_data
        generate_data.generate_all()


def _stub_llms():
    for mod in _LLM_MODULES:
        mod.agent = lambda *a, **k: "stub narrative"


class PeriodThreadingTest(unittest.TestCase):
    """#1 - each agent computes for the requested period, not a hardcoded one."""

    @classmethod
    def setUpClass(cls):
        _ensure_data()
        _stub_llms()

    def test_agents_honor_a_non_default_period(self):
        period = "2026-04"
        exp = fc.pnl_usd(period)
        ctx = CFOContext()

        controller_agent.run(ctx, period)
        treasury_agent.run(ctx, period)
        financial_reporting_agent.run(ctx, period)
        internal_controls_agent.run(ctx, period)
        audit_agent.run(ctx, period)
        fpa_agent.run(ctx, period)
        strategic_finance_agent.run(ctx, period)

        # Controller and Reporting compute the requested period's P&L.
        self.assertAlmostEqual(ctx.get("Controller", "pnl")["revenue"], exp["revenue"], places=2)
        self.assertAlmostEqual(ctx.get("Financial Reporting", "income_statement")["revenue"],
                               exp["revenue"], places=2)
        # Treasury's cash is the requested period's consolidated cash.
        self.assertAlmostEqual(ctx.get("Treasury", "cash"), fc.cash_total_usd(period), places=2)
        # FP&A's budget variance and Strategic's run-rate anchor on the same period.
        rev_row = next(r for r in ctx.get("FP&A", "budget_variance")["rows"]
                       if r["label"] == "Revenue")
        self.assertAlmostEqual(rev_row["actual"], exp["revenue"], places=2)
        self.assertAlmostEqual(ctx.get("Strategic Finance", "metrics")["run_rate"] / 12.0,
                               exp["revenue"], places=2)

    def test_default_period_unchanged(self):
        # The default still computes 2026-05 (no behavior change when omitted).
        ctx = CFOContext()
        controller_agent.run(ctx)
        self.assertAlmostEqual(ctx.get("Controller", "pnl")["revenue"],
                               fc.pnl_usd("2026-05")["revenue"], places=2)


class O2CGateTest(unittest.TestCase):
    """#2 - O2C hard-control failures block the CFO's consolidated sign-off."""

    @classmethod
    def setUpClass(cls):
        _ensure_data()
        _stub_llms()

    def test_o2c_hard_controls_block_the_board_pack(self):
        # 2026-05 close is clean, but O2C (same period) has hard control failures.
        ctx = orch.run(period="2026-05")
        cfo = ctx.get("CFO")
        # the period threaded all the way through the stages
        self.assertAlmostEqual(ctx.get("Controller", "pnl")["revenue"],
                               fc.pnl_usd("2026-05")["revenue"], places=2)
        # O2C ran as a sub-orchestration and reported its hard failures
        self.assertGreaterEqual(ctx.get("Order-to-Cash", "hard_failures", 0), 1)
        # the CFO did NOT release an approved consolidated pack
        self.assertEqual(cfo.get("status"), "blocked_o2c_hard_controls")
        self.assertNotIn("board_pack", cfo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
