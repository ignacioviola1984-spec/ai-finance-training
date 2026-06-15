# Credit agents (LendingClub track)

The maker agents for the credit operating model. Each does its work over the
deterministic engine [`orchestration/credit_core.py`](../../orchestration/credit_core.py)
and **narrates** the result — it never invents a number. Each function is signed
off by its domain expert (see `CREDIT_REVIEWERS` in [`../review.py`](../review.py)),
and the staged run is driven by [`../credit_stages.py`](../credit_stages.py) and
[`../credit_orchestrator.py`](../credit_orchestrator.py).

Layers: **data foundation** (ingestion → data quality → traceability) →
**fintech analytics** (loan portfolio → credit risk → revenue & unit economics) →
**benchmark** (public benchmark → variance & explainability) → **assurance**
(model risk) → **CFO narrative + final sign-off**.
