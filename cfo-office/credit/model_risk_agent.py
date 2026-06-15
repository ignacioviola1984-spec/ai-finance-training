"""
model_risk_agent.py - Model Risk / Audit Agent (credit / LendingClub track).

Reads the deterministic model-risk review from credit_core (cc.model_risk_review):
flags, assumptions and limitations. It only narrates the model-risk posture and
passes through the engine's escalation flags; it never invents or recomputes a figure.
"""
import os
import sys
from dotenv import load_dotenv
from anthropic import Anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "orchestration"))   # credit_core
sys.path.insert(0, os.path.join(ROOT, "cfo-office"))      # shared_state
import credit_core as cc
from shared_state import CFOContext

load_dotenv(os.path.join(ROOT, ".env"))
client = Anthropic()
MODEL = "claude-sonnet-4-6"


def agent(system, prompt, max_tokens=400):
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def run(ctx=None):
    own = ctx is None
    ctx = ctx or CFOContext()
    ctx.audit("Model Risk", "start", "reviewing model-risk posture")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    data = cc.model_risk_review()
    flags = data["flags"]
    n_flags = data["n_flags"]
    assumptions = data["assumptions"]
    limitations = data["limitations"]

    # 2) escalations: pass through each engine flag verbatim ([severity, msg])
    esc = list(flags)

    # 3) build a facts string from data, then narrate
    flag_lines = "\n".join("- [" + str(f[0]) + "] " + str(f[1]) for f in flags) or "- (none)"
    assumption_lines = "\n".join("- " + a for a in assumptions) or "- (none stated)"
    limitation_lines = "\n".join("- " + l for l in limitations) or "- (none stated)"
    facts = (
        "MODEL-RISK / AUDIT REVIEW (LendingClub credit track)\n"
        "Total flags raised: " + str(n_flags) + "\n"
        "Flags (severity, message):\n" + flag_lines + "\n\n"
        "Stated assumptions:\n" + assumption_lines + "\n\n"
        "Stated limitations:\n" + limitation_lines
    )
    narrative = agent(
        "You are a model risk / audit reviewer for a consumer-credit portfolio. "
        "In 2-4 sentences of plain English, narrate the model-risk posture: data realness, "
        "data-quality status, reliance on documented proxies, and any benchmark drift, then "
        "summarize the stated assumptions and limitations. Use ONLY the numbers and flags given; "
        "never invent or recompute any figure.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Model Risk", {
        "flags": flags,
        "n_flags": n_flags,
        "assumptions": assumptions,
        "limitations": limitations,
        "narrative": narrative,
        "escalations": esc,
    })
    ctx.audit("Model Risk", "ok", str(n_flags) + " model-risk flags raised")

    if own:
        print("\n--- MODEL RISK ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
