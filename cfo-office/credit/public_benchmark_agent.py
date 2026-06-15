"""
public_benchmark_agent.py - Public Financial Benchmark Agent (credit / LendingClub track).

Reads cc.benchmark_vs_filings() for the per-metric comparison of computed KPIs against
LendingClub's reported public-filing values (filed vs computed vs var_pct). It only
narrates how each KPI lines up with the filing (citing the source); it never invents or
recomputes a figure.
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
    ctx.audit("Public Benchmark", "start", "computed KPIs vs public filings")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    data = cc.benchmark_vs_filings()
    rows = data["rows"]
    n = data["n"]
    max_abs_var_pct = data["max_abs_var_pct"]

    # 2) no escalations for this agent (per spec)
    esc = []

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
        "Public financial benchmark: computed KPIs vs public-filing values "
        "(n=" + str(n) + ", max abs var_pct=" + str(max_abs_var_pct) + "%):\n"
        + "\n".join(lines)
        + "\n\nNOTE: the filed values are LendingClub's REAL reported 10-K/8-K figures "
        "(see the source per row); only loan originations is benchmarked (the metric "
        "comparable to the filings)."
    )

    narrative = agent(
        "You are a Public Financial Benchmark analyst for a LendingClub credit book. "
        "In 2-4 sentences of English, narrate how each computed KPI compares to its "
        "public-filing value (filed vs computed vs var_pct). The filed values are "
        "LendingClub's real reported 10-K/8-K figures (cite the source); treat the "
        "variance as a real reconciliation gap to be explained, not a placeholder "
        "artifact. Use ONLY the numbers given; never invent or recompute any figure.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Public Benchmark", {
        "rows": rows,
        "n": n,
        "max_abs_var_pct": max_abs_var_pct,
        "narrative": narrative,
    })
    ctx.audit(
        "Public Benchmark", "ok",
        "n=" + str(n) + " KPIs benchmarked, max abs var_pct=" + str(max_abs_var_pct) + "%",
    )

    if own:
        print("\n--- PUBLIC BENCHMARK ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
