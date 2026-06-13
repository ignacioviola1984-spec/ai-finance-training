# AI Finance Training

Hands-on projects building automation and AI tools for finance work. Each script is a small, self-contained tool with a clear purpose, written to be read and run by someone else.

## Projects

### `fx_rates.py` — Real-time foreign exchange rates

Pulls official exchange rates (European Central Bank, via the Frankfurter API) and:

- Lists every available currency with its full name in an aligned table
- Converts an amount between two currencies
- Handles connection failures and bad responses instead of crashing
- Needs no API key

**Run it:**

```bash
python fx_rates.py
```

**Concepts shown:** REST API calls, JSON parsing, functions, error handling (try/except, request timeouts, status checks), and formatted output.

### `hello_finance.py` — First script

A minimal margin calculation. Starting point for the training.

## Requirements

- Python 3
- `requests` — install with `pip install requests`

## About

Training repo documenting my move from 17 years in senior finance into AI-enabled finance engineering. Built step by step, project by project.

