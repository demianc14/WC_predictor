# WC_predictor — Brief para Claude Code

Predictor de fútbol: selecciones (temporada 2026-27, Mundial 2026 como archivo) y las cinco
grandes ligas (E0, SP1, D1, I1, F1), con un modelo supervisado y un ciclo diario que publica
predicciones auditables en https://demianc14.github.io/WC_predictor/. Es pieza de portafolio:
importan la verificabilidad y la honestidad de las métricas más que el tamaño del stack.

Contexto completo: `README.md` y `docs/PROYECTO_OBSIDIAN.md` (bitácora, §2.1 principios,
§15 limitaciones, §16 roadmap). Briefs de cada fase: `docs/PROMPT_AGENTE_FASE*.md`.

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
pytest                                    # 117 tests, sin red (tests/conftest.py la bloquea)
ruff check . && mypy                      # lo mismo que corre CI
python -m src.clubs.run [--league SP1]    # ajusta ligas → data/processed/clubs_<div>.json
python -m src.clubs.h2h SP1 barcelona "real madrid" --odds 1.95 3.9 3.6
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
- `src/ml`: dataset con huella, features anti-fuga, modelos, `metrics.py` (solo numpy), train, report.
- `src/pipeline`: `daily.py` (todo o nada) y `store.py` (almacén solo-para-agregar).
- `tools/`: export a la web y scripts puntuales. `app/index.html`: web autocontenida, en JS vanilla.
- `.github/workflows`: `ci.yml` (ruff, mypy, pytest 3.11/3.12, docker), `daily.yml`
  (05:30 UTC, el bot commitea en main) y `pages.yml`.

## Reglas de trabajo

- Una rama y un PR por tarea, con commits chicos. Email de git en este repo: `demiandidier3@gmail.com`.
- **Nunca reescribir `data/predictions/predicciones.csv`**: solo se agregan filas y se completan
  resultados. `store.save` lo verifica, y no hay que esquivarlo.
- No editar a mano lo generado: `docs/RESULTADOS_ML.md`, `docs/ml/` y los bloques
  `const CLUBS=` / `const LIVE=` / datos de `app/index.html` (salen de `tools/export_frontend.py`).
- Cambiar `src/clubs/` cambia la versión del modelo (hash del árbol) y hace que el bot cree
  predicciones nuevas. Hacerlo a propósito y decirlo.
- `data/cache/` va versionada a propósito: reproduce cifras sin red.
- Los tests no tocan la red ni mutan `data/cache/`. Las fixtures van en `tests/fixtures/`.
- Corridas oficiales de ML: desde un árbol limpio (el manifiesto usa `git describe --dirty`).
- Una tarea se cierra con lo hecho, lo verificado (con el comando) y lo pendiente. Marcar **OJO**
  todo lo no verificado.

## Gotchas

- El bot commitea en `main` todos los días: hacer `git pull` / rebase antes de empujar a `main`.
- Con PRs apilados, no mergear el PR base con `--delete-branch`, porque GitHub cierra el hijo.
- En Docker no hay `.git`: la versión del modelo entra por build args (`make docker-build`).
- Entrenar en Docker sin `data/ml/cache` recalcula las features (~54 min).
