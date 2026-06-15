"""
credit_core.py - Deterministic credit / loan-book engine for the LendingClub track.

Same philosophy as finance_core.py: this module computes the NUMBERS (no prose) so
the credit agents can reason and narrate without ever inventing a figure. One
source of data: ../lendingclub-data. The engine looks for the real Kaggle files
first and falls back to the seeded sample, so it runs today and points at real
data the moment the real CSVs are dropped in.

SCALE: the real accepted_2007_to_2018Q4.csv is ~1.6 GB / ~2.2M rows. The engine
reads it in a SINGLE STREAMING PASS (csv.DictReader is a lazy iterator — we never
materialize the file into a list), accumulating only aggregates keyed by grade,
term, vintage and status. Memory is O(buckets), not O(rows), so the full real loan
book runs on a laptop. The one O(rows) structure is the set of loan ids used for
duplicate detection (~200 MB at full scale). Set env LC_MAX_ROWS to cap the scan
for fast iteration (off by default — the real test runs on the full file).

Function families (one per downstream agent):
  ingestion_summary()      -> Source Ingestion Agent
  data_quality()           -> Data Quality & Schema Agent
  provenance()             -> Source Traceability Agent
  portfolio_metrics()      -> Loan Portfolio Agent
  credit_risk()            -> Credit Risk / Losses Agent
  unit_economics()         -> Revenue & Unit Economics Agent
  benchmark_vs_filings()   -> Public Benchmark + Variance & Explainability Agents
  model_risk_review()      -> Model Risk / Audit Agent

Proxies (origination-fee rate, LGD floors, expected-loss formula) are documented
and conservative; they are clearly flagged as proxies for the model-risk layer.
"""

import csv
import os
import re

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lendingclub-data")

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
GRADES = ["A", "B", "C", "D", "E", "F", "G"]

# Documented PROXY: LendingClub origination fee by grade (a stand-in for the real
# fee schedule; flagged as a proxy to the model-risk layer).
_ORIG_FEE = {"A": 0.02, "B": 0.03, "C": 0.04, "D": 0.05, "E": 0.05, "F": 0.06, "G": 0.06}

# Statuses that represent a resolved (matured) outcome vs. still on the book.
_RESOLVED = {"Fully Paid", "Charged Off"}
_DELINQUENT = {"Late (31-120 days)", "Late (16-30 days)", "Default",
               "In Grace Period", "Charged Off"}

_KEY_COLS = ["loan_amnt", "int_rate", "grade", "loan_status", "issue_d"]
_REQUIRED_ACC = ["id", "loan_amnt", "funded_amnt", "term", "int_rate", "grade",
                 "issue_d", "loan_status", "total_rec_prncp", "total_rec_int", "recoveries"]


# --- parsing helpers (tolerant; the real file is large and messy) ----------

def _f(x, default=0.0):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return default


def _rate(x):
    return _f(str(x).replace("%", "")) / 100.0


def _term(x):
    s = "".join(c for c in str(x) if c.isdigit())
    return int(s) if s else 0


def _year(issue_d):
    """Robust 4-digit year from LendingClub issue_d shapes: 'Dec-2015', 'Dec-15',
    bare '2015', ISO '2015-12'. Returns None if no year can be found."""
    s = str(issue_d).strip()
    m = re.search(r"(?:19|20)\d{2}", s)        # explicit 4-digit year anywhere
    if m:
        return int(m.group())
    m2 = re.search(r"-(\d{2})$", s)            # 'Mon-YY' two-digit year (LC is 2007+)
    if m2:
        return 2000 + int(m2.group(1))
    return None


# Real LC files prefix some terminal statuses with this; strip it so the
# resolved/charged/delinquent classification matches (e.g. "Does not meet the
# credit policy. Status:Charged Off" -> "Charged Off").
def _status(r):
    s = str(r.get("loan_status", "")).strip()
    if s.startswith("Does not meet the credit policy") and "Status:" in s:
        return s.split("Status:", 1)[1].strip()
    return s


# --- pick the data files (real first, sample fallback) ---------------------

def _pick(names):
    for n in names:
        if os.path.exists(os.path.join(DATA, n)):
            return os.path.join(DATA, n), n
    return os.path.join(DATA, names[-1]), names[-1]


_ACC_PATH, ACCEPTED_FILE = _pick(["accepted_2007_to_2018Q4.csv", "accepted_sample.csv"])
_REJ_PATH, REJECTED_FILE = _pick(["rejected_2007_to_2018Q4.csv", "rejected_sample.csv"])


def _load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_FIL = _load("public_filings.csv")
FILINGS_FILE = "public_filings.csv" if _FIL else None


# --- the single streaming pass: accumulate every aggregate the agents need --

def _new_agg():
    return {
        "n": 0, "columns": set(), "capped": False,
        "sum_funded": 0.0, "sum_funded_rate": 0.0, "sum_int_income": 0.0,
        "sum_total_pymnt": 0.0, "sum_fees": 0.0,
        "matured": 0, "charged": 0, "onbook_n": 0, "onbook_outstanding": 0.0,
        "delinquent": 0, "charged_off_usd": 0.0,
        "dup": 0, "miss": {c: 0 for c in _KEY_COLS}, "bad_dates": 0,
        "outliers": 0, "rate_bad": 0,
        "g_funded": {}, "g_matured": {}, "g_charged": {},
        "g_co_prncp": {}, "g_recov": {}, "g_onbook_out": {},
        "t_funded": {}, "by_status": {},
        "y_funded": {}, "y_received": {}, "y_int_income": {},
        "y_count": {}, "y_funded_rate": {}, "y_matured": {}, "y_charged": {},
        "rej_n": 0, "rej_sum": 0.0,
    }


def _scan():
    a = _new_agg()
    seen = set()
    cap = int(os.environ.get("LC_MAX_ROWS", "0") or 0)

    if os.path.exists(_ACC_PATH):
        with open(_ACC_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            a["columns"] = set(reader.fieldnames or [])
            for r in reader:
                if cap and a["n"] >= cap:
                    a["capped"] = True
                    break
                a["n"] += 1
                rid = r.get("id")
                if rid:
                    if rid in seen:
                        a["dup"] += 1
                    else:
                        seen.add(rid)
                for c in _KEY_COLS:
                    if not str(r.get(c, "")).strip():
                        a["miss"][c] += 1
                funded = _f(r.get("funded_amnt"))
                rate = _rate(r.get("int_rate"))
                amt = _f(r.get("loan_amnt"))
                if amt <= 0 or amt > 100000:
                    a["outliers"] += 1
                if not (0 < rate < 0.5):
                    a["rate_bad"] += 1
                g = r.get("grade", "?")
                term = _term(r.get("term"))
                y = _year(r.get("issue_d"))
                if y is None:
                    a["bad_dates"] += 1
                st = _status(r) or "?"
                rec_prncp = _f(r.get("total_rec_prncp"))
                recov = _f(r.get("recoveries"))
                rec_int = _f(r.get("total_rec_int"))
                tot_pymnt = _f(r.get("total_pymnt"))

                a["sum_funded"] += funded
                a["sum_funded_rate"] += funded * rate
                a["sum_int_income"] += rec_int
                a["sum_total_pymnt"] += tot_pymnt
                a["sum_fees"] += funded * _ORIG_FEE.get(g, 0.04)
                a["g_funded"][g] = a["g_funded"].get(g, 0.0) + funded
                a["t_funded"][term] = a["t_funded"].get(term, 0.0) + funded
                a["by_status"][st] = a["by_status"].get(st, 0) + 1
                # By-year buckets only for rows with a parseable vintage; bad-date
                # rows (e.g. LendingClub's trailing junk rows) are flagged by DQ and
                # kept out of the vintage analytics (no None key downstream).
                if y is not None:
                    a["y_funded"][y] = a["y_funded"].get(y, 0.0) + funded
                    a["y_received"][y] = a["y_received"].get(y, 0.0) + tot_pymnt
                    a["y_int_income"][y] = a["y_int_income"].get(y, 0.0) + rec_int
                    a["y_count"][y] = a["y_count"].get(y, 0) + 1
                    a["y_funded_rate"][y] = a["y_funded_rate"].get(y, 0.0) + funded * rate

                if st in _RESOLVED:
                    a["matured"] += 1
                    a["g_matured"][g] = a["g_matured"].get(g, 0) + 1
                    if y is not None:
                        a["y_matured"][y] = a["y_matured"].get(y, 0) + 1
                    if st == "Charged Off":
                        a["charged"] += 1
                        a["g_charged"][g] = a["g_charged"].get(g, 0) + 1
                        if y is not None:
                            a["y_charged"][y] = a["y_charged"].get(y, 0) + 1
                        a["g_co_prncp"][g] = a["g_co_prncp"].get(g, 0.0) + (funded - rec_prncp)
                        a["g_recov"][g] = a["g_recov"].get(g, 0.0) + recov
                        a["charged_off_usd"] += (funded - rec_prncp)
                else:
                    a["onbook_n"] += 1
                    out = max(0.0, funded - rec_prncp)
                    a["onbook_outstanding"] += out
                    a["g_onbook_out"][g] = a["g_onbook_out"].get(g, 0.0) + out
                    if st in _DELINQUENT and st != "Charged Off":
                        a["delinquent"] += 1

    # Rejected file: stream a count + sum only (it can be very large).
    if os.path.exists(_REJ_PATH):
        with open(_REJ_PATH, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if cap and a["rej_n"] >= cap:
                    break
                a["rej_n"] += 1
                a["rej_sum"] += _f(r.get("Amount Requested"))
    return a


_CACHE = None


def _agg():
    """Scan once, cache. The first call that needs the numbers triggers the pass."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _scan()
    return _CACHE


# --- Source Ingestion ------------------------------------------------------

def ingestion_summary():
    a = _agg()
    years = sorted(y for y in a["y_funded"] if y is not None)
    return {
        "accepted_file": ACCEPTED_FILE, "rejected_file": REJECTED_FILE,
        "filings_file": FILINGS_FILE,
        "accepted_rows": a["n"], "rejected_rows": a["rej_n"], "filing_rows": len(_FIL),
        "vintage_years": years, "is_real_data": not ACCEPTED_FILE.endswith("_sample.csv"),
        "capped": a["capped"],
    }


# --- Data Quality & Schema -------------------------------------------------

def data_quality():
    a = _agg()
    n = a["n"] or 1
    checks = []
    missing_cols = [c for c in _REQUIRED_ACC if c not in a["columns"]]
    checks.append({"id": "DQ1", "name": "Required columns present",
                   "status": "PASS" if not missing_cols else "FAIL",
                   "detail": "all present" if not missing_cols else f"missing: {missing_cols}"})
    checks.append({"id": "DQ2", "name": "No duplicate loan ids",
                   "status": "PASS" if a["dup"] == 0 else "FAIL",
                   "detail": f"{a['dup']} duplicate id(s)"})
    worst = max(a["miss"].values()) if a["miss"] else 0
    checks.append({"id": "DQ3", "name": "Missing values in key fields",
                   "status": "PASS" if worst == 0 else ("WARN" if worst / n < 0.05 else "FAIL"),
                   "detail": ", ".join(f"{c}={v}" for c, v in a["miss"].items())})
    checks.append({"id": "DQ4", "name": "Valid issue dates",
                   "status": "PASS" if a["bad_dates"] == 0 else "WARN",
                   "detail": f"{a['bad_dates']} unparseable issue_d"})
    checks.append({"id": "DQ5", "name": "Loan amount within bounds (0, 100k]",
                   "status": "PASS" if a["outliers"] == 0 else ("WARN" if a["outliers"] / n < 0.05 else "FAIL"),
                   "detail": f"{a['outliers']} outlier amount(s)"})
    checks.append({"id": "DQ6", "name": "Interest rate within (0%, 50%)",
                   "status": "PASS" if a["rate_bad"] == 0 else ("WARN" if a["rate_bad"] / n < 0.05 else "FAIL"),
                   "detail": f"{a['rate_bad']} out-of-range rate(s)"})
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    n_warn = sum(1 for c in checks if c["status"] == "WARN")
    return {"checks": checks, "n_pass": sum(1 for c in checks if c["status"] == "PASS"),
            "n_warn": n_warn, "n_fail": n_fail, "rows_checked": a["n"], "clean": n_fail == 0}


# --- Source Traceability ---------------------------------------------------

def provenance():
    return {
        "source_file": ACCEPTED_FILE,
        "metrics": {
            "originations": {"file": ACCEPTED_FILE, "columns": ["funded_amnt", "issue_d"],
                             "filter": "all accepted loans"},
            "charge_off_rate": {"file": ACCEPTED_FILE, "columns": ["loan_status"],
                                "filter": "loan_status in {Fully Paid, Charged Off}"},
            "interest_income": {"file": ACCEPTED_FILE, "columns": ["total_rec_int"],
                                "filter": "all accepted loans"},
            "expected_loss": {"file": ACCEPTED_FILE,
                              "columns": ["funded_amnt", "total_rec_prncp", "grade", "loan_status"],
                              "filter": "on-book loans (not resolved), PD by grade x LGD"},
            "approval_rate": {"file": f"{ACCEPTED_FILE} + {REJECTED_FILE}",
                              "columns": ["count"], "filter": "accepted / (accepted + rejected)"},
        },
        "proxies": {
            "origination_fee": "grade-based fee schedule (A 2% … G 6%) — PROXY, not a disclosure",
            "expected_loss": "realized PD by grade x LGD (1 - recovery rate) x outstanding — PROXY",
        },
    }


# --- Loan Portfolio --------------------------------------------------------

def portfolio_metrics():
    a = _agg()
    total = a["sum_funded"]
    n = a["n"] or 1
    return {
        "n_loans": a["n"], "originations_usd": total, "avg_loan_usd": total / n,
        "wair": (a["sum_funded_rate"] / total) if total else 0.0,
        "by_grade_usd": {g: a["g_funded"].get(g, 0.0) for g in GRADES},
        "by_term_usd": dict(a["t_funded"]), "by_vintage_usd": dict(a["y_funded"]),
        "status_counts": dict(a["by_status"]),
    }


# --- Credit Risk / Losses --------------------------------------------------

def credit_risk():
    a = _agg()
    co_rate = a["charged"] / (a["matured"] or 1)

    pd_grade, lgd_grade = {}, {}
    lgd_clamped = 0
    for g in GRADES:
        gm, gc = a["g_matured"].get(g, 0), a["g_charged"].get(g, 0)
        pd_grade[g] = (gc / gm) if gm else 0.0
        co_prncp, recov = a["g_co_prncp"].get(g, 0.0), a["g_recov"].get(g, 0.0)
        if co_prncp > 0:
            raw = 1 - (recov / co_prncp)
            if raw < 0 or raw > 1:
                lgd_clamped += 1
            lgd_grade[g] = max(0.0, min(1.0, raw))
        else:
            lgd_grade[g] = 0.55

    # Expected loss on the ON-BOOK loans, summed by grade: outstanding x PD x LGD.
    el = sum(out * pd_grade.get(g, co_rate) * lgd_grade.get(g, 0.55)
             for g, out in a["g_onbook_out"].items())
    outstanding_total = a["onbook_outstanding"]

    return {
        "n_matured": a["matured"], "n_charged_off": a["charged"],
        "charge_off_rate": co_rate, "charged_off_usd": a["charged_off_usd"],
        "pd_by_grade": pd_grade, "lgd_by_grade": lgd_grade,
        "lgd_clamped_grades": lgd_clamped,
        "n_onbook": a["onbook_n"], "onbook_outstanding_usd": outstanding_total,
        "expected_loss_usd": el,
        "expected_loss_pct": (el / outstanding_total) if outstanding_total else 0.0,
        "n_delinquent": a["delinquent"],
        "delinquency_rate": a["delinquent"] / (a["onbook_n"] or 1),
    }


# --- Revenue & Unit Economics ----------------------------------------------

def unit_economics():
    a = _agg()
    funded = a["sum_funded"]
    int_income, fees = a["sum_int_income"], a["sum_fees"]
    cohorts = {}
    for y in a["y_funded"]:
        fu, re_ = a["y_funded"][y], a["y_received"].get(y, 0.0)
        cohorts[y] = {"funded_usd": fu, "received_usd": re_, "net_usd": re_ - fu,
                      "cash_on_cash": (re_ / fu) if fu else 0.0}
    return {
        "interest_income_usd": int_income, "origination_fees_usd": fees,
        "total_revenue_proxy_usd": int_income + fees,
        "yield_realized": (int_income / funded) if funded else 0.0,
        "take_rate": (fees / funded) if funded else 0.0,
        "net_cash_to_date_usd": a["sum_total_pymnt"] - funded,
        "cohorts": cohorts,
    }


# --- Rejection / approval --------------------------------------------------

def approval_metrics():
    a = _agg()
    na, nr = a["n"], a["rej_n"]
    total = na + nr
    return {"accepted": na, "rejected": nr,
            "approval_rate": (na / total) if total else 0.0,
            "avg_requested_rejected_usd": (a["rej_sum"] / nr) if nr else 0.0}


# --- Public Benchmark + Variance -------------------------------------------

def _computed_for(metric, period):
    """Compute a metric for a filing period (a year, or 'ALL') from the aggregates."""
    a = _agg()
    allp = period in ("ALL", "", None)
    yr = None if allp else int(period) if str(period).isdigit() else period
    if metric == "originations_usd":
        return a["sum_funded"] if allp else a["y_funded"].get(yr, 0.0)
    if metric == "interest_income_usd":
        return a["sum_int_income"] if allp else a["y_int_income"].get(yr, 0.0)
    if metric == "loan_count":
        return float(a["n"]) if allp else float(a["y_count"].get(yr, 0))
    if metric == "avg_interest_rate":
        fr = a["sum_funded_rate"] if allp else a["y_funded_rate"].get(yr, 0.0)
        fu = a["sum_funded"] if allp else a["y_funded"].get(yr, 0.0)
        return (fr / fu) if fu else 0.0
    if metric == "charge_off_rate":
        mat = a["matured"] if allp else a["y_matured"].get(yr, 0)
        co = a["charged"] if allp else a["y_charged"].get(yr, 0)
        return (co / mat) if mat else 0.0
    return None


def benchmark_vs_filings():
    # The public-filing values are REAL LendingClub 10-K/8-K figures, so the
    # benchmark is only meaningful against the REAL loan book. On the seeded sample
    # there is nothing real to reconcile — skip it rather than report nonsense drift.
    if not _FIL:
        return {"rows": [], "n": 0, "max_abs_var_pct": 0.0,
                "skipped": "no public_filings.csv loaded"}
    if ACCEPTED_FILE.endswith("_sample.csv"):
        return {"rows": [], "n": 0, "max_abs_var_pct": 0.0,
                "skipped": "benchmark runs on real data only (load the real Kaggle CSV to benchmark vs filings)"}
    out = []
    for r in _FIL:
        metric, period = r.get("metric"), r.get("period")
        filed = _f(r.get("value"))
        computed = _computed_for(metric, period)
        if computed is None:
            continue
        var = computed - filed
        out.append({"metric": metric, "period": period, "filed": filed,
                    "computed": computed, "var": var,
                    "var_pct": (var / filed * 100) if filed else 0.0,
                    "source_doc": r.get("source_doc", ""), "note": r.get("note", "")})
    return {"rows": out, "n": len(out),
            "max_abs_var_pct": max((abs(x["var_pct"]) for x in out), default=0.0)}


# --- Model Risk / Audit ----------------------------------------------------

def model_risk_review():
    """Red-flag review of the credit MODEL itself (not a re-run of other functions'
    risks): data realness, reliance on documented proxies, and proxy stress.
    Data-quality failures and benchmark drift are owned and escalated by the Data
    Quality and Variance functions and are NOT re-escalated here, so the CFO sees
    each risk from a single owner."""
    ing = ingestion_summary()
    cr = credit_risk()
    flags = []
    if not ing["is_real_data"]:
        flags.append(["HIGH", "running on the seeded SAMPLE, not the real LendingClub files"])
    if ing.get("capped"):
        flags.append(["MEDIUM", f"scan capped at LC_MAX_ROWS ({ing['accepted_rows']} rows) — not the full book"])
    flags.append(["MEDIUM", "expected-loss and fee figures use documented PROXIES, not disclosures"])
    if not _FIL:
        flags.append(["MEDIUM", "no public-filing benchmark loaded (public_filings.csv empty)"])
    if cr.get("lgd_clamped_grades", 0) > 0:
        flags.append(["MEDIUM",
                      f"LGD recovery rate clamped for {cr['lgd_clamped_grades']} grade(s) — possible data issue"])
    return {"flags": flags, "n_flags": len(flags),
            "assumptions": ["realized PD by grade", "LGD = 1 - recovery rate",
                            "origination fee = grade-based proxy",
                            "Default and other late statuses are treated as on-book exposures "
                            "(outstanding x PD x LGD), not as realized/near-certain losses"],
            "limitations": ["sample unless real files dropped",
                            "data-quality failures and benchmark drift are owned by the Data "
                            "Quality and Variance functions",
                            "no macroeconomic overlay", "no forward-looking ECL staging"]}
