# API Integration

Connecting finance workflows to live external data through APIs, from a raw
request up to a natural-language agent that calls an API as a tool.

## Contents

### `agent_fx.py` — Natural-language FX agent (tool use)
An agent that answers currency questions in plain language. The model
selects a live FX tool and explains the result; the code executes the call
against the real API. Needs `ANTHROPIC_API_KEY` in the repo-root `.env`.

```bash
python agent_fx.py
```

### `fx_rates.py` — Multi-currency FX rates & conversion
Live exchange rates and conversion against official ECB data (Frankfurter
API), presented as an aligned table, with connection and response error
handling. No API key required.

```bash
python fx_rates.py
```

### `api_fx.py` — Direct FX API client
A focused REST client: hits a public FX endpoint, parses the JSON response,
and prints the rates. The minimal client `fx_rates.py` builds on.

```bash
python api_fx.py
```

## Stack
Python, `requests`, REST/JSON, Anthropic tool use, error handling, secrets
via `.env`.
