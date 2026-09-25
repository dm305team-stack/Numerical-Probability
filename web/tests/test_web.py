"""Tests de la capa web: semilla, guardia de cifras y rutas."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app, proximo_sorteo, resumen_determinista, semilla_de
from engine.matrix import POWERBALL
from llm.openrouter import texto_limpio

cliente = TestClient(app)


# ------------------------------------------------------- guardia de cifras
@pytest.mark.parametrize("texto,pasa", [
    # lo unico que puede escribir el modelo: prosa sin ninguna cantidad
    ("Estos boletos no valen más que cualquier otra combinación del bombo.", True),
    ("El reparto evita los patrones que juega mucha gente.", True),
    # red 1: cifras
    ("Estos 5 boletos tienen un 12% de acierto.", False),
    # red 2: numeros en letra -- la que faltaba
    ("Uno entre doscientos noventa y dos millones.", False),
    ("El cuarenta y cuatro lleva tiempo sin salir.", False),
    # red 3: vocabulario prohibido
    ("El numero 7 esta caliente.", False),
    ("Te garantizo que vas a ganar.", False),
    ("Buena suerte con la jugada.", False),
    ("Es la mejor combinación posible.", False),
    ("Este número está atrasado y le toca.", False),
    ("Invierte más en esta jugada.", False),
    ("", False),
])
def test_guardia_de_afirmaciones(texto, pasa):
    """Tres redes: ni cifras, ni números en letra, ni promesas."""
    assert texto_limpio(texto) is pasa


# ------------------------------------------------------- semilla
def test_semilla_fijada_manda():
    s, fija = semilla_de("lo que sea", POWERBALL, "20260727")
    assert (s, fija) == (20260727, True)


def test_semilla_misma_peticion_mismo_dia():
    a, _ = semilla_de("dame cinco", POWERBALL)
    b, _ = semilla_de("dame cinco", POWERBALL)
    assert a == b


def test_semilla_ignora_espacios_y_mayusculas():
    a, _ = semilla_de("Dame  CINCO combinaciones", POWERBALL)
    b, _ = semilla_de("dame cinco combinaciones", POWERBALL)
    assert a == b


def test_semilla_cambia_con_la_peticion():
    a, _ = semilla_de("dame cinco", POWERBALL)
    b, _ = semilla_de("dame seis", POWERBALL)
    assert a != b


def test_proximo_sorteo_cae_en_dia_de_sorteo():
    # 2026-09-25 es viernes; el proximo Powerball es el sabado 26
    assert proximo_sorteo(POWERBALL, date(2026, 9, 25)) == date(2026, 9, 26)
    # un lunes es dia de sorteo: se devuelve el mismo dia
    assert proximo_sorteo(POWERBALL, date(2026, 9, 28)) == date(2026, 9, 28)


# ------------------------------------------------------- resumen del servidor
def test_resumen_del_servidor_no_promete_nada():
    params = {"cuantos": 5, "incluir": [12], "excluir": [13], "incluir_en": 2}
    t = resumen_determinista(params, POWERBALL, 2004)
    assert "292.201.338" in t
    assert "más probabilidad" in t
    for prohibida in ("suerte", "caliente", "seguro", "ganarás", "garantiza"):
        assert prohibida not in t.lower()


# ------------------------------------------------------- rutas
def test_salud():
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json()["sorteos"] == 2004


def test_index_responde():
    r = cliente.get("/")
    assert r.status_code == 200
    assert "Numerical" in r.text


def test_generar_devuelve_boletos():
    r = cliente.post("/generar", data={"peticion": "dame cinco combinaciones"})
    assert r.status_code == 200
    assert r.text.count('class="bola"') == 25  # 5 boletos x 5 principales
    assert r.text.count('class="bola extra"') == 5


def test_generar_respeta_las_restricciones():
    r = cliente.post("/generar", data={
        "peticion": "seis boletos con el 12 en algunos y sin el 13"})
    import re
    bolas = [re.findall(r">(\d{2})</b>", li)
             for li in re.findall(r"<li>(.*?)</li>", r.text, re.S)]
    bolas = [b for b in bolas if b]
    assert len(bolas) == 6
    assert sum(1 for b in bolas if "12" in b[:-1]) == 2
    assert not any("13" in b for b in bolas)


def test_semilla_fijada_reproduce_el_baseline_de_julio():
    """La via web tiene que dar lo mismo que el script medido."""
    import re
    r = cliente.post("/generar", data={
        "peticion": "dame cinco combinaciones", "semilla_fijada": "20260727"})
    bolas = [re.findall(r">(\d{2})</b>", li)
             for li in re.findall(r"<li>(.*?)</li>", r.text, re.S)]
    bolas = [b for b in bolas if b]
    assert bolas[0] == ["12", "21", "30", "42", "69", "05"]
    assert bolas[4] == ["03", "32", "42", "61", "67", "13"]


def test_peticion_imposible_da_error_legible():
    r = cliente.post("/generar", data={"peticion": "dame 40 combinaciones"})
    assert r.status_code == 200
    assert "entre 1 y 14" in r.text   # 14 es el techo REAL, medido


def test_numero_fuera_de_matriz():
    r = cliente.post("/generar", data={"peticion": "dame cinco con el 80"})
    assert "no existe en Powerball" in r.text


def test_rigor_dice_que_no_hay_alta_probabilidad():
    r = cliente.get("/rigor")
    assert r.status_code == 200
    assert "no existen combinaciones con más probabilidad" in r.text
    assert "292.201.338" in r.text
