"""Carga web/.env en el entorno. Sin dependencias.

Se importa ANTES que nada que lea os.environ (seguridad.py y openrouter.py leen
sus variables en tiempo de import, asi que el orden importa).

Regla deliberada: lo que YA este en el entorno real GANA sobre el fichero. Asi
el .env sirve para desarrollo y el VPS puede inyectar las suyas por Docker sin
que un fichero olvidado las pise.
"""
import os

RUTA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))


def cargar(ruta=RUTA):
    """Devuelve la lista de claves cargadas. No lanza si el fichero no existe."""
    if not os.path.exists(ruta):
        return []
    cargadas = []
    with open(ruta, encoding="utf-8") as f:
        for numero, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if linea.startswith("export "):
                linea = linea[7:].lstrip()
            if "=" not in linea:
                continue  # linea suelta: se ignora en silencio, no rompe el arranque
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip()
            # quita comillas envolventes, si las hay
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            if not clave:
                continue
            if clave in os.environ:
                continue  # el entorno real manda
            os.environ[clave] = valor
            cargadas.append(clave)
    return cargadas


CARGADAS = cargar()
