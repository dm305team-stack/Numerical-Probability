#!/usr/bin/env python3
"""Extrae los sorteos de Knowledge/Base-Secuence.pdf a web/data/draws_pdf.csv.

Se corre UNA vez. La app lee el CSV, no el PDF.

Ojo: el PDF no tiene fechas. La columna `idx_pdf` conserva la posicion original
(0 = fila mas nueva del PDF) para poder cotejarlo despues contra el archivo
oficial fechado cuando exista la ingesta.
"""
import csv, os, re, subprocess, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, "..", ".."))
PDF = os.path.join(RAIZ, "Knowledge", "Base-Secuence.pdf")
DESTINO = os.path.join(AQUI, "..", "data", "draws_pdf.csv")

def main():
    if not os.path.exists(PDF):
        sys.exit(f"no existe el PDF: {PDF}")
    txt = os.path.join(tempfile.gettempdir(), "np_base_extract.txt")
    subprocess.run(["pdftotext", "-layout", PDF, txt], check=True)
    filas = []
    for linea in open(txt):
        n = [int(x) for x in re.findall(r"\d+", linea)]
        if len(n) == 6:
            filas.append(n)
    with open(DESTINO, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx_pdf", "n1", "n2", "n3", "n4", "n5", "pb"])
        for i, n in enumerate(filas):
            w.writerow([i] + n)
    print(f"{len(filas)} filas -> {os.path.relpath(DESTINO, RAIZ)}")

if __name__ == "__main__":
    main()
