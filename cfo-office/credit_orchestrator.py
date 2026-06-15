"""
credit_orchestrator.py - The CFO of the credit (LendingClub) office.

Runs the lending close as a staged operating model (credit_stages) with two-tier
HITL: each function signed off by its domain expert (first line), then the CFO
gives the final consolidated sign-off and the board narrative. Numbers come from
credit_core (deterministic); the model only narrates. Persists to cfo_state.json.

Correr:  python credit_orchestrator.py   (needs ANTHROPIC_API_KEY in ../.env)
"""

import os
import sys

from dotenv import load_dotenv
from anthropic import Anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "orchestration"))   # credit_core
sys.path.insert(0, HERE)                                  # shared_state, review

import credit_core as cc
from shared_state import CFOContext
import review
import credit_stages

load_dotenv(os.path.join(ROOT, ".env"))
client = Anthropic()
MODEL = "claude-sonnet-4-6"


def agent(system, prompt, max_tokens=700):
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# --- deterministic cross-checks between the credit agents -------------------

def cross_checks(ctx):
    """The analytics agents must agree with the benchmark agent on the shared
    numbers (both derive from credit_core, so they must match — catches drift)."""
    issues = []
    bench = {(r["metric"], r["period"]): r["computed"]
             for r in ctx.get("Public Benchmark", "rows", [])}
    orig = ctx.get("Loan Portfolio", "originations_usd")
    if orig is not None and ("originations_usd", "ALL") in bench:
        if abs(orig - bench[("originations_usd", "ALL")]) > 1:
            issues.append(f"originations mismatch: portfolio {orig:,.0f} vs benchmark "
                          f"{bench[('originations_usd', 'ALL')]:,.0f}")
    ii = ctx.get("Revenue & Unit Economics", "interest_income_usd")
    if ii is not None and ("interest_income_usd", "ALL") in bench:
        if abs(ii - bench[("interest_income_usd", "ALL")]) > 1:
            issues.append(f"interest income mismatch: revenue {ii:,.0f} vs benchmark "
                          f"{bench[('interest_income_usd', 'ALL')]:,.0f}")
    return issues


def gather_escalations(ctx):
    esc = []
    for f in review.CREDIT_FUNCTIONS:
        esc.extend(tuple(e) for e in ctx.get(f, "escalations", []))
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    return sorted(esc, key=lambda e: order.get(e[0], 9))


def cfo_final_gate(ctx, esc):
    """The CFO's final sign-off — contingent on every function being signed off by
    its domain expert (the first line)."""
    fl = review.first_line_status(ctx, review.CREDIT_FUNCTIONS)
    print(f"\n  [CFO final sign-off] First line: {len(fl['approved'])}/{fl['total']} "
          "credit functions signed off by their domain experts.")
    if not fl["all_approved"]:
        print("   NOT cleared (must resolve before the CFO can sign): " + ", ".join(fl["rejected"]))
        return False
    serious = [e for e in esc if e[0] in ("HIGH", "CRITICAL")]
    if serious:
        print("   Material items for the CFO:")
        for sev, msg in serious:
            print(f"     - [{sev}] {msg}")
    if review._auto():
        return True
    try:
        return input("  CFO — approve the consolidated credit board pack? [y/N]: ").strip().lower() == "y"
    except EOFError:
        return False


def compose_cfo_narrative(ctx):
    """The CFO Narrative Agent: translate the analysis into executive commentary."""
    p = ctx.get("Loan Portfolio")
    r = ctx.get("Credit Risk")
    u = ctx.get("Revenue & Unit Economics")
    facts = (
        f"Originations: USD {p.get('originations_usd', 0):,.0f} across {p.get('n_loans', 0)} loans; "
        f"weighted-avg rate {p.get('wair', 0) * 100:.1f}%.\n"
        f"Credit risk: charge-off rate {r.get('charge_off_rate', 0) * 100:.1f}%, "
        f"expected loss USD {r.get('expected_loss_usd', 0):,.0f} "
        f"({r.get('expected_loss_pct', 0) * 100:.1f}% of on-book), "
        f"delinquency {r.get('delinquency_rate', 0) * 100:.1f}%.\n"
        f"Unit economics: interest income USD {u.get('interest_income_usd', 0):,.0f}, "
        f"realized yield {u.get('yield_realized', 0) * 100:.1f}%, take rate {u.get('take_rate', 0) * 100:.2f}%.\n"
        f"Risk narrative: {ctx.get('Credit Risk', 'narrative', '')}\n"
        f"Benchmark: {ctx.get('Public Benchmark', 'narrative', '')}\n"
        f"Model risk: {ctx.get('Model Risk', 'narrative', '')}"
    )
    return agent(
        "You are the CFO of a consumer-lending fintech. Write a board narrative of 6-8 sentences "
        "covering growth (originations), credit quality (charge-off, expected loss/provisions), unit "
        "economics (yield, take rate) and the outlook. CFO tone, direct, no filler. Use ONLY the "
        "numbers given; do not invent figures. Write in English.",
        facts,
    )


def compose_actions(ctx):
    esc = gather_escalations(ctx)
    esc_txt = "\n".join(f"  - [{s}] {m}" for s, m in esc) or "  (no escalations)"
    return agent(
        "You are the CFO of a lending fintech. Propose 3 concrete, prioritized actions from the "
        "escalations. One line each. Do not add new numbers. Write in English.",
        f"Escalations:\n{esc_txt}\n\nPropose 3 prioritized actions.",
    )


def run():
    print("=" * 60)
    print("CREDIT CFO OFFICE | LendingClub portfolio")
    print("=" * 60)
    ctx = CFOContext()
    ctx.audit("Credit CFO", "start", "running the credit operating model")

    stage_results, all_passed = credit_stages.run_all(ctx)
    if not all_passed:
        blocked = next((s for s in stage_results if s["status"] == "blocked"), None)
        ctx.put("Credit CFO", {"status": "blocked_stage",
                               "blocked_stage": blocked["name"] if blocked else None})
        ctx.save()
        print(f"\n  Credit model halted at stage {blocked['id']} ({blocked['name']}): {blocked['reason']}"
              if blocked else "\n  Credit model halted.")
        return ctx

    issues = cross_checks(ctx)
    if issues:
        for i in issues:
            ctx.audit("cross_check", "FAIL", i)
        ctx.put("Credit CFO", {"status": "halted_inconsistent"})
        ctx.save()
        print("\n  Stopped: the credit agents don't agree on the numbers.")
        return ctx
    ctx.audit("cross_check", "ok", "credit agents consistent on the shared numbers")

    ctx.put("Credit CFO", {"first_line": review.first_line_status(ctx, review.CREDIT_FUNCTIONS)})
    esc = gather_escalations(ctx)
    for sev, msg in esc:
        ctx.audit("escalation", sev, msg)

    if not cfo_final_gate(ctx, esc):
        ctx.put("Credit CFO", {"status": "rejected"})
        ctx.audit("Credit CFO", "REJECTED", "CFO did not approve")
        ctx.save()
        print("\n  Stopped by CFO decision.")
        return ctx
    ctx.audit("Credit CFO", "approved", "CFO signed off the consolidated credit board pack")

    narrative = compose_cfo_narrative(ctx)
    actions = compose_actions(ctx)
    ctx.put("CFO Narrative", {"narrative": narrative, "actions": actions, "status": "approved"})
    ctx.audit("CFO Narrative", "ok", "consolidated credit board narrative and actions fixed")

    path = ctx.save()
    print("\n--- CREDIT BOARD NARRATIVE (CFO) ---\n" + narrative)
    print("\n--- PROPOSED ACTIONS ---\n" + actions)
    print(f"\nShared state saved to: {os.path.basename(path)} ({len(ctx.state['audit'])} audit events)")
    return ctx


if __name__ == "__main__":
    run()
