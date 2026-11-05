# Roadmap: tareas listas para tomar

Este es el tablero de trabajo. La bitácora (`docs/PROYECTO_OBSIDIAN.md`) es el historial y explica el porqué de cada cifra. Este archivo dice **qué sigue y cómo cerrarlo**.

**Cómo usarlo (en una sesión nueva de Claude Code):**
1. Leer `CLAUDE.md`, que tiene los principios, los comandos y las reglas.
2. Tomar la primera tarea `[ ]` de la cola. Hacer `git pull` y abrir una rama y un PR por tarea, con commits chicos.
3. Las cifras salen de un comando. Lo que no se midió se marca **OJO** y no se inventa.
4. Cerrar con lo hecho, lo verificado (con el comando) y lo pendiente. Marcar la tarea `[x]` acá y dejar la cifra en la bitácora.

Estado al 5-nov-2026:
- **Champions:** en vivo desde el 4-nov (PRs #16, #17 y #18), con 9 partidos evaluados. Es muy poca muestra para leer algo.
- **Ligas:** 107 partidos evaluados. El mercado le gana al modelo (RPS 0,209 contra 0,204, misma muestra).

---

## Cola

### [ ] T1. Calibración de la Champions

**Por qué.** El Dixon-Coles conjunto (`src/europe/`, bitácora §12.5) le gana a la base en la UCL, pero está mal calibrado. Walk-forward sobre la UCL 2024-25 y 2025-26, n = 376, `python -m src.europe.backtest`:

| | Predicho | Real |
|---|---|---|
| Empate | 22,2% | 15,7% |
| Victoria local | 45,1% | 50,5% |

RPS actual: 0.1949 (la base tiene 0.2380).

**Qué se sabe.** Hay dos ajustes ya probados, pero **se eligieron mirando el test**, así que son una pista y no un resultado:
- localía europea: λ_local × k_h / k_a, donde k_h y k_a son los goles reales sobre los esperados en los partidos europeos de los 2 años anteriores. RPS 0.1949 → 0.1944;
- abrir la escala de los ratings, con (ataque·defensa)^γ y γ entre 1,15 y 1,3, y ρ = 0. RPS hasta 0.1933, empate predicho 19,5%.

**Pasos.**
1. Agregar a `src/europe/backtest.py` un walk-forward de **validación**: UCL 2021-22 a 2023-24 (formato de grupos), con los mismos datos y el mismo reajuste semanal.
2. Elegir en validación los candidatos de la grilla: k_h/k_a sí o no, γ en {1; 1,1; 1,2; 1,3} y ρ ajustado o 0. El criterio es log-loss o RPS, decidido antes de mirar.
3. Medir **una sola vez** la variante elegida en el test 2024-25 y 2025-26. Reportar Brier, RPS y log-loss con n, contra el modelo actual y contra la base, sobre la misma muestra. Para la diferencia con el modelo actual, usar el IC por bootstrap pareado (`src.ml.metrics.bootstrap`).
4. Si mejora en test, aplicarla en `src/europe/run.py`, sobre las λ y sin tocar el ajuste. Si no mejora, no se adopta y se documenta igual.

**Archivos.** `src/europe/backtest.py`, `src/europe/run.py`, `tests/test_europe.py` (los tests verifican que la validación no use fechas del test) y la bitácora §12.5.

**OJO:**
- **No tocar `src/clubs/`**: cambia la versión del modelo de ligas, y el bot volvería a predecir todo.
- Cambiar `src/europe/` sí cambia la versión de la UCL (`<src/clubs>+<src/europe>`). Eso está bien, pero hay que decirlo en el PR.

**Cierre.** Tabla de validación y de test en §12.5 y en el PR, más la decisión tomada. Conviene tenerlo antes de la J5 (24-25 nov), así las predicciones de esa jornada ya salen con la versión nueva.

---

### [ ] T2. Eliminatorias de la Champions simuladas desde la tabla

**Por qué.** Hoy solo se simula la fase de liga: P(octavos), P(playoff) y P(afuera) en `ucl.json`. La idea es llegar hasta P(campeón), como el simulador del Mundial (`src/simulation/tournament.py`), pero partiendo de la tabla simulada.

**Pasos.**
1. **Verificar el formato 2026-27 con una fuente oficial de la UEFA** antes de escribir código:
   - cómo se arma el cuadro desde las posiciones de la fase de liga (pares de puestos sembrados y sorteo dentro de cada par);
   - ida y vuelta;
   - prórroga y penales;
   - sede de la final.

   Lo que no se pueda verificar va marcado **OJO** y no se inventa.
2. En `src/europe/run.py`, extender el Monte Carlo. Cada corrida simula el resto de la fase de liga y después:
   - el playoff (9-24);
   - octavos, cuartos y semis, a ida y vuelta;
   - la final, a partido único en cancha neutral.

   El motor es el Dixon-Coles conjunto (`Ratings.probs` y la matriz de marcadores), no `match_engine`. Una llave empatada en el global se resuelve con una regla simple y documentada, por ejemplo prórroga como 1/3 de partido y penales 50/50.
3. Agregar a `ucl.json`, por club: P(playoff ganado), P(cuartos), P(semis), P(final) y P(campeón). Sumar las columnas a la web (`app/index.html`, sección Champions) y regenerar con `python -m tools.export_frontend`, sin editar a mano el bloque `const UCL=`.
4. **Almacén:** hoy `store.match_id(div, season, home, away)` chocaría en ida y vuelta. Extenderlo de forma compatible (por ejemplo, con la ronda solo para las eliminatorias), sin cambiar los ids de la fase de liga ya guardados. Sumar un test de solo-para-agregar. Después, el ciclo diario predice también los partidos de eliminatorias cuando el feed los publique.

**Archivos.** `src/europe/run.py`, `src/pipeline/store.py`, `src/pipeline/daily.py`, `app/index.html`, `tools/export_frontend.py`, tests y la bitácora (§12.5 y §14.1).

**OJO:** el cuadro real depende de un sorteo que todavía no se hizo, así que hasta entonces se simula también el sorteo. Que las probabilidades sumen 1 por ronda es un test.

**Cierre.** P(campeón) en la web, tests de las sumas por ronda y del `match_id` compatible, y el reglamento citado en la bitácora. Prioridad después de T1: el playoff es en febrero de 2027.

---

### [ ] T3. Horario real del ciclo diario

**Por qué.** `daily.yml` tiene el cron a las 05:30 UTC, pero GitHub lo dispara entre las 10 y las 13 UTC (medido del 22-oct al 3-nov). Como un partido del mismo día solo se predice antes de las 10:00 UTC (`CUTOFF_HOUR_UTC`), hoy cada partido se predice en el ciclo del día anterior. Todavía no se perdió ninguno, pero un partido reprogramado para el mismo día se perdería.

**Pasos.** Probar un segundo cron de respaldo más temprano o mover el actual. El almacén ya es idempotente: una segunda corrida no duplica nada (comprobarlo con el test que ya existe). Medir durante una semana a qué hora corre en realidad.

**Cierre.** El horario medido en la bitácora §14.1 y en `CLAUDE.md`.

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

- [x] Champions: Dixon-Coles conjunto y backtest (#16), ciclo diario y tabla simulada (#17), y la sección en la web (#18). Bitácora §12.5 y §14.1.
- [x] Métricas en vivo por versión del modelo (#15).
- [x] `hgb` en Docker con `OMP_NUM_THREADS=4` (#14).
