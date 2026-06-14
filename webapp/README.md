# Web App (Live Demo)

A single Streamlit app that puts a usable interface over the three projects
in this repo, so a non-technical person can operate them without touching
code.

## Tabs

- **FX Agent** — ask a currency question in natural language; the model picks
  a tool, the code runs it against a live API, and the model answers.
- **Operating Model** — runs the month-end close with sub-agents, shows the
  escalations, and gates the board report behind a human approval button
  (human-in-the-loop).
- **Document Intelligence** — ask questions over contracts (RAG with source
  citations) and extract key terms into a table.

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Needs `ANTHROPIC_API_KEY` in the repo-root `.env`. The Document Intelligence
tab downloads a small embedding model the first time it runs.

## Notes

The app reuses the existing project code (`api-integration/`,
`orchestration/`, `document-intelligence/`) via imports; nothing is
duplicated. Heavy dependencies load lazily, only when the relevant tab is
used.
