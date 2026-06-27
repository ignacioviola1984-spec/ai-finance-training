"""
mapper.py - Pure, deterministic ERPNext (Frappe) -> canonical transform.

This is where ERPNext (Frappe) names die. Every ERPNext Account is routed into one
of the 12 canonical rollup codes (schema.CANONICAL_COA); every report and DocType
becomes the canonical tables finance_core already reads, PLUS the optional
Order-to-Cash tables (schema.O2C_TABLES). No model, no network, no randomness:
same input -> same output, always.

KEY DIFFERENCE vs QuickBooks (the point of this source): ERPNext is multi-company
(each Company = a legal entity) and multi-currency. So `entities` has one row per
Company, every row carries its document currency, and `fx_rates` (from Currency
Exchange) lets finance_core consolidate to USD. This source exercises the
multi-entity / multi-currency consolidation the QuickBooks sandbox could not.

Account routing (ERPNext root_type / account_type / name -> canonical code):
  Asset + Bank/Cash (or name cash/bank)        -> 1000 cash
  Asset + Receivable (or name receivable)      -> 1100 AR
  Asset, other                                 -> 1500 fixed/other assets
  Liability + Payable (or name payable)        -> 2000 AP
  Liability named deferred/unearned            -> 2500 deferred revenue
  Liability, other                             -> 2000 AP bucket
  Equity named retained/accumulated/net income -> 3900 retained earnings
  Equity, other                                -> 3000 paid-in capital
  Income                                        -> 4000 revenue
  Expense + Cost of Goods Sold (or name cogs)  -> 5000 cost of revenue
  Expense named marketing/sales/advertising    -> 6000 sales & marketing
  Expense named research/development/eng       -> 6100 R&D
  Expense, other                                -> 6200 G&A

The raw shape this consumes is documented in sources/erpnext/README.md and is
produced by ERPNextConnector.extract_raw (record_fixture.py captures a real one).
"""

from schema import (CANONICAL_COA, COA_NAME, COA_TYPE,
                    PNL_REVENUE, PNL_COGS, PNL_SM, PNL_RD, PNL_GA, PNL_EXPENSE_CODES,
                    BS_CASH, BS_AR, BS_FIXED, BS_AP, BS_DEFERRED,
                    BS_PAID_IN, BS_RETAINED, OPEN, PAID)

REPORTING_CURRENCY = "USD"

_SM_WORDS = ("market", "sales", "advertis", "promot", "commission")
_RD_WORDS = ("research", "develop", "r&d", "engineer", "product")
_DEFERRED_WORDS = ("deferred", "unearned")
_RETAINED_WORDS = ("retained", "accumulated", "net income", "profit and loss")
_COGS_WORDS = ("cost of goods", "cogs", "cost of revenue", "cost of sales")
_CASH_WORDS = ("cash", "bank", "checking", "savings")


def _money(v):
    if v is None or v == "":
        return 0.0
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


def _is_num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _lc(s):
    return (s or "").strip().lower()


# --------------------------------------------------------------------------
# Company / account metadata
# --------------------------------------------------------------------------
def company_index(companies, default_country="United States"):
    """{company_name -> {entity_id, currency, country, name}}. entity_id is the
    Company abbreviation (ERPNext suffixes account names with it)."""
    out = {}
    for c in companies or []:
        name = c.get("company") or c.get("name") or ""
        abbr = c.get("abbr") or _abbr_from_name(name)
        out[name] = {
            "entity_id": abbr,
            "name": name,
            "currency": c.get("default_currency") or REPORTING_CURRENCY,
            "country": c.get("country") or default_country,
        }
    return out


def _abbr_from_name(name):
    return "".join(w[0] for w in (name or "X").split()).upper()[:5] or "X"


def account_meta(accounts):
    """{account key -> {root_type, account_type}} keyed by both `name` and
    `account_name` so report leaf rows can be routed even when they only carry
    one of them."""
    out = {}
    for a in accounts or []:
        meta = {"root_type": a.get("root_type", ""), "account_type": a.get("account_type", "")}
        for key in (a.get("name"), a.get("account_name")):
            if key:
                out[key] = meta
    return out


# --------------------------------------------------------------------------
# Account routing
# --------------------------------------------------------------------------
def canonical_code(root_type, account_type, name):
    """Route one ERPNext account -> canonical rollup code (or None to ignore)."""
    rt, at, n = _lc(root_type), _lc(account_type), _lc(name)
    if rt == "asset":
        if at in ("bank", "cash") or any(w in n for w in _CASH_WORDS):
            return BS_CASH
        if at == "receivable" or "receivable" in n:
            return BS_AR
        return BS_FIXED
    if rt == "liability":
        if any(w in n for w in _DEFERRED_WORDS):
            return BS_DEFERRED
        return BS_AP
    if rt == "equity":
        return BS_RETAINED if any(w in n for w in _RETAINED_WORDS) else BS_PAID_IN
    if rt == "income":
        return PNL_REVENUE
    if rt == "expense":
        if at == "cost of goods sold" or any(w in n for w in _COGS_WORDS):
            return PNL_COGS
        if any(w in n for w in _SM_WORDS):
            return PNL_SM
        if any(w in n for w in _RD_WORDS):
            return PNL_RD
        return PNL_GA
    return None


# --------------------------------------------------------------------------
# Financial-statement reports -> rolled-up rows per canonical code
# --------------------------------------------------------------------------
def _report_amount(row):
    """The leaf amount of a Frappe report row. Prefers an explicit 'amount';
    otherwise takes the last numeric value among the non-structural fields."""
    if "amount" in row:
        return _money(row["amount"])
    skip = {"indent", "is_group", "has_value", "parent_account", "account", "account_name",
            "root_type", "account_type", "currency", "company", "warn_if_negative"}
    nums = [_money(v) for k, v in row.items() if k not in skip and _is_num(v)]
    return nums[-1] if nums else 0.0


def _route_row(row, ameta):
    name = row.get("account") or row.get("account_name") or ""
    meta = ameta.get(name) or ameta.get(row.get("account_name")) or {}
    root_type = row.get("root_type") or meta.get("root_type")
    account_type = row.get("account_type") or meta.get("account_type")
    return canonical_code(root_type, account_type, name)


def _rollup_report(rows, ameta, keep_codes):
    agg = {}
    for r in rows or []:
        if str(r.get("is_group", 0)) in ("1", "True", "true"):
            continue
        code = _route_row(r, ameta)
        if code in keep_codes:
            agg[code] = round(agg.get(code, 0.0) + abs(_report_amount(r)), 2)
    return agg


def map_pnl_for_company(pl_rows, ameta, entity_id, period):
    agg = _rollup_report(pl_rows, ameta, {PNL_REVENUE, PNL_COGS, PNL_SM, PNL_RD, PNL_GA})
    return [{"entity_id": entity_id, "period": period, "account_code": code, "amount_local": agg[code]}
            for code in sorted(agg)]


def map_bs_for_company(bs_rows, ameta, entity_id, period):
    keep = {BS_CASH, BS_AR, BS_FIXED, BS_AP, BS_DEFERRED, BS_PAID_IN, BS_RETAINED}
    agg = _rollup_report(bs_rows, ameta, keep)
    return [{"entity_id": entity_id, "period": period, "account_code": code, "amount_local": agg[code]}
            for code in sorted(agg)]


def derive_trial_balance(pnl_rows, bs_rows, entity_id, period, currency):
    """Pre-closing canonical trial balance from the rolled-up P&L + balance sheet
    of ONE company. Same convention as the QuickBooks mapper: assets/expenses are
    debits; liabilities/equity/income are credits; retained earnings is rolled
    back by the period's net income so the result is not double-counted. Debits
    equal credits whenever the company's balance sheet foots."""
    debit_types = {"Asset", "Expense"}

    def _sum(rows, codes):
        return round(sum(float(r["amount_local"]) for r in rows if r["account_code"] in codes), 2)

    net_income = round(_sum(pnl_rows, (PNL_REVENUE,)) - _sum(pnl_rows, (PNL_COGS,))
                       - _sum(pnl_rows, PNL_EXPENSE_CODES), 2)
    rows = []
    for r in bs_rows + pnl_rows:
        code = r["account_code"]
        amt = round(float(r["amount_local"]), 2)
        if code == BS_RETAINED:
            amt = round(amt - net_income, 2)
        is_debit = COA_TYPE.get(code) in debit_types
        rows.append({"entity_id": entity_id, "period": period, "account_code": code,
                     "account_name": COA_NAME.get(code, ""),
                     "debit": amt if is_debit else 0.0,
                     "credit": 0.0 if is_debit else amt,
                     "currency": currency})
    return rows


# --------------------------------------------------------------------------
# FX (Currency Exchange -> units_per_usd per entity currency)
# --------------------------------------------------------------------------
def map_fx_rates(fx_raw, currencies, period):
    """One fx_rates row per currency used by an entity, as units_per_usd (local
    units per 1 USD). USD is 1. Others come from Currency Exchange rows, in either
    direction (USD->C or C->USD)."""
    per_usd = {REPORTING_CURRENCY: 1.0}
    for x in fx_raw or []:
        frm, to = (x.get("from_currency") or "").upper(), (x.get("to_currency") or "").upper()
        rate = _money(x.get("exchange_rate"))
        if rate <= 0:
            continue
        if frm == REPORTING_CURRENCY and to:
            per_usd[to] = rate                       # 1 USD = rate * to
        elif to == REPORTING_CURRENCY and frm:
            per_usd[frm] = round(1.0 / rate, 8)      # 1 frm = rate USD -> units_per_usd = 1/rate
    out = []
    for ccy in sorted(set(currencies) | {REPORTING_CURRENCY}):
        if ccy in per_usd:
            out.append({"period": period, "currency": ccy, "units_per_usd": _fmt(per_usd[ccy])})
    return out


def _fmt(x):
    return ("%.8f" % x).rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


# --------------------------------------------------------------------------
# Transactional / O2C DocType mappers (per company, document currency)
# --------------------------------------------------------------------------
def _eid(row, cidx):
    return (cidx.get(row.get("company"), {}) or {}).get("entity_id", row.get("company", ""))


def _status_outstanding(row):
    return OPEN if _money(row.get("outstanding_amount")) > 0 else PAID


def map_ar_invoices(sales_invoices, cidx):
    out = []
    for inv in sales_invoices or []:
        if str(inv.get("is_return", 0)) in ("1", "True", "true"):
            continue
        out.append({
            "invoice_id": inv.get("name", ""), "entity_id": _eid(inv, cidx),
            "customer": inv.get("customer") or inv.get("customer_name") or "",
            "currency": inv.get("currency") or REPORTING_CURRENCY,
            "amount_local": _money(inv.get("grand_total")),
            "issue_date": inv.get("posting_date", ""),
            "due_date": inv.get("due_date") or inv.get("posting_date", ""),
            "status": _status_outstanding(inv)})
    return out


def map_credit_notes(sales_invoices, cidx):
    out = []
    for inv in sales_invoices or []:
        if str(inv.get("is_return", 0)) not in ("1", "True", "true"):
            continue
        out.append({
            "credit_note_id": inv.get("name", ""), "entity_id": _eid(inv, cidx),
            "customer": inv.get("customer") or inv.get("customer_name") or "",
            "currency": inv.get("currency") or REPORTING_CURRENCY,
            "amount_local": abs(_money(inv.get("grand_total"))),
            "issue_date": inv.get("posting_date", ""),
            "against_invoice": inv.get("return_against", ""),
            "status": inv.get("status", "")})
    return out


def map_ap_invoices(purchase_invoices, cidx):
    out = []
    for b in purchase_invoices or []:
        out.append({
            "bill_id": b.get("name", ""), "entity_id": _eid(b, cidx),
            "vendor": b.get("supplier") or b.get("supplier_name") or "",
            "currency": b.get("currency") or REPORTING_CURRENCY,
            "amount_local": _money(b.get("grand_total")),
            "issue_date": b.get("posting_date", ""),
            "due_date": b.get("due_date") or b.get("posting_date", ""),
            "status": _status_outstanding(b)})
    return out


def map_payments(payment_entries, cidx):
    out = []
    for p in payment_entries or []:
        party_type = _lc(p.get("party_type"))
        applied = "AR" if party_type == "customer" else "AP" if party_type == "supplier" else ""
        out.append({
            "payment_id": p.get("name", ""), "entity_id": _eid(p, cidx),
            "party": p.get("party") or p.get("party_name") or "",
            "party_type": party_type or "",
            "currency": p.get("party_account_currency") or p.get("currency") or REPORTING_CURRENCY,
            "amount_local": _money(p.get("paid_amount") or p.get("received_amount")),
            "txn_date": p.get("posting_date", ""), "applied_to": applied})
    return out


def map_customers(customers, cidx):
    return [{"customer_id": c.get("name", ""), "entity_id": _eid(c, cidx),
             "name": c.get("customer_name") or c.get("name") or "",
             "currency": c.get("default_currency") or REPORTING_CURRENCY,
             "balance": _money(c.get("outstanding_amount"))}
            for c in customers or []]


def map_vendors(suppliers, cidx):
    return [{"vendor_id": s.get("name", ""), "entity_id": _eid(s, cidx),
             "name": s.get("supplier_name") or s.get("name") or "",
             "currency": s.get("default_currency") or REPORTING_CURRENCY,
             "balance": _money(s.get("outstanding_amount"))}
            for s in suppliers or []]


def map_journal_entries(gl_entries, accounts, cidx, period):
    ameta = account_meta(accounts)
    out = []
    for g in gl_entries or []:
        name = g.get("account", "")
        meta = ameta.get(name, {})
        code = canonical_code(meta.get("root_type"), meta.get("account_type"), name)
        if not code:
            continue
        out.append({
            "je_id": g.get("voucher_no") or g.get("name", ""), "entity_id": _eid(g, cidx),
            "period": period, "account_code": code,
            "debit": _money(g.get("debit")), "credit": _money(g.get("credit")),
            "currency": g.get("account_currency") or REPORTING_CURRENCY,
            "txn_date": g.get("posting_date", "")})
    return out


def map_opportunities(opportunities, cidx):
    return [{"opportunity_id": o.get("name", ""), "entity_id": _eid(o, cidx),
             "customer": o.get("party_name") or o.get("customer_name") or "",
             "currency": o.get("currency") or REPORTING_CURRENCY,
             "amount_local": _money(o.get("opportunity_amount")),
             "stage": o.get("sales_stage") or "", "status": o.get("status", ""),
             "opportunity_date": o.get("transaction_date", "")}
            for o in opportunities or []]


def map_quotations(quotations, cidx):
    return [{"quotation_id": q.get("name", ""), "entity_id": _eid(q, cidx),
             "customer": q.get("party_name") or q.get("customer_name") or "",
             "currency": q.get("currency") or REPORTING_CURRENCY,
             "amount_local": _money(q.get("grand_total")),
             "quotation_date": q.get("transaction_date", ""),
             "valid_till": q.get("valid_till", ""), "status": q.get("status", "")}
            for q in quotations or []]


def map_sales_orders(sales_orders, cidx):
    return [{"sales_order_id": s.get("name", ""), "entity_id": _eid(s, cidx),
             "customer": s.get("customer") or s.get("customer_name") or "",
             "currency": s.get("currency") or REPORTING_CURRENCY,
             "amount_local": _money(s.get("grand_total")),
             "order_date": s.get("transaction_date", ""),
             "delivery_date": s.get("delivery_date", ""), "status": s.get("status", "")}
            for s in sales_orders or []]


def map_collections_reminders(dunnings, payment_requests, cidx):
    out = []
    for d in dunnings or []:
        out.append({"reminder_id": d.get("name", ""), "entity_id": _eid(d, cidx),
                    "customer": d.get("customer") or "",
                    "currency": d.get("currency") or REPORTING_CURRENCY,
                    "amount_local": _money(d.get("outstanding_amount") or d.get("grand_total")),
                    "reminder_type": d.get("dunning_type") or "Dunning",
                    "reminder_date": d.get("posting_date", ""), "status": d.get("status", "")})
    for p in payment_requests or []:
        out.append({"reminder_id": p.get("name", ""), "entity_id": _eid(p, cidx),
                    "customer": p.get("party") or p.get("party_name") or "",
                    "currency": p.get("currency") or REPORTING_CURRENCY,
                    "amount_local": _money(p.get("grand_total")),
                    "reminder_type": "Payment Request",
                    "reminder_date": p.get("transaction_date", ""), "status": p.get("status", "")})
    return out


def map_cash_bank(bank_accounts, cidx):
    return [{"account_id": b.get("name", ""), "entity_id": _eid(b, cidx),
             "account_name": b.get("account_name") or b.get("account") or b.get("name", ""),
             "bank": b.get("bank") or "", "currency": b.get("account_currency") or REPORTING_CURRENCY,
             "balance": _money(b.get("balance"))}
            for b in bank_accounts or []]


# --------------------------------------------------------------------------
# Top-level: raw ERPNext responses -> full canonical table set
# --------------------------------------------------------------------------
def build_canonical(raw, period, default_country="United States"):
    """Transform one extraction's raw ERPNext responses into all canonical tables,
    across every Company (entity) in the extraction."""
    cidx = company_index(raw.get("companies"), default_country)
    accounts = raw.get("accounts", [])
    ameta = account_meta(accounts)
    reports = raw.get("reports", {}) or {}

    entities, pnl, bs, tb = [], [], [], []
    currencies = set()
    for company_name, meta in cidx.items():
        eid, ccy = meta["entity_id"], meta["currency"]
        currencies.add(ccy)
        entities.append({"entity_id": eid, "name": meta["name"],
                         "country": meta["country"], "currency": ccy})
        rep = reports.get(company_name, {}) or {}
        c_pnl = map_pnl_for_company(rep.get("profit_and_loss"), ameta, eid, period)
        c_bs = map_bs_for_company(rep.get("balance_sheet"), ameta, eid, period)
        pnl.extend(c_pnl)
        bs.extend(c_bs)
        tb.extend(derive_trial_balance(c_pnl, c_bs, eid, period, ccy))

    return {
        "entities": entities,
        "fx_rates": map_fx_rates(raw.get("fx_rates"), currencies, period),
        "chart_of_accounts": [dict(a) for a in CANONICAL_COA],
        "pnl_activity": pnl,
        "balance_sheet": bs,
        "budget": [],                # ERPNext budgets exist but are out of scope here (documented)
        "ar_invoices": map_ar_invoices(raw.get("sales_invoices"), cidx),
        "ap_invoices": map_ap_invoices(raw.get("purchase_invoices"), cidx),
        "tax_obligations": [],       # mapped from tax templates later if needed (documented)
        "trial_balance": tb,
        "payments": map_payments(raw.get("payment_entries"), cidx),
        "customers": map_customers(raw.get("customers"), cidx),
        "vendors": map_vendors(raw.get("suppliers"), cidx),
        "journal_entries": map_journal_entries(raw.get("gl_entries"), accounts, cidx, period),
        # --- Order-to-Cash extension tables (ERPNext fills these) ---
        "crm_opportunities": map_opportunities(raw.get("opportunities"), cidx),
        "quotations": map_quotations(raw.get("quotations"), cidx),
        "sales_orders": map_sales_orders(raw.get("sales_orders"), cidx),
        "credit_notes": map_credit_notes(raw.get("sales_invoices"), cidx),
        "collections_reminders": map_collections_reminders(
            raw.get("dunnings"), raw.get("payment_requests"), cidx),
        "cash_bank": map_cash_bank(raw.get("bank_accounts"), cidx),
    }


# --------------------------------------------------------------------------
# Independent ERP tie-out (sources/reconcile/): the ERP's native reports are the
# ANSWER KEY, and MY statements are recomputed from the GL - so for ERPNext the
# whole tie-out is independent (different derivation on each side), unlike a
# source whose canonical P&L/Balance are built from its own reports.
# Everything here is per Company (entity), in the company's local currency.
# --------------------------------------------------------------------------
def _statements_from_codes(net, period, entity_id, tb):
    """Build the vendor-neutral {pnl, balance, trial_balance} from a code->net map
    (net = debit - credit, i.e. debit-positive).

    The trial balance is PRE-closing (retained earnings at opening, P&L accounts
    still holding the period's activity), matching the ERP's TrialBalance report.
    The balance sheet is a CLOSING view, so retained earnings folds in the period's
    net income (RE_closing = RE_opening + net income) - exactly how the engine's TB
    is rolled back for QuickBooks. The two views are internally consistent."""
    def bal(code):
        return round(net.get(code, 0.0), 2)
    revenue, cogs = round(-bal(PNL_REVENUE), 2), bal(PNL_COGS)
    opex = round(bal(PNL_SM) + bal(PNL_RD) + bal(PNL_GA), 2)
    gross = round(revenue - cogs, 2)
    net_income = round(gross - opex, 2)
    cash, ar, fixed = bal(BS_CASH), bal(BS_AR), bal(BS_FIXED)
    ap, deferred = round(-bal(BS_AP), 2), round(-bal(BS_DEFERRED), 2)
    paid, retained_opening = round(-bal(BS_PAID_IN), 2), round(-bal(BS_RETAINED), 2)
    retained_closing = round(retained_opening + net_income, 2)   # balance sheet is closing
    return {
        "period": period, "entity_id": entity_id,
        "pnl": {"revenue": revenue, "cogs": cogs, "gross": gross, "opex": opex,
                "operating_income": net_income, "net_income": net_income},
        "balance": {"total_assets": round(cash + ar + fixed, 2),
                    "total_liabilities": round(ap + deferred, 2),
                    "total_equity": round(paid + retained_closing, 2),
                    "cash": cash, "ar": ar, "ap": ap},
        "trial_balance": tb,
    }


def compute_statements_from_gl(raw, company, entity_id, period):
    """BLIND compute: MY statements for one company, recomputed from GL Entry (the
    transactional ledger), NEVER from the ERP's native reports. Routes each GL
    account to a canonical code and nets debit-credit; the per-code net is the
    closing balance, from which the trial balance, P&L and balance sheet derive."""
    ameta = account_meta(raw.get("accounts"))
    net = {}
    for g in raw.get("gl_entries", []):
        if g.get("company") != company:
            continue
        name = g.get("account", "")
        meta = ameta.get(name, {})
        code = canonical_code(meta.get("root_type"), meta.get("account_type"), name)
        if not code:
            continue
        net[code] = round(net.get(code, 0.0) + _money(g.get("debit")) - _money(g.get("credit")), 2)
    tb = {code: {"debit": round(n, 2) if n >= 0 else 0.0, "credit": round(-n, 2) if n < 0 else 0.0}
          for code, n in net.items()}
    return _statements_from_codes(net, period, entity_id, tb)


def _map_native_tb_rows(tb_rows, ameta):
    """Native TrialBalance report rows -> {canonical_code: {debit, credit}}."""
    agg = {}
    for r in tb_rows or []:
        name = r.get("account") or r.get("account_name") or ""
        meta = ameta.get(name, {})
        code = canonical_code(r.get("root_type") or meta.get("root_type"),
                              r.get("account_type") or meta.get("account_type"), name)
        if not code:
            continue
        a = agg.setdefault(code, {"debit": 0.0, "credit": 0.0})
        a["debit"] = round(a["debit"] + _money(r.get("debit")), 2)
        a["credit"] = round(a["credit"] + _money(r.get("credit")), 2)
    return agg


def map_native_statements(raw, company, entity_id, period):
    """The ERP's OWN P&L / BalanceSheet / TrialBalance reports for one company,
    normalized into the vendor-neutral shape (the reconciler's answer key)."""
    ameta = account_meta(raw.get("accounts"))
    rep = (raw.get("reports") or {}).get(company, {}) or {}
    pnl = map_pnl_for_company(rep.get("profit_and_loss"), ameta, entity_id, period)
    bs = map_bs_for_company(rep.get("balance_sheet"), ameta, entity_id, period)
    tb = _map_native_tb_rows(rep.get("trial_balance"), ameta)

    def s(rows, codes):
        return round(sum(float(r["amount_local"]) for r in rows if r["account_code"] in codes), 2)

    revenue, cogs = s(pnl, (PNL_REVENUE,)), s(pnl, (PNL_COGS,))
    opex = s(pnl, (PNL_SM, PNL_RD, PNL_GA))
    cash, ar, fixed = s(bs, (BS_CASH,)), s(bs, (BS_AR,)), s(bs, (BS_FIXED,))
    ap, deferred = s(bs, (BS_AP,)), s(bs, (BS_DEFERRED,))
    paid, retained = s(bs, (BS_PAID_IN,)), s(bs, (BS_RETAINED,))
    gross = round(revenue - cogs, 2)
    oi = round(gross - opex, 2)
    return {
        "period": period, "entity_id": entity_id,
        "pnl": {"revenue": revenue, "cogs": cogs, "gross": gross, "opex": opex,
                "operating_income": oi, "net_income": oi},
        "balance": {"total_assets": round(cash + ar + fixed, 2),
                    "total_liabilities": round(ap + deferred, 2),
                    "total_equity": round(paid + retained, 2),
                    "cash": cash, "ar": ar, "ap": ap},
        "trial_balance": tb,
    }
