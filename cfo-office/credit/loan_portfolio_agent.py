"""
loan_portfolio_agent.py - Loan Portfolio narrator (credit / LendingClub track).

Lee numeros deterministas de credit_core: cc.portfolio_metrics(). Solo narra
originaciones (USD + numero de prestamos), prestamo promedio, tasa de interes
ponderada (WAIR), mix por grade y por plazo, tendencia por vintage y distribucion
por status; nunca inventa ni recalcula una cifra.
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
    ctx.audit("Loan Portfolio", "start", "reading portfolio_metrics")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    pm = cc.portfolio_metrics()

    n_loans = pm["n_loans"]
    originations_usd = pm["originations_usd"]
    avg_loan_usd = pm["avg_loan_usd"]
    wair = pm["wair"]
    by_grade_usd = pm["by_grade_usd"]
    by_term_usd = pm["by_term_usd"]
    by_vintage_usd = pm["by_vintage_usd"]
    status_counts = pm["status_counts"]

    # 2) no escalations per spec
    esc = []

    # 3) build a facts string from data, then narrate
    grade_lines = [
        f"  Grade {g}: ${by_grade_usd[g]:,.0f}"
        for g in sorted(by_grade_usd)
    ]
    grade_block = "\n".join(grade_lines) if grade_lines else "  (no grade data)"

    term_lines = [
        f"  {term} months: ${by_term_usd[term]:,.0f}"
        for term in sorted(by_term_usd)
    ]
    term_block = "\n".join(term_lines) if term_lines else "  (no term data)"

    vintage_lines = [
        f"  {year}: ${by_vintage_usd[year]:,.0f}"
        for year in sorted(by_vintage_usd)
    ]
    vintage_block = "\n".join(vintage_lines) if vintage_lines else "  (no vintage data)"

    status_lines = [
        f"  {status}: {status_counts[status]:,} loans"
        for status in sorted(status_counts, key=lambda s: -status_counts[s])
    ]
    status_block = "\n".join(status_lines) if status_lines else "  (no status data)"

    facts = (
        "Loan portfolio (LendingClub credit track).\n"
        f"Total originations: ${originations_usd:,.0f} across {n_loans:,} loans\n"
        f"Average loan size: ${avg_loan_usd:,.0f}\n"
        f"Weighted-average interest rate (WAIR): {wair * 100:.2f}%\n"
        "Mix by grade (USD):\n"
        f"{grade_block}\n"
        "Mix by term (USD):\n"
        f"{term_block}\n"
        "Originations by vintage year (USD):\n"
        f"{vintage_block}\n"
        "Status distribution (loan counts):\n"
        f"{status_block}"
    )

    narrative = agent(
        "You are the Loan Portfolio analyst for a LendingClub-based credit portfolio. "
        "Write 3-4 sentences in English summarizing the loan book. "
        "Use ONLY the numbers provided; never invent or recompute any figure. "
        "Cover total originations (USD and loan count), average loan size, the "
        "weighted-average interest rate, the mix by grade and by term, the vintage "
        "trend across years, and the status distribution of the book.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Loan Portfolio", {
        "n_loans": n_loans,
        "originations_usd": originations_usd,
        "avg_loan_usd": avg_loan_usd,
        "wair": wair,
        "by_grade_usd": by_grade_usd,
        "by_term_usd": by_term_usd,
        "by_vintage_usd": by_vintage_usd,
        "status_counts": status_counts,
        "narrative": narrative,
    })
    ctx.audit(
        "Loan Portfolio", "ok",
        f"originations ${originations_usd:,.0f} across {n_loans:,} loans, WAIR {wair * 100:.2f}%",
    )

    if own:
        print("\n--- LOAN PORTFOLIO ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
