# O2C Control Tower - Interview Script

A ready-to-use explanation of the Revenue Operations / Order-to-Cash control tower
([`cfo-office/o2c/`](README.md)), at three depths, plus business impact and demo
commands.

---

## A. 60-second explanation

> I built this as an agent-first but human-led Finance Operations / O2C control
> tower. The agents don't invent numbers. The financial logic is deterministic.
> The agents diagnose exceptions, prioritize workflows, route approvals, and
> generate executive-ready reporting. Hard controls block reporting when CRM,
> billing, revenue recognition, AR, cash application, bank, or deferred revenue do
> not tie out.

To make it concrete I ship two periods on identical controls: a problematic month
that gets blocked with an adverse audit opinion, and a clean month where the data
ties out and reporting is released. Same code, same thresholds, only the data
differs.

---

## B. 3-minute walkthrough

**Start with the data.** There are 15 datasets that form one relational chain:
customer master, CRM opportunities, contracts, sales orders, billing schedule,
invoices, credit memos, payments, bank receipts, cash application, revenue
schedule, deferred revenue rollforward, collections activity, disputes, and credit
limits. Multi-entity, multi-region (NA / EMEA / LATAM), multi-currency, all
consolidated to USD with an explicit FX table.

**The O2C chain.** The data traces the full order-to-cash flow: CRM opportunity to
contract to sales order to billing schedule to invoice to revenue recognition to
AR to collections to payment to bank receipt to cash application to GL and
reporting. Each handoff is a place where money or revenue can leak, so each handoff
has a control.

**Why a blocked period and a clean period.** I generate `2026-05` with seeded
exceptions (unbilled work, invoice mismatches, duplicate invoices, unapplied cash,
revenue cutoff errors, deferred breaks, credit-limit breaches, and more) so the
tower catches them and blocks reporting. I generate `2026-06` clean, where the
source data ties out, so the same controls pass. I did not relax thresholds to get
the pass; the controls are identical across both periods. That is the whole point:
the gate reflects the data, not a tuned switch.

**Maker/checker controls.** Every workflow has a maker (an agent that does the
analysis) and a checker (the domain expert who signs it off). There are 15 hard
controls that block reporting and 10 soft controls that route work. A hard failure
sets the run to BLOCKED and exits non-zero in CI. Human approvals are recorded in
the audit trail; in batch runs they auto-approve and are explicitly marked as auto,
never passed off as a human sign-off.

**What each agent owns.** Order Intake owns CRM-to-order conversion; Customer
Master owns data quality; Contract owns terms and renewal risk; Billing owns
completeness, accuracy, timeliness, and leakage; Revenue Recognition owns cutoff
and deferred rollforward; Collections owns aging, the cash forecast, and risk
scoring; Cash Application owns the bank-to-AR tie-out and unapplied cash;
Disputes & Credit owns blocked cash, credit breaches, and hold violations; RevOps
Analytics owns the bookings-to-cash bridge and the board narrative; and the O2C
Audit agent independently re-performs the tie-outs and issues an opinion.

**The board pack.** The orchestrator produces an executive summary, a board pack
(narrative, bookings-to-cash bridge, AR aging, collections risk, billing accuracy,
revenue issues, cash issues, control failures, and an owner/action/date table), a
workflow map, plus machine-readable control results, metrics, exceptions, agent
findings, and the audit trail.

**How it maps to the function.** Billing -> the Billing agent and the billing
controls. Collections -> the Collections agent, aging, and the cash forecast.
RevOps -> the analytics bridge and conversion bottlenecks. Reconciliations -> the
AR subledger, cash, and deferred tie-outs. Close support -> the hard gate that
blocks reporting until everything ties. Reporting -> the executive summary and
board pack. Controls -> the 25-control framework and the audit trail. Finance
Operations -> the whole governed, auditable loop.

---

## C. Technical walkthrough

- **Data loader** (`o2c_data_loader.py`): loads the 15 CSVs for a period from
  `data/<period>/`, enforces the schema contract (fails loudly on a missing column),
  parses dates, and adds USD-normalized columns from the FX table.
- **Deterministic core** (`o2c_core.py`): the only place business numbers are
  computed - open AR and aging, billing completeness/accuracy/timeliness, cash
  application, revenue recognition and the deferred rollforward, credit exposure,
  the collections forecast, DSO, and the bookings-to-cash bridge. Every function
  returns explicit columns traceable to source rows.
- **Metrics** (`o2c_metrics.py`): a 35-metric framework; each metric carries its
  definition, source tables, owner, threshold, and a status band (OK / REVIEW /
  URGENT / CRITICAL).
- **Controls** (`o2c_controls.py`): 15 hard + 10 soft controls, each a
  `ControlResult` with failing records, failing amount, owner/checker, recommended
  action, and a `blocks_reporting` flag. Each control re-derives its answer; it
  never trusts a pre-computed number.
- **Agents** (`agents/`): 10 deterministic maker classes over a shared base and
  context. No LLM, no API key. Each produces structured findings, escalations, a
  templated narrative, and recommended actions.
- **Orchestrator** (`o2c_orchestrator.py`): load -> validate -> calculate ->
  controls -> agents + maker/checker -> hard gate -> metrics -> outputs.
- **Audit trail** (`outputs/o2c_audit_trail.json`): run id, timestamp, period,
  inputs and record counts, calculations, controls, agents, hard failures, soft
  warnings, approvals required, audit score and opinion, output files, and final
  status.
- **Output artifacts** (`outputs/`): `o2c_control_results.csv`, `o2c_metrics.csv`,
  `o2c_exceptions.csv`, `o2c_agent_findings.json`, `o2c_audit_trail.json`,
  `o2c_executive_summary.md`, `o2c_board_pack.md`, `o2c_workflow_map.md`.
- **Tests** (`tests/`): data integrity (existence, schema, keys, no dangling FKs),
  controls catch the seeded exceptions, billing completeness, cash application,
  revenue recognition, collections risk scoring, the two-period scenarios, and that
  the orchestrator generates every output. Runs under pytest or the bundled runner.

---

## D. Business impact

- **Reduces manual reconciliation:** CRM, billing, revenue, cash, bank, and AR tie
  out in code, not in spreadsheets.
- **Catches billing leakage:** unbilled-but-due work and invoice mismatches are
  quantified the moment they occur.
- **Improves cash conversion:** unapplied cash and stuck AR are surfaced and ranked,
  shortening DSO.
- **Identifies collections risk:** a deterministic risk score ranks the accounts to
  work first, and disputed cash is routed out of the forecast.
- **Improves close readiness:** reporting cannot be released until the subledgers
  tie to the control accounts.
- **Creates auditability:** every number traces to source rows, every decision is
  recorded, and an independent agent re-performs and issues an opinion.
- **Gives leadership decision-useful reporting:** a board pack with the
  bookings-to-cash bridge, the top issues, and an owner/action/date plan.

---

## E. Demo commands

```
# headline for the default (problematic) period
python run_o2c_control_tower.py

# side-by-side: problematic 2026-05 vs clean 2026-06
python run_o2c_control_tower.py --compare

# full run per period (writes all 8 outputs)
python cfo-office/o2c/o2c_orchestrator.py --period 2026-05    # BLOCKED_HARD_CONTROLS
python cfo-office/o2c/o2c_orchestrator.py --period 2026-06    # PASS_WITH_WARNINGS

# tests (pytest if available, else the bundled runner)
python -m pytest cfo-office/o2c/tests
python cfo-office/o2c/tests/run_tests.py
```
