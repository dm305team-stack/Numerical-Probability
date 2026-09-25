"""Aislamiento de la bateria de tests.

DOS COSAS QUE NO PUEDEN PASAR NUNCA AL CORRER LOS TESTS:
  1. Gastar dinero. En cuanto existe web/.env con OPENROUTER_API_KEY, la app
     llama al modelo de verdad: la bateria pasaba a costar dinero y a depender
     de la red, y un test que depende de la red no es un test.
  2. Depender del .env del desarrollador. Los resultados deben ser los mismos
     en tu portatil, en CI y en el VPS.
Para probar la capa del modelo estan los dobles y las pruebas manuales, no la
bateria.
"""
import os

os.environ["LOCAL"] = os.environ.get("LOCAL", "1")
os.environ["OPENROUTER_API_KEY"] = ""      # apaga la llamada de pago
os.environ["PROXIES_DE_CONFIANZA"] = ""    # nada de cabeceras de confianza
