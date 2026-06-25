"""
stages.py - The agentic operating model as an explicit, end-to-end sequence of
STAGES, each with its own controls.

This is what turns "a pipeline with reviews" into an operating model. Every stage
of the month-end close is a first-class object with:
  - the agent(s) that do the work          (the MAKER),
  - a deterministic CONTROL that must pass  (code, not the model — a hard gate),
  - a HITL control: sign-off by the domain expert for that stage (the CHECKER),
  - an on-reject path: a deterministic CONTROL failure blocks immediately (a code
    gate over static inputs can't be cleared by re-running); a sign-off REJECTION
    gets a rework cycle (re-run + re-review, capped) and then blocks.

The close runs end to end through these stages. A stage only passes when its
deterministic control holds AND its function(s) are signed off by their domain
expert(s). If a stage cannot pass, the whole close is BLOCKED — you do not build
a board pack on top of an un-controlled, un-reviewed stage. The CFO's final gate
(in cfo_orchestrator) is contingent on every stage having passed.

State per stage (status, control result, reviewers, attempts) is recorded in the
shared state and the audit trail.
"""

import review
import controller_agent
import treasury_agent
import administration_agent
import accounting_reporting_agent
import fpa_agent
import strategic_finance_agent
import internal_controls_agent
import audit_agent

MAX_ATTEMPTS = 2   # 1 run + up to (MAX_ATTEMPTS-1) rework cycles before BLOCK


# --- deterministic stage controls (code-level gates, not the model) --------

def _ctrl_close(ctx):
    cr = ctx.get("Accounting & Close", "reconciliations", {})
    rep = ctx.get("Financial Reporting") or {}
    bs, cf = rep.get("balance_sheet", {}), rep.get("cash_flow", {})
    # Default the balance check to a value that FAILS the gate when absent, so a
    # missing balance_check fails closed (consistent with the sibling controls
    # below). float("inf") is only used in this comparison, never serialized.
    ok = (bool(cr.get("all_reconciled"))
          and abs(bs.get("balance_check", float("inf"))) <= 1.0
          and bool(cf.get("foots")))
    return ok, ("subledgers tie, statements articulate and foot" if ok
                else "close/statements do not tie")


def _ctrl_internal_controls(ctx):
    s = ctx.get("Internal Controls", "summary", {})
    ok = s.get("n_fail", 1) == 0
    return ok, (f"{s.get('n_pass', 0)} controls pass, 0 integrity failures" if ok
                else f"{s.get('n_fail', 1)} integrity control failure(s)")


def _ctrl_audit(ctx):
    op = ctx.get("Audit", "opinion", "adverse")
    return op != "adverse", f"audit opinion: {op}"


# --- stage runners: the maker does the work, then the single-function stages
#     route through their reviewer here (composite stages review inside) -------

def _run_controller(ctx, period):
    controller_agent.run(ctx, period)
    p = ctx.get("Controller", "pnl", {})
    review.review(ctx, "Controller", f"operating income USD {p.get('operating_income', 0):,.0f}")


def _run_treasury(ctx, period):
    treasury_agent.run(ctx, period)
    rw = ctx.get("Treasury", "runway")
    review.review(ctx, "Treasury",
                  f"cash USD {ctx.get('Treasury', 'cash', 0):,.0f}, runway "
                  + (f"{rw:.1f} months" if rw else "n/a"))


def _run_administration(ctx, period):
    administration_agent.run(ctx, period)        # reviews AR / AP / Tax inside


def _run_accounting_reporting(ctx, period):
    accounting_reporting_agent.run(ctx, period)  # reviews Close / Financial Reporting inside


def _run_fpa(ctx, period):
    fpa_agent.run(ctx, period)
    review.review(ctx, "FP&A", "forecast, MoM and budget variance, anomalies")


def _run_strategic(ctx, period):
    strategic_finance_agent.run(ctx, period)
    sm = ctx.get("Strategic Finance", "metrics", {})
    review.review(ctx, "Strategic Finance",
                  f"Rule of 40 {sm.get('rule_of_40', 0):.0f}, burn multiple {sm.get('burn_multiple') or 0:.1f}x")


def _run_internal_controls(ctx, period):
    internal_controls_agent.run(ctx, period)
    cs = ctx.get("Internal Controls", "summary", {})
    review.review(ctx, "Internal Controls",
                  f"{cs.get('n_pass', 0)} pass / {cs.get('n_fail', 0)} fail / {cs.get('n_exception', 0)} exc")


def _run_audit(ctx, period):
    audit_agent.run(ctx, period)
    review.review(ctx, "Audit", f"opinion {ctx.get('Audit', 'opinion', '?')}")


# --- the operating model: stages end to end --------------------------------

STAGES = [
    {"id": 1, "name": "Controllership review", "run": _run_controller,
     "functions": ["Controller"], "control": None},
    {"id": 2, "name": "Treasury & liquidity", "run": _run_treasury,
     "functions": ["Treasury"], "control": None},
    {"id": 3, "name": "Working capital & tax", "run": _run_administration,
     "functions": ["Accounts Receivable", "Accounts Payable", "Tax"], "control": None},
    {"id": 4, "name": "Close & financial statements", "run": _run_accounting_reporting,
     "functions": ["Accounting & Close", "Financial Reporting"], "control": _ctrl_close},
    {"id": 5, "name": "Planning & analysis (FP&A)", "run": _run_fpa,
     "functions": ["FP&A"], "control": None},
    {"id": 6, "name": "Strategic finance", "run": _run_strategic,
     "functions": ["Strategic Finance"], "control": None},
    {"id": 7, "name": "Internal controls", "run": _run_internal_controls,
     "functions": ["Internal Controls"], "control": _ctrl_internal_controls},
    {"id": 8, "name": "Independent audit", "run": _run_audit,
     "functions": ["Audit"], "control": _ctrl_audit},
]


def run_stage(ctx, stage, period="2026-05"):
    """Run one stage end to end: maker -> deterministic control -> HITL sign-off.

    A deterministic CONTROL failure blocks immediately: the controls read static,
    code-computed inputs, so re-running the same stage is guaranteed to produce the
    same failure — a rework cycle there would only waste an LLM call and (in
    interactive mode) pointlessly re-prompt the domain expert before blocking
    anyway. A sign-off REJECTION is the only failure a re-run can plausibly resolve
    (the expert asked for a correction), so it gets a rework cycle, capped, and
    then blocks. Returns a status dict.
    """
    reviewers = [review.REVIEWERS.get(f, "Domain reviewer") for f in stage["functions"]]

    def _blocked(attempt, detail, reason):
        ctx.audit("Operating Model", "stage BLOCKED", f"{stage['name']}: {reason}")
        return {"id": stage["id"], "name": stage["name"], "status": "blocked",
                "attempts": attempt, "control": detail, "reason": reason,
                "functions": stage["functions"], "reviewers": reviewers}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        tag = f"stage {stage['id']}" + (f" (rework {attempt - 1})" if attempt > 1 else "")
        ctx.audit("Operating Model", tag, f"{stage['name']}: running")
        stage["run"](ctx, period)

        ok, detail = stage["control"](ctx) if stage["control"] else (True, "no code-level control")
        fl = review.first_line_status(ctx, stage["functions"])

        if ok and fl["all_approved"]:
            ctx.audit("Operating Model", "stage PASS",
                      f"{stage['name']}: control [{detail}]; signed off by {', '.join(reviewers)}")
            return {"id": stage["id"], "name": stage["name"], "status": "passed",
                    "attempts": attempt, "control": detail,
                    "functions": stage["functions"], "reviewers": reviewers}

        # Deterministic control failed -> block now; a re-run can't change a code
        # gate over static inputs.
        if not ok:
            return _blocked(attempt, detail, "control failed: " + detail)

        # Control held but a domain expert rejected -> rework (the only failure a
        # correction could resolve), then block if it still isn't signed off.
        reason = "not signed off: " + ", ".join(fl["rejected"])
        if attempt < MAX_ATTEMPTS:
            ctx.audit("Operating Model", "stage REWORK", f"{stage['name']}: {reason} -> rework")
            continue
        return _blocked(attempt, detail, reason)


def run_all(ctx, period="2026-05"):
    """Run every stage in order. Stops at the first BLOCKED stage. Returns the
    list of stage status dicts and whether the whole model passed."""
    results = []
    for stage in STAGES:
        print(f"\n[stage {stage['id']}/{len(STAGES)}] {stage['name']}...")
        res = run_stage(ctx, stage, period)
        results.append(res)
        if res["status"] == "blocked":
            break
    all_passed = all(r["status"] == "passed" for r in results) and len(results) == len(STAGES)
    ctx.put("Operating Model", {"stages": results, "all_passed": all_passed})
    return results, all_passed
