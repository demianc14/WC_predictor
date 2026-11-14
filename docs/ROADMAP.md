# Roadmap: tareas listas para tomar

Este es el tablero de trabajo. La bitácora (`docs/PROYECTO_OBSIDIAN.md`) es el historial y explica el porqué de cada cifra. Este archivo dice **qué sigue y cómo cerrarlo**.

**Cómo usarlo (en una sesión nueva de Claude Code):**
1. Leer `CLAUDE.md`, que tiene los principios, los comandos y las reglas.
2. Tomar la primera tarea `[ ]` de la cola. Hacer `git pull` y abrir una rama y un PR por tarea, con commits chicos.
3. Las cifras salen de un comando. Lo que no se midió se marca **OJO** y no se inventa.
4. Cerrar con lo hecho, lo verificado (con el comando) y lo pendiente. Marcar la tarea `[x]` acá y dejar la cifra en la bitácora.

Estado al 14-nov-2026:
- **Champions:** en vivo desde el 4-nov (PRs #16, #17 y #18), con 9 partidos evaluados. Es muy poca muestra para leer algo. La calibración del empate (T1) se midió y no se adoptó.
- **Ligas:** 107 partidos evaluados. El mercado le gana al modelo (RPS 0,209 contra 0,204, misma muestra).

---

## Cola

### [ ] T2. Eliminatorias de la Champions en el almacén y el ciclo diario

**Pendiente: espera al feed.** No se empieza hasta que fixturedownload publique los partidos del playoff (febrero de 2027) y se pueda ver cómo nombra las rondas.

**Ya hecho (9-nov, `src/europe/knockout.py`):**
- La simulación del cuadro completo, según el reglamento 2026/27 (Art. 19-22 y Anexo B), hasta P(campeón).
- El cuadro "si terminara hoy" y el proyectado, en la web.
- Las reglas y las simplificaciones están en la bitácora §12.5.

**Lo que falta:** predecir y guardar los partidos de eliminatorias cuando el feed los publique (el playoff es en febrero de 2027).

**Pasos.**
1. Hoy `store.match_id(div, season, home, away)` chocaría entre la ida y la vuelta. Hay que extenderlo de forma compatible, por ejemplo con la ronda solo para las eliminatorias, sin cambiar los ids de la fase de liga ya guardados. Sumar un test de solo-para-agregar.
2. En `src/europe/run.py`, incluir en `next` los partidos de las rondas mayores que 8 del feed, con su ronda. En `src/pipeline/daily.py`, guardarlos y completar sus resultados.
3. Una vez sorteado el cuadro real, simular desde el cuadro sorteado en lugar de sortearlo en cada corrida.

**Archivos.** `src/pipeline/store.py`, `src/pipeline/daily.py`, `src/europe/run.py` y `src/europe/knockout.py`, tests y la bitácora §14.1.

**OJO:** verificar cómo nombra el feed las rondas de eliminatorias (`RoundNumber`) cuando aparezcan. Ahora no hay ninguna.

**Cierre.** Partidos de eliminatorias guardados antes de jugarse, con un `match_id` compatible y un test.

---

### [ ] T3. Horario real del ciclo diario

**Por qué.** `daily.yml` tiene el cron a las 05:30 UTC, pero GitHub lo dispara entre las 09:39 y las 14:08 UTC (23 corridas, del 21-oct al 12-nov). Como un partido del mismo día solo se predice antes de las 10:00 UTC (`CUTOFF_HOUR_UTC`), hoy cada partido se predice en el ciclo del día anterior. Todavía no se perdió ninguno, pero un partido reprogramado para el mismo día se perdería.

**Pasos.** Probar un segundo cron de respaldo más temprano o mover el actual. El almacén ya es idempotente: una segunda corrida no duplica nada (comprobarlo con el test que ya existe). Medir durante una semana a qué hora corre en realidad.

**Cierre.** El horario medido en la bitácora §14.1 y en `CLAUDE.md`.

**Avance (12-nov).** Hecho: horario del cron de las 05:30 medido (23 corridas, arranca entre las 09:39 y las 14:08 UTC; ningún partido perdido), cron de respaldo a las 00:17 UTC y `test_una_segunda_corrida_el_mismo_dia_no_duplica_nada`. **Falta para marcarla `[x]`:** medir el horario real del respaldo con una semana de corridas (desde el 20-nov, comando en §14.1) y dejar la cifra en §14.1 y en `CLAUDE.md`. Si el respaldo tampoco arranca antes de las 10:00 UTC, adelantarlo o quitarlo.

---

## Después (sin orden fijo)

- **xG como feature del supervisado**, cuando 2026-27 tenga muestra suficiente. Mientras tanto, el Dixon-Coles ya lo usa.
- **Austria y Noruega** para LASK, Bodø/Glimt y Viking. football-data los publica en otro formato (`new leagues`), y hay que cruzar los nombres.
- **Cuotas de la Champions**, si aparece una fuente con fecha. Hoy la UCL solo se compara contra la base.
- **Copas nacionales y Conference** en el descanso del supervisado, si aparece una fuente con fecha. Europa ya se probó y no mejoró (§13.5).
- **Selecciones:** mapeos más allá de las 48, y ρ y el modelo de empates estimados sobre el historial completo.
- **Otros torneos:** un cuadro de la Euro o la Copa América que reutilice `match_engine.py`.
- **Métricas en vivo:** volver a leerlas con temporadas enteras, no con semanas.
- **Infraestructura,** solo si hace falta (base de datos o API). Hoy el CSV versionado es más auditable.

## Hecho recientemente

- [x] **T1. Calibración de la Champions (14-nov): medida, no se adopta.** Detalle y tablas en la bitácora §12.5.
  - **Qué quedó.** En `src/europe/backtest.py`: la regla de decisión (`adopt`, commit propio antes del test), la validación (UCL 2021-22 a 2023-24) y el test de una sola vez, con c = 0,90 congelado. Tests de no solapamiento de temporadas y fechas, de que c solo se elige con validación y de que el test no corre dos veces. `src/europe/run.py` no cambia.
  - **Resultado.** Test, n = 376: Δlog-loss −0.0059 [−0.0098, −0.0020]. El IC excluye el cero, pero la mejora no supera 0,012, así que no se adopta. En validación (n = 372), −0.0009 [−0.0052, +0.0035].
  - **Cómo se verificó:** `python -m src.europe.backtest --fase validacion` (→ `docs/ucl/validacion.json`), `python -m src.europe.backtest --fase test` (→ `docs/ucl/test.json`, commit 53a36a8), `pytest`, `ruff check . && mypy`.
  - **Versión de la UCL.** Cambió `src/europe/` (solo `backtest.py`), así que cambia `<src/clubs>+<src/europe>`. Las probabilidades son las mismas, pero el bot va a guardar filas nuevas con la versión nueva para los partidos de los próximos 7 días. Las filas ya publicadas no se tocan, y las métricas en vivo de la UCL usan la primera predicción de cada partido.
  - **Qué sigue:** volver a medir el empate con la Champions 2026-27 completa (formato de 36), sin reabrir este test.
  - **Qué decides tú:**
    1. Si el umbral de 0,012 se revisa para una tarea futura. Para c = 0,90 el IC real fue ±0,004, y cambiarlo para este test sería ajustarlo al resultado.
    2. Si se agenda la medición prospectiva sobre la 2026-27, con c congelado de antemano.
    3. Cuándo mergear: antes del 17-nov, la J5 ya sale con la versión nueva.

- [x] Champions: cuadro de eliminatorias simulado hasta P(campeón), en la web, ticker con los partidos más atractivos y textos en español neutro (9-nov).
- [x] Champions: Dixon-Coles conjunto y backtest (#16), ciclo diario y tabla simulada (#17), y la sección en la web (#18). Bitácora §12.5 y §14.1.
- [x] Métricas en vivo por versión del modelo (#15).
- [x] `hgb` en Docker con `OMP_NUM_THREADS=4` (#14).
