# 🏆 World Cup Predictor

[![CI](https://github.com/demianc14/WC_predictor/actions/workflows/ci.yml/badge.svg)](https://github.com/demianc14/WC_predictor/actions/workflows/ci.yml)

> El proyecto nació como predictor del **Mundial 2026** (grupos reales del sorteo del 5-dic-2025) y de ahí conserva el nombre. Terminado el torneo (🇪🇸 España campeona, 1-0 a Argentina el 19-jul), hoy es un **predictor de fútbol de selecciones** para la temporada internacional 2026-27. El Mundial quedó como archivo.

- **Datos al 6-oct-2026**: incluye la ventana del 23-sep al 6-oct (UEFA y Concacaf Nations League, clasificación a la Copa África, amistosos)
- **Pipeline ETL** validado con Pydantic (fail fast)
- **xG real de StatsBomb Open Data**: 250 partidos (Euro 2020, Mundial 2022, AFCON 2023, Euro 2024, Copa América 2024) → ratings de xG sin penales ajustados por rival y por recencia, que reemplazan en parte el xG curado del CSV
- **Modelo de fuerzas** inspirado en Bayes: 20% historia + 50% actualidad = 70% base estadística + 30% contexto del partido
- **Motor Maher + Dixon-Coles**: ataque/defensa separados y corrección ρ=−0.13 de marcadores bajos; prórroga y penales
- **Breaking News Engine**: eventos canónicos elegibles desde menú + inyección manual
- **Interfaz web** autocontenida (`app/index.html`), dividida en dos secciones:
  - **Selecciones 2026-27**: próxima ventana (predicciones del 11 al 17-nov: Nations League, Concacaf, clasif. Copa África, amistosos), última ventana (resultados vs. lo que esperaba el modelo, quién subió y bajó), partido y cuotas a 90' entre cualquier par, ranking (fuerza, Δ ventana, ELO, forma de los últimos 5, valor de plantilla, edad, xG)
  - **Clubes · cinco grandes ligas**: por liga, tabla proyectada (10.000 temporadas simuladas), próximos 7 días contra las cuotas y backtest contra el mercado
  - **Archivo · Mundial 2026**: dos cuadros (cómo terminó y lo que esperaba el modelo, que acertó 26 de 31 partidos), probabilidad exacta de llegar a cada ronda y backtest

## xG de StatsBomb

`src/etl/scrapers/statsbomb.py` baja los eventos de cada partido una sola vez y guarda solo un resumen de tiros (`data/cache/statsbomb/shots/`, ~1.8 MB para los 250 partidos). `src/etl/xg_ratings.py` ajusta `npxG(i vs j) ≈ MU × ataque_i × defensa_j` por mínimos cuadrados ponderados, con peso `exp(-edad/730 días)` y 2 partidos ficticios de shrinkage. El ETL mezcla ese xG con el del CSV según la muestra efectiva de cada equipo (`n_eff / (n_eff + 2)`) y escribe el detalle en `data/processed/xg_statsbomb.json`.

Cobertura: 40 de las 48 selecciones del modelo. Sin datos: Bosnia, Haití, Curazao, Nueva Zelanda, Irak, Noruega, Jordania y Uzbekistán (usan el xG del CSV). El Mundial 2026 todavía no está en el open data.

## Clubes: las cinco grandes ligas

`src/clubs/` reutiliza la matriz Dixon-Coles del proyecto, pero ajusta los parámetros a cada liga en vez de heredarlos de las selecciones. Ligas: Premier League (E0), LaLiga (SP1), Bundesliga (D1), Serie A (I1) y Ligue 1 (F1), configuradas en `leagues.py`.

- **Datos** (`data.py`): CSVs de [football-data.co.uk](https://www.football-data.co.uk/) con resultados, cuotas de cierre y xG (este último solo desde 2026-27, en las diez divisiones), más `fixtures.csv` con los partidos de los próximos días y sus cuotas. Caché en `data/cache/clubs/`; la temporada actual se refresca cada 12 h.
- **Calendario** (`calendar.py`): la temporada completa sale de [fixturedownload.com](https://fixturedownload.com/). Los nombres no coinciden con los de football-data, así que el cruce se deduce de los partidos ya jugados (mismo día ±1 y mismo marcador) y falla con el nombre exacto si un equipo queda sin pareja. También exige una liga a dos ruedas: el feed de Ligue 1 trae Rennes-PSG dos veces y ningún PSG-Rennes, se corrige a la vista (consola y `calendar_fixes` en el JSON). Si el feed no está disponible, la simulación usa todo cruce no jugado.
- **Modelo** (`model.py`): ataque y defensa por club, localía, μ y ρ por máxima verosimilitud Poisson (algoritmo iterativo de Maher, sin scipy), con peso `exp(−0.0019·días)` y 3 goles ficticios de shrinkage. Se ajusta junto con la segunda división para que los ascendidos lleguen con historia. Cuando hay xG, el objetivo es 50% goles + 50% xG.
- **Temporada** (`season.py`): Monte Carlo de los partidos que faltan → puntos esperados y probabilidad de cada puesto.
- **Contra el mercado** (`backtest.py`): walk-forward semanal. Sobre los mismos partidos se comparan el modelo, las cuotas de cierre promedio sin margen y una base que solo conoce la frecuencia de 1/X/2 de la liga hasta esa semana.

```bash
python -m src.clubs.run                 # las cinco: escribe data/processed/clubs_<div>.json
python -m src.clubs.run --league SP1    # una sola
python -m tools.export_frontend         # lo inyecta en la web
```

Brier y RPS 1X2, menor es mejor; en negrita, el mejor entre modelo y mercado:

| Liga | Temporada | Partidos | Brier modelo | Brier mercado | Brier base | RPS modelo | RPS mercado | RPS base |
|---|---|---|---|---|---|---|---|---|
| Premier League | 2025-26 | 380 | 0.623 | **0.608** | 0.656 | 0.212 | **0.204** | 0.228 |
| Premier League | 2026-27 (al 19-oct) | 70 | **0.597** | 0.601 | 0.663 | **0.197** | 0.198 | 0.229 |
| LaLiga | 2025-26 | 380 | 0.579 | **0.572** | 0.633 | 0.200 | **0.196** | 0.224 |
| LaLiga | 2026-27 (al 19-oct) | 88 | 0.562 | **0.538** | 0.654 | 0.183 | **0.174** | 0.225 |
| Bundesliga | 2025-26 | 306 | 0.575 | **0.562** | 0.649 | 0.196 | **0.190** | 0.232 |
| Bundesliga | 2026-27 (al 19-oct) | 54 | **0.572** | 0.591 | 0.627 | **0.203** | 0.211 | 0.231 |
| Serie A | 2025-26 | 380 | 0.598 | **0.583** | 0.661 | 0.203 | **0.196** | 0.234 |
| Serie A | 2026-27 (al 19-oct) | 70 | 0.564 | **0.542** | 0.638 | 0.208 | **0.199** | 0.242 |
| Ligue 1 | 2025-26 | 306 | 0.599 | **0.582** | 0.644 | 0.207 | **0.200** | 0.229 |
| Ligue 1 | 2026-27 (al 19-oct) | 63 | 0.591 | **0.579** | 0.647 | 0.206 | **0.200** | 0.232 |

El modelo le gana con claridad a la base en todas las ligas, pero **pierde contra el mercado en las cinco en la temporada completa 2025-26**. En 2026-27 lo supera en la Premier y la Bundesliga, con 54 a 70 partidos: muy pocos para decir que sea mejor. Apostar cada discrepancia de más de 5% habría perdido entre 9% y 29% en 2025-26 según la liga, así que la web muestra dónde discrepa el modelo, no "valor".

## Arquitectura

El corazón del proyecto es un **pipeline ETL** (`src/etl/`) que toma datos crudos de las 48 selecciones (`data/raw/teams_2026.csv`), los valida con contratos Pydantic (fail fast: una fila corrupta detiene el pipeline con un mensaje exacto de qué falló) y calcula una **fuerza por equipo** combinando 20% historia mundialista + 50% forma/xG reciente. Ese CSV es solo el punto de partida: el ETL lo enriquece con scrapers en vivo (ELO actual de eloratings.net, historial de partidos desde 1872 para resiliencia y forma dinámica, valor de plantilla de Transfermarkt), cada uno con la misma **degradación elegante** del narrador — si una fuente falla, el pipeline cae al valor del CSV en vez de romperse. Esa fuerza (70% base estadística) se combina en tiempo de partido con un 30% de contexto (lesiones, clima, altura, hinchada) inyectado por el Breaking News Engine. El resultado se serializa a `data/processed/strengths_2026.json`, única fuente de verdad tanto para la CLI como para la app web.

Los goles se modelan con un **motor Maher + Dixon-Coles** (`src/simulation/match_engine.py`): Maher (1982) separa perfiles de ataque y defensa por equipo en vez de usar un solo número de fuerza, y Dixon-Coles (1997) corrige el sesgo conocido del Poisson independiente en marcadores bajos (subestima 0-0/1-1, sobreestima 1-0/0-1) con un factor ρ=−0.13 calibrado sobre la literatura. Un torneo completo (`src/simulation/tournament.py`) arma el cuadro oficial de la FIFA (M73–M104), resuelve la asignación de los 8 mejores terceros a sus llaves por backtracking, y resuelve empates en eliminación directa con prórroga y penales. Para responder preguntas probabilísticas ("¿qué tan probable es que Argentina sea campeón?") se corren miles de torneos independientes (**Monte Carlo**) y se cuenta la frecuencia de cada resultado — el error de la estimación cae como 1/√N, lo que fija cuántas simulaciones vale la pena correr (10.000 mundiales, 50.000 partidos cara a cara).

El único punto de contacto con un LLM es el narrador (`src/agents/narrator.py`), y es deliberadamente opcional: por defecto genera crónicas con plantillas f-string, y solo si existe `ANTHROPIC_API_KEY` y se pasa `--llm` usa Claude para crónicas generativas. Es un patrón de **degradación elegante** — todo el sistema (ETL, motor de partido, torneo, Monte Carlo) funciona sin el LLM, que aquí es una mejora cosmética, no una dependencia. Por eso el proyecto se llama "Predictor" y no "Simulador LLM": la predicción es 100% estadística.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m src.cli etl                  # pipeline ETL
python -m src.cli simulate --seed 2026 # una copa fase a fase
python -m src.cli montecarlo -n 2000   # ¿quién gana la copa?
python -m src.cli h2h BRA MAR          # Brasil vs Marruecos
python -m src.cli backtest             # ¿qué tan bien predijo el Mundial real?
python -m src.etl.xg_ratings           # ranking xG de StatsBomb (desde la caché)
python -m tools.export_frontend        # reinyecta fuerzas y última ventana en app/index.html
pytest                                 # 78 tests, sin red
ruff check .                           # lo mismo que corre CI
```

**Datos versionados:** `data/cache/` (~18 MB) va en el repo a propósito: con la caché, el ETL, los backtests y las cifras de este README se reproducen sin red y aunque una fuente cambie o desaparezca. Las temporadas cerradas no se vuelven a bajar; lo vivo se refresca cada 12 h.

**Interfaz para amigos:** abre `app/index.html` en el navegador. Sin servidor, sin instalación. Tras cada `etl`, correr `python -m tools.export_frontend` para actualizarla. La vista "Última ventana" compara contra `data/snapshots/strengths_2026-09-22.json` (fuerzas congeladas antes de la ventana); en la próxima fecha FIFA, guardar un snapshot nuevo y actualizar `WINDOW_SNAPSHOT`/`WINDOW_FROM` en `tools/export_frontend.py`.

**Próxima ventana:** el calendario vive en `data/raw/fixtures_2026-11.csv` (curado a mano desde UEFA, Concacaf, NBC Sports y ESPN; nombres como en martj42). Los rivales fuera de las 48 se estiman desde su ELO con una recta ajustada sobre las 48 (R² ≈ 0.87 en la fuerza) y la web los marca con ≈. Las fuerzas con que se predijo quedaron en `data/snapshots/strengths_2026-10-15.json`. Cuando termine la ventana, ese snapshot pasa a ser el `WINDOW_SNAPSHOT` de "Última ventana".

## ¿Qué tan bien predijo?

### Última ventana (23-sep al 6-oct-2026)

127 partidos de las 48 selecciones (UEFA y Concacaf Nations League, clasificación a la Copa África, amistosos). En los 35 que enfrentaron a dos selecciones del modelo, con las fuerzas congeladas al 22-sep (`data/snapshots/strengths_2026-09-22.json`):

| Métrica | Modelo | Azar |
|---|---|---|
| Acierta el resultado más probable | **57%** (20/35) | 33% |
| Brier 1X2 | **0.529** | 0.667 |

Más subieron: Bosnia (+0.029), Estados Unidos (+0.023), Suecia (+0.021). Más bajaron: Ghana (−0.031), Turquía (−0.026), Egipto (−0.015). La muestra es chica: sirve para seguir al modelo fecha a fecha, no para sacar conclusiones. El detalle partido a partido está en la vista "Última ventana" de la web.

### Archivo: Mundial 2026

Backtest contra los 104 partidos reales del Mundial 2026, usando el modelo tal como estaba el 15-jun (sin ver resultados posteriores). Se compara contra un ELO pre-torneo reconstruido desde el historial y contra el azar. En Brier score, menor es mejor:

| Tramo | Modelo | ELO | Azar |
|---|---|---|---|
| Grupos, 1X2 (72) | **0.478** | 0.541 | 0.667 |
| Grupos fuera de muestra (48) | **0.408** | 0.442 | 0.667 |
| Eliminatorias, ¿quién clasifica? (32) | **0.134** | 0.148 | 0.250 |

El modelo supera al azar con claridad y al ELO en la estimación puntual. Pero en los tramos sin fuga de datos la ventaja sobre ELO cae dentro del margen de error (bootstrap al 95%). Está bien calibrado: cuando dice 28% pasa el 29%, y cuando dice 68% pasa el 70%. Subestima un poco los empates (21% vs 27.8%). Reajustar K/BASE/ρ con estos datos no mejora de forma significativa, así que se mantienen. Detalle y metodología en [`docs/PROYECTO_OBSIDIAN.md` §10.1](docs/PROYECTO_OBSIDIAN.md#101-backtest-el-modelo-contra-los-104-partidos-reales).

## Limitaciones

- **Cobertura de datos en vivo limitada a 48 selecciones**: los scrapers (ELO, historial, valor de plantilla) solo mapean los equipos del Mundial 2026 — el CSV curado sigue siendo el fallback y la base para cualquier otro cruce.
- **"Bayes" es una combinación lineal**, no inferencia bayesiana formal — es una inspiración conceptual (prior actualizado por evidencia), útil y transparente, pero no el teorema aplicado con distribuciones.
- El sesgo de independencia del Poisson en marcadores bajos ya está corregido (Dixon-Coles) con un ρ fijo de la literatura. Estimarlo sobre el Mundial 2026 no es concluyente; hace falta ajustarlo sobre el historial completo.
- **Validación con poca muestra**: 80 partidos fuera de muestra no alcanzan para afirmar que el modelo supera a un ELO bien hecho, solo que no es peor.

## Cómo escalar

El proyecto está pensado para crecer sin tocar el motor de partido: más selecciones o torneos, ajustar ρ y el modelo de empates sobre el historial completo, refresco automático del ETL, persistencia de simulaciones, etc. Cada cambio se puede validar con el mismo `backtest`. El detalle categorizado está en [`docs/PROYECTO_OBSIDIAN.md` §13](docs/PROYECTO_OBSIDIAN.md#13-roadmap-cómo-escalar-el-proyecto).

## Documentación completa

Toda la explicación conceptual (modelo, matemática, arquitectura, testing, limitaciones, roadmap) está en
[`docs/PROYECTO_OBSIDIAN.md`](docs/PROYECTO_OBSIDIAN.md) — listo para importar a Obsidian.
