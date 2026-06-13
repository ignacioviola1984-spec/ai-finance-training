"""
agent_fx.py - Primer agente con tool use.

Claude recibe una pregunta en lenguaje natural sobre tipos de cambio.
Decide cuando usar la herramienta get_rate, nosotros la ejecutamos
contra la API real, y Claude arma la respuesta final.
"""

import os
import requests
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()                       # lee el archivo .env
client = Anthropic()                # toma la key de ANTHROPIC_API_KEY

API = "https://api.frankfurter.dev/v1"


def get_rate(desde, hacia):
    """Trae cuanto vale 1 unidad de 'desde' en 'hacia'. Datos reales."""
    r = requests.get(f"{API}/latest?base={desde}&symbols={hacia}", timeout=10)
    r.raise_for_status()
    return r.json()["rates"][hacia]


# 1. Le describimos la herramienta a Claude: que hace y que necesita.
tools = [
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

pregunta = "Cuanto son 1500 dolares en euros?"

# 2. Primer llamado: le mandamos la pregunta y le ofrecemos la herramienta.
mensajes = [{"role": "user", "content": pregunta}]
respuesta = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=mensajes,
)

# 3. Si Claude pidio usar la herramienta, la ejecutamos nosotros.
if respuesta.stop_reason == "tool_use":
    bloque_tool = next(b for b in respuesta.content if b.type == "tool_use")
    args = bloque_tool.input
    print("Claude pidio la herramienta:", bloque_tool.name, args)

    resultado = get_rate(args["desde"], args["hacia"])
    print("Resultado real de la API:", resultado)

    # 4. Le devolvemos el resultado y dejamos que arme la respuesta final.
    mensajes.append({"role": "assistant", "content": respuesta.content})
    mensajes.append({
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": bloque_tool.id,
            "content": str(resultado),
        }],
    })

    final = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=tools,
        messages=mensajes,
    )
    print("\nRespuesta de Claude:")
    print(final.content[0].text)
else:
    print(respuesta.content[0].text)