"""
finance_core.py - Calculo financiero deterministico (numeros crudos).

Lee los mismos CSV que el MCP server y devuelve numeros (no texto), para
que el orquestador pueda hacer cuentas (ej: runway = caja / burn) sin
depender del modelo. Una sola fuente de datos: ../finance-mcp/data.

Nota de arquitectura: en un refactor "de produccion", el MCP server
importaria estas funciones en vez de tener su propia copia de la logica.
Aca lo mantengo separado para no tocar el server ya validado.
"""

import csv
import os
import datetime

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "finance-mcp", "data")
LATEST = "2026-05"


def _load(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_ENT = _load("entities.csv")
_FX = {(r["period"], r["currency"]): float(r["units_per_usd"]) for r in _load("fx_rates.csv")}
_PNL = _load("pnl_activity.csv")
_BS = _load("balance_sheet.csv")
_INV = _load("ar_invoices.csv")
_CCY = {r["entity_id"]: r["currency"] for r in _ENT}


def _usd(amount_local, currency, period):
    return amount_local / _FX[(period, currency)]


def pnl_usd(period):
    """P&L consolidado en USD para un periodo. Devuelve numeros."""
    agg = {}
    for r in _PNL:
        if r["period"] != period:
            continue
        usd = _usd(float(r["amount_local"]), _CCY[r["entity_id"]], period)
        agg[r["account_code"]] = agg.get(r["account_code"], 0.0) + usd
    rev = agg.get("4000", 0.0)
    cogs = agg.get("5000", 0.0)
    gross = rev - cogs
    opex = agg.get("6000", 0.0) + agg.get("6100", 0.0) + agg.get("6200", 0.0)
    return {
        "revenue": rev,
        "cogs": cogs,
        "gross": gross,
        "opex": opex,
        "operating_income": gross - opex,
    }


def cash_total_usd():
    """Caja consolidada en USD al ultimo cierre."""
    return sum(
        _usd(float(r["amount_local"]), _CCY[r["entity_id"]], LATEST)
        for r in _BS if r["account_code"] == "1000"
    )


def ar_overdue_usd(as_of="2026-05-31"):
    """Cartera por cobrar en USD: corriente vs vencida (todo lo pasado de fecha).

    Aplica la definicion correcta: 'vencido' = cualquier factura abierta
    pasada su fecha de vencimiento (incluye el tramo 1-30).
    """
    asof = datetime.date.fromisoformat(as_of)
    current = 0.0
    overdue = 0.0
    for r in _INV:
        if r["status"] != "open":
            continue
        due = datetime.date.fromisoformat(r["due_date"])
        amt = _usd(float(r["amount_local"]), r["currency"], LATEST)
        if (asof - due).days <= 0:
            current += amt
        else:
            overdue += amt
    total = current + overdue
    return {"current": current, "overdue": overdue, "total": total,
            "overdue_pct": (overdue / total * 100) if total else 0}
