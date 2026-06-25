# api_fx.py
# Primera llamada a una API: trae tipos de cambio reales.
# Falla "cerrado": si la red, el codigo de estado o el cuerpo JSON no son los
# esperados, avisa y corta en vez de seguir con datos a medias.

import requests

# 1. La direccion (URL) del servicio al que le pedimos datos.
URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,GBP,BRL,JPY"
TIMEOUT_S = 10


def fetch_rates(url=URL):
    """Trae las cotizaciones. Devuelve el dict de la API o lanza una excepcion
    clara si algo falla (timeout, status != 2xx, JSON invalido o incompleto)."""
    resp = requests.get(url, timeout=TIMEOUT_S)   # sin timeout, un cuelgue de red bloquea para siempre
    resp.raise_for_status()                       # 4xx/5xx -> excepcion, no datos basura
    try:
        datos = resp.json()
    except ValueError as e:                        # cuerpo no-JSON
        raise ValueError(f"la API no devolvio JSON valido: {e}") from e
    # Validamos la FORMA, no solo la presencia de claves: un cuerpo JSON valido
    # pero de tipo inesperado (un numero, null, o 'rates' que no es un mapa) no
    # debe explotar mas adelante con TypeError/AttributeError, sino fallar aca.
    if (not isinstance(datos, dict) or "base" not in datos
            or not isinstance(datos.get("rates"), dict)):
        raise ValueError(f"respuesta con forma inesperada (se espera base + rates dict): {datos!r}"[:200])
    return datos


def main():
    try:
        datos = fetch_rates()
    except (requests.exceptions.RequestException, ValueError) as e:
        print("No se pudo obtener el tipo de cambio:", e)
        return 1

    print("Fecha:", datos.get("date", "?"))
    print("Moneda base:", datos["base"])
    print("Cotizaciones (1 USD =):")
    for moneda, valor in datos["rates"].items():
        print("  ", valor, moneda)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
