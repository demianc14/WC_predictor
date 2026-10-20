# Prompt Fase 2: las 5 grandes ligas

Pega esto en una sesión de Claude Code abierta en la raíz de `WC_predictor`. Requisito: la Fase 1 (CI) ya está mergeada y `pytest` y `ruff` pasan.

---

## Contexto

Lee `README.md` (sección "Clubes: piloto con la Premier League") y todo `src/clubs/` (`data.py`, `model.py`, `season.py`, `backtest.py`, `premier.py`). Hoy el piloto está acoplado a la Premier League (E0) y la Championship (E1, se ajusta junto para que los ascendidos lleguen con historia). Los principios de trabajo están en `docs/PROMPT_AGENTE_FASE1.md`, sección "Principios". Aplican igual aquí.

## Objetivo

Que el mismo código prediga y simule las 5 grandes ligas: Premier League, LaLiga, Bundesliga, Serie A y Ligue 1, con la próxima jornada de cada una.

## Tareas

1. **Verifica las fuentes antes de asumir nada.** football-data.co.uk publica CSVs con la misma estructura para E0, SP1, D1, I1 y F1 (y segundas divisiones E1, SP2, D2, I2, F2). Descarga un archivo de cada liga y confirma: nombre de las columnas, cuáles traen cuotas de cierre y desde qué temporada hay xG (en la Premier se agregó en 2026-27 según el README; no asumas que las otras ligas lo tienen). Anota en el PR una tabla liga → columnas disponibles.
2. **Parametriza por liga.** Crea una configuración simple (un dataclass o dict) con: código de liga, código de segunda división para el ajuste conjunto, temporadas a usar, número de equipos y de jornadas. Quita todo lo que diga "premier" o "E0" hardcodeado en `data.py`, `model.py`, `season.py` y `backtest.py`. El punto de entrada pasa a ser algo como `python -m src.clubs.run --league SP1`.
3. **Normalización de nombres de equipos.** Los nombres cambian entre temporadas y entre `fixtures.csv` y los resultados. Detecta los desajustes con un test que falle con el nombre exacto sin mapear, nunca los ignores en silencio.
4. **Calendarios.** Obtén la próxima jornada de cada liga. Primero revisa qué ofrece football-data (`fixtures.csv`). Si no cubre las 5 ligas, dime qué alternativa gratuita y legal propones antes de implementarla. No hagas scraping de sitios que lo prohíban.
5. **Salida.** Un JSON por liga en `data/processed/` con el mismo esquema que `clubs_premier.json` más un campo `league`. Ajusta `tools/export_frontend.py` y `app/index.html` solo lo mínimo para listar las ligas; no rediseñes la web.
6. **Tests herméticos** con CSVs pequeños en `tests/fixtures/` (sin red). Cubre: lectura de cada formato, el mapeo de nombres, y que el modelo ajuste en cada liga con datos de juguete.
7. **Backtest por liga.** Corre el walk-forward semanal contra las cuotas de cierre sin margen y reporta Brier del modelo y del mercado por liga y temporada, con número de partidos. Actualiza la tabla del README con los números reales que salgan. Si el modelo pierde contra el mercado, dilo.

## Criterios de aceptación

- `python -m src.clubs.run --league <código>` funciona para las 5 ligas.
- CI en verde.
- Tabla del README con resultados reales por liga.
- PR con: qué cambió, la tabla de columnas por liga, y lista de lo que quedó pendiente o no se pudo verificar (marca OJO).

## Fuera de alcance

El modelo supervisado (Fase 3), la automatización (Fase 4), Docker (Fase 5) y copas europeas. Una sola liga extra por vez si algo se complica: primero Premier, LaLiga y Bundesliga, luego las demás.
