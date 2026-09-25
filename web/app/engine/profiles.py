"""Perfiles estructurales del historico. Verbatim del baseline (paso 3).

Estos son los patrones que SI son estables en un sorteo aleatorio: no predicen
nada, describen como se reparten los numeros cuando salen. Son la base de los
filtros de generacion, cuyo proposito es evitar los boletos que juega mucha
gente, no acertar mas.
"""
import collections


def perfil(sorteos, matriz):
    n = len(sorteos)
    sumas = sorted(sum(s.principales) for s in sorteos)
    q1, q3 = sumas[n // 4], sumas[3 * n // 4]
    mediana = sumas[n // 2]

    impares_total = sum(1 for s in sorteos for x in s.principales if x % 2)
    mitad = matriz.max_principal // 2 + 1  # 35 en Powerball
    bajos_total = sum(1 for s in sorteos for x in s.principales if x <= mitad)
    reparto_impares = collections.Counter(
        sum(1 for x in s.principales if x % 2) for s in sorteos
    )
    decenas = collections.Counter(
        len(set((x - 1) // 10 for x in s.principales)) for s in sorteos
    )
    rachas = collections.Counter(_racha_maxima(s.principales) for s in sorteos)
    con_par_consecutivo = sum(
        1 for s in sorteos if _racha_maxima(s.principales) >= 2
    )
    return {
        "n": n,
        "suma_q1": q1,
        "suma_q3": q3,
        "suma_mediana": mediana,
        "umbral_bajos": mitad,
        "pct_impares": 100 * impares_total / (n * matriz.principales),
        "pct_bajos": 100 * bajos_total / (n * matriz.principales),
        "reparto_impares": {k: 100 * v / n for k, v in sorted(reparto_impares.items())},
        "decenas": {k: 100 * v / n for k, v in sorted(decenas.items())},
        "rachas": {k: (v, 100 * v / n) for k, v in sorted(rachas.items())},
        "pct_con_par_consecutivo": 100 * con_par_consecutivo / n,
    }


def _racha_maxima(principales):
    mejor = actual = 1
    for i in range(len(principales) - 1):
        actual = actual + 1 if principales[i + 1] - principales[i] == 1 else 1
        mejor = max(mejor, actual)
    return mejor


def perfil_boleto(principales, matriz, umbral_bajos):
    return {
        "suma": sum(principales),
        "impares": sum(1 for x in principales if x % 2),
        "bajos": sum(1 for x in principales if x <= umbral_bajos),
        "decenas": len(set((x - 1) // 10 for x in principales)),
        "racha_maxima": _racha_maxima(principales),
    }
