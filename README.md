# AI Finance Portfolio

Finance AI engineering projects: live API integration, a custom MCP
connector for a multi-entity finance system, and a multi-agent month-end
close model with reliability controls. Built by a finance operator with 17
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
