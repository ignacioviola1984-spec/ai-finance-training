"""
variance_explainability_agent.py - explains computed-vs-filed variances (credit / LendingClub track).

Reads cc.benchmark_vs_filings() for the per-metric variance rows (filed vs computed,
var, var_pct) and the max absolute variance. It only narrates the PLAUSIBLE drivers of
those differences using the given numbers; it never invents reconciliations or new figures.
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
    ctx.audit("Variance & Explainability", "start", "benchmark computed vs filings")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    data = cc.benchmark_vs_filings()
    rows = data["rows"]
    max_abs_var_pct = data["max_abs_var_pct"]

    # 2) escalations: each row with abs(var_pct) > 10 -> ['MEDIUM', ...]
    esc = []
    for r in rows:
        if abs(r["var_pct"]) > 10:
            esc.append([
                "MEDIUM",
                r["metric"] + " " + str(r["period"]) + ": " + str(r["var_pct"]) + "% vs filing",
            ])

    # 3) build a facts string from data, then narrate
    lines = []
    for r in rows:
        lines.append(
            "- " + str(r["metric"]) + " (" + str(r["period"]) + "): filed="
            + str(r["filed"]) + ", computed=" + str(r["computed"])
            + ", var=" + str(r["var"]) + ", var_pct=" + str(r["var_pct"]) + "%"
            + ", source=" + str(r["source_doc"]) + ", note=" + str(r["note"])
        )
    facts = (
        "Benchmark of computed metrics vs public filings (n=" + str(data["n"])
        + ", max abs var_pct=" + str(max_abs_var_pct) + "%):\n"
        + "\n".join(lines)
    )

    narrative = agent(
        "You are a Variance & Explainability analyst for a LendingClub credit book. "
        "In 2-4 sentences of English, explain the PLAUSIBLE drivers behind the differences "
        "between the computed metrics and the public disclosures (e.g. scope/period/definition "
        "differences flagged in the notes). Use ONLY the numbers and notes provided; never invent "
        "reconciliations, new figures, or causes not supported by the data. If a gap cannot be "
        "explained from what is given, say so explicitly.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Variance & Explainability", {
        "rows": rows,
        "max_abs_var_pct": max_abs_var_pct,
        "narrative": narrative,
        "escalations": esc,
    })
    ctx.audit(
        "Variance & Explainability", "ok",
        "max abs var_pct=" + str(max_abs_var_pct) + "%, " + str(len(esc)) + " escalation(s)",
    )

    if own:
        print("\n--- VARIANCE & EXPLAINABILITY ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
