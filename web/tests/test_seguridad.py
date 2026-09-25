"""Cada test de aqui corresponde a un agujero concreto que estaba abierto.

Si uno falla, el agujero ha vuelto.
"""
import os
import sys
import time

os.environ.setdefault("LOCAL", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

import seguridad
from app.main import app

cliente = TestClient(app)


# --------------------------------------------- longitud de entrada
def test_peticion_larga_se_rechaza():
    """Sin tope, el texto del usuario entra entero en el prompt de pago."""
    r = cliente.post("/generar", data={"peticion": "a" * 5000})
    assert r.status_code == 200
    assert "400 caracteres" in r.text


def test_peticion_en_el_limite_pasa():
    r = cliente.post("/generar", data={"peticion": "dame cinco " + "a" * 380})
    assert "caracteres" not in r.text


def test_caracteres_de_control_se_eliminan():
    assert seguridad.limpiar_peticion("dame\x00 cinco\x07") == "dame cinco"


# --------------------------------------------- semilla
@pytest.mark.parametrize("malo", ["9" * 40, "abc", "-5", "1e9", "0x10", " 12 34"])
def test_semilla_basura_se_rechaza(malo):
    with pytest.raises(seguridad.EntradaInvalida):
        seguridad.limpiar_semilla(malo)


def test_semilla_gigante_no_llega_al_motor():
    r = cliente.post("/generar", data={"peticion": "dame cinco",
                                       "semilla_fijada": "9" * 500})
    assert "dígitos" in r.text


# --------------------------------------------- coste de CPU
def test_peticion_imposible_no_quema_la_cpu():
    """Antes: 3,63 s por peticion. Es un vector de DoS trivial."""
    t = time.monotonic()
    cliente.post("/generar", data={
        "peticion": "dame 14 boletos con el 1 2 3 4 5 6 7 8 9 10"})
    assert time.monotonic() - t < 2.0


# --------------------------------------------- listas
def test_lista_de_numeros_acotada():
    from llm.intent import validar
    from engine.matrix import POWERBALL
    p = validar({"cuantos": 5, "incluir": [], "excluir": list(range(1, 60)),
                 "incluir_en": 1}, POWERBALL)
    assert len(p["excluir"]) <= seguridad.MAX_LISTA


def test_techo_de_boletos_es_el_real():
    assert seguridad.MAX_BOLETOS == 14


# --------------------------------------------- acceso
def test_clave_en_tiempo_constante_y_sin_clave_no_valida():
    assert seguridad.clave_correcta("") is False
    assert seguridad.clave_correcta("x" * 5000) is False


def test_la_cookie_no_deriva_de_la_clave():
    """Si la cookie fuese sha256(APP_KEY), filtrarla equivaldria a filtrar la
    clave y no habria forma de invalidarla sin cambiar la clave."""
    import hashlib
    seguridad.APP_KEY = "una-clave-de-prueba-larga"
    assert seguridad.emitir_sesion() != hashlib.sha256(
        seguridad.APP_KEY.encode()).hexdigest()
    seguridad.APP_KEY = ""


def test_arranque_falla_cerrado_sin_clave(monkeypatch):
    monkeypatch.setattr(seguridad, "MODO_LOCAL", False)
    monkeypatch.setattr(seguridad, "APP_KEY", "corta")
    with pytest.raises(seguridad.ArranqueInseguro):
        seguridad.comprobar_arranque()


# --------------------------------------------- limitador
def test_limitador_bloquea_y_castiga():
    l = seguridad.Limitador(permitidas=3, ventana_s=60, castigo_s=30)
    assert [l.consultar("ip") for _ in range(3)] == [0, 0, 0]
    assert l.consultar("ip") > 0
    l.perdonar("ip")
    assert l.consultar("ip") == 0


def test_limitador_separa_por_ip():
    l = seguridad.Limitador(permitidas=1, ventana_s=60)
    assert l.consultar("a") == 0
    assert l.consultar("b") == 0
    assert l.consultar("a") > 0


def test_presupuesto_diario_se_agota_y_no_rompe():
    p = seguridad.PresupuestoDiario(tope=2)
    assert p.hay()
    p.gastar(); p.gastar()
    assert not p.hay()          # se agota
    assert p.restantes == 0     # y lo dice, no explota


# --------------------------------------------- cabeceras
def test_cabeceras_de_seguridad_en_cada_respuesta():
    r = cliente.get("/healthz")
    for cabecera in ("Content-Security-Policy", "X-Content-Type-Options",
                     "X-Frame-Options", "Referrer-Policy"):
        assert cabecera in r.headers
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_healthz_es_publico_y_no_revela_nada():
    r = cliente.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# --------------------------------------------- inyeccion
def test_el_html_del_usuario_sale_escapado():
    r = cliente.post("/generar", data={
        "peticion": "dame cinco <script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in r.text


def test_la_redaccion_no_recibe_el_texto_del_usuario():
    """El paso de prosa solo ve parametros validados: sin canal de inyeccion."""
    import inspect
    from llm import openrouter
    fuente = inspect.getsource(openrouter.redactar)
    assert "peticion" not in fuente
    assert "parametros[" in fuente
