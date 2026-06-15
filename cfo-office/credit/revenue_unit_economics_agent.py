"""
revenue_unit_economics_agent.py - Revenue & Unit Economics narrator (credit / LendingClub track).

Lee numeros deterministas de credit_core: cc.unit_economics() y cc.approval_metrics().
Solo narra interest income, origination fees, total revenue proxy, realized yield,
take rate y rentabilidad por cohorte (cash-on-cash); nunca inventa ni recalcula una cifra.
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
    ctx.audit("Revenue & Unit Economics", "start", "reading unit_economics + approval_metrics")

    # 1) deterministic numbers from credit_core (NEVER compute numbers in the model)
    ue = cc.unit_economics()
    am = cc.approval_metrics()

    interest_income_usd = ue["interest_income_usd"]
    origination_fees_usd = ue["origination_fees_usd"]
    total_revenue_proxy_usd = ue["total_revenue_proxy_usd"]
    yield_realized = ue["yield_realized"]
    take_rate = ue["take_rate"]
    net_cash_to_date_usd = ue["net_cash_to_date_usd"]
    cohorts = ue["cohorts"]
    approval_rate = am["approval_rate"]

    # 2) no escalations per spec
    esc = []

    # 3) build a facts string from data, then narrate
    cohort_lines = []
    for year in sorted(cohorts):
        c = cohorts[year]
        cohort_lines.append(
            f"  {year}: funded ${c['funded_usd']:,.0f}, received ${c['received_usd']:,.0f}, "
            f"net ${c['net_usd']:,.0f}, cash-on-cash {c['cash_on_cash']:.2f}x"
        )
    cohort_block = "\n".join(cohort_lines) if cohort_lines else "  (no cohort data)"

    facts = (
        "Revenue & unit economics (LendingClub credit track). "
        "Revenue figures use a DOCUMENTED FEE PROXY, not booked GAAP revenue.\n"
        f"Interest income: ${interest_income_usd:,.0f}\n"
        f"Origination fees (proxy): ${origination_fees_usd:,.0f}\n"
        f"Total revenue proxy: ${total_revenue_proxy_usd:,.0f}\n"
        f"Realized yield: {yield_realized * 100:.2f}%\n"
        f"Take rate: {take_rate * 100:.2f}%\n"
        f"Net cash to date: ${net_cash_to_date_usd:,.0f}\n"
        f"Approval rate: {approval_rate * 100:.2f}%\n"
        "Cohort / vintage profitability (cash-on-cash):\n"
        f"{cohort_block}"
    )

    narrative = agent(
        "You are the Revenue & Unit Economics analyst for a LendingClub-based credit portfolio. "
        "Write 3-4 sentences in English summarizing revenue and unit economics. "
        "Use ONLY the numbers provided; never invent or recompute any figure. "
        "Explicitly note that the revenue figures rely on a documented fee PROXY, not booked revenue. "
        "Cover interest income, origination fees, total revenue proxy, realized yield, take rate, "
        "and cohort/vintage cash-on-cash profitability.",
        facts,
    )

    # 4) leave the structured result + narrative in the shared book
    ctx.put("Revenue & Unit Economics", {
        "interest_income_usd": interest_income_usd,
        "origination_fees_usd": origination_fees_usd,
        "total_revenue_proxy_usd": total_revenue_proxy_usd,
        "yield_realized": yield_realized,
        "take_rate": take_rate,
        "net_cash_to_date_usd": net_cash_to_date_usd,
        "cohorts": cohorts,
        "approval_rate": approval_rate,
        "narrative": narrative,
    })
    ctx.audit(
        "Revenue & Unit Economics", "ok",
        f"total revenue proxy ${total_revenue_proxy_usd:,.0f}, take rate {take_rate * 100:.2f}%",
    )

    if own:
        print("\n--- REVENUE & UNIT ECONOMICS ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
