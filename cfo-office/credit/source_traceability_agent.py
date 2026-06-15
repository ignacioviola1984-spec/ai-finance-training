"""
source_traceability_agent.py - Source Traceability Agent (credit / LendingClub track).

La columna de auditoria: lee cc.provenance() y narra que metrica de salida traza
a que archivo / columnas / filtro, y nombra explicitamente los PROXIES documentados.
Solo redacta el mapeo determinista que devuelve credit_core; nunca inventa una cifra
ni cambia un origen.
"""
import os
import sys

from dotenv import load_dotenv
from anthropic import Anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "orchestration"))   # credit_core
sys.path.insert(0, os.path.join(ROOT, "cfo-office"))      # shared_state

import credit_core as cc
from shared_state import CFOContext

load_dotenv(os.path.join(ROOT, ".env"))
client = Anthropic()
MODEL = "claude-sonnet-4-6"


def agent(system, prompt, max_tokens=400):
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def run(ctx=None):
    own = ctx is None
    ctx = ctx or CFOContext()
    ctx.audit("Source Traceability", "start", "tracing metrics to source")

    # 1) deterministic provenance map from credit_core (no figures invented here)
    data = cc.provenance()
    source_file = data["source_file"]
    metrics = data["metrics"]
    proxies = data["proxies"]

    # 2) build a compact facts string from the provenance map, then narrate
    metric_lines = "\n".join(
        f"- {name}: file={m['file']}; columns={', '.join(m['columns'])}; filter={m['filter']}"
        for name, m in metrics.items()
    )
    proxy_lines = "\n".join(f"- {name}: {desc}" for name, desc in proxies.items())
    facts = (
        f"Primary source file: {source_file}\n\n"
        f"Metric -> source mapping:\n{metric_lines}\n\n"
        f"Documented PROXIES (not disclosed figures):\n{proxy_lines}"
    )
    narrative = agent(
        "You are the Source Traceability auditor for a LendingClub credit book. In 2-4 sentences, "
        "explain which output metrics trace to which file, columns and filter, and explicitly name "
        "the documented PROXIES so a reviewer knows those figures are modeled, not disclosed. Use "
        "ONLY the mapping given; never invent figures, files, columns or proxies. Write in English.",
        facts,
    )

    # 3) leave the structured provenance + narrative in the shared book
    ctx.put("Source Traceability", {
        "source_file": source_file,
        "metrics": metrics,
        "proxies": proxies,
        "narrative": narrative,
    })
    ctx.audit("Source Traceability", "ok",
              f"{len(metrics)} metric(s) traced, {len(proxies)} proxy(ies) flagged")

    if own:
        print("\n--- SOURCE TRACEABILITY ---\n" + narrative)
        path = ctx.save()
        print("\nShared state saved to: " + os.path.basename(path))
    return ctx


if __name__ == "__main__":
    run()
