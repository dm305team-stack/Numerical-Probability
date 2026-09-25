# Numerical Probability — web

Interfaz web del motor estadístico de NUMERICAL-PROBABILITY. Pides boletos en
lenguaje natural y los calcula el motor determinista portado —verbatim— de
`Analysis/baseline_analysis.py`.

## Arranque local

```sh
./run-local.sh              # http://127.0.0.1:8000
```

Sin variables de entorno funciona en **modo local**: no pide clave y usa el
intérprete local de peticiones. Para probar con modelo:

```sh
OPENROUTER_API_KEY=sk-or-... ./run-local.sh
```

Tests:

```sh
python3 -m pytest tests/ -q      # 37 tests
```

## Variables de entorno

| Variable | Efecto si falta |
|---|---|
| `APP_KEY` | **La app no pide clave.** Obligatoria al desplegar. |
| `OPENROUTER_API_KEY` | Intérprete local + resumen del servidor. La app no se rompe. |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-haiku` |
| `TZ` | Obligatoria en el VPS: `America/New_York`. Sin ella, un servidor en UTC calcula mal el próximo sorteo. |

## Las cinco reglas que no se tocan

1. **El modelo nunca genera números.** Interpreta la petición y redacta. Los
   boletos salen siempre del motor.
2. **El texto del modelo no puede contener ni un dígito.** Se comprueba con una
   regex; si se cuela uno, el texto se descarta entero y se usa el resumen del
   servidor. Así es imposible que invente un boleto o una probabilidad.
3. **El orden cronológico es sagrado.** El PDF viene del sorteo más nuevo al más
   viejo. Si alguien quita la inversión de `engine/data.py`, todos los retrasos
   salen al revés y nada avisa.
4. **Los golden tests son el contrato.** `tests/test_golden.py` comprueba que el
   motor reproduce exactamente los boletos publicados del baseline. Si fallan,
   el motor ha dejado de ser el que se midió: investiga el motor, no el test.
5. **No existe la alta probabilidad.** Cada boleto vale 1 entre 292.201.338.
   Todo lo que hace el ranking y los filtros es evitar los patrones más jugados
   para reducir el riesgo de *compartir* un premio.

## Estructura

```
app/
  main.py            rutas, semilla, acceso, orquestación
  engine/            el motor. stats.py y generate.py son verbatim del baseline
    matrix.py        la matriz del juego como DATO (Powerball hoy, MM preparada)
    data.py          carga, corrige el orden invertido y el corte de matriz
    stats.py         chi2_sf a mano, runs, Markov por permutaciones
    profiles.py      perfiles estructurales del histórico
    ranking.py       55% frecuencia + 45% retraso
    generate.py      filtros y generación. El orden del RNG es CONTRACTUAL
  llm/
    intent.py        petición -> parámetros validados, con respaldo local
    openrouter.py    cliente + la guardia de cifras
  templates/         index, resultado, rigor, error, entrar
  static/            style.css y htmx vendorizado (funciona sin red)
data/
  draws_pdf.csv      2.702 filas extraídas del PDF. SIN FECHAS
  analysis_cache.json  el veredicto cacheado por huella del histórico
tools/extract_pdf.py   regenera el CSV desde el PDF
```

## Lo que falta

- **Ingesta oficial fechada.** `engine/data.cargar_oficial()` está declarada y
  lanza `NotImplementedError`. Mientras no exista: el histórico no se actualiza,
  el retraso del ranking envejece, y la frontera de octubre de 2015 se detecta
  por heurística (primera fila con bola extra > 26) en vez de por fecha.
- **Despliegue.** No hay Dockerfile ni compose: esta entrega es local. Falta
  saber qué proxy hay delante de glowbychoice.com.
- **Mega Millions.** La matriz está definida en `engine/matrix.py` pero sin
  histórico. No ofrecerla hasta que la ingesta la llene.
- **Bitácora de resultados.** Cotejar los boletos contra los sorteos reales.
