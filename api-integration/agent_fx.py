"""
agent_fx.py - Agente con tool use sobre tipos de cambio.

Claude recibe una pregunta en lenguaje natural, decide cuando usar la
herramienta get_rate, nosotros la ejecutamos contra la API real, y Claude
arma la respuesta final.

Expone run(pregunta) para poder usarlo desde otros programas (ej: la web app)
sin ejecutar nada al importar.
"""

import os

import requests
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
client = Anthropic()                # toma la key de ANTHROPIC_API_KEY (del .env de la raiz)
MODEL = "claude-sonnet-4-6"
API = "https://api.frankfurter.dev/v1"


def get_rate(desde, hacia):
    """Trae cuanto vale 1 unidad de 'desde' en 'hacia'. Datos reales."""
    r = requests.get(f"{API}/latest?base={desde}&symbols={hacia}", timeout=10)
    r.raise_for_status()
    return r.json()["rates"][hacia]


TOOLS = [
    {
        "name": "get_rate",
        "description": "Devuelve el tipo de cambio actual entre dos monedas (codigos ISO como USD, EUR, BRL).",
        "input_schema": {
            "type": "object",
            "properties": {
                "desde": {"type": "string", "description": "Moneda de origen, ej: USD"},
                "hacia": {"type": "string", "description": "Moneda de destino, ej: EUR"},
            },
            "required": ["desde", "hacia"],
        },
    }
]


def run(pregunta):
    """Corre el agente sobre una pregunta. Devuelve un dict con el detalle:
    que herramienta pidio, con que argumentos, el dato real, y la respuesta."""
    mensajes = [{"role": "user", "content": pregunta}]
    respuesta = client.messages.create(
        model=MODEL, max_tokens=1024, tools=TOOLS, messages=mensajes,
    )
    if respuesta.stop_reason != "tool_use":
        return {"tool": None, "args": None, "rate": None,
                "answer": respuesta.content[0].text}

    bloque = next(b for b in respuesta.content if b.type == "tool_use")
    args = bloque.input
    rate = get_rate(args["desde"], args["hacia"])

    mensajes.append({"role": "assistant", "content": respuesta.content})
    mensajes.append({
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": bloque.id,
            "content": str(rate),
        }],
    })
    final = client.messages.create(
        model=MODEL, max_tokens=1024, tools=TOOLS, messages=mensajes,
    )
    return {"tool": bloque.name, "args": args, "rate": rate,
            "answer": final.content[0].text}


if __name__ == "__main__":
    out = run("Cuanto son 1500 dolares en euros?")
    print("Claude pidio la herramienta:", out["tool"], out["args"])
    print("Resultado real de la API:", out["rate"])
    print("\nRespuesta de Claude:")
    print(out["answer"])
