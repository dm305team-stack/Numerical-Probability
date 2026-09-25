"""Carga del historico de sorteos.

FUENTE ACTUAL: web/data/draws_pdf.csv, extraido de Knowledge/Base-Secuence.pdf.
Ese PDF NO TIENE FECHAS y viene ordenado del sorteo mas NUEVO al mas VIEJO.

Los dos bugs de datos documentados en SESSION-2026-07-27.md se tratan aqui y
solo aqui:
  1. Orden invertido -> se invierte al cargar, para que el indice 0 sea el mas
     antiguo. Todo calculo de retraso depende de esto.
  2. Mezcla de dos matrices -> las filas anteriores a octubre de 2015 son de la
     matriz 5/59 + PB 1/35 y se descartan. Sin fechas, la frontera se detecta
     por la primera fila con PB > 26, que es una HEURISTICA. Cuando exista la
     ingesta oficial fechada, `cargar_oficial` la sustituye por la fecha real y
     esta heuristica debe morir.
"""
import csv
import os
from dataclasses import dataclass

from .matrix import Matriz

AQUI = os.path.dirname(os.path.abspath(__file__))
CSV_PDF = os.path.abspath(os.path.join(AQUI, "..", "..", "data", "draws_pdf.csv"))


@dataclass(frozen=True)
class Sorteo:
    principales: tuple   # ordenadas de menor a mayor
    extra: int
    fecha: object = None # date o None: el PDF no trae fechas

    def __iter__(self):
        # compatibilidad con el desempaquetado (m, p) del baseline
        yield list(self.principales)
        yield self.extra


class HistoricoVacio(RuntimeError):
    pass


def _filas_crudas(ruta):
    with open(ruta) as f:
        for fila in csv.DictReader(f):
            yield [int(fila[c]) for c in ("n1", "n2", "n3", "n4", "n5", "pb")]


def cargar_pdf(matriz: Matriz, ruta=CSV_PDF):
    """Historico del PDF, acotado a la matriz vigente y en orden cronologico.

    Devuelve (sorteos, descartados_por_matriz).
    """
    if not os.path.exists(ruta):
        raise HistoricoVacio(
            f"no existe {ruta}. Corre: python3 tools/extract_pdf.py"
        )
    filas = list(_filas_crudas(ruta))
    corte = next(
        (i for i, r in enumerate(filas) if r[5] > matriz.max_extra), len(filas)
    )
    vigentes = filas[:corte][::-1]  # bug 1: invertir a orden cronologico
    sorteos = []
    for r in vigentes:
        principales, extra = r[:5], r[5]
        if not all(1 <= x <= matriz.max_principal for x in principales):
            continue
        if not 1 <= extra <= matriz.max_extra:
            continue
        if len(set(principales)) != matriz.principales:
            continue
        sorteos.append(Sorteo(tuple(sorted(principales)), extra))
    if not sorteos:
        raise HistoricoVacio("el historico quedo vacio tras el filtro de matriz")
    return sorteos, len(filas) - corte


def cargar_oficial(matriz: Matriz):
    """Historico oficial FECHADO. Pendiente de la investigacion de la fuente.

    Cuando exista, sustituye a cargar_pdf y con ella desaparece la heuristica
    del corte por PB>26: la frontera de octubre de 2015 pasa a ser una fecha.
    """
    raise NotImplementedError(
        "ingesta oficial no implementada todavia; usando el historico del PDF"
    )
