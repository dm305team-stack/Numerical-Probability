"""Ranking 55% frecuencia historica + 45% retraso. Verbatim del baseline (paso 4).

AVISO QUE DEBE SOBREVIVIR A CUALQUIER REFACTOR: este ranking NO mejora la
probabilidad de acertar. El historico es uniforme (chi2 p=0,162) y cada boleto
vale 1 entre 292.201.338 se elija como se elija. El ranking existe para dar un
criterio estable de preferencia y para alimentar los pesos de la generacion, no
porque unos numeros salgan mas.

El retraso se mide en NUMERO DE SORTEOS, no en dias. Depende de que `sorteos`
venga en orden cronologico ascendente; si alguien invierte esa lista, todos los
retrasos salen al reves y nada avisa.
"""
import collections

PESO_FRECUENCIA = 0.55
PESO_RETRASO = 0.45
TOPE_RETRASO = 2.5  # un retraso de mas de 2,5x el medio no puntua mas


def _puntuar(frecuencias, retrasos, universo, esperado_freq, retraso_medio):
    return {
        n: PESO_FRECUENCIA * (frecuencias.get(n, 0) / esperado_freq)
        + PESO_RETRASO * min(retrasos[n] / retraso_medio, TOPE_RETRASO)
        for n in universo
    }


def calcular(sorteos, matriz):
    """Devuelve (score_principales, score_extra, frecuencias, retrasos)."""
    n = len(sorteos)
    frec_principales = collections.Counter()
    frec_extra = collections.Counter()
    for s in sorteos:
        frec_principales.update(s.principales)
        frec_extra[s.extra] += 1

    ultima = {}
    for i, s in enumerate(sorteos):
        for x in s.principales:
            ultima[x] = i
    universo = range(1, matriz.max_principal + 1)
    retrasos = {x: n - 1 - ultima.get(x, -1) for x in universo}
    score = _puntuar(
        frec_principales,
        retrasos,
        universo,
        n * matriz.principales / matriz.max_principal,
        sum(retrasos.values()) / matriz.max_principal,
    )

    ultima_e = {}
    for i, s in enumerate(sorteos):
        ultima_e[s.extra] = i
    universo_e = range(1, matriz.max_extra + 1)
    retrasos_e = {p: n - 1 - ultima_e.get(p, -1) for p in universo_e}
    score_e = _puntuar(
        frec_extra,
        retrasos_e,
        universo_e,
        n / matriz.max_extra,
        sum(retrasos_e.values()) / matriz.max_extra,
    )
    return score, score_e, (frec_principales, frec_extra), (retrasos, retrasos_e)
