"""
source_ingestion_agent.py - Source Ingestion Agent (credit / LendingClub track).

Reads the deterministic ingestion summary from credit_core (cc.ingestion_summary):
which CSV files were loaded (accepted / rejected / public filings), their row
counts, the vintage years covered, and whether the engine is pointing at the real
Kaggle data or the seeded sample. It only narrates these numbers; it never invents
or recomputes a figure.
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
    ctx.audit("Source Ingestion", "start", "loading credit source files")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    data = cc.ingestion_summary()
    accepted_file = data["accepted_file"]
    rejected_file = data["rejected_file"]
    filings_file = data["filings_file"]
    accepted_rows = data["accepted_rows"]
    rejected_rows = data["rejected_rows"]
    filing_rows = data["filing_rows"]
    vintage_years = data["vintage_years"]
    is_real_data = data["is_real_data"]

    # 2) no escalations for this agent (pure ingestion reporting)

    # 3) build a compact facts string from the numbers, then narrate
    source_label = "REAL Kaggle data" if is_real_data else "seeded sample data"
    vintages = ", ".join(str(y) for y in vintage_years) if vintage_years else "none"
    facts = (
        f"Credit source ingestion ({source_label}):\n"
        f"- Accepted loans file: {accepted_file} ({accepted_rows} rows)\n"
        f"- Rejected applications file: {rejected_file} ({rejected_rows} rows)\n"
        f"- Public filings file: {filings_file} ({filing_rows} rows)\n"
        f"- Vintage years covered: {vintages}\n"
        f"- is_real_data flag: {is_real_data}"
    )
    narrative = agent(
        "You are the Source Ingestion Agent for a LendingClub credit book. In 2-4 sentences, "
        "report which files were loaded (accepted loans, rejected applications, public filings), "
        "their row counts, the vintage years covered, and whether this is the REAL Kaggle data or "
        "the seeded sample. Use ONLY the numbers given; never invent or recompute a figure. "
        "Write in English.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Source Ingestion", {
        "accepted_file": accepted_file,
        "rejected_file": rejected_file,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "filing_rows": filing_rows,
        "vintage_years": vintage_years,
        "is_real_data": is_real_data,
        "narrative": narrative,
    })
    ctx.audit("Source Ingestion", "ok",
              f"{accepted_rows} accepted / {rejected_rows} rejected rows; "
              f"{'real' if is_real_data else 'sample'} data")

    if own:
        print("\n--- SOURCE INGESTION ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
