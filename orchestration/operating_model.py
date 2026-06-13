"""
operating_model.py - AI Finance Operating Model v2 (Fase 3.3)

Toma el orquestador de la 3.2 y le agrega la capa de confiabilidad:

  - Checks deterministicos entre etapas (validan los datos antes de seguir).
  - Audit trail: cada paso se registra con timestamp en audit_log.jsonl.
  - Reglas de escalamiento: marca riesgos por severidad (ALTA/CRITICA).
  - Human-in-the-loop: si hay escalamientos serios, frena y pide tu
    aprobacion antes de emitir el reporte al board.

Es el patron de un sistema agentico confiable: el modelo trabaja, pero
hay controles de codigo y un humano en los puntos criticos.

Requisitos: ANTHROPIC_API_KEY en el .env de la raiz del repo.
Correr:  python operating_model.py
"""

import datetime
import json
import os

import finance_core as fc
from orchestrator import close_review_agent, cash_forecast_agent, reporting_agent

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_PATH = os.path.join(HERE, "audit_log.jsonl")

_trail = []


def audit(stage, status, detail):
    """Registra un evento en el audit trail (memoria + archivo jsonl)."""
    evt = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "stage": stage,
        "status": status,
        "detail": detail,
    }
    _trail.append(evt)
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    print(f"  [audit] {stage:16} {status:10} {detail}")


# --------------------------------------------------------------------------
# Checks deterministicos (codigo, no modelo).
# --------------------------------------------------------------------------

def check_pnl(p):
    issues = []
    if p["revenue"] <= 0:
        issues.append("revenue no positivo")
    if p["gross"] > p["revenue"]:
        issues.append("gross > revenue (imposible)")
    if p["opex"] < 0:
        issues.append("opex negativo")
    return issues


# --------------------------------------------------------------------------
# Reglas de escalamiento (por severidad).
# --------------------------------------------------------------------------

def escalations(pnl, cash):
    out = []
    if pnl["operating_income"] < 0:
        out.append(("ALTA", "perdida operativa: requiere revision de estructura de gasto"))
    ar = fc.ar_overdue_usd()
    if ar["overdue_pct"] > 50:
        out.append(("ALTA", f"{ar['overdue_pct']:.0f}% de la cartera por cobrar esta vencida"))
    if cash["runway"] < 6:
        out.append(("CRITICA", f"runway {cash['runway']:.1f} meses (< 6): riesgo de liquidez"))
    return out


# --------------------------------------------------------------------------
# Gate human-in-the-loop.
# --------------------------------------------------------------------------

def hitl_gate(esc):
    serios = [e for e in esc if e[0] in ("ALTA", "CRITICA")]
    if not serios:
        return True
    print("\n  [human-in-the-loop] Hay escalamientos que requieren tu visto bueno:")
    for sev, msg in serios:
        print(f"     - [{sev}] {msg}")
    try:
        resp = input("  Aprobas continuar al reporte del board? [s/N]: ").strip().lower()
    except EOFError:
        resp = "n"
    return resp == "s"


# --------------------------------------------------------------------------
# Pipeline con controles.
# --------------------------------------------------------------------------

def run(period="2026-05"):
    print("=" * 60)
    print(f"AI FINANCE OPERATING MODEL v2 | cierre {period}")
    print("=" * 60)
    audit("inicio", "ok", f"periodo {period}")

    # Etapa 1: datos + check antes de gastar tokens en el modelo.
    pnl = fc.pnl_usd(period)
    issues = check_pnl(pnl)
    if issues:
        audit("check_pnl", "FALLA", "; ".join(issues))
        print("\n  Pipeline detenido: los datos no pasaron el control.")
        return
    audit("check_pnl", "ok", "P&L internamente consistente")

    _, close_out = close_review_agent(period)
    audit("close_review", "ok", "resumen de cierre y flags generados")

    # Etapa 2: forecast de caja (runway por codigo).
    cash = cash_forecast_agent(period)
    audit("cash_forecast", "ok", f"runway {cash['runway']:.1f} meses")

    # Evaluar escalamientos y registrarlos.
    esc = escalations(pnl, cash)
    for sev, msg in esc:
        audit("escalamiento", sev, msg)

    # Gate humano antes del reporte final.
    if not hitl_gate(esc):
        audit("hitl", "RECHAZADO", "el humano no aprobo; se detiene antes del board")
        print("\n  Pipeline detenido por decision humana.")
        return
    audit("hitl", "aprobado", "el humano aprobo continuar")

    # Etapa 3: reporte al board.
    report = reporting_agent(close_out, cash["narrative"])
    audit("reporting", "ok", "resumen para el board generado")
    print("\nRESUMEN PARA EL BOARD:\n" + report)

    audit("fin", "ok", "pipeline completo")
    print(f"\nAudit trail guardado en: {os.path.basename(AUDIT_PATH)} ({len(_trail)} eventos)")


if __name__ == "__main__":
    run()
