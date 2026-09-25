#!/usr/bin/env bash
# Arranque local para pruebas. Sin APP_KEY no pide clave.
#
#   ./run-local.sh                          # interprete local, sin modelo
#   OPENROUTER_API_KEY=sk-or-... ./run-local.sh   # con modelo
#
set -e
cd "$(dirname "$0")"
if [ ! -f data/draws_pdf.csv ]; then
  echo "· extrayendo los sorteos del PDF (solo la primera vez)"
  python3 tools/extract_pdf.py
fi
# LOCAL=1 desactiva la exigencia de APP_KEY. En el VPS NO se pone: alli la app
# debe negarse a arrancar sin clave.
export LOCAL="${LOCAL:-1}"
export PYTHONPATH="$PWD/app:$PYTHONPATH"
echo "· http://127.0.0.1:8000"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
