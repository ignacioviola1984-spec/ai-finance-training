"""
data_quality_agent.py - Data Quality & Schema Agent (credit / LendingClub track).

Reads the deterministic schema/integrity register from credit_core (cc.data_quality):
the PASS/WARN/FAIL checks on the accepted loan book (columns, duplicates, missing
values, dates, outliers). It only narrates the data-quality posture and escalates
failed/warned checks; it never invents or recomputes a figure.
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
    ctx.audit("Data Quality", "start", "schema + integrity checks")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    data = cc.data_quality()
    checks = data["checks"]
    n_pass = data["n_pass"]
    n_warn = data["n_warn"]
    n_fail = data["n_fail"]
    rows_checked = data["rows_checked"]
    clean = data["clean"]

    # 2) escalations: one per check that does not pass (FAIL = HIGH, WARN = MEDIUM)
    esc = []
    for c in checks:
        if c["status"] == "FAIL":
            esc.append(["HIGH", c["name"] + ": " + c["detail"]])
        elif c["status"] == "WARN":
            esc.append(["MEDIUM", c["name"] + ": " + c["detail"]])

    # 3) build a facts string from data, then narrate
    register = "\n".join(
        "[" + c["id"] + "] " + c["name"] + ": " + c["status"] + " - " + c["detail"]
        for c in checks
    ) or "- (no checks)"
    facts = (
        "DATA QUALITY & SCHEMA REGISTER (LendingClub accepted loan book)\n"
        "Rows checked: " + str(rows_checked) + "\n"
        "Result: " + str(n_pass) + " pass / " + str(n_warn) + " warn / "
        + str(n_fail) + " fail (clean=" + str(clean) + ")\n"
        "Checks (id, name, status, detail):\n" + register
    )
    narrative = agent(
        "You are a data quality / schema reviewer for a consumer-credit portfolio. "
        "In 2-4 sentences of plain English, narrate the schema and integrity posture: "
        "whether required columns are present, duplicates, missing values in key fields, "
        "valid issue dates, and amount/rate outliers, then state whether the book is clean "
        "for downstream metrics. Use ONLY the numbers and statuses in the register given; "
        "never invent or recompute any figure.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Data Quality", {
        "checks": checks,
        "n_pass": n_pass,
        "n_warn": n_warn,
        "n_fail": n_fail,
        "rows_checked": rows_checked,
        "clean": clean,
        "narrative": narrative,
        "escalations": esc,
    })
    ctx.audit("Data Quality", "ok",
              str(n_pass) + " pass / " + str(n_warn) + " warn / " + str(n_fail)
              + " fail; " + str(len(esc)) + " escalation(s)")

    if own:
        print("\n--- DATA QUALITY ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
