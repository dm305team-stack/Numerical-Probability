"""Tests de oro: el motor portado debe dar EXACTAMENTE lo que dio el baseline.

Si uno de estos falla, el motor ha dejado de ser el que se midio. No "arregles"
el test: averigua que cambio en el motor.

Las referencias salen de Analysis/baseline_analysis.py y de SESSION-2026-07-27.md.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from engine.data import cargar_pdf
from engine.generate import NoConverge, generar
from engine.matrix import POWERBALL
from engine.profiles import perfil
from engine.ranking import calcular
from engine.stats import chi2, chi2_sf, markov_permutacion, runs_test

# --- boletos publicados en SESSION-2026-07-27.md, semilla 20260727 ---
BASELINE_JULIO = [
    ([12, 21, 30, 42, 69], 5),
    ([14, 31, 44, 51, 54], 15),
    ([13, 29, 38, 52, 65], 6),
    ([9, 11, 30, 60, 64], 25),
    ([3, 32, 42, 61, 67], 13),
]

# --- boletos entregados el 2026-09-07 en conversacion, semilla 20260907 ---
BASELINE_SEPTIEMBRE = [
    ([3, 29, 36, 45, 68], 22),
    ([12, 13, 32, 44, 61], 10),
    ([17, 25, 30, 39, 64], 1),
    ([8, 18, 45, 65, 69], 16),
    ([15, 18, 35, 42, 66], 13),
    ([7, 17, 38, 53, 60], 7),
]


@pytest.fixture(scope="module")
def motor():
    sorteos, descartados = cargar_pdf(POWERBALL)
    p = perfil(sorteos, POWERBALL)
    score, score_extra, frecuencias, retrasos = calcular(sorteos, POWERBALL)
    return {
        "sorteos": sorteos,
        "descartados": descartados,
        "perfil": p,
        "score": score,
        "score_extra": score_extra,
        "frecuencias": frecuencias,
        "retrasos": retrasos,
    }


# ---------------------------------------------------------------- datos
def test_recuento_de_filas(motor):
    """2.004 de la matriz vigente y 698 de la era anterior a octubre de 2015.

    Ojo: SESSION-2026-07-27.md dice 2.703 filas totales; son 2.702.
    """
    assert len(motor["sorteos"]) == 2004
    assert motor["descartados"] == 698


def test_orden_cronologico(motor):
    """El PDF viene del mas nuevo al mas viejo y hay que invertirlo (bug 1).

    No hay fechas para comprobarlo directamente, asi que se comprueba contra la
    fila que el PDF trae primera: debe quedar la ULTIMA del historico cargado.
    """
    ultimo = motor["sorteos"][-1]
    assert ultimo.principales == (11, 26, 27, 53, 55)
    assert ultimo.extra == 12


def test_ninguna_bola_fuera_de_matriz(motor):
    for s in motor["sorteos"]:
        assert all(1 <= n <= POWERBALL.max_principal for n in s.principales)
        assert 1 <= s.extra <= POWERBALL.max_extra
        assert len(set(s.principales)) == POWERBALL.principales


# ---------------------------------------------------------------- estadistica
def test_uniformidad_principales(motor):
    """chi2 = 79,42 con df=68, p = 0,162. No se rechaza la uniformidad."""
    import collections

    frec = collections.Counter()
    for s in motor["sorteos"]:
        frec.update(s.principales)
    x2 = chi2(frec, POWERBALL.max_principal, len(motor["sorteos"]) * 5)
    assert round(x2, 2) == 79.42
    assert round(chi2_sf(x2, 68), 3) == 0.162


def test_uniformidad_extra(motor):
    """chi2 = 13,57 con df=25, p = 0,969."""
    import collections

    frec = collections.Counter(s.extra for s in motor["sorteos"])
    x2 = chi2(frec, POWERBALL.max_extra, len(motor["sorteos"]))
    assert round(x2, 2) == 13.57
    assert round(chi2_sf(x2, 25), 3) == 0.969


def test_runs(motor):
    """z = +0,741: sin memoria serial en las sumas."""
    sumas = [sum(s.principales) for s in motor["sorteos"]]
    _, _, z = runs_test(sumas)
    assert round(z, 3) == 0.741


def test_markov_sin_dependencia(motor):
    """p = 0,113 con 20.000 permutaciones y estados colapsados."""
    _, p = markov_permutacion(motor["sorteos"])
    assert round(p, 3) == 0.113


def test_perfil_estructural(motor):
    """Banda intercuartil de la suma: 148-206."""
    p = motor["perfil"]
    assert (p["suma_q1"], p["suma_q3"]) == (148, 206)
    assert p["rachas"][1][0] == 1459   # sorteos sin ningun par consecutivo
    assert p["rachas"][4][0] == 2      # y solo dos con cuatro seguidos
    assert 5 not in p["rachas"]        # cinco consecutivos: nunca ha pasado


# ---------------------------------------------------------------- generacion
def test_golden_julio(motor):
    boletos, _ = generar(
        motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
        semilla=20260727, cuantos=5,
    )
    assert boletos == BASELINE_JULIO


def test_golden_septiembre(motor):
    boletos, intentos = generar(
        motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
        semilla=20260907, cuantos=6,
    )
    assert boletos == BASELINE_SEPTIEMBRE
    assert intentos == 299  # el consumo del RNG tambien es contractual


def test_misma_semilla_mismo_resultado(motor):
    a, _ = generar(motor["score"], motor["score_extra"], POWERBALL,
                   motor["perfil"], semilla=42, cuantos=5)
    b, _ = generar(motor["score"], motor["score_extra"], POWERBALL,
                   motor["perfil"], semilla=42, cuantos=5)
    assert a == b


def test_semillas_distintas_resultados_distintos(motor):
    a, _ = generar(motor["score"], motor["score_extra"], POWERBALL,
                   motor["perfil"], semilla=1, cuantos=5)
    b, _ = generar(motor["score"], motor["score_extra"], POWERBALL,
                   motor["perfil"], semilla=2, cuantos=5)
    assert a != b


# ---------------------------------------------------------------- restricciones
def test_excluir_saca_el_numero_de_todo(motor):
    boletos, _ = generar(
        motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
        semilla=20260907, cuantos=6, excluir=[13],
    )
    for principales, extra in boletos:
        assert 13 not in principales
        assert extra != 13


def test_incluir_mete_el_numero_en_los_boletos_pedidos(motor):
    boletos, _ = generar(
        motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
        semilla=20260907, cuantos=6, incluir=[12], incluir_en=2,
    )
    con_doce = [b for b in boletos if 12 in b[0]]
    assert len(con_doce) == 2


def test_incluir_y_excluir_a_la_vez_es_error(motor):
    with pytest.raises(NoConverge):
        generar(motor["score"], motor["score_extra"], POWERBALL,
                motor["perfil"], semilla=1, cuantos=5,
                incluir=[7], excluir=[7])


def test_restriccion_imposible_no_cuelga(motor):
    """Excluir casi todo debe fallar rapido y claro, no girar 500.000 veces."""
    with pytest.raises(NoConverge):
        generar(motor["score"], motor["score_extra"], POWERBALL,
                motor["perfil"], semilla=1, cuantos=5,
                excluir=list(range(1, 27)))


def test_filtros_estructurales_se_cumplen(motor):
    boletos, _ = generar(
        motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
        semilla=777, cuantos=6,
    )
    p = motor["perfil"]
    extras = set()
    for principales, extra in boletos:
        assert p["suma_q1"] <= sum(principales) <= p["suma_q3"]
        assert sum(1 for n in principales if n % 2) in (2, 3)
        assert len(set((n - 1) // 10 for n in principales)) >= 4
        assert extra not in extras
        extras.add(extra)


def test_solapamiento_maximo_de_uno(motor):
    boletos, _ = generar(
        motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
        semilla=777, cuantos=6,
    )
    for i in range(len(boletos)):
        for j in range(i + 1, len(boletos)):
            compartidos = set(boletos[i][0]) & set(boletos[j][0])
            assert len(compartidos) <= 1


def test_los_boletos_nunca_comparten_mas_de_uno_ni_con_numeros_forzados(motor):
    """El contrato de solape <= 1 valia solo sin restricciones: los numeros
    forzados se restaban de la cuenta y se entregaban boletos que compartian
    tres numeros."""
    import itertools
    # Este caso exacto entregaba dos boletos con [7, 31, 55] compartidos.
    # Ahora o cumple el contrato o se niega; lo que no puede es incumplirlo.
    for semilla in range(6):
        try:
            boletos, _ = generar(
                motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
                semilla=semilla, cuantos=2, incluir=[7, 31, 55], incluir_en=2,
            )
        except NoConverge:
            continue
        for a, b in itertools.combinations(boletos, 2):
            assert len(set(a[0]) & set(b[0])) <= 1


def test_nunca_se_entrega_un_boleto_con_mas_bolas_de_las_que_caben(motor):
    for n in (1, 2, 3):
        try:
            boletos, _ = generar(
                motor["score"], motor["score_extra"], POWERBALL, motor["perfil"],
                semilla=3, cuantos=n, incluir=[7, 19, 31, 44, 55, 66], incluir_en=2,
            )
        except NoConverge:
            continue   # negarse es la respuesta correcta
        for principales, _extra in boletos:
            assert len(principales) == POWERBALL.principales
