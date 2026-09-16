# 🏆 World Cup Predictor

Predictor del Mundial 2026 (grupos reales del sorteo del 5-dic-2025) con:

- **Pipeline ETL** validado con Pydantic (fail fast)
- **Modelo de fuerzas** inspirado en Bayes: 20% historia + 50% actualidad = 70% base estadística + 30% contexto del partido
- **Motor Maher + Dixon-Coles**: ataque/defensa separados (xG normalizado) y corrección ρ=−0.13 de marcadores bajos; prórroga y penales
- **Torneo completo**: cuadro OFICIAL FIFA (M73–M104) con asignación de terceros por backtracking
- **Monte Carlo**: hasta 10.000 mundiales (±0.5%) y 50.000 partidos en el cara a cara; anfitriones con ventaja de local
- **Breaking News Engine**: eventos canónicos elegibles desde menú + inyección manual (sin azar en torneo/MC)
- **Interfaz web** autocontenida (`app/index.html`): partido (grupo/eliminación), mundial, Monte Carlo y pronóstico con resultados reales

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
pytest                                 # 14 tests
```

**Interfaz para amigos:** abre `app/index.html` en el navegador. Sin servidor, sin instalación.

## Limitaciones

- **Cobertura de datos en vivo limitada a 48 selecciones**: los scrapers (ELO, historial, valor de plantilla) solo mapean los equipos del Mundial 2026 — el CSV curado sigue siendo el fallback y la base para cualquier otro cruce.
- **"Bayes" es una combinación lineal**, no inferencia bayesiana formal — es una inspiración conceptual (prior actualizado por evidencia), útil y transparente, pero no el teorema aplicado con distribuciones.
- El sesgo de independencia del Poisson en marcadores bajos ya está corregido (Dixon-Coles) con un ρ fijo de la literatura; el siguiente refinamiento sería estimarlo por máxima verosimilitud sobre datos reales.

## Cómo escalar

El proyecto está pensado para crecer sin tocar el motor de partido: más selecciones o torneos, calibración contra resultados reales (Brier score), refresco automático del ETL, persistencia de simulaciones, etc. El detalle categorizado está en [`docs/PROYECTO_OBSIDIAN.md` §13](docs/PROYECTO_OBSIDIAN.md#13-roadmap-cómo-escalar-el-proyecto).

## Documentación completa

Toda la explicación conceptual (modelo, matemática, arquitectura, testing, limitaciones, roadmap) está en
[`docs/PROYECTO_OBSIDIAN.md`](docs/PROYECTO_OBSIDIAN.md) — listo para importar a Obsidian.
