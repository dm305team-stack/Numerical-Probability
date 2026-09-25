"""Cliente de OpenRouter. Dos trabajos, ninguno de ellos generar numeros.

DEFENSA CENTRAL DE ESTE MODULO: el texto que redacta el modelo NO PUEDE
CONTENER NINGUNA CIFRA. Se le pide que escriba los numeros con palabras y se
comprueba con una expresion regular; si se cuela un digito, su texto se tira y
se usa el resumen deterministico del servidor. Asi es imposible que el modelo
invente un boleto o una probabilidad, por mucho que alucine: los numeros de la
pantalla salen todos del motor.

Sin OPENROUTER_API_KEY la app funciona igual: interprete local + resumen
deterministico. Se pierde el lenguaje natural, no el producto.
"""
import json
import os
import re

import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
# OJO: "anthropic/claude-3.5-haiku" estaba aqui y esta MUERTO (cero endpoints
# sirviendolo en OpenRouter, comprobado 2026-09-25). Un slug muerto no da error:
# la app cae al interprete local en silencio. Anclar version, nunca "~latest",
# y comprobar /models/<slug>/endpoints antes de cambiarlo.
MODELO_POR_DEFECTO = os.environ.get("OPENROUTER_MODEL", "openai/gpt-5-nano")
MODELO_REDACCION = os.environ.get("OPENROUTER_MODELO_PROSA", "openai/gpt-5-mini")
TIMEOUT = float(os.environ.get("OPENROUTER_TIMEOUT", "20"))

_DIGITO = re.compile(r"\d")

# Numeros escritos con palabras: el regex de digitos no los caza, y "el
# cuarenta y cuatro" al lado de boletos de verdad se lee como un boleto.
# OJO con "un" y "una": en espanol son ARTICULOS, no numeros. Incluirlos hacia
# que la guardia rechazase practicamente cualquier frase correcta ("una
# combinacion", "un premio") y dejaba el modelo inservible. Un articulo no se
# puede confundir con una bola; "uno" suelto si, y ese sigue bloqueado.
_NUMERO_PALABRA = re.compile(
    r"\b(cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|"
    r"doce|trece|catorce|quince|diecis|veinti|treinta|cuarenta|cincuenta|"
    r"sesenta|setenta|ochenta|noventa|cien|mil|mill)\b", re.I)

# Vocabulario prohibido: promesas, supersticion de loteria y consejo financiero.
# Estas son las frases que convertirian una herramienta de analisis en un
# producto que enga\u00f1a, que es el eje real del riesgo legal.
_PROHIBIDO = re.compile(
    r"\b(garantiz\w*|asegur\w*|segur[oa]s?\b|infalible|imbatible|"
    r"caliente|fri[oa]s?\b|atrasad\w*|le toca|tocan?\b|"
    r"predic\w*|pronostic\w*|anticip\w*|adivin\w*|"
    r"m[aá]s probable|mejor combinaci|mayor probabilidad|m[aá]s posibilidades|"
    r"suerte|afortunad\w*|ganar[aá]s|vas a ganar|no puedes perder|"
    r"invierte|invertir|apuesta fuerte|dobla|"
    r"guaranteed|surefire|hot number|due to hit|lucky)", re.I)


class SinClave(RuntimeError):
    pass


def hay_clave():
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def _cabeceras():
    clave = os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        raise SinClave("falta OPENROUTER_API_KEY")
    return {
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        # OpenRouter los usa para atribucion; no son obligatorios
        "HTTP-Referer": os.environ.get("APP_URL", "http://localhost:8000"),
        "X-Title": "Numerical Probability",
    }


async def _pedir(mensajes, *, esquema=None, max_tokens=1600, temperatura=0.2,
                 modelo=None, esfuerzo="low"):
    cuerpo = {
        "model": modelo or MODELO_POR_DEFECTO,
        "messages": mensajes,
        "max_tokens": max_tokens,
        "temperature": temperatura,
        # Sin esto, los modelos de razonamiento se gastan TODO el cupo pensando
        # y devuelven contenido vacio con finish_reason="length". Medido:
        # 256 de 256 tokens en razonamiento y content=None.
        "reasoning": {"effort": esfuerzo},
    }
    if esquema is not None:
        # OpenAI en modo strict exige que 'required' incluya TODAS las claves de
        # 'properties' y que additionalProperties sea false. Sin eso devuelve un
        # 400 que OpenRouter reenvia como "Provider returned error".
        cuerpo["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "parametros", "strict": True, "schema": esquema},
        }
    async with httpx.AsyncClient(timeout=TIMEOUT) as cliente:
        r = await cliente.post(URL, headers=_cabeceras(), json=cuerpo)
        r.raise_for_status()
        datos = r.json()
    return datos["choices"][0]["message"]["content"]


async def interpretar(texto, esquema, sistema):
    """Devuelve los parametros como dict. Lanza si el modelo no colabora."""
    crudo = await _pedir(
        [{"role": "system", "content": sistema},
         {"role": "user", "content": texto}],
        esquema=esquema, max_tokens=1500,
    )
    params = json.loads(crudo)
    params["origen"] = "modelo"
    return params


SISTEMA_REDACCION = """Escribes el parrafo que acompana a unos boletos de
loteria que YA han sido calculados por un motor estadistico.

PROHIBICION ABSOLUTA: no escribas ni un solo digito. Ninguna cifra, ningun
numero, ninguna fecha, ningun porcentaje en numeros. Tampoco escribas numeros
en palabras: ni "cinco", ni "doscientos noventa y dos millones". Las cantidades
las pone la plantilla; tu solo pones la prosa que va alrededor. Un solo numero,
en cifra o en letra, y tu texto se descarta entero.

Que debes decir, en dos o tres frases y en espanol de Espana, tono sobrio y
directo, sin entusiasmo comercial:
- Que se ha entendido de la peticion.
- Que estos boletos no tienen mas probabilidad de acertar que cualquier otra
  combinacion: el historico es uniforme y eso esta medido.
- Que lo que si aportan es un reparto estructural que evita los patrones que
  juega mucha gente, lo cual reduce el riesgo de COMPARTIR un premio, no el de
  acertarlo.

No prometas nada. No digas "buena suerte". No sugieras que un numero esta
"caliente", "frio" o "a punto de salir"."""


def motivo_de_rechazo(texto):
    """None si el texto pasa; si no, por que se rechaza.

    Tres redes, de mas dura a mas blanda:
      1. ni un digito         -> imposible escribir un boleto en cifras
      2. ni un numero en letra -> ni escribirlo deletreado
      3. vocabulario prohibido -> ni prometer, ni decir que un numero esta
         "caliente", ni dar consejo de cuanto jugar
    Las cantidades legitimas (cuantos boletos, la probabilidad) las pone la
    plantilla desde el motor, no el modelo. Por eso puede ser tan estricto.
    """
    if not texto or not texto.strip():
        return "el modelo devolvió texto vacío"
    if _DIGITO.search(texto):
        return "el modelo escribió cifras"
    m = _NUMERO_PALABRA.search(texto)
    if m:
        return f"el modelo escribió un número en letra ({m.group(0)!r})"
    m = _PROHIBIDO.search(texto)
    if m:
        return f"el modelo usó vocabulario prohibido ({m.group(0)!r})"
    return None


def texto_limpio(texto):
    """True si el texto pasa todas las redes."""
    return motivo_de_rechazo(texto) is None


async def redactar(parametros):
    """Redacta a partir de PARAMETROS YA VALIDADOS, nunca del texto del usuario.

    Esto corta la inyeccion de instrucciones en el paso de prosa: lo que el
    usuario escribe solo llega al paso de interpretacion, cuyo esquema estricto
    no tiene forma de expresar ni un boleto ni una frase.
    """
    descripcion = (
        f"boletos_pedidos={parametros['cuantos']}; "
        f"numeros_forzados={len(parametros['incluir'])}; "
        f"numeros_excluidos={len(parametros['excluir'])}"
    )
    texto = await _pedir(
        [{"role": "system", "content": SISTEMA_REDACCION},
         {"role": "user", "content": descripcion}],
        max_tokens=1600, temperatura=0.4, modelo=MODELO_REDACCION,
    )
    texto = (texto or "").strip()
    return texto, motivo_de_rechazo(texto)
