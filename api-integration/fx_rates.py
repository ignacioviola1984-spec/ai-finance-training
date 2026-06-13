"""
fx_rates.py - Tipos de cambio en tiempo real.

Trae las cotizaciones oficiales del Banco Central Europeo (via la API
Frankfurter), las muestra en una tabla con el nombre de cada moneda,
y convierte un monto entre dos monedas. No requiere API key.
Fuente: https://frankfurter.dev
"""

import requests

API = "https://api.frankfurter.dev/v1"


def get_currencies():
    """Devuelve un diccionario {codigo: nombre} de las monedas disponibles."""
    respuesta = requests.get(f"{API}/currencies", timeout=10)
    respuesta.raise_for_status()
    return respuesta.json()


def get_rates(base="USD"):
    """Devuelve las cotizaciones de 'base' contra las demas monedas."""
    respuesta = requests.get(f"{API}/latest?base={base}", timeout=10)
    respuesta.raise_for_status()
    return respuesta.json()


def print_table(base, fecha, rates, nombres):
    """Imprime una tabla alineada: codigo, nombre, valor."""
    print(f"\nTipos de cambio  |  base: {base}  |  fecha: {fecha}")
    print("-" * 54)
    print(f"{'Codigo':<8}{'Moneda':<30}{'1 ' + base + ' =':>14}")
    print("-" * 54)
    for codigo in sorted(rates):
        nombre = nombres.get(codigo, "")
        valor = rates[codigo]
        print(f"{codigo:<8}{nombre:<30}{valor:>14.4f}")
    print("-" * 54)


def convertir(monto, desde, hacia):
    """Convierte 'monto' de la moneda 'desde' a la moneda 'hacia'."""
    datos = get_rates(base=desde)
    tasa = datos["rates"][hacia]
    return monto * tasa


def main():
    try:
        nombres = get_currencies()
        datos = get_rates(base="USD")
    except requests.exceptions.RequestException as e:
        print("No se pudo conectar con la API:", e)
        return

    print_table(datos["base"], datos["date"], datos["rates"], nombres)

    monto = 1000
    resultado = convertir(monto, "USD", "EUR")
    print(f"\nConversion de ejemplo: {monto} USD = {resultado:,.2f} EUR\n")


if __name__ == "__main__":
    main()