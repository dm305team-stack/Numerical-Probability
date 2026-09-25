# SESSION — Numerical Probability

> ⚠️ **Handoff más reciente: [SESSION-2026-09-25.md](SESSION-2026-09-25.md)** — web app
> construida y en GitHub, el corpus contaminado con Double Play, y la revisión de
> seguridad. Antes de esa: [SESSION-2026-07-27.md](SESSION-2026-07-27.md) — baseline
> local generado, dos bugs de datos en Base-Secuence.pdf documentados, bitácora de
> sorteos abierta. Este archivo queda como registro de la sesión de junio.

> Handoff para retomar. Última actualización: 2026-06-11 (segunda sesión del día).

## Dónde quedamos

El GPT personalizado **NUMERICAL PROBABILITY** de ChatGPT quedó convertido en una
**app nativa de macOS (SwiftUI)**, construida y commiteada en `main` en una sola
sesión. La app **compila sin Xcode** (solo Command Line Tools + SPM), pasó una
**revisión adversarial de 28 agentes** (11 hallazgos reales corregidos, 2 de ellos
críticos), y quedó lista con la API key guardada en Keychain y los 4 PDFs de
conocimiento cargados.

En la segunda sesión se resolvió la inconsistencia del prompt original
(seis vs. cinco números): **el formato correcto es 5 + 1** — cinco números dobles
más uno adicional, seis valores en total, estilo lotería. El prompt embebido, el
kickoff y el contrato de salida ya lo dicen explícito, y la tarjeta de secuencias
muestra el plus-one separado (`04 18 23 35 41 + 49`). Commit `c1b2330`.

Falta la **primera corrida real** (clic en *Analyze & Generate* — la hace Fermín
porque consume tokens de Opus). La app quedó relanzada y lista; al cierre de
sesión no se había reportado resultado de la corrida.

## Estado por pieza

| Pieza | Estado |
| --- | --- |
| Código (16 archivos Swift: modelos, servicios, vistas, AppModel) | ✅ completo, compila limpio |
| Build sin Xcode (`swift build` + `Scripts/bundle.sh` → app firmada) | ✅ verificado de punta a punta |
| API key Anthropic | ✅ guardada en Keychain vía la app |
| Knowledge: Base-Secuence (66pp) + Markov + Fibonacci + Luck Factor | ✅ en `Knowledge/`, auto-cargan |
| Revisión adversarial aplicada | ✅ commits `68596a1` + `f649c12` |
| README + memoria de proyecto | ✅ |
| Formato 5+1 resuelto en prompt + UI | ✅ commit `c1b2330` |
| **Primera corrida E2E** (Analyze → reporte → secuencias → Export PDF) | ⏳ **pendiente** |

## Decisiones clave de arquitectura

- **Motor**: `claude-opus-4-8`, streaming SSE por `URLSession` crudo (no hay SDK
  Swift), thinking adaptativo con resumen visible.
- **Cálculo real**: herramienta de **code execution** del lado del servidor de
  Anthropic (Python: chi-cuadrado, Benford, Monte Carlo) — el equivalente del
  Code Interpreter del GPT. El PDF final se genera en el sandbox y se descarga
  por **Files API**.
- **Conocimiento**: los 4 PDFs van como document blocks base64 con **cache de
  1 hora** (breakpoint en el último doc); turnos siguientes releen a ~0.1× precio.
- **pause_turn**: los análisis largos se auto-reanudan (hasta 8 rondas) y el
  contenido se **fusiona en UN solo mensaje assistant** (mensajes consecutivos
  del mismo rol = error 400 — fue el hallazgo crítico #1 de la revisión).
- **Historial**: bloques assistant guardados como JSON crudo (`JSONValue`) y
  reenviados textuales — los thinking blocks no admiten modificación en replay.
- El prompt original del GPT está **embebido textual** en `Prompts.swift`; el
  mensaje kickoff impone el contrato `<final_sequences>` parseable y el nombre
  fijo `Numerical_Probability_Report.pdf`.

## Cómo arrancar la app

```bash
cd /Volumes/NEXUS-WEST/Antigravity/NUMERICAL-PROBABILITY

Scripts/bundle.sh release --run   # app real firmada en dist/ (recomendado)
# o doble clic en dist/NumericalProbability.app desde Finder
# o, para desarrollo:
swift run                         # debug; acepta ANTHROPIC_API_KEY=... como env
```

## Pendientes (al retomar mañana)

1. **Primera corrida real**: lanzar la app (`Scripts/bundle.sh release --run` o
   doble clic en `dist/`) y clic en *Analyze & Generate*. Verificar: reporte
   fluye en vivo con estados ("Running Python…"), la tarjeta *Final Sequences*
   parsea las secuencias en formato `5 + 1`, *Export PDF* descarga el reporte.
   Ojo: la primera corrida es la cara (escribe ~91 págs al cache + análisis
   pesado); repetir dentro de la misma hora sale mucho más barato. Tras el
   rebuild, el Keychain pedirá permiso una vez — "Permitir siempre". En DEBUG,
   la consola imprime `[cache] read N input tokens` para confirmar el cache.
2. Tras la corrida, probar el **chat de seguimiento** (misma conversación,
   reutiliza el sandbox — p. ej. "regenerate the PDF with 10 sequences").
3. **v1.1 opcional**: subir Base-Secuence.pdf también vía `POST /v1/files` +
   bloque `container_upload`, para que el Python del sandbox parsee los dígitos
   directo del PDF (hoy el modelo los transcribe desde su contexto).
4. Detalle conocido del dev-loop: con firma ad-hoc, el Keychain puede volver a
   pedir permiso tras cada rebuild — en DEBUG usar el env var lo evita.

## Resuelto en la sesión 2 (2026-06-11 tarde)

- **Formato de secuencias = 5 + 1** (cinco números dobles + uno adicional,
  seis en total). Aplicado en `Prompts.swift` (regla de generación, paso 4 del
  kickoff, contrato `<final_sequences>`) y en `GeneratedSequence.display`
  (RunState.swift). Commit `c1b2330`.
