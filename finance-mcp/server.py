"""
Lumen Finance MCP Server
=========================

Expone el sistema financiero de Lumen Inc. (una SaaS B2B post-seed con 6
entidades legales en 6 monedas) como un conjunto de herramientas MCP que
cualquier cliente compatible (Claude, Cowork, etc.) puede operar en
lenguaje natural.

Herramientas:
  - list_entities        : entidades legales y su moneda funcional
  - get_pnl              : P&L consolidado por periodo, en la moneda que se pida
  - get_balance_sheet    : balance consolidado (ultimo cierre)
  - get_ar_aging         : aging de cuentas por cobrar por tramos
  - get_cash_position    : caja por entidad y consolidada

Decision de arquitectura: la consolidacion multi-moneda usa la tasa de
CIERRE de cada periodo (tabla fija fx_rates.csv), no una tasa en vivo.
Asi el P&L de un periodo cerrado no cambia con el tiempo, que es como se
consolida en contabilidad real.

Superficie deliberadamente READ-ONLY: el server solo lee y reporta. No
expone ninguna herramienta que escriba, borre o mueva dinero. Esa es una
decision de seguridad, no una limitacion.
"""

import csv
import os
import datetime
from collections import defaultdict

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lumen-finance")

# --------------------------------------------------------------------------
# Capa de datos: cargamos los CSV una vez al iniciar.
# --------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LATEST_PERIOD = "2026-05"


def _load(name):
    with open(os.path.join(DATA_DIR, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


ENTITIES = _load("entities.csv")
COA = {r["account_code"]: r for r in _load("chart_of_accounts.csv")}
FX = {(r["period"], r["currency"]): float(r["units_per_usd"]) for r in _load("fx_rates.csv")}
PNL = _load("pnl_activity.csv")
BS = _load("balance_sheet.csv")
INVOICES = _load("ar_invoices.csv")

ENTITY_CCY = {r["entity_id"]: r["currency"] for r in ENTITIES}
ENTITY_IDS = [r["entity_id"] for r in ENTITIES]
PERIODS = sorted({r["period"] for r in PNL})
CURRENCIES = sorted({r["currency"] for r in ENTITIES})


# --------------------------------------------------------------------------
# Helpers de conversion FX.
# --------------------------------------------------------------------------

def _to_usd(amount_local, currency, period):
    """Convierte un monto en moneda local a USD usando la tasa de cierre."""
    return amount_local / FX[(period, currency)]


def _from_usd(amount_usd, currency, period):
    """Convierte un monto en USD a la moneda destino a la tasa de cierre."""
    return amount_usd * FX[(period, currency)]


def _convert(amount_local, currency, period, report_currency):
    """Convierte moneda local -> USD -> moneda de reporte (tasa de cierre)."""
    usd = _to_usd(amount_local, currency, period)
    if report_currency == "USD":
        return usd
    return _from_usd(usd, report_currency, period)


def _validate_currency(report_currency):
    if report_currency not in CURRENCIES:
        raise ValueError(
            f"Moneda '{report_currency}' no soportada. Opciones: {', '.join(CURRENCIES)}."
        )


def _validate_period(period):
    if period not in PERIODS:
        raise ValueError(
            f"Periodo '{period}' no disponible. Opciones: {', '.join(PERIODS)}."
        )


def _validate_entity(entity_id):
    """Acepta vacio (=consolidado) o un entity_id valido. Falla claro si no."""
    if entity_id and entity_id not in ENTITY_IDS:
        raise ValueError(
            f"Entidad '{entity_id}' no existe. Opciones: {', '.join(ENTITY_IDS)} "
            f"(o vacio para consolidado)."
        )


def _money(x, currency):
    return f"{currency} {x:,.0f}"


# --------------------------------------------------------------------------
# Herramientas MCP.
# --------------------------------------------------------------------------

@mcp.tool()
def list_entities() -> str:
    """Lista las entidades legales de Lumen, su pais y su moneda funcional."""
    lines = ["Entidades legales de Lumen Inc.:", ""]
    for r in ENTITIES:
        lines.append(f"  {r['entity_id']:3} | {r['name']:22} | {r['country']:15} | {r['currency']}")
    return "\n".join(lines)


@mcp.tool()
def get_pnl(period: str, report_currency: str = "USD", entity_id: str = "") -> str:
    """Devuelve el P&L consolidado de un periodo, convertido a report_currency.

    Args:
        period: periodo a reportar, formato YYYY-MM (ej: 2026-05).
        report_currency: moneda de reporte (USD, EUR, GBP, BRL, ARS, INR). Default USD.
        entity_id: si se indica (ej: US), reporta solo esa entidad; si no, consolida las 6.
    """
    _validate_period(period)
    _validate_currency(report_currency)
    _validate_entity(entity_id)

    agg = defaultdict(float)
    for r in PNL:
        if r["period"] != period:
            continue
        if entity_id and r["entity_id"] != entity_id:
            continue
        ccy = ENTITY_CCY[r["entity_id"]]
        agg[r["account_code"]] += _convert(float(r["amount_local"]), ccy, period, report_currency)

    rev = agg["4000"]
    cogs = agg["5000"]
    gross = rev - cogs
    sm, rd, ga = agg["6000"], agg["6100"], agg["6200"]
    opex = sm + rd + ga
    op_income = gross - opex

    scope = entity_id if entity_id else "Consolidado (6 entidades)"
    gm = (gross / rev * 100) if rev else 0
    om = (op_income / rev * 100) if rev else 0
    return "\n".join([
        f"P&L {scope} | periodo {period} | moneda {report_currency}",
        "-" * 52,
        f"  Revenue            {_money(rev, report_currency):>22}",
        f"  Cost of revenue    {_money(-cogs, report_currency):>22}",
        f"  Gross profit       {_money(gross, report_currency):>22}   ({gm:.1f}%)",
        f"  Sales & marketing  {_money(-sm, report_currency):>22}",
        f"  R&D                {_money(-rd, report_currency):>22}",
        f"  G&A                {_money(-ga, report_currency):>22}",
        f"  Operating income   {_money(op_income, report_currency):>22}   ({om:.1f}%)",
    ])


@mcp.tool()
def get_balance_sheet(report_currency: str = "USD", entity_id: str = "") -> str:
    """Balance consolidado al ultimo cierre, convertido a report_currency.

    Args:
        report_currency: moneda de reporte. Default USD.
        entity_id: si se indica, reporta solo esa entidad; si no, consolida.
    """
    _validate_currency(report_currency)
    _validate_entity(entity_id)
    agg = defaultdict(float)
    for r in BS:
        if r["period"] != LATEST_PERIOD:      # el balance tiene 2 periodos: tomar solo el cierre
            continue
        if entity_id and r["entity_id"] != entity_id:
            continue
        ccy = ENTITY_CCY[r["entity_id"]]
        agg[r["account_code"]] += _convert(float(r["amount_local"]), ccy, LATEST_PERIOD, report_currency)

    assets = agg["1000"] + agg["1100"] + agg["1500"]
    liab = agg["2000"] + agg["2500"]
    equity = agg["3000"] + agg["3900"]
    scope = entity_id if entity_id else "Consolidado (6 entidades)"
    return "\n".join([
        f"Balance Sheet {scope} | cierre {LATEST_PERIOD} | moneda {report_currency}",
        "-" * 52,
        "  ACTIVO",
        f"    Cash & equivalents   {_money(agg['1000'], report_currency):>20}",
        f"    Accounts receivable  {_money(agg['1100'], report_currency):>20}",
        f"    Fixed assets, net    {_money(agg['1500'], report_currency):>20}",
        f"    Total assets         {_money(assets, report_currency):>20}",
        "  PASIVO",
        f"    Accounts payable     {_money(agg['2000'], report_currency):>20}",
        f"    Deferred revenue     {_money(agg['2500'], report_currency):>20}",
        f"    Total liabilities    {_money(liab, report_currency):>20}",
        "  PATRIMONIO",
        f"    Paid-in capital      {_money(agg['3000'], report_currency):>20}",
        f"    Retained earnings    {_money(agg['3900'], report_currency):>20}",
        f"    Total equity         {_money(equity, report_currency):>20}",
        "-" * 52,
        f"  Check (A - P - PN)     {_money(assets - liab - equity, report_currency):>20}",
    ])


@mcp.tool()
def get_ar_aging(report_currency: str = "USD", as_of_date: str = "2026-05-31", entity_id: str = "") -> str:
    """Aging de cuentas por cobrar (facturas abiertas) por tramos de mora.

    Args:
        report_currency: moneda de reporte. Default USD.
        as_of_date: fecha de corte YYYY-MM-DD. Default 2026-05-31.
        entity_id: si se indica, solo esa entidad; si no, consolida.
    """
    _validate_currency(report_currency)
    _validate_entity(entity_id)
    asof = datetime.date.fromisoformat(as_of_date)
    buckets = {"Corriente": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for r in INVOICES:
        if r["status"] != "open":
            continue
        if entity_id and r["entity_id"] != entity_id:
            continue
        due = datetime.date.fromisoformat(r["due_date"])
        overdue = (asof - due).days
        amt = _convert(float(r["amount_local"]), r["currency"], LATEST_PERIOD, report_currency)
        if overdue <= 0:
            buckets["Corriente"] += amt
        elif overdue <= 30:
            buckets["1-30"] += amt
        elif overdue <= 60:
            buckets["31-60"] += amt
        elif overdue <= 90:
            buckets["61-90"] += amt
        else:
            buckets["90+"] += amt

    total = sum(buckets.values())
    scope = entity_id if entity_id else "Consolidado (6 entidades)"
    lines = [
        f"AR Aging {scope} | corte {as_of_date} | moneda {report_currency}",
        "-" * 52,
    ]
    for k, v in buckets.items():
        pct = (v / total * 100) if total else 0
        lines.append(f"  {k:10} {_money(v, report_currency):>20}   ({pct:.0f}%)")
    lines.append("-" * 52)
    lines.append(f"  {'Total':10} {_money(total, report_currency):>20}")
    return "\n".join(lines)


@mcp.tool()
def get_cash_position(report_currency: str = "USD") -> str:
    """Posicion de caja por entidad y consolidada, al ultimo cierre."""
    _validate_currency(report_currency)
    lines = [
        f"Posicion de caja | cierre {LATEST_PERIOD} | moneda {report_currency}",
        "-" * 52,
    ]
    total = 0.0
    for r in BS:
        if r["account_code"] != "1000" or r["period"] != LATEST_PERIOD:
            continue
        ccy = ENTITY_CCY[r["entity_id"]]
        local = float(r["amount_local"])
        conv = _convert(local, ccy, LATEST_PERIOD, report_currency)
        total += conv
        lines.append(f"  {r['entity_id']:3} {_money(local, ccy):>18}  ->  {_money(conv, report_currency):>18}")
    lines.append("-" * 52)
    lines.append(f"  Total consolidado {_money(total, report_currency):>28}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
