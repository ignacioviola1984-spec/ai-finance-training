# api_fx.py
# Primera llamada a una API: trae tipos de cambio reales.

import requests

# 1. La direccion (URL) del servicio al que le pedimos datos.
url = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,GBP,BRL,JPY"

# 2. Hacemos el pedido y guardamos la respuesta.
respuesta = requests.get(url)

# 3. Convertimos la respuesta (que viene en JSON) en un diccionario de Python.
datos = respuesta.json()

# 4. Mostramos lo que vino.
print("Codigo de estado:", respuesta.status_code)
print("Moneda base:", datos["base"])
print("Fecha:", datos["date"])
print("Cotizaciones (1 USD =):")
for moneda, valor in datos["rates"].items():
    print("  ", valor, moneda)