# sources/reconcile/ - independent ERP tie-out (software vs software)

Does my pipeline (canonical layer + `finance_core`) **reproduce the financial
statements the ERP itself generates?** This is a software-vs-software tie-out: the
answer key is **the ERP's own native reports**, not something I produce. Same
principle as `test-dlocal/` (compute blind, diff against an answer key, exit
non-zero on any break), but the source of truth is the ERP, not the SEC.

```
canonical data ─► finance_core computes my P&L / Balance / Trial Balance  (BLIND)
                                              │
ERP native ProfitAndLoss / BalanceSheet /     ├─► reconciler (reads BOTH) ─► PASS/FAIL per line
TrialBalance reports (the answer key) ────────┘        exit non-zero on any break
```

## The hard rule (independence)

The **compute path never sees the native reports.** `compute.py` runs
`finance_core` over the canonical CSVs only and imports nothing from the native
path. The **reconciler** (`run_reconcile.py` + `reconcile.py`) is the *only* thing
that reads both my computed statements and `connector.fetch_native_statements(...)`
and diffs them. Break that separation and the tie-out stops being independent.

## What it checks

- **Backbone: the trial balance.** Every canonical account's closing balance, mine
  (`finance_core.trial_balance_usd`) vs the ERP's native TrialBalance report
  (rolled into the same 12 canonical codes), debit and credit. If the TB ties, the
  statements derive by construction.
- **Statement-level cross-check:** P&L (revenue, COGS, gross profit, opex, operating
  income, net income) and Balance (total assets / liabilities / equity, plus cash,
  AR, AP subtotals).
- Both trial balances must **self-balance** (debits = credits); an unrouted or
  dropped account surfaces as a structural break, never absorbed.

**Tolerance: 0.01 USD absolute** (cent-level rounding only). The fixture ties at
delta 0.00 on every line. Sign conventions and the account/line grouping are
aligned by reusing the same deterministic account routing the canonical mapper
uses; any reclassification would show up as a per-line break, by design.

## Run

```bash
# Live (needs the source's read-only credentials in .env):
python sources/reconcile/run_reconcile.py --period 2026-05 --source quickbooks
# prints the PASS/FAIL table, writes an immutable snapshot, exits non-zero on any break.
```

Offline, deterministic test (in CI via `sources/tests/run_tests.py`):
`sources/tests/test_reconcile.py` reconciles the recorded QuickBooks fixture (a PASS
case where my statements reproduce the native reports) and a tamper case (break one
canonical account, the reconciler FAILS). No live instance, no secret.

## Snapshot

Each run writes an append-only immutable snapshot: my computed statements, the ERP's
raw native reports, the reconciliation table, period, company, source, timestamp,
and the `validation_result`.

## Vendor-neutral by design

`fetch_native_statements(period, company)` and `reconcile_units(period)` are on the
`SourceConnector` interface, so the reconciler core does not change per vendor:

- **QuickBooks** (single entity): one unit. The compute side is `finance_core` over
  the canonical, which is built from QuickBooks' P&L/Balance reports, so the
  P&L/Balance lines are a **regression guard**; the trial balance is the
  independent cross-report check.
- **ERPNext** (multi-company / multi-currency): one unit per company, each
  reconciled in its local currency. The compute side recomputes each company's
  statements **from the GL** (`compute_statements_from_gl`), independently of
  ERPNext's reports, so **every line - P&L, Balance and trial balance - is an
  independent cross-check.** The output labels each line accordingly.

## Honest boundary

- This validates **integration + mapping + compute** against a SECOND, independent
  engine (the ERP's report engine) on **sandbox / seeded data**, not against the
  books of a production company. It is a software-vs-software tie-out, **not an
  external or statutory audit.**
- For QuickBooks, the canonical P&L / Balance are themselves built from QuickBooks'
  P&L / BalanceSheet reports, so those statement-level lines are primarily a
  **mapping + recompute regression guard** (they tie by construction unless the
  mapping or `finance_core` drifts). The **trial-balance backbone is the genuine
  cross-report check**: my TB is derived from the P&L + Balance, and it must agree
  with QuickBooks' *separate* TrialBalance report, account by account.
- **ERPNext is the fully-independent case:** its compute side is recomputed from
  the GL, not from ERPNext's reports, so the P&L, Balance AND trial balance are all
  independent cross-checks against ERPNext's own reports (per company, local
  currency). This is the tie-out at full strength.
- The committed fixture is **representative** (modeled on Intuit's documented report
  shapes); `sources/quickbooks/record_fixture.py` captures a real one.
