"""API publica del motor. La app solo habla con este modulo.

Corte entre precalculo y peticion (decision de diseno):
  PRECALCULADO UNA VEZ al arrancar, porque es caro y no depende de la peticion:
    carga del historico, chi2, runs, Markov con 20.000 permutaciones, perfiles
    estructurales y el ranking 55/45. El Markov solo ya tarda ~9 s.
  POR PETICION, porque es barato (milisegundos) y depende de lo que pida el
    usuario: la generacion de boletos.
  BAJO DEMANDA, nunca en la ruta de la peticion: el Monte Carlo de 300.000
    sorteos.
"""
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field

from .data import cargar_pdf
from .generate import NoConverge, generar
from .matrix import MATRICES, POWERBALL, Matriz
from .profiles import perfil, perfil_boleto
from .ranking import calcular
from .stats import chi2, chi2_sf, markov_permutacion, runs_test

CACHE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "analysis_cache.json")
)


@dataclass
class Analisis:
    matriz: Matriz
    sorteos: list
    descartados: int
    perfil: dict
    score: dict
    score_extra: dict
    frecuencias: tuple
    retrasos: tuple
    veredicto: dict
    fuente: str
    calculado_en: float = 0.0

    @property
    def n(self):
        return len(self.sorteos)

    def top(self, cuantos=14):
        orden = sorted(self.score, key=self.score.get, reverse=True)
        return [(n, self.score[n]) for n in orden[:cuantos]]

    def top_extra(self, cuantos=6):
        orden = sorted(self.score_extra, key=self.score_extra.get, reverse=True)
        return [(p, self.score_extra[p]) for p in orden[:cuantos]]


def _huella(sorteos):
    crudo = ";".join(f"{'-'.join(map(str, s.principales))}:{s.extra}" for s in sorteos)
    return hashlib.sha256(crudo.encode()).hexdigest()[:16]


def _veredicto(sorteos, matriz, huella):
    """Las pruebas caras. Se cachean en disco por huella del historico."""
    if os.path.exists(CACHE):
        try:
            guardado = json.load(open(CACHE))
            if guardado.get("huella") == huella:
                return guardado["veredicto"]
        except (ValueError, KeyError, OSError):
            pass  # cache corrupta: se recalcula y se pisa

    import collections

    n = len(sorteos)
    frec = collections.Counter()
    for s in sorteos:
        frec.update(s.principales)
    x2m = chi2(frec, matriz.max_principal, n * matriz.principales)
    pm = chi2_sf(x2m, matriz.max_principal - 1)

    frec_e = collections.Counter(s.extra for s in sorteos)
    x2e = chi2(frec_e, matriz.max_extra, n)
    pe = chi2_sf(x2e, matriz.max_extra - 1)

    runs, esperado, z = runs_test([sum(s.principales) for s in sorteos])
    x2mk, pmk = markov_permutacion(sorteos)

    v = {
        "principales": {"x2": x2m, "df": matriz.max_principal - 1, "p": pm,
                        "uniforme": pm > 0.05},
        "extra": {"x2": x2e, "df": matriz.max_extra - 1, "p": pe,
                  "uniforme": pe > 0.05},
        "runs": {"runs": runs, "esperado": esperado, "z": z,
                 "sin_memoria": abs(z) < 1.96},
        "markov": {"x2": x2mk, "p": pmk, "sin_dependencia": pmk > 0.05,
                   "permutaciones": 20000},
        "combinaciones": matriz.combinaciones,
        "probabilidad_pct": 100 / matriz.combinaciones,
    }
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump({"huella": huella, "veredicto": v}, open(CACHE, "w"), indent=2)
    except OSError:
        pass  # sin cache en disco se recalcula al arrancar; no es fatal
    return v


_ANALISIS = {}


def analizar(clave="powerball", recargar=False):
    """Devuelve el analisis completo de una matriz. Cacheado en memoria."""
    if clave in _ANALISIS and not recargar:
        return _ANALISIS[clave]
    matriz = MATRICES[clave]
    inicio = time.time()
    sorteos, descartados = cargar_pdf(matriz)
    p = perfil(sorteos, matriz)
    score, score_extra, frecuencias, retrasos = calcular(sorteos, matriz)
    v = _veredicto(sorteos, matriz, _huella(sorteos))
    a = Analisis(
        matriz=matriz, sorteos=sorteos, descartados=descartados, perfil=p,
        score=score, score_extra=score_extra, frecuencias=frecuencias,
        retrasos=retrasos, veredicto=v,
        fuente="Base-Secuence.pdf (sin fechas)",
        calculado_en=time.time() - inicio,
    )
    _ANALISIS[clave] = a
    return a


def boletos(analisis, semilla, cuantos=5, incluir=(), excluir=(), incluir_en=1):
    """Genera boletos y los devuelve ya con su perfil estructural."""
    crudos, intentos = generar(
        analisis.score, analisis.score_extra, analisis.matriz, analisis.perfil,
        semilla=semilla, cuantos=cuantos, incluir=incluir, excluir=excluir,
        incluir_en=incluir_en,
    )
    salida = []
    for principales, extra in crudos:
        salida.append({
            "principales": principales,
            "extra": extra,
            **perfil_boleto(principales, analisis.matriz,
                            analisis.perfil["umbral_bajos"]),
        })
    return salida, intentos


def cobertura(lista):
    """Cuantos numeros distintos cubren los boletos y cuanto se solapan."""
    numeros, extras = set(), set()
    for b in lista:
        numeros |= set(b["principales"])
        extras.add(b["extra"])
    solape = 0
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            solape = max(
                solape,
                len(set(lista[i]["principales"]) & set(lista[j]["principales"])),
            )
    return {"numeros": len(numeros), "extras": len(extras), "solape_max": solape}


def monte_carlo(lista, matriz, sorteos=300000, semilla=7):
    """Tasa de premio de cualquier nivel. CARO: no llamar en la ruta web."""
    rng = random.Random(semilla)
    aciertos = [0] * len(lista)
    universo = range(1, matriz.max_principal + 1)
    for _ in range(sorteos):
        d = set(rng.sample(universo, matriz.principales))
        de = rng.randrange(1, matriz.max_extra + 1)
        for i, b in enumerate(lista):
            if de == b["extra"] or len(d & set(b["principales"])) >= 3:
                aciertos[i] += 1
    return [100 * a / sorteos for a in aciertos]
