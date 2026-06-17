# Real-data test: CFO model vs dLocal (NASDAQ: DLO)

Tests the CFO multi-agent model on dLocal's real, audited public financials (FY2024 and FY2025), then audits the result independently. Built from dLocal's SEC Form 6-K earnings releases. FY2025 full-year figures are audited. Amounts in thousands of USD; dLocal reports in USD under IFRS, so no FX conversion is needed.

## Why this is a real audit, not the model grading itself

The independence does not come from who runs the comparison. It comes from two things:

1. The ground truth is dLocal's reported, audited numbers. Their audit firm signed them. They are external and fixed. Neither the model nor Claude Code produces them.
2. The model's figures are computed by deterministic code (finance_core), not narrated by the LLM. There is no opinion to bend toward an answer.

On top of that, the exercise is split like a real audit, so the preparer and the auditor are not the same context:

- Step 1 (1_RUN_PROMPT.md): the model runs BLIND. It loads the inputs and computes its numbers into model_output.csv. It is told not to open the answer key.
- Step 2 (2_AUDIT_PROMPT.md): a SEPARATE, fresh Claude Code chat compares model_output.csv to EXPECTED_from_dLocal_SEC_filings.csv and to the primary filings. It does not run the model.

The model that runs never sees the target, so it cannot steer the result. The audit just diffs two fixed files and re-checks against the source.

(Inside the model, you still have your own three lines: the operating agents compute, internal controls and cross-checks test consistency, and the independent Audit agent re-derives from source. Those are internal. This pack adds the external validation against the real world.)

## How to run

1. In Claude Code, paste 1_RUN_PROMPT.md and let it run. It creates load_dlocal.py and model_output.csv.
2. Open a NEW Claude Code chat and paste 2_AUDIT_PROMPT.md. It prints the PASS/FAIL table.

If you would rather be the auditor yourself: after Step 1, open model_output.csv next to EXPECTED_from_dLocal_SEC_filings.csv and compare. The human as third line is the most independent option of all.

## Files

- entities.csv, fx_rates.csv, pnl_activity.csv, balance_sheet.csv, budget.csv, kpis_reference.csv : the inputs the model consumes.
- EXPECTED_from_dLocal_SEC_filings.csv : dLocal's reported figures (the answer key). Used only in Step 2.
- 1_RUN_PROMPT.md / 2_AUDIT_PROMPT.md : the two steps.
- model_output.csv : created by Step 1 (the model's computed numbers).

## Sources (primary)

- dLocal 4Q/FY2025 earnings release (Form 6-K, filed 2026-03-18): https://www.sec.gov/Archives/edgar/data/0001846832/000207097926000110/a991dlocal4q25_earningsres.htm
- dLocal 4Q/FY2024 earnings release (Form 6-K, filed 2025-02-27): https://www.sec.gov/Archives/edgar/data/0001846832/000095017025029045/dlo-ex99_1.htm
- All dLocal SEC filings (CIK 0001846832): https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001846832&type=6-K
