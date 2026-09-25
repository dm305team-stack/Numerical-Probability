"""Numerical Probability - interfaz web.

ARRANQUE LOCAL:
    cd web && ./run-local.sh
    (o: OPENROUTER_API_KEY=... python3 -m uvicorn app.main:app --reload)

MODO LOCAL vs MODO DESPLEGADO
  Sin APP_KEY en el entorno, la app NO pide clave: es el modo de pruebas local.
  Con APP_KEY definida, exige esa clave por cookie de sesion. En el VPS detras
  del proxy con HTTPS hay que definirla siempre.

Sin OPENROUTER_API_KEY la app funciona con el interprete local y un resumen
deterministico. Es una degradacion, no una averia.
"""
import hashlib
import os
import re
from datetime import date, timedelta

from contextlib import asynccontextmanager

from fastapi import Cookie, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import engine
import seguridad
from engine.generate import NoConverge
from llm import intent, openrouter

AQUI = os.path.dirname(os.path.abspath(__file__))
APP_KEY = seguridad.APP_KEY

@asynccontextmanager
async def ciclo(_app):
    """El analisis caro (Markov con 20.000 permutaciones) se hace UNA vez al
    arrancar, no en la primera peticion de un usuario."""
    modo = seguridad.comprobar_arranque()   # falla CERRADO si falta la clave
    engine.analizar("powerball")
    print(f"[arranque] modo={modo} modelo={openrouter.MODELO_POR_DEFECTO} "
          f"tope_llm_diario={seguridad.PRESUPUESTO_LLM.tope}")
    yield


app = FastAPI(
    title="Numerical Probability", docs_url=None, redoc_url=None, lifespan=ciclo
)
app.mount("/static", StaticFiles(directory=os.path.join(AQUI, "static")), name="static")
plantillas = Jinja2Templates(directory=os.path.join(AQUI, "templates"))


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, siguiente):
    respuesta = await siguiente(request)
    for k, v in seguridad.CABECERAS.items():
        respuesta.headers.setdefault(k, v)
    return respuesta


# ------------------------------------------------------------------ acceso
def _cookie_valida(valor):
    return seguridad.sesion_valida(valor)


def _exigir(sesion):
    if not seguridad.sesion_valida(sesion):
        raise HTTPException(status_code=401, detail="no autorizado")


def _frenar(limitador, request, que):
    """Limitacion por IP. Devuelve None si pasa, o los segundos de espera."""
    espera = limitador.consultar(seguridad.ip_de(request))
    if espera:
        raise HTTPException(
            status_code=429,
            detail=f"demasiados intentos de {que}; espera {espera} s",
            headers={"Retry-After": str(espera)},
        )


# ------------------------------------------------------------------ semilla
def proximo_sorteo(matriz, hoy=None):
    """El proximo dia de sorteo, incluido hoy.

    OJO: esto razona en la fecha LOCAL del servidor. En el VPS hay que fijar
    TZ=America/New_York, porque los sorteos son en hora del este y un servidor
    en UTC cambia de dia antes que el sorteo.
    """
    hoy = hoy or date.today()
    for salto in range(8):
        d = hoy + timedelta(days=salto)
        if d.weekday() in matriz.dias_sorteo:
            return d
    return hoy


def semilla_de(texto, matriz, fijada=None):
    """Semilla reproducible y auditable.

    Deriva de (proximo sorteo + peticion normalizada). Consecuencias buscadas:
      - la misma peticion el mismo dia da los mismos boletos: es auditable, y
        recargar la pagina no reparte premios distintos;
      - cambia sola al pasar al siguiente sorteo;
      - el usuario puede fijarla a mano para reproducir una tirada antigua.
    """
    if fijada is not None:
        return int(fijada), True
    normal = re.sub(r"\s+", " ", (texto or "").strip().lower())
    crudo = f"{proximo_sorteo(matriz).isoformat()}|{matriz.clave}|{normal}"
    digest = hashlib.sha256(crudo.encode()).hexdigest()[:12]
    return int(digest, 16) % (2**31), False


# ------------------------------------------------------------------ respaldo
def _enumerar(numeros):
    """01, 02 y 03 -- con la 'y' delante del ultimo, como se escribe en espanol."""
    piezas = [f"{n:02d}" for n in numeros]
    if len(piezas) == 1:
        return piezas[0]
    return ", ".join(piezas[:-1]) + " y el " + piezas[-1]


def resumen_determinista(params, matriz, n_sorteos):
    """El texto que se usa cuando no hay modelo o cuando el modelo escribio
    cifras. Lo escribe el servidor, asi que es incapaz de mentir."""
    # el rotulo del panel ya dice cuantos boletos y de que juego: no se repite
    partes = []
    if params["incluir"]:
        lista = _enumerar(params["incluir"])
        cuantos = params["incluir_en"]
        cuenta = "un boleto" if cuantos == 1 else f"{cuantos} boletos"
        cada = " cada uno" if len(params["incluir"]) > 1 else ""
        partes.append(f"Con el {lista}, en {cuenta}{cada}.")
    if params["excluir"]:
        partes.append(f"Sin el {_enumerar(params['excluir'])}.")
    partes.append(
        f"Ninguno tiene más probabilidad que otro: el histórico de {n_sorteos} "
        f"sorteos es uniforme y cada boleto vale 1 entre "
        f"{matriz.combinaciones:,}".replace(",", ".") + "."
    )
    partes.append(
        "Lo que sí aportan es un reparto estructural que evita los patrones "
        "más jugados, lo que reduce el riesgo de compartir un premio."
    )
    return " ".join(partes)


# ------------------------------------------------------------------ rutas
@app.get("/healthz")
def healthz():
    """Publico y barato a proposito: no toca el motor ni revela nada."""
    return {"ok": True}


@app.get("/salud")
def estado(sesion: str = Cookie(None)):
    """Detalle de operacion. Tras la clave: dice que modelo usas y cuanto queda
    de presupuesto, y eso no es asunto de un visitante cualquiera."""
    _exigir(sesion)
    a = engine.analizar()
    return {
        "ok": True,
        "sorteos": a.n,
        "fuente": a.fuente,
        "modelo": openrouter.MODELO_POR_DEFECTO if openrouter.hay_clave() else None,
        "llm_restantes_hoy": seguridad.PRESUPUESTO_LLM.restantes,
        "modo": "privado" if APP_KEY else "abierto (local)",
    }


@app.get("/entrar", response_class=HTMLResponse)
def entrar(request: Request, error: str = ""):
    if not APP_KEY:
        return RedirectResponse("/", status_code=303)
    return plantillas.TemplateResponse(request, "entrar.html", {"error": error})


@app.post("/entrar")
def entrar_post(request: Request, clave: str = Form("")):
    _frenar(seguridad.LIMITE_LOGIN, request, "acceso")
    if not seguridad.clave_correcta(clave):
        return RedirectResponse("/entrar?error=1", status_code=303)
    seguridad.LIMITE_LOGIN.perdonar(seguridad.ip_de(request))
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(
        "sesion", seguridad.emitir_sesion(),
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14,
        secure=not seguridad.MODO_LOCAL,
    )
    return r


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, sesion: str = Cookie(None)):
    if not _cookie_valida(sesion):
        return RedirectResponse("/entrar", status_code=303)
    a = engine.analizar()
    return plantillas.TemplateResponse(
        request,
        "index.html",
        {
            "a": a,
            "hay_modelo": openrouter.hay_clave(),
            "proximo": proximo_sorteo(a.matriz),
        },
    )


@app.post("/generar", response_class=HTMLResponse)
async def generar(
    request: Request,
    peticion: str = Form(""),
    semilla_fijada: str = Form(""),
    sesion: str = Cookie(None),
):
    _exigir(sesion)
    _frenar(seguridad.LIMITE_GENERAR, request, "generación")
    try:
        peticion = seguridad.limpiar_peticion(peticion)
        semilla_pedida = seguridad.limpiar_semilla(semilla_fijada)
    except seguridad.EntradaInvalida as e:
        return plantillas.TemplateResponse(
            request, "_error.html", {"mensaje": str(e)}, status_code=200
        )
    a = engine.analizar()

    # 1. interpretar: modelo si hay clave, interprete local si no o si falla
    aviso = None
    crudo = None
    if openrouter.hay_clave() and seguridad.PRESUPUESTO_LLM.hay():
        try:
            seguridad.PRESUPUESTO_LLM.gastar()
            crudo = await openrouter.interpretar(
                peticion, intent.ESQUEMA, intent.SISTEMA
            )
        except Exception as e:  # red, cuota, modelo retirado, JSON roto
            aviso = f"El modelo no respondió ({type(e).__name__}); usando el intérprete local."
    elif openrouter.hay_clave():
        aviso = "Presupuesto diario del modelo agotado; usando el intérprete local."
    if crudo is None:
        crudo = intent.interpretar_local(peticion)

    try:
        params = intent.validar(crudo, a.matriz)
    except intent.PeticionInvalida as e:
        return plantillas.TemplateResponse(
            request, "_error.html", {"mensaje": str(e)}, status_code=200
        )

    # 2. generar: esto SIEMPRE lo hace el motor, nunca el modelo
    semilla, era_fija = semilla_de(peticion, a.matriz, semilla_pedida)
    try:
        lista, intentos = engine.boletos(
            a, semilla=semilla, cuantos=params["cuantos"],
            incluir=params["incluir"], excluir=params["excluir"],
            incluir_en=params["incluir_en"],
        )
    except NoConverge as e:
        return plantillas.TemplateResponse(
            request, "_error.html", {"mensaje": str(e)}, status_code=200
        )

    # 3. redactar: el modelo no puede escribir cifras; si lo hace, se descarta
    texto = resumen_determinista(params, a.matriz, a.n)
    fuente_texto = "servidor"
    if openrouter.hay_clave() and seguridad.PRESUPUESTO_LLM.hay():
        try:
            seguridad.PRESUPUESTO_LLM.gastar()
            # se le pasan los PARAMETROS, no el texto del usuario: el paso de
            # prosa no es superficie de inyeccion
            candidato, motivo = await openrouter.redactar(params)
            if motivo is None:
                texto, fuente_texto = candidato, "modelo"
            else:
                aviso = (aviso or "") + f" Texto del modelo descartado: {motivo}."
        except Exception as e:
            aviso = (aviso or "") + f" El modelo no pudo redactar ({type(e).__name__})."

    return plantillas.TemplateResponse(
        request,
        "_resultado.html",
        {
            "a": a, "boletos": lista, "params": params,
            "texto": texto, "fuente_texto": fuente_texto, "aviso": aviso,
            "semilla": semilla, "era_fija": era_fija, "intentos": intentos,
            "cobertura": engine.cobertura(lista),
            "proximo": proximo_sorteo(a.matriz),
        },
    )


@app.get("/rigor", response_class=HTMLResponse)
def rigor(request: Request, sesion: str = Cookie(None)):
    """El panel 'como se calculo'. Se carga a demanda, no en cada respuesta."""
    _exigir(sesion)
    a = engine.analizar()
    return plantillas.TemplateResponse(request, "_rigor.html", {"a": a})
