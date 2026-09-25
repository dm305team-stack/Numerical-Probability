"""Interpretacion de la peticion en lenguaje natural -> parametros validados.

El modelo NUNCA genera numeros de boleto. Su unico trabajo aqui es convertir
"dame cinco combinaciones con el 12 y sin el 13" en:
    {"cuantos": 5, "incluir": [12], "excluir": [13], "incluir_en": 1}

Y ese objeto se VALIDA contra la matriz antes de llegar al motor. Si el modelo
devuelve basura, se cae al interprete local de abajo, que es deterministico y
no cuesta nada.
"""
import re

import seguridad

MAX_LISTA = seguridad.MAX_LISTA
MAX_BOLETOS = seguridad.MAX_BOLETOS   # 14: el techo REAL bajo la regla de solape <= 1

ESQUEMA = {
    "type": "object",
    # strict exige additionalProperties:false y que 'required' liste TODAS las
    # claves de 'properties'. Faltaba 'explicacion' y daba 400.
    "additionalProperties": False,
    "properties": {
        "cuantos": {
            "type": "integer",
            "description": "cuantos boletos pide el usuario; 5 si no lo dice",
        },
        "incluir": {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": MAX_LISTA,
            "description": "numeros que el usuario quiere que aparezcan",
        },
        "excluir": {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": MAX_LISTA,
            "description": "numeros que el usuario quiere evitar",
        },
        "incluir_en": {
            "type": "integer",
            "description": "en cuantos boletos debe aparecer cada numero incluido; 1 por defecto, mas si dice 'en varios' o 'en algunos'",
        },
        "explicacion": {
            "type": "string",
            "description": "en una frase, que has entendido. Sin cifras.",
        },
    },
    "required": ["cuantos", "incluir", "excluir", "incluir_en", "explicacion"],
}

SISTEMA = """Eres el interprete de peticiones de una app de loteria.

Conviertes lo que escribe el usuario en parametros. NO generas numeros de
loteria, NO calculas nada, NO opinas sobre probabilidades. Solo extraes lo que
el usuario pidio.

Reglas:
- "cuantos" es cuantos boletos quiere. Si no lo dice, 5.
- "incluir" son numeros que quiere que salgan. "excluir", los que quiere evitar.
- "incluir_en": 1 por defecto. Si dice "en algunos", "en varios" o "en un par",
  pon 2. Si dice "en todos", pon el mismo valor que "cuantos".
- Si el usuario no menciona numeros concretos, las listas van vacias.
- En "explicacion" resume lo que entendiste en una frase, SIN ESCRIBIR CIFRAS:
  usa palabras ("cinco boletos", "sin el trece")."""

PALABRAS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# continuacion de una lista de numeros: ", 33", " y el 33", " and 33"
_COLA = r"(?:\s*(?:,|y|and|ni|o|or|nor)?\s*(?:el\s+|the\s+)?\d{1,2})*"

_INCLUIR = re.compile(
    r"(?:con(?:\s+el)?|incluy[ea]n?d?o?|que\s+teng[ao]n?(?:\s+el)?|inclu[iy]r?|with)\s+"
    r"((?:\d{1,2}|" + "|".join(PALABRAS) + r")" + _COLA + r")",
    re.I,
)
_EXCLUIR = re.compile(
    r"(?:sin(?:\s+el)?|evit[ae]n?d?o?|excluy[ea]n?d?o?|que\s+no\s+teng[ao]n?(?:\s+el)?|"
    r"nada\s+de|without|avoid)\s+"
    r"((?:\d{1,2}|" + "|".join(PALABRAS) + r")" + _COLA + r")",
    re.I,
)
_CUANTOS = re.compile(
    r"(\d{1,2}|" + "|".join(PALABRAS) + r")\s+"
    r"(?:combinaci|boleto|jugada|ticket|linea|l[ií]nea|secuencia)",
    re.I,
)
_VARIOS = re.compile(r"\b(algunos|varios|un\s+par|algunas|some|several)\b", re.I)
_TODOS = re.compile(r"\b(todos|todas|cada\s+uno|all|every)\b", re.I)


def _numeros(trozo):
    salida = []
    for tok in re.findall(r"\d{1,2}|[a-zá-ú]+", trozo, re.I):
        if tok.isdigit():
            salida.append(int(tok))
        elif tok.lower() in PALABRAS:
            salida.append(PALABRAS[tok.lower()])
    return salida


def interpretar_local(texto):
    """Interprete deterministico, sin modelo. Es el respaldo y tambien el
    camino cuando no hay clave de OpenRouter configurada."""
    incluir, excluir = [], []
    for m in _EXCLUIR.finditer(texto):
        excluir += _numeros(m.group(1))
    for m in _INCLUIR.finditer(texto):
        candidatos = _numeros(m.group(1))
        incluir += [n for n in candidatos if n not in excluir]
    cuantos = 5
    m = _CUANTOS.search(texto)
    if m:
        v = m.group(1)
        cuantos = int(v) if v.isdigit() else PALABRAS.get(v.lower(), 5)
    incluir_en = 1
    if _TODOS.search(texto):
        incluir_en = cuantos
    elif _VARIOS.search(texto):
        incluir_en = 2
    return {
        "cuantos": cuantos,
        "incluir": incluir,
        "excluir": excluir,
        "incluir_en": incluir_en,
        "explicacion": None,
        "origen": "local",
    }


class PeticionInvalida(ValueError):
    pass


def validar(params, matriz):
    """Recorta y valida los parametros contra la matriz. Lo que venga del
    modelo pasa por aqui SIEMPRE."""
    try:
        cuantos = int(params.get("cuantos") or 5)
    except (TypeError, ValueError):
        cuantos = 5
    if not 1 <= cuantos <= MAX_BOLETOS:
        raise PeticionInvalida(
            f"pide entre 1 y {MAX_BOLETOS} boletos (pediste {cuantos})"
        )

    def _limpiar(lista, etiqueta):
        salida = []
        for x in (lista or [])[: seguridad.MAX_LISTA]:
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if not 1 <= n <= matriz.max_principal:
                raise PeticionInvalida(
                    f"el {n} no existe en {matriz.nombre}: van del 1 al "
                    f"{matriz.max_principal}"
                )
            if n not in salida:
                salida.append(n)
        return salida

    incluir = _limpiar(params.get("incluir"), "incluir")
    excluir = _limpiar(params.get("excluir"), "excluir")
    choque = set(incluir) & set(excluir)
    if choque:
        raise PeticionInvalida(
            f"pides incluir y evitar a la vez: {', '.join(map(str, sorted(choque)))}"
        )
    try:
        incluir_en = int(params.get("incluir_en") or 1)
    except (TypeError, ValueError):
        incluir_en = 1
    incluir_en = max(1, min(incluir_en, cuantos))
    return {
        "cuantos": cuantos,
        "incluir": incluir,
        "excluir": excluir,
        "incluir_en": incluir_en,
        "explicacion": params.get("explicacion"),
        "origen": params.get("origen", "modelo"),
    }
