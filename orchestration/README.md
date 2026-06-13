# Orchestration patterns

Agent orchestration patterns from Anthropic's "Building Effective Agents",
applied to the Lumen finance data. Reuses the `finance-mcp` server functions
as the source of truth for every number.

## `patterns.py`

- **Prompt chaining** — a fixed pipeline: real P&L numbers → key
  observations → executive summary. Each step feeds the next.
- **Routing** — a cheap classifier sends each question to the right
  specialist (P&L, cash, or AR aging), which pulls real data.

Run it (needs `ANTHROPIC_API_KEY` in the repo-root `.env`):

```bash
python patterns.py
```

## `orchestrator.py`

An orchestrator that coordinates three specialized sub-agents in sequence,
passing each one's output to the next, like a month-end close:

1. **close review** — summarizes the close and raises risk flags
2. **cash forecast** — projects runway (the number is computed in code)
3. **reporting** — writes a board-ready summary from the two above

Each sub-agent has its own system prompt and a defined input/output.

## `operating_model.py` — AI Finance Operating Model v2

The orchestrator plus a reliability layer:

- **Deterministic checks** between stages (validate data before spending tokens)
- **Audit trail** — every step logged with a timestamp to `audit_log.jsonl`
- **Escalation rules** by severity (operating loss, overdue AR, low runway)
- **Human-in-the-loop gate** — if serious escalations exist, it stops and
  asks for human approval before issuing the board report

This is the pattern of a trustworthy agentic system: the model does the
work, but code controls and a human signs off at the critical points.

## `finance_core.py`

Deterministic finance math (raw numbers, no model) read from the shared
`finance-mcp/data`. Keeps a single source of data across the project.

## Design principle

Numbers are computed by code (deterministic). The model only observes,
routes, and writes prose. It never invents a figure.

## A real lesson from this build

In one run the model labeled "overdue receivables" as ">30 days past due"
(USD 604,582, 53% of the book). The figures were exact, but the framing
understated reality: the 1-30 bucket is already overdue, so ~97% of the
book is past due, not 53%. The math was right; the interpretation could
mislead. This is why a reliability layer (evals/guardrails) and a
human-in-the-loop reviewer matter in finance: a correct number can still
produce a wrong conclusion.
