# LendingClub data

Real-data foundation for the **credit operating model**. The deterministic engine
([`orchestration/credit_core.py`](../orchestration/credit_core.py)) reads the CSVs
here; the credit agents narrate over those numbers (they never invent a figure).

## Files

| File | What it is | Source |
|---|---|---|
| `accepted_sample.csv` | Funded loans (the loan book) — **sample** with the real schema | mirrors `accepted_2007_to_2018Q4.csv` |
| `rejected_sample.csv` | Declined applications — **sample** with the real schema | mirrors `rejected_2007_to_2018Q4.csv` |
| `public_filings.csv` | LendingClub reported loan originations (FY2016-2018) to benchmark against | **real, SEC-cited** (8-K Ex 99.1) |
| `generate_sample.py` | Reproducible (seeded) generator for the two sample files | — |

## Pointing at the REAL data

1. Download the LendingClub dataset (Kaggle: `wordsforthewise/lending-club`).
2. Drop the real files in this folder. The engine first looks for the real
   filenames and falls back to the `_sample` files, so either name works:
   - `accepted_2007_to_2018Q4.csv`  (or keep `accepted_sample.csv`)
   - `rejected_2007_to_2018Q4.csv`   (or keep `rejected_sample.csv`)
3. `public_filings.csv` already holds **real** LendingClub loan-origination figures
   (FY2016-2018, from the 8-K Ex 99.1). The benchmark only runs on the real data;
   add more periods/metrics there if you want a wider reconciliation. Note: only
   originations is benchmarked — charge-off (cohort-lifetime) and interest income
   (loan cash flows) are not apples-to-apples with the 10-K's annual net figures.

No API key is needed to read the data; the agents need `ANTHROPIC_API_KEY` only to
write the narrative.

## Performance / memory

The engine reads the files in a **single streaming pass** (`csv.DictReader` is a
lazy iterator — the file is never loaded into a list), accumulating only aggregates
keyed by grade, term, vintage and status. Memory stays **flat (~80 MB even for 1M+
rows)**, so the full real loan book runs on a laptop. The full real files
(~2.2M accepted + ~27M rejected rows) take a few minutes to scan once.

- `LC_MAX_ROWS=200000 python ../cfo-office/credit_orchestrator.py` caps the scan
  for fast iteration (off by default — the real test runs on the full file; the
  model-risk agent flags when a run was capped).

> The sample exists so the credit operating model is built and verified **now**.
> Numbers computed on the sample are illustrative; the real test runs on the full
> Kaggle files.
