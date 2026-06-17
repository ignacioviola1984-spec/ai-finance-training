# dLocal reproducibility and dual-model AI-assisted external audit

**Date:** 2026-06-17

This document records the reproducibility evidence for the dLocal statement-level test and the dual-model AI-assisted external audit behind it. As defined below, that phrase is used in the engineering sense; it is not a formal external or statutory audit, a certification, an assurance opinion, or a substitute for a human auditor. It describes what was reproduced, what was checked, and the boundary of what the evidence supports.

## Reproducible commands

Run from the repository root:

```
py -3 test-dlocal\run_dlocal_test.py
py -3 test-dlocal\audit_dlocal_test.py
cd evals && py -3 eval_runner.py
```

- `run_dlocal_test.py` regenerates `test-dlocal\model_output.csv` deterministically from the public dLocal input CSVs. It does not read the answer key (`EXPECTED_from_dLocal_SEC_filings.csv`) or the existing `model_output.csv`.
- `audit_dlocal_test.py` reads only `model_output.csv` and `EXPECTED_from_dLocal_SEC_filings.csv`, joins by key, and prints a PASS/FAIL table. It does not recompute figures from `pnl_activity.csv` or `balance_sheet.csv`.
- `eval_runner.py` runs the full local eval harness (Numbers, Extraction, Grounding).

## Scope

- dLocal public consolidated FY2024 and FY2025 USD financials. dLocal reports in USD under IFRS, so no FX conversion is applied.
- Statement-level and analytical calculations only: P&L subtotals, balance-sheet section totals, margins, and year-over-year growth.
- No validation of transaction-level AR, AP, or tax agents, and no validation of multi-entity or multi-currency consolidation, because that data is not public.

## What "dual-model AI-assisted external audit" means

This is a dual-model AI-assisted external audit in the engineering sense: Claude Code implemented and verified the deterministic preparer/auditor workflow, while Codex independently reviewed the repo, the dLocal test design, the local eval evidence, and the claim boundaries. It is external to the model-output generation path, but it is not a formal external audit, statutory audit, certification, or assurance opinion.

- "External" means external to the preparer and the model-output generation path: Codex independently reviewed the repo, the evidence, the local eval results, and the claim boundaries after Claude Code implemented and ran the workflow. Codex did not produce the dLocal model output.
- This is not a formal external or statutory audit, not a certification, and not a substitute for a human auditor.

## Independence

- The preparer script does not read the answer key.
- The auditor script does not recompute model figures; it only diffs two fixed files.
- The expected file is SEC-derived and fixed, built from dLocal's Form 6-K earnings releases.
- Codex did not produce the dLocal model output. It reviewed the design and the evidence.

## Evidence summary

- The dLocal model output matched all 17 expected SEC-derived figures: 17 PASS, 0 FAIL, exit code 0.
- The full local eval harness passed: Numbers 22/22, Extraction 9/9, Grounding 2/2, Total 33/33.
- The auditor guardrails were self-tested and fail closed: a wrong USD value fails, missing or unexpected keys fail, duplicate keys fail, and non-numeric values fail. A pct delta at the 0.1 boundary passes correctly.
- `model_output.csv` is byte-for-byte unchanged by the audit run, confirming the auditor is read-only.

## Final claim boundary

This supports a narrow claim: the repo can reproduce and audit statement-level calculations against dLocal's public reported consolidated numbers, with a dual-model AI-assisted external audit layer. It does not prove the entire CFO Office operating model on real transaction-level data.
