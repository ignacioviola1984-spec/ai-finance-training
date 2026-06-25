"""
orchestrator.py - Orquestador con sub-agentes (Fase 3.2).

Un coordinador corre tres sub-agentes especializados, en secuencia, y
pasa el resultado de uno al siguiente, como un cierre de mes:

  1) close_review_agent  -> resume el cierre y levanta flags de riesgo
  2) cash_forecast_agent -> proyecta el runway (el numero lo calcula el codigo)
  3) reporting_agent     -> arma el resumen para el board con lo anterior

Cada sub-agente tiene un input/output definido y su propia especializacion
(system prompt distinto). El orquestador pasa el estado entre ellos.

Principio CFO-grade: los numeros salen de finance_core (deterministico).
Los sub-agentes razonan y redactan; nunca inventan una cifra.

Requisitos: ANTHROPIC_API_KEY en el .env de la raiz del repo.
Correr:  python orchestrator.py
"""

import os
from dotenv import load_dotenv
from anthropic import Anthropic

import finance_core as fc

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))
client = Anthropic()
MODEL = "claude-sonnet-4-6"

PERIOD = "2026-05"


def agent(system, prompt, max_tokens=600):
    """Un sub-agente = una llamada con su propia especializacion (system)."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# --------------------------------------------------------------------------
# Sub-agente 1: revision de cierre
# --------------------------------------------------------------------------

def close_review_agent(period):
    pnl = fc.pnl_usd(period)
    ar = fc.ar_overdue_usd()
    facts = (
        f"P&L {period} (USD): revenue {pnl['revenue']:,.0f}, gross {pnl['gross']:,.0f} "
        f"({pnl['gross']/pnl['revenue']*100:.1f}%), opex {pnl['opex']:,.0f}, "
        f"operating income {pnl['operating_income']:,.0f}.\n"
        f"Cuentas por cobrar (USD): corriente {ar['current']:,.0f}, "
        f"vencida {ar['overdue']:,.0f} ({ar['overdue_pct']:.0f}% del total)."
    )
    system = (
        "Sos un analista de cierre financiero. Tu trabajo: resumir el cierre en "
        "2 frases y listar como maximo 3 flags de riesgo concretos. Usá solo los "
        "numeros que te dan. No inventes cifras."
    )
    return facts, agent(system, facts)


# --------------------------------------------------------------------------
# Sub-agente 2: forecast de caja (el numero lo calcula el codigo)
# --------------------------------------------------------------------------

def cash_forecast_agent(period):
    cash = fc.cash_total_usd(period)
    op_income = fc.pnl_usd(period)["operating_income"]
    burn = -op_income if op_income < 0 else 0.0
    runway = (cash / burn) if burn > 0 else float("inf")
    runway_txt = f"{runway:.1f} meses" if burn > 0 else "sin burn (operativo positivo)"
    facts = (
        f"Caja consolidada: USD {cash:,.0f}. Burn operativo mensual: USD {burn:,.0f}. "
        f"Runway calculado: {runway_txt}."
    )
    system = (
        "Sos un analista de tesoreria. Explicá en 2 frases la situacion de runway "
        "y su implicancia. Usá exactamente el runway que te dan; no lo recalcules."
    )
    return {"cash": cash, "burn": burn, "runway": runway,
            "narrative": agent(system, facts)}


# --------------------------------------------------------------------------
# Sub-agente 3: reporting (compone con las salidas anteriores)
# --------------------------------------------------------------------------

def reporting_agent(close_out, cash_out):
    system = (
        "Sos quien redacta el informe para el board. Con los insumos de cierre y "
        "tesoreria, escribí un resumen ejecutivo de 4-6 frases, tono CFO, directo, "
        "sin relleno. No agregues numeros nuevos."
    )
    prompt = (
        f"--- Revision de cierre ---\n{close_out}\n\n"
        f"--- Forecast de caja ---\n{cash_out}\n\n"
        "Redactá el resumen para el board."
    )
    return agent(system, prompt, max_tokens=700)


# --------------------------------------------------------------------------
# Orquestador: corre las etapas y pasa el estado entre ellas
# --------------------------------------------------------------------------

def orchestrate(period=PERIOD):
    print("=" * 60)
    print(f"ORQUESTADOR DE CIERRE | periodo {period}")
    print("=" * 60)

    print("\n[Etapa 1/3] Sub-agente de revision de cierre...")
    facts, close_out = close_review_agent(period)
    print("  datos (deterministicos):")
    for line in facts.split("\n"):
        print("   ", line)
    print("  salida del sub-agente:\n" + close_out)

    print("\n[Etapa 2/3] Sub-agente de forecast de caja...")
    cash = cash_forecast_agent(period)
    print(f"  runway calculado por codigo: {cash['runway']:.1f} meses")
    print("  salida del sub-agente:\n" + cash["narrative"])

    print("\n[Etapa 3/3] Sub-agente de reporting (usa las dos salidas)...")
    report = reporting_agent(close_out, cash["narrative"])
    print("  RESUMEN PARA EL BOARD:\n" + report)

    return {"close": close_out, "cash": cash, "report": report}


if __name__ == "__main__":
    orchestrate()
