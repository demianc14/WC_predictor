# WC_predictor — Brief para Claude Code

Predictor de fútbol con tres partes:
- selecciones (temporada 2026-27, con el Mundial 2026 como archivo);
- las cinco grandes ligas (E0, SP1, D1, I1, F1), con un modelo supervisado;
- la Champions League (Dixon-Coles conjunto entre ligas: partidos de la fase de liga y cuadro
  de eliminatorias simulado hasta el campeón).

Un ciclo diario publica predicciones auditables en https://demianc14.github.io/WC_predictor/.
Es pieza de portafolio: importan la verificabilidad y la honestidad de las métricas más que
el tamaño del stack.

- **Qué sigue:** `docs/ROADMAP.md`, la cola de tareas con pasos y criterio de cierre. Se toma
  la primera `[ ]`.
- **Contexto:** `README.md` y `docs/PROYECTO_OBSIDIAN.md` (bitácora: §2.1 principios,
  §12.5 Champions, §15 limitaciones, §16 historial del roadmap). Los briefs de las fases 1 a
  5 están en `docs/briefs/FASE*.md`.

## Principios no negociables

1. "El LLM propone, el código verifica": ninguna predicción depende de un LLM.
2. No inventar datos, cifras ni métricas. Lo no medido se escribe como pendiente.
3. Lo simple primero: sin dependencias ni capas que la tarea no pida.
4. Walk-forward siempre: nunca mezclar fechas entre train y test.
5. Las cuotas de cierre nunca son feature, solo benchmark (`test_las_cuotas_nunca_son_feature`).
6. Brier, RPS y log-loss sobre la misma muestra para modelo, baseline y mercado, siempre con n.
7. Degradación elegante: si una fuente falla, nada se rompe ni queda a medias.

## Comandos

```bash
pip install -e ".[dev]"                   # núcleo + [ml] (sklearn) + [llm] (anthropic) + herramientas
pytest                                    # 144 tests, sin red (tests/conftest.py la bloquea)
ruff check . && mypy                      # lo mismo que corre CI
python -m src.clubs.run [--league SP1]    # ajusta ligas → data/processed/clubs_<div>.json
python -m src.clubs.h2h SP1 barcelona "real madrid" --odds 1.95 3.9 3.6
python -m src.europe.run                  # Champions → data/processed/ucl.json
python -m src.ml.train --leagues all      # entrena y regenera docs/RESULTADOS_ML.md
python -m src.ml.report data/ml/runs/<run>  # regenera el reporte sin reentrenar
python -m src.pipeline.daily              # ciclo diario completo (descarga, predice, exporta)
python -m tools.export_frontend           # reinyecta los datos en app/index.html
python -m tools.capturas                  # capturas, GIF y portadas → docs/img/ (pillow + Chrome)
make docker-build docker-test             # imágenes wc-predictor (app) y wc-predictor:ml
```

## Mapa del código

- `src/etl`, `src/simulation`, `src/agents`, `src/evaluation`: selecciones y Mundial (Parte I).
- `src/clubs`: ligas (`leagues.py`), datos de football-data, calendario de fixturedownload,
  Dixon-Coles por liga, temporada, partido y cuotas (`h2h.py`), backtest contra el mercado.
- `src/europe`: Dixon-Coles conjunto entre ligas para la Champions (ligas extra + Europa),
  backtest y fase de liga (`run.py`). Reutiliza los feeds de `src/ml/europe.py`, que solo
  aporta los días con partido europeo como feature del supervisado.
- `src/ml`: dataset con huella, features anti-fuga, modelos, `metrics.py` (solo numpy), train, report.
- `src/pipeline`: `daily.py` (todo o nada) y `store.py` (almacén solo-para-agregar).
- `tools/`: `export_frontend.py` y `capturas.py` están en uso; el resto son scripts puntuales del
  Mundial (snapshot, calibración de K, export de resultados y goleadores).
- `app/index.html`: web autocontenida, en JS vanilla.
- `data/`:
  - `raw/`: entradas curadas a mano de selecciones, no se tocan;
  - `snapshots/`: entradas congeladas para los backtests;
  - `cache/`: fuentes descargadas, versionadas;
  - `processed/`: generado;
  - `predictions/`: el almacén;
  - `ml/runs/`: corridas oficiales.
- `docs/`: bitácora, `ROADMAP.md`, `RESULTADOS_ML.md` y `ml/` (generados), `briefs/` e `img/`.
- `.github/workflows`: `ci.yml` (ruff, mypy, pytest 3.11/3.12, docker), `daily.yml`
  (crons a las 00:17 y 05:30 UTC; el de las 05:30 arranca de hecho entre las 09:39 y las 14:08,
  n = 23, bitácora §14.1; el bot commitea en main) y
  `pages.yml`.

## Reglas de trabajo

- Textos de la web y la documentación en español neutro, con tú (nada de voseo).
- Una rama y un PR por tarea, con commits chicos. Email de git en este repo: `demiandidier3@gmail.com`.
- **Nunca reescribir `data/predictions/predicciones.csv`**: solo se agregan filas y se completan
  resultados. `store.save` lo verifica, y no hay que esquivarlo.
- No editar a mano lo generado:
  - `docs/RESULTADOS_ML.md` y `docs/ml/`;
  - `docs/ucl/` (`python -m src.europe.backtest --fase …`; el test de la calibración ya se corrió y no se repite);
  - `data/processed/*.json`;
  - los bloques de datos de `app/index.html` (`const CLUBS=`, `const LIVE=`, `const UCL=`, …),
    que salen de `tools/export_frontend.py`.
- Cambiar `src/clubs/` cambia la versión del modelo (hash del árbol) y hace que el bot cree
  predicciones nuevas. La versión de la Champions es `<src/clubs>+<src/europe>`. Cambiar
  cualquiera de los dos árboles se hace a propósito y se dice en el PR.
- `data/cache/` va versionada a propósito: reproduce cifras sin red.
- Los tests no tocan la red ni mutan `data/cache/`. Las fixtures van en `tests/fixtures/`.
- Corridas oficiales de ML: desde un árbol limpio (el manifiesto usa `git describe --dirty`).
- Una tarea se cierra con lo hecho, lo verificado (con el comando) y lo pendiente. Marcar **OJO**
  todo lo no verificado. Si venía de `docs/ROADMAP.md`, marcarla `[x]` ahí.

## Gotchas

- El bot commitea en `main` todos los días: hacer `git pull` / rebase antes de empujar a `main`.
- Un partido del mismo día solo se predice antes de las 10:00 UTC (`CUTOFF_HOUR_UTC`). El cron de
  las 05:30 casi siempre arranca más tarde, así que cada partido se predice en el ciclo del día
  anterior. El respaldo de las 00:17 (12-nov) busca cubrir eso; **OJO:** su horario real falta
  medirlo (desde el 20-nov, con el comando de §14.1). Dos corridas el mismo día no duplican nada.
- Champions: en el almacén va con `league=UCL` y solo la fase de liga, porque en las
  eliminatorias `store.match_id` chocaría entre la ida y la vuelta. Sus métricas van en
  `live.json` → `ucl`, fuera de `all`, `by_league` y `by_version`. No hay cuotas: se compara
  contra la base.
- Con PRs apilados, no mergear el PR base con `--delete-branch`, porque GitHub cierra el hijo.
- En Docker no hay `.git`: la versión del modelo entra por build args (`make docker-build`).
- `hgb` en Docker necesita `OMP_NUM_THREADS` fijo (4 en la imagen `:ml`; `make docker-train OMP=n`):
  con un hilo por CPU visible es ~40× más lento (§14.3). Para reproducir una corrida oficial,
  usar `--network none`, porque con red `dataset.load` refresca los datos y cambia la huella.
