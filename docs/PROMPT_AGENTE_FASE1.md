# Prompt para el agente de código: WC_predictor → predictor de las 5 grandes ligas

Pega esto tal cual en una sesión de Claude Code abierta en la raíz del repo `WC_predictor`.

---

## Contexto

Repo: `WC_predictor` (Python ≥3.11, `pyproject.toml` con hatchling, 12 archivos en `tests/`, `src/` con `etl/`, `simulation/`, `clubs/`, `evaluation/`, `betting/`, `agents/`). Lee primero `README.md` y `docs/PROYECTO_OBSIDIAN.md` (§12 limitaciones, §13 roadmap).

Hoy el proyecto predice selecciones (modelo Maher + Dixon-Coles con pesos fijos 20/50/30) y tiene un piloto de clubes solo para la Premier League en `src/clubs/` (datos de football-data.co.uk, ajuste Poisson por máxima verosimilitud, backtest walk-forward contra cuotas de cierre).

Objetivo final: un predictor de las 5 grandes ligas (Premier League, LaLiga, Bundesliga, Serie A, Ligue 1) con calendarios, un modelo de aprendizaje supervisado reproducible, y automatización con CI y ejecución diaria programada. Es una pieza de portafolio para Datos/IA/Automatización, así que importan la verificabilidad y la honestidad de las métricas más que el tamaño del stack.

## Principios (no negociables)

1. "El LLM propone, el código verifica": ninguna predicción depende de un LLM. Todo número reportado sale de código con tests.
2. No inventes datos, cifras ni métricas. Si algo no se pudo medir, escríbelo como pendiente.
3. Prefiere lo simple. No agregues dependencias ni capas que la tarea no pida.
4. Validación walk-forward siempre (entrenar con el pasado, predecir lo siguiente). Nunca mezcles fechas entre train y test.
5. No uses las cuotas de cierre como feature. Solo como benchmark. Si las usaras como feature el modelo copiaría al mercado.
6. Métricas: Brier 1X2, RPS (Ranked Probability Score) y log-loss, con la misma muestra para modelo, baseline y mercado. Reporta tamaño de muestra siempre.
7. Mantén el patrón de degradación elegante: si una fuente falla, el pipeline no se rompe.

## Fuera de alcance (no lo hagas)

Prophet o modelos de series de tiempo de precios, MCP, n8n, VPS, Streamlit, Supabase, Docker. Docker y la base de datos se evalúan en una fase posterior.

## Fase 1: CI y higiene del repo (haz esto primero, en una rama, con PR)

1. Revisa que `pytest` pase en limpio y reporta cuántos tests corren. El README dice 53 y `grep "def test_"` da 57; corrige el README con el número real.
2. Agrega `.gitignore` (venv, `__pycache__`, `.env`, cachés pesadas si corresponde; decide con criterio qué de `data/cache/` va versionado y justifícalo en el PR).
3. Corrige lo que `ruff check` marque con la configuración que ya está en `pyproject.toml`. Revisa también si `mypy` es viable sin reescribir medio repo; si no lo es, no lo actives.
4. Crea `.github/workflows/ci.yml`: en cada push y PR, Python 3.11 y 3.12, instala con `pip install -e ".[dev]"`, corre `ruff check` y `pytest`. Cachea pip.
5. Los tests deben ser herméticos (sin red). Si alguno pega a internet, aíslalo con un mock o márcalo para que CI no dependa de él.
6. Agrega un badge de CI al README.

Criterio de aceptación: CI en verde en GitHub, y el PR explica qué cambió y qué quedó pendiente.

## Fase 2: 5 ligas (después de que la Fase 1 esté mergeada)

1. Parametriza `src/clubs/` por liga. football-data.co.uk usa el mismo formato de CSV para E0 (Premier), SP1 (LaLiga), D1 (Bundesliga), I1 (Serie A) y F1 (Francia). Verifica los códigos descargando un archivo de cada una antes de asumirlos.
2. Soporta el calendario de la próxima jornada por liga (hoy es `fixtures.csv`).
3. Tests con fixtures pequeñas locales, sin red.
4. Reporta el Brier por liga y temporada contra el mercado, igual que la tabla actual del README.

## Fase 3: modelo supervisado (solo con aprobación de Demian tras la Fase 2)

Plantea el problema como clasificación 1X2. Features candidatas: diferencia de ELO, ataque/defensa de Maher, forma reciente, xG cuando exista, descanso, localía. Empieza con regresión logística multinomial, luego gradient boosting. Compara contra el modelo Dixon-Coles actual y contra el mercado. La meta realista es igualar al mercado con buena calibración, no superarlo. Incluye curva de calibración.

## Cómo trabajar

- Una rama y un PR por fase. Commits pequeños.
- Antes de cambiar algo que no entiendas, léelo. No refactorices por gusto.
- Si algo bloquea o es ambiguo, detente y pregunta en vez de asumir.
- Al terminar cada fase, resume: qué hiciste, qué verificaste y con qué comando, qué quedó pendiente. Marca como OJO todo lo que no hayas podido verificar.
