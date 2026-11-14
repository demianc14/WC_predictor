# Roadmap: tareas listas para tomar

Este es el tablero de trabajo. La bitácora (`docs/PROYECTO_OBSIDIAN.md`) es el historial y explica el porqué de cada cifra. Este archivo dice **qué sigue y cómo cerrarlo**.

**Cómo usarlo (en una sesión nueva de Claude Code):**
1. Leer `CLAUDE.md`, que tiene los principios, los comandos y las reglas.
2. Tomar la primera tarea `[ ]` de la cola. Hacer `git pull` y abrir una rama y un PR por tarea, con commits chicos.
3. Las cifras salen de un comando. Lo que no se midió se marca **OJO** y no se inventa.
4. Cerrar con lo hecho, lo verificado (con el comando) y lo pendiente. Marcar la tarea `[x]` acá y dejar la cifra en la bitácora.

Estado al 14-nov-2026:
- **Champions:** en vivo desde el 4-nov (PRs #16, #17 y #18), con 9 partidos evaluados. Es muy poca muestra para leer algo. La calibración del empate (T1) se midió y no se adoptó. Las idas de eliminatorias ya tienen código (T2) y se guardarán desde el playoff de febrero.
- **Ligas:** 107 partidos evaluados. El mercado le gana al modelo (RPS 0,209 contra 0,204, misma muestra).

---

## Cola

### [ ] T2. Eliminatorias de la Champions en el almacén y el ciclo diario

**Ya no espera al feed.** El 14-nov se midió en los feeds de 2024-25 y 2025-26 (en caché) cómo nombra fixturedownload las eliminatorias, y el código quedó listo. Se activa solo cuando el feed 2026 traiga las rondas mayores que 8.

**Avance (14-nov, PR de T2).** Hecho:
- `store.match_id(..., ko_round)`: la ronda va en el id solo en las eliminatorias (`UCL-2627-R9-…`), y los ids ya guardados no cambian (test contra todas las filas UCL del almacén). El choque real era con la fase de liga, no entre la ida y la vuelta: 6 cruces repetidos en 2024-25 y 7 en 2025-26.
- `src/europe/run.py`: lee las rondas 9 a 17 (playoff 9/10, octavos 11/12, cuartos 13/14, semis 15/16, final 17) y las valida por ronda. Una ronda incompleta o con un club sin rating se salta entera y se avisa en `ucl.json` → `ko`.
- **Solo las idas (9, 11, 13 y 15) van al almacén**, porque el feed no separa la prórroga. Las vueltas y la final salen en la web marcadas "no se guarda", y la final se predice en cancha neutral.
- `src/pipeline/daily.py`: guarda las idas, completa sus resultados y suma `ucl.by_stage` en `live.json`.
- Tests en `tests/test_ucl_eliminatorias.py`. Detalle y cifras en la bitácora §14.1.

**Falta para marcarla `[x]`:**
1. Comprobar en producción que las idas del playoff (feb-2027) quedan guardadas antes de jugarse: `grep -c "^UCL-2627-R9-" data/predictions/predicciones.csv` tiene que dar 8. Revisar antes `ko.state` en `data/processed/ucl.json`.
2. Una vez sorteado el cuadro real (fines de enero de 2027), simular desde el cuadro sorteado en lugar de sortearlo en cada corrida (`src/europe/knockout.py`).

**OJO:** no se sabe si fixturedownload publica las rondas antes del sorteo con nombres provisionales. Si lo hace, el fail fast las salta hasta que lleguen los clubes reales.

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
