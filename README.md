# AI Finance Portfolio

Finance AI engineering projects: live API integration, a custom MCP
connector for a multi-entity finance system, a multi-agent month-end close
model with reliability controls, and a multi-agent CFO office that runs the
close over a shared, auditable state. Built by a finance operator with 17
years of experience, now building the systems.

## Projects

### Finance MCP Connector (`finance-mcp/`)
A Model Context Protocol server that exposes the finance system of a
multi-entity SaaS (6 legal entities, 6 currencies) as callable tools:
consolidated P&L, balance sheet, AR aging, and cash position, with
multi-currency consolidation at period-close FX. Ships with a Python MCP
client that drives the server over the protocol, plus input validation and
a deliberately read-only surface. Details: [`finance-mcp/README.md`](finance-mcp/README.md).

**Stack:** Python, MCP (FastMCP), stdio transport, multi-entity consolidation.

### Multi-Agent Close & Reporting Model (`orchestration/`)
The AI Finance Operating Model v2: an orchestrator that coordinates
specialized sub-agents (close review, cash forecast, reporting) and adds a
reliability layer, deterministic checks between stages, a timestamped audit
trail, severity-based escalation, and a human-in-the-loop approval gate
before any figure reaches the board. Details:
[`orchestration/README.md`](orchestration/README.md).

**Stack:** Python, Anthropic API, agent patterns (chaining, routing,
sub-agents), audit trail, human-in-the-loop controls.

### CFO Office — multi-agent team over shared state (`cfo-office/`)
The operating model evolved into a CFO office: specialized agents
(Controller, Treasury, FP&A) that communicate through a shared state book
(`CFOContext`), coordinated by a CFO orchestrator. The CFO runs the agents
over one shared state, reconciles their numbers with deterministic
cross-checks, consolidates escalations by severity without double-counting,
and asks for a single human sign-off before fixing the board pack. FP&A
reports two variance lenses: month-over-month and budget-vs-actual (favorable
/unfavorable by line type, with a materiality threshold). Details:
[`cfo-office/README.md`](cfo-office/README.md).

**Stack:** Python, Anthropic API, shared-state multi-agent coordination,
budget-vs-actual variance, cross-agent reconciliation, audit trail,
human-in-the-loop controls.

### Finance Document Intelligence / RAG (`document-intelligence/`)
Semantic search, retrieval-augmented generation, and structured extraction
over finance documents (vendor contracts, expense policy): embeds and
chunks the documents, answers questions with source citations, and extracts
key contract terms into a table. Includes the judgment of when RAG helps and
when full context is better. Details:
[`document-intelligence/README.md`](document-intelligence/README.md).

**Stack:** Python, sentence-transformers / PyTorch, embeddings & cosine
similarity, RAG, structured extraction, Anthropic API.

### Evals, Guardrails & Reliability (`evals/`)
An evaluation harness that measures whether the agents are trustworthy:
regression on consolidated numbers, accuracy of contract extraction against a
known ground truth, and a grounding guardrail that checks the RAG refuses
out-of-scope questions instead of inventing. Exits non-zero on failure, so it
works as a regression test. Details: [`evals/README.md`](evals/README.md).

**Stack:** Python, evaluation harness, regression testing, grounding
guardrails. This is the reliability layer over the other projects.

### Web App / Live Demo (`webapp/`)
A Streamlit app that puts a usable interface over three of the projects so a
non-technical person can operate them: the FX agent, the operating model
(with the human-in-the-loop approval as a button), and document intelligence
(RAG + extraction). Run with `streamlit run app.py`. Details:
[`webapp/README.md`](webapp/README.md).

**Stack:** Python, Streamlit, reuses the project code via imports.

### API Integration (`api-integration/`)
Connecting finance workflows to live external data: a direct FX API client,
a multi-currency rates and conversion tool against official ECB data, and a
natural-language agent that calls an FX API as a tool. Details:
[`api-integration/README.md`](api-integration/README.md).

**Stack:** Python, `requests`, REST/JSON, Anthropic tool use, error handling.

## Diagrams (`diagrams/`)
Architecture diagrams for the agent tool-use flow, the MCP protocol, the
SDK's role, and the operating model. Index: [`diagrams/README.md`](diagrams/README.md).

## Design principle

In finance the number has to be right. Across every project, figures are
computed deterministically in code; the model routes, reasons, and writes
prose, but never produces a number on its own. Controls and a human approve
at the critical points.

## Requirements

- Python 3
- `pip install requests anthropic python-dotenv mcp`
- An Anthropic API key in a local `.env` as `ANTHROPIC_API_KEY` (never committed)

## About

17 years in senior finance, now building AI systems for finance operations.
These projects run on synthetic data modeled on a multi-entity SaaS; the
architecture and accounting logic are built to point at production data.
