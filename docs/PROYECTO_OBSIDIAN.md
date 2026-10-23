# 🏆 World Cup Predictor — Bitácora del Proyecto

> [!info] Metadatos
> **Autor:** Demian · **Stack:** Python 3.11+, numpy, pandas, Pydantic, scikit-learn (opcional), pytest, ruff, mypy, GitHub Actions, Docker, HTML/JS vanilla
> **Objetivo:** predecir fútbol con modelos probabilísticos verificables. Cubre selecciones (temporada internacional 2026-27) y las cinco grandes ligas europeas, con un modelo supervisado reproducible y un ciclo diario automático que publica predicciones antes de cada partido y las mide después.
> **Web:** https://demianc14.github.io/WC_predictor/ (se actualiza sola cada día)
> **Nivel:** explicado para Ing. en Cs. de la Computación, 7mo semestre.

> [!note] Nota histórica: tres etapas
> 1. **Mundial 2026 (jun-jul 2026).** El proyecto nació como "World Cup LLM Simulator" y se renombró a **World Cup Predictor**, porque el LLM (`src/agents/narrator.py`, §9) es un narrador opcional, no parte del motor. El nombre se conservó.
> 2. **Selecciones 2026-27 (sep 2026).** Terminado el torneo (España campeona), el modelo siguió con las ventanas FIFA. El Mundial quedó como archivo y su backtest sigue en §10.1.
> 3. **Cinco grandes ligas (oct 2026).** Premier League, LaLiga, Bundesliga, Serie A y Ligue 1, en cinco fases con brief escrito (`docs/PROMPT_AGENTE_FASE1.md` … `FASE5.md`): CI, ligas y calendarios, modelo supervisado, ejecución diaria y Docker.
>
> Esta bitácora se organiza igual: **Parte I** es el motor original de selecciones (§3-§11), **Parte II** los clubes (§12), **Parte III** el modelo supervisado (§13) y **Parte IV** la operación (§14).

---

## 1. La idea en una frase

Convertir resultados históricos en una **distribución de probabilidad sobre resultados**, compararla de forma honesta con alternativas (azar, ELO, frecuencias, el mercado de apuestas) y dejar que el propio código pruebe que cada predicción existía antes del partido.

```
Datos crudos → validación → fuerzas por equipo → Dixon-Coles (Poisson corregido)
            → partido / torneo / temporada (Monte Carlo) → probabilidades
            → evaluación walk-forward contra baseline y mercado (Brier, RPS, log-loss, con n)
```

---

## 2. Arquitectura del repositorio

```
WC_predictor/
├── data/
│   ├── raw/                        ← datos curados a mano (selecciones), INTOCABLES
│   ├── snapshots/                  ← fuerzas congeladas antes de cada ventana (backtests)
│   ├── cache/                      ← fuentes descargadas, versionadas a propósito (~18 MB)
│   │   └── clubs/                  ← CSVs de football-data y calendarios de fixturedownload
│   ├── processed/                  ← salidas: strengths_2026.json, clubs_<div>.json, live.json
│   ├── predictions/predicciones.csv← almacén de predicciones, solo para agregar (§14.1)
│   └── ml/runs/<fecha>_<huella>/   ← artefactos del modelo supervisado
├── src/
│   ├── etl/                        ← selecciones: contratos Pydantic, scrapers, xG StatsBomb
│   ├── simulation/                 ← motor de partido Maher + Dixon-Coles, torneo, Monte Carlo
│   ├── agents/                     ← Breaking News Engine y narrador (LLM opcional)
│   ├── evaluation/                 ← ELO reconstruido y backtest del Mundial
│   ├── betting/odds.py             ← cuota justa, EV y Kelly
│   ├── clubs/                      ← las cinco ligas: datos, calendario, modelo, temporada, h2h, backtest
│   ├── ml/                         ← modelo supervisado: dataset, features, modelos, métricas, train, report
│   ├── pipeline/                   ← ciclo diario y almacén de predicciones
│   └── cli.py                      ← interfaz de línea de comandos
├── tools/                          ← export a la web, snapshots, calibraciones
├── app/index.html                  ← interfaz web autocontenida (datos inyectados por tools/export_frontend.py)
├── tests/                          ← 120 tests con pytest, sin red
├── .github/workflows/              ← ci.yml, daily.yml, pages.yml (§14.2)
├── Dockerfile · Makefile           ← dos imágenes reproducibles (§14.3)
└── docs/                           ← esta bitácora, los briefs de cada fase y RESULTADOS_ML.md
```

> [!tip] Principio de diseño: separación de capas
> El ETL no sabe que existe un simulador. El simulador no sabe de dónde vienen los datos. El Breaking News Engine no sabe de Poisson. Los clubes reutilizan la matriz Dixon-Coles, pero no el ETL de selecciones. El ciclo diario solo orquesta: no tiene modelo propio. Cada capa se puede testear y reemplazar de forma independiente: **bajo acoplamiento, alta cohesión**.

### 2.1 Principios no negociables

Los fijó el brief de la fase 1 y valen para todo el proyecto. En una entrevista, son la respuesta a "¿cómo sé que tus números son ciertos?":

1. **"El LLM propone, el código verifica."** Ninguna predicción depende de un LLM. Todo número reportado sale de código con tests.
2. **No inventar datos ni métricas.** Lo que no se pudo medir se escribe como pendiente.
3. **Lo simple primero.** Sin dependencias ni capas que la tarea no pida (por eso no hay scipy: el ajuste de Maher es iterativo, §12.2).
4. **Walk-forward siempre.** Se entrena con el pasado y se predice lo siguiente; nunca se mezclan fechas entre train y test.
5. **Las cuotas de cierre nunca son feature.** Solo benchmark: si fueran feature, el modelo aprendería a copiar al mercado y la comparación no diría nada. Un test lo verifica (§13.1).
6. **Brier, RPS y log-loss sobre la misma muestra** para modelo, baseline y mercado, siempre con el tamaño de muestra.
7. **Degradación elegante.** Si una fuente falla, el pipeline no se rompe ni deja estado a medias.

---

# Parte I · Selecciones y Mundial 2026 (archivo)


## 3. El Pipeline ETL paso a paso

### 3.1 Extract
`extract()` lee `data/raw/teams_2026.csv` con pandas y **no transforma nada**. La carpeta `raw/` es de solo lectura por convención: si el dato original se corrompe, no hay forma de reconstruir nada.

### 3.2 Transform (validación)
Cada fila pasa por el contrato `Team` de **Pydantic**:

```python
form_last10: str = Field(pattern=r"^[WDL]{10}$")
fifa_rank: int = Field(ge=1, le=211)
```

Si una fila trae `form_last10="WWXDWLWWDW"` (una `X` que no existe), el pipeline **falla inmediatamente** con un mensaje que dice exactamente qué fila y qué campo. Esto se llama **fail fast**: es infinitamente más barato fallar en el ETL que descubrir un bug en una simulación de 2.000 mundiales.

### 3.3 Transform (cálculo de fuerzas)
Aquí vive el modelo del proyecto. Ver §4.

### 3.4 Load
El resultado se serializa a `data/processed/strengths_2026.json`. Tanto la CLI de Python como la app web consumen *este* archivo (la web lo lleva embebido), nunca el CSV crudo. **El procesado es la única fuente de verdad para la simulación.**

---

## 4. El modelo de probabilidad (la matemática)

### 4.1 El esquema de pesos

```
[Prior: 20% Historia]        → títulos, participaciones, ranking FIFA
        │  ×
[Likelihood: 50% Actualidad] → forma últimos 10, diferencia de xG
        │  =
[Posterior: 70% Base]        → "fuerza real del equipo hoy"
        │  +
[Contexto: 30% Partido]      → clima, lesiones, altura, hinchada
        │
[Fuerza final del partido]
```

> [!note] ¿Es esto Bayes "de verdad"?
> Es **inspiración bayesiana**, no el teorema aplicado formalmente. En Bayes puro, posterior ∝ prior × likelihood con distribuciones. Aquí usamos una **combinación lineal ponderada** — más simple, interpretable y suficiente para el objetivo. Pero la *filosofía* es la misma: una creencia previa (historia) actualizada por evidencia reciente (forma actual). En tu defensa del portafolio, di exactamente esto: demuestra que entiendes la diferencia.

### 4.2 Prior — `compute_prior()`

```python
rank_score = exp(-(rank - 1) / 35)
```

¿Por qué exponencial y no lineal? Porque la diferencia entre el puesto 1 y el 10 del ranking FIFA es *enorme*, pero entre el 60 y el 70 es casi ruido. La exponencial captura esa **no-linealidad**: decae rápido al inicio y se aplana después.

La historia mundialista suma: `títulos×0.16 + participaciones×0.015 + mejor_resultado×0.30`, recortado a 1.0.

### 4.3 Likelihood — `compute_likelihood()`

- **Forma:** puntos de los últimos 10 partidos (W=3, D=1) ÷ 30 → vive en [0,1].
- **xG:** la diferencia `xg_for − xg_against` puede ser cualquier número real, así que la pasamos por una **sigmoide** `1/(1+e^(−2.2x))` que la comprime a (0,1). La sigmoide es la misma función de activación que viste en redes neuronales — aquí cumple el mismo rol: normalizar sin perder el orden.

### 4.4 Posterior — la renormalización

Los pesos absolutos son prior=0.20 y likelihood=0.50, que suman 0.70 (el bloque "base estadística"). Para que el posterior viva en [0,1]:

```python
posterior = (0.20*prior + 0.50*likelihood) / 0.70
```

Dentro del bloque, eso equivale a pesos relativos de **2/7 y 5/7**. Detalle pequeño pero importante: sin la división, un equipo perfecto tendría posterior 0.70 y el contexto pesaría proporcionalmente más de lo diseñado.

### 4.5 Contexto — la capa del 30%

```python
final = 0.70 * posterior + 0.30 * contexto    # contexto ∈ [0,1], 0.5 = neutro
```

El contexto NO se calcula en el ETL porque **cambia partido a partido**: lo produce el Breaking News Engine + los ajustes manuales del usuario, y se inyecta en `simulate_match()`. Esto es **inyección de dependencias a nivel de datos**.

---

## 5. El motor de partido: Maher + Dixon-Coles (v3)

Los goles son **eventos raros e independientes en un intervalo fijo** (90 min) — la definición de libro de un proceso de Poisson. Pero el Poisson *independiente* tiene dos defectos documentados que la v3 corrige.

### 5.1 Maher (1982): ataque y defensa separados

Un solo número de "fuerza" no distingue a un equipo ofensivo de un cerrojo. El ETL ahora calcula dos perfiles normalizados sobre el promedio del torneo:

```
att  = xg_for / promedio(xg_for)        → 1.0 = ataque promedio
defe = xg_against / promedio(xg_against) → >1.0 = defensa permeable
```

Y la λ se construye con la forma multiplicativa clásica:

```
λ_home = 1.30 × att_home × defe_away × exp(1.6 × (S_home − S_away))
```

donde `S` sigue siendo la fuerza global (70% posterior + 30% contexto) — el modelo 20/50/30 del proyecto queda intacto; att/defe solo definen el *perfil* con que esa clase se convierte en goles. Test que lo verifica: `test_maher_att_def_definen_perfil` (mismo posterior, perfiles distintos → λ distintas).

### 5.2 Dixon-Coles (1997): la corrección de marcadores bajos

El Poisson independiente **subestima 0-0 y 1-1, y sobreestima 1-0 y 0-1** — sesgo medido en tres temporadas de la liga inglesa por Dixon y Coles. Su factor τ corrige exactamente esas cuatro celdas:

```
τ(0,0) = 1 − λμρ      τ(0,1) = 1 + λρ
τ(1,0) = 1 + μρ       τ(1,1) = 1 − ρ        (resto = 1)
```

Con ρ = −0.13 (calibración estándar de la literatura), nuestro test estadístico con 200.000 muestras reproduce el efecto del paper: **0-0 sube +18%, 1-1 sube +12%, 1-0 baja −14%, 0-1 baja −17%**. La literatura reporta ~15% de mejora de precisión predictiva sobre el Poisson simple.

### 5.3 Cómo se muestrea: rejection sampling

En vez de construir la matriz completa de marcadores, muestreamos por **rechazo**: se propone (x,y) del Poisson independiente y se acepta con probabilidad τ(x,y)/c, donde c = max τ. Es exacto (la distribución aceptada es proporcional a P_Poisson·τ) y eficiente (rechazo < 15%). Mismo algoritmo en Python y en JS, con paridad verificada: λ(BRA-MAR) = (1.45, 1.12) en ambos.

### 5.4 Ventaja de anfitrión

USA, México y Canadá reciben +0.08 de contexto en todas sus simulaciones de torneo (la literatura mide ~+0.5 goles de ventaja local promedio; nuestro bonus equivale a ~+0.1 goles esperados, conservador para sedes "semi-neutras" de un Mundial).

**Eliminación directa:** empate → prórroga (Poisson λ/3, 30 min) → penales (0.5 + 0.55·ΔS, recortado a [0.22, 0.78]).

### 5.5 ¿Cuántas simulaciones? La matemática del error

El error estándar de una probabilidad estimada es √(p(1−p)/N) — converge como **1/√N**: para 10× más precisión se necesitan 100× más muestras.

| N | Error en p≈0.6 | Veredicto |
|---|---|---|
| 10.000 | ±0.5% | bien |
| **50.000** | **±0.22%** | **el sweet spot del cara a cara** |
| 100.000 | ±0.15% | rendimiento decreciente |

Por eso la app usa **50.000** simulaciones en Partido y ofrece **10.000 mundiales** en Monte Carlo (±0.5% sobre probabilidades de campeón). Más allá de eso, el cuello de botella es la calidad del modelo, no el tamaño de la muestra.

## 6. El torneo: formato real 2026

- **48 equipos, 12 grupos (A–L) de 4** — los grupos del proyecto son los **reales del sorteo del 5-dic-2025** (Grupo C: Brasil, Marruecos, Haití, Escocia; Grupo J: Argentina, Argelia, Austria, Jordania; etc.).
- Round-robin: 6 partidos por grupo, 72 en total.
- Clasifican **los 2 primeros + los 8 mejores terceros** → 32 equipos.
- Dieciseisavos → Octavos → Cuartos → Semifinales → 3er puesto → Final. 104 partidos en total.

> [!success] Cuadro OFICIAL de la FIFA (v2)
> El simulador implementa las llaves reales M73–M104: cada posición de grupo va a su partido fijo (p.ej. M76 = 1°C vs 2°F, M84 = 1°H vs 2°J) y cada tercero entra solo a las llaves que la FIFA permite para su grupo (M74 recibe al tercero de A/B/C/D/F; M79 al de C/E/F/H/I; etc.). La asignación de los 8 terceros a sus slots se resuelve con **backtracking** (`assign_thirds()`): un problema clásico de *matching* en grafo bipartito, garantizado con solución porque FIFA diseñó los slots para cubrir las 495 combinaciones posibles. Esto es un test en sí mismo: `test_terceros_caen_en_llaves_permitidas`.

---

## 7. Monte Carlo: de un mundo a la distribución

Una simulación es **una** historia posible. Para obtener probabilidades, jugamos N mundiales independientes y contamos:

```
P(Argentina campeón) ≈ (# mundiales donde ARG ganó) / N
```

Esto es la **Ley de los Grandes Números** en acción: el estimador converge al valor verdadero del modelo cuando N→∞. El error estándar de una proporción es √(p(1−p)/N): con N=2000 y p≈0.15, el error es ±0.8% — suficiente para conversar entre amigos, insuficiente para apostar (y este proyecto no es para eso 😄).

> [!example] Resultados con N=500 (seed=1)
> ARG 16.6% · ESP 15.6% · ENG 11.2% · FRA 11.0% · BRA 9.2% · GER 7.4%...
> Sensato: refleja el orden de las casas de análisis reales, sin haberlas copiado.

**Reproducibilidad:** todo recibe un `seed`. Mismo seed → exactamente el mismo mundial. Esto es crítico para testing y para depurar ("¿por qué Uruguay salió campeón en el seed 2026?").

---

## 8. Breaking News Engine (Eventos Canónicos)

En la v2 las noticias son **deterministas y elegidas por el usuario**, no aleatorias:

1. **En la app web**: un menú desplegable por equipo con 14 eventos canónicos (lesión de figura −0.14, altura de CDMX −0.07, estadio a favor +0.08, regreso de la figura +0.07...). Cada noticia agregada mueve el contexto y se muestra como chip removible. El Mundial completo y Monte Carlo corren **siempre en contexto neutro (0.5)** — las noticias solo afectan el simulador de partido, donde el usuario las controla.
2. **En Python**: `engine.inject("BRA", -0.12, "Neymar fuera")` sigue disponible para escenarios programáticos, y el catálogo aleatorio existe pero está **desactivado por defecto** (`news_enabled=False`).

El efecto medido en el cruce Brasil–Marruecos (10.000 simulaciones):

| Escenario | Brasil | Marruecos |
|---|---|---|
| Neutro | 61.2% | 38.8% |
| Brasil con figura lesionada + crisis interna; Marruecos motivado | 42.0% | 58.0% |

El contexto **mueve el resultado sin romper el modelo**: Brasil sigue siendo más fuerte en lo estadístico (posterior 0.874 vs 0.787), pero el 30% de contexto puede dar vuelta una llave. Exactamente como el fútbol real.

---

## 9. El agente narrador (patrón "degradación elegante")

`narrator.py` genera crónicas de los partidos. Si existe `ANTHROPIC_API_KEY` en `.env` y pasas `--llm`, llama a Claude para crónicas generativas; si no, usa plantillas f-string. **El sistema completo funciona sin el LLM** — el LLM es mejora, no dependencia. Este patrón (graceful degradation) es lo que diferencia un proyecto de IA robusto de una demo que muere sin internet.

---

## 10. Testing: qué se prueba y por qué

| Test | Qué garantiza |
|---|---|
| `test_team_rechaza_form_invalida` | El contrato Pydantic ataja datos corruptos |
| `test_final_strength_respeta_pesos` | La fórmula 70/30 es exactamente la diseñada |
| `test_jerarquia_de_fuerzas_es_sensata` | Sanity check: España > Haití (si esto falla, el modelo está roto aunque el código "funcione") |
| `test_torneo_produce_campeon_reproducible` | Mismo seed → mismo mundial (determinismo) |
| `test_estructura_del_cuadro` | 16→8→4→2→1 partidos por fase; 12 partidos por grupo |
| `test_montecarlo_probabilidades_suman_1` | Las probabilidades forman una distribución válida |
| `test_breaking_news_inyectado_baja_contexto` | inject(−0.2) produce contexto 0.3 exacto |

Nota el test de **jerarquía sensata**: no testea código, testea *el modelo*. En proyectos de datos, los tests de plausibilidad valen tanto como los unitarios.

### 10.1 Backtest: el modelo contra los 104 partidos reales

Los tests de plausibilidad dicen que el modelo *no está roto*; el backtest dice *qué tan bueno es*. Con el Mundial terminado, `python -m src.cli backtest` compara las probabilidades que el modelo daba **antes** de cada partido con lo que pasó (`src/evaluation/backtest.py`).

**Cómo se evita hacer trampa (fuga de datos):**
- El modelo se evalúa con el snapshot del ETL del 15-jun (`data/snapshots/strengths_2026-06-15.json`), no con el ETL de hoy, que ya "vio" el torneo entero.
- Ese ETL ya había visto la jornada 1, y BASE/K se ajustaron mirando partidos hasta el 17-jun. Por eso se reporta aparte el tramo **fuera de muestra**: los 48 partidos de grupos posteriores al 17-jun.
- Los resultados reales están congelados en `data/raw/wc2026_results.csv` (`tools/snapshot_wc2026.py`). El backtest nunca lee cachés que se refrescan solas.

**Contra qué se compara.** Un modelo solo "es bueno" en relación a una alternativa:
- **ELO pre-torneo**: reconstruido con la metodología de eloratings.net sobre el historial martj42, usando solo partidos anteriores al 11-jun (`src/evaluation/elo.py`). Es el baseline serio, porque eloratings.net solo publica el rating actual. Para convertir ELO en 1X2 se usa un modelo de empate de un parámetro, ajustado con los Mundiales 1998–2022.
- **Uniforme**: 1/3 por resultado. Es el piso de "no sé nada".

**Métricas** (en todas, menor = mejor): Brier (0 = perfecto, 0.667 = uniforme), **RPS**, que es la métrica estándar en fútbol porque decir "empate" cuando gana el local es un error menor que decir "gana el visitante", y log-loss. En eliminatorias el dataset registra el marcador tras la prórroga, así que se evalúa *quién clasifica*, integrando prórroga y penales igual que `simulate_match()`.

| Tramo | Modelo (Brier) | ELO (Brier) | Uniforme | Modelo − ELO, IC 95% |
|---|---|---|---|---|
| Grupos, 72 partidos | **0.478** | 0.541 | 0.667 | −0.062 [−0.118, −0.010] |
| Grupos fuera de muestra, 48 | **0.408** | 0.442 | 0.667 | −0.034 [−0.091, +0.020] |
| Eliminatorias, 32 (¿quién clasifica?) | **0.134** | 0.148 | 0.250 | −0.014 [−0.047, +0.017] |

Los intervalos salen de un **bootstrap pareado** (5.000 remuestreos de partidos): si el intervalo cruza el 0, la diferencia puede ser ruido.

**Cómo leerlo:**
1. El modelo le gana con claridad al azar en todos los tramos, y le gana al ELO en la estimación puntual de los tres.
2. En los 72 partidos de grupos la ventaja sobre ELO es significativa, pero ese tramo incluye los 24 partidos que el modelo pudo "ver". En el tramo limpio (48) y en eliminatorias (32) la ventaja **no es estadísticamente significativa**. La conclusión honesta: el modelo es *al menos tan bueno* como un ELO bien hecho, y probablemente algo mejor, pero 80 partidos limpios no alcanzan para afirmarlo.
3. **Calibración**: cuando el modelo dice 10% pasa el 9%; 28% → 29%; 68% → 70%; en el tramo de 80–100% (n=15) dice 90% y pasa el 80%, un leve exceso de confianza en los grandes favoritos. Goles por partido: predicho 3.08, real 2.99.
4. **Empates**: el modelo predijo 21% y hubo 27.8% (15 esperados vs 20 reales, z = 1.4). No es significativo, pero es el sesgo a vigilar.

**¿Hay que recalibrar K/BASE/ρ?** `backtest --refit` busca los valores que maximizan la verosimilitud del marcador exacto en grupos y los valida en eliminatorias. Encuentra K=1.3, BASE=1.35, ρ=−0.20 (más empates, coherente con el punto 4), pero la ganancia es de 0.35 unidades de log-verosimilitud con 3 parámetros libres (una prueba de razón de verosimilitud pediría ~3.9) y en eliminatorias mejora el Brier en 0.0008, con un IC que cruza el 0. **Decisión: los valores actuales se quedan.** La superficie es casi plana alrededor de K=1.2 / BASE=1.4, así que cambiarlos sería ajustar ruido y además rompería la paridad con el motor JS de la app.

> [!warning] El backtest no lee cachés vivas
> `transform()` llama a los scrapers de resiliencia y forma, que en uso normal refrescan `data/cache/` cuando vence el TTL semanal. La suite de tests está aislada (`tests/conftest.py` bloquea la red y no deja mutar `data/cache/`), pero el backtest igual solo lee `data/snapshots/` y `data/raw/`, para que sus cifras no dependan de cuándo se corre.

---

## 11. Cómo correr todo

```bash
# setup (una vez)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # núcleo + scikit-learn + anthropic + herramientas

# selecciones
python -m src.cli etl
python -m src.cli simulate --seed 2026
python -m src.cli montecarlo -n 2000
python -m src.cli h2h BRA MAR -n 10000
python -m src.cli h2h BRA MAR --ctx-home 0.25 --ctx-away 0.6   # con drama
python -m src.cli backtest            # §10.1
python -m src.cli backtest --refit

# clubes (§12), modelo supervisado (§13) y ciclo diario (§14)
python -m src.clubs.run                                   # las cinco ligas → data/processed/clubs_<div>.json
python -m src.clubs.h2h SP1 barcelona "real madrid" --odds 1.95 3.9 3.6
python -m src.ml.train --leagues all                      # entrena, evalúa y escribe docs/RESULTADOS_ML.md
python -m src.pipeline.daily                              # descarga, predice, registra, exporta
python -m tools.export_frontend                           # reinyecta los datos en app/index.html

# calidad
pytest            # 120 tests, sin red
ruff check .
mypy
```

**La interfaz web:** `app/index.html` se abre con doble clic, sin servidor, o en https://demianc14.github.io/WC_predictor/. El menú tiene cuatro secciones, cada una con subsecciones:
- **Inicio**: landing con los colores tri-sede del Mundial y fondo animado en `<canvas>`.
- **Selecciones 2026-27**: próxima ventana, última ventana (resultados contra lo que esperaba el modelo), partido y cuotas entre cualquier par, con las noticias del Breaking News Engine como chips, y ranking.
- **Ligas · cinco grandes**: selector de liga y, para cada una, tabla proyectada, próxima jornada contra las cuotas, partido y cuotas entre cualquier par de clubes, ranking (xPts, ataque contra defensa) y backtest contra el mercado. Arriba, la barra de métricas en vivo (§14.1).
- **Archivo · Mundial 2026**: el cuadro real y el que esperaba el modelo, probabilidad de llegar a cada ronda y el backtest.

La web y Python usan la misma fórmula: `python -m src.clubs.h2h` y la vista "Partido" de una liga dan los mismos números.

---

# Parte II · Clubes: las cinco grandes ligas

## 12. De selecciones a clubes

`src/clubs/` reutiliza la matriz Dixon-Coles de §5, pero **estima** sus parámetros con los partidos de cada liga en vez de fijarlos a mano. A diferencia de selecciones, no hay noticias ni contexto: solo ataque, defensa y localía.

### 12.1 Datos y calendario

- **Resultados y cuotas** (`data.py`): CSVs de [football-data.co.uk](https://www.football-data.co.uk/), con el mismo formato para E0, SP1, D1, I1 y F1 y sus segundas divisiones. Traen las cuotas de cierre promedio (solo como benchmark, §2.1) y xG desde 2026-27. `fixtures.csv` trae los partidos de los próximos días con sus cuotas.
- **Calendario completo** (`calendar.py`): feeds JSON de [fixturedownload.com](https://fixturedownload.com/). Tres problemas reales y cómo se resuelven:
  1. **Los nombres no coinciden** ("Man United" contra "Man Utd", "Tottenham" contra "Spurs"). No hay diccionario a mano: el cruce se **deduce por votos** a partir de los partidos ya jugados (mismo día ±1 y mismo marcador). Si un equipo queda sin pareja, falla con el nombre exacto (fail fast, como §3.2).
  2. **El feed puede estar mal.** El de Ligue 1 traía Rennes-PSG dos veces y ningún PSG-Rennes (305 partidos en vez de 306). `repair_round_robin` exige una liga a dos ruedas, invierte el duplicado no jugado más reciente y lo deja a la vista en la consola y en `calendar_fixes` del JSON. Corregir en silencio sería inventar datos.
  3. **Horarios sin confirmar.** Vienen como medianoche local; se marcan `tbc` en vez de mostrarse como una hora real.
- **Degradación elegante:** si el feed no está disponible, la simulación usa todo cruce no jugado.

### 12.2 El modelo: Dixon-Coles estimado por liga

`model.py` ajusta ataque y defensa por club, la localía, la media μ y ρ por **máxima verosimilitud Poisson**, con el algoritmo iterativo de Maher (cada parámetro se actualiza en forma cerrada dado el resto, sin scipy). Tres decisiones:

- **Decaimiento temporal:** cada partido pesa `exp(−0.0019·días)`, así que uno de hace un año pesa ~50%. Era uno de los pendientes del roadmap de la etapa del Mundial.
- **Shrinkage:** 3 goles ficticios hacia el promedio, para que un equipo con pocos partidos no tenga parámetros extremos.
- **Segunda división en el mismo ajuste:** los ascendidos llegan con historia en vez de empezar en cero.
- Cuando hay xG (2026-27), el objetivo es 50% goles + 50% xG: el xG tiene menos ruido que los goles.

ρ se busca por grilla sobre la verosimilitud, con los mismos pesos.

### 12.3 Temporada, partido y cuotas

- **Temporada** (`season.py`): Monte Carlo de los partidos que faltan (10.000 temporadas) → puntos esperados y probabilidad de cada puesto.
- **Partido y cuotas** (`h2h.py`): 1X2, goles, ambos anotan, marcadores, cuota justa y EV con ¼ de Kelly contra las cuotas que le pases. Busca el equipo sin importar tildes y falla si el nombre es ambiguo.

### 12.4 Contra el mercado

`backtest.py` hace un **walk-forward semanal**: cada lunes reajusta con lo jugado hasta ahí y predice esa semana. Sobre los mismos partidos compara tres cosas: el modelo, las cuotas de cierre promedio **sin margen** (no-vig) y una base que solo conoce la frecuencia de 1/X/2 de la liga hasta esa semana.

| Liga | Temporada | n | Brier modelo | Brier mercado | Brier base | RPS modelo | RPS mercado |
|---|---|---|---|---|---|---|---|
| Premier League | 2025-26 | 380 | 0.623 | **0.608** | 0.656 | 0.212 | **0.204** |
| LaLiga | 2025-26 | 380 | 0.579 | **0.572** | 0.633 | 0.200 | **0.196** |
| Bundesliga | 2025-26 | 306 | 0.575 | **0.562** | 0.649 | 0.196 | **0.190** |
| Serie A | 2025-26 | 380 | 0.598 | **0.583** | 0.661 | 0.203 | **0.196** |
| Ligue 1 | 2025-26 | 306 | 0.599 | **0.582** | 0.644 | 0.207 | **0.200** |

(La tabla con 2026-27 está en el README.)

**Cómo leerlo:** el modelo le gana con claridad a la base en todas las ligas, pero **pierde contra el mercado en las cinco** en la temporada completa. Es lo esperable: el mercado de cierre incorpora lesiones, alineaciones y el dinero de miles de apostadores. Apostar cada discrepancia de más de 5% habría perdido entre 9% y 29% según la liga. Por eso la web muestra *dónde discrepa* el modelo, nunca "valor".

---

# Parte III · Modelo supervisado

## 13. Clasificación 1X2 con validación honesta

`src/ml/` responde una pregunta concreta: **¿un modelo entrenado con features mejora al Dixon-Coles?** El reporte completo, con tablas por liga, intervalos, calibración y ablación, lo genera el código: [`RESULTADOS_ML.md`](RESULTADOS_ML.md). Las cifras de esta sección salen de ahí.

### 13.1 Features sin fuga de datos

Todas se calculan con partidos de **días anteriores** (`features.py`):
- **ELO de clubes:** K=20, +60 de localía; arranca en 1500 en primera y 1350 en segunda, y se actualiza también con los partidos de segunda.
- **Forma de los últimos 5:** puntos, goles a favor y en contra.
- **Días de descanso**, con tope 21.
- **Liga**, en one-hot.
- En una variante, las **probabilidades y λ del Dixon-Coles**, reajustado cada lunes con los 3 años previos.
- **Europa** (fase 6, §13.5): descanso contando Champions y Europa League (`rest_all`) y partidos europeos en los 14 días previos (`eu_n14`).

Quedan afuera el xG (solo existe desde 2026-27), las copas nacionales y la Conference League, las lesiones y las alineaciones.

> [!warning] Cómo se prueba que no hay fuga
> `test_cambiar_el_futuro_no_mueve_las_features_del_pasado` altera resultados futuros y comprueba que ninguna feature pasada cambia. `test_partidos_del_mismo_dia_no_se_ven_entre_si` cubre el caso borde de la misma jornada. `test_las_cuotas_nunca_son_feature` hace cumplir el principio 5. Un test de fuga vale más que cualquier explicación en el README.

### 13.2 Modelos y validación

- **Modelos:** base de frecuencias por liga, regresión logística multinomial (sin y con Dixon-Coles, con imputación y escalado) y `HistGradientBoostingClassifier`.
- **Splits por temporada:**
  - 2019-20 solo como historia previa;
  - entrenamiento 2020-21 a 2022-23;
  - validación 2023-24 y 2024-25, donde se eligen los hiperparámetros;
  - test 2025-26 y lo que va de 2026-27, que no se mira hasta el final.
- **Walk-forward mensual:** para predecir un mes se entrena solo con meses anteriores. Lo verifica `test_walk_forward_entrena_solo_con_meses_anteriores`.
- **Elección:** en cada familia gana el de menor log-loss en validación, entre candidatos con y sin las features europeas. La ablación agrega features de a una: ELO, forma, descanso, liga, Dixon-Coles y Europa.

### 13.3 Resultados (test, cinco ligas juntas, n = 2098 para todos)

| Modelo | RPS [IC 95%] | Log-loss |
|---|---|---|
| Base (frecuencias) | 0.2294 [0.2263, 0.2324] | 1.0715 |
| Logística sin Dixon-Coles | 0.2020 [0.1960, 0.2078] | 0.9914 |
| Logística + Dixon-Coles | 0.2019 [0.1963, 0.2074] | 0.9908 |
| Gradient boosting (+ Europa) | 0.2034 [0.1976, 0.2089] | 0.9969 |
| Dixon-Coles | 0.2027 [0.1977, 0.2078] | 0.9936 |
| **Mercado (cierre, sin margen)** | **0.1971 [0.1918, 0.2024]** | **0.9742** |

Las comparaciones se hacen con **diferencias pareadas por bootstrap**: se remuestrean partidos y se calcula la diferencia en cada remuestreo. Si el intervalo cruza el 0, la diferencia puede ser ruido.

- Logística + Dixon-Coles contra Dixon-Coles: ΔRPS −0.0008 [−0.0019, +0.0003]. **No se distingue.**
- Logística + Dixon-Coles contra mercado: ΔRPS +0.0048 [+0.0026, +0.0070]. **Peor.**
- **Calibración:** los cuatro modelos están bien calibrados, también en empates (predicen 25.3-25.5%, hubo 25.2%). El sesgo de empates del Mundial (§10.1, punto 4) no aparece con muestras grandes.
- El gradient boosting no supera a la logística: con ~11.000 partidos y señales casi lineales, no hay interacciones que aprovechar.

**Conclusión para la defensa:** el supervisado no mejora al Dixon-Coles y no alcanza al mercado. Es un resultado negativo **bien medido**, y eso vale más que un número lindo sin intervalo. La meta realista del brief era igualar al mercado con buena calibración; la calibración se logró, igualarlo no.

### 13.4 Reproducibilidad

Cada corrida escribe `data/ml/runs/<fecha>_<huella>/` con las predicciones, las métricas, los modelos y un manifiesto con el commit, las versiones de las librerías, la semilla y la **huella SHA-256 del dataset**. `python -m src.ml.report <run>` regenera el reporte sin reentrenar. El commit se toma con `git describe --dirty`: una corrida desde un árbol con cambios sin commitear queda marcada, y por eso la oficial se corrió desde uno limpio. La vigente es la de la fase 6 (`8347a73`, huella `9bd592bc9bef`, 6 minutos en local con `--rebuild`); la anterior fue `84fdeb2`, huella `0a9df3af955e`.

### 13.5 Europa en el descanso (fase 6)

**Pregunta:** el descanso solo veía la liga, así que un equipo que jugó Champions el miércoles figuraba con 7 días de descanso. ¿Mejora el modelo si ve el calendario europeo?

- **Fuente:** fixturedownload.com publica Champions y Europa League desde 2019-20, con fecha y marcador, desde la fase de grupos (`src/ml/europe.py`, caché en `data/cache/clubs/europe/`). Los nombres se cruzan con football-data por igualdad o con una tabla de 20 alias; `python -m src.ml.europe --report` lista lo que queda sin cruzar (115 nombres, todos clubes de fuera de las cinco ligas, revisados a mano). Resultado: 2296 partidos-club de 62 clubes.
- **Fuera:** la Conference League (su feed existe recién desde 2024-25; meterla solo en test haría que train y test midieran cosas distintas) y las copas nacionales (no están en la fuente). Las previas europeas tampoco.
- **Sin fuga:** solo cuentan partidos europeos de días anteriores (`tests/test_ml_europe.py`). La huella del dataset incluye los feeds europeos.

**Resultado (validación 2023-24 y 2024-25, n = 3504):**
- En la ablación de la logística, sumar Europa empeora apenas: log-loss 0.9806 → 0.9811, RPS 0.1979 → 0.1981.
- La logística elige la variante sin Europa en sus dos familias.
- El gradient boosting elige la variante con Europa por una diferencia mínima (log-loss 0.9919 contra 0.9927), pero en test sigue sin distinguirse del Dixon-Coles (ΔRPS +0.0007 [−0.0009, +0.0022]).

**Conclusión:** saber qué clubes jugaron en Europa no cierra la brecha con el mercado. Una explicación plausible, **no verificada**, es que la carga europea ya está en el ELO y en el Dixon-Coles: los que juegan Europa son los mejores equipos, y el efecto de un partido entre semana es chico frente al ruido de un 1X2.

---

# Parte IV · Operación

## 14. Que corra solo, y que se pueda auditar

### 14.1 Ciclo diario y almacén de predicciones

Cada día a las 05:30 UTC, antes de cualquier partido europeo, GitHub Actions (`daily.yml`) corre `python -m src.pipeline.daily`:

1. **Descarga todo o nada.** Baja la temporada actual de las 10 divisiones, `fixtures.csv` y los 5 calendarios a una carpeta temporal y valida cada archivo (una página de error HTML no pasa por CSV). Si una sola fuente falla, termina con código 2 sin tocar nada, y GitHub avisa por correo.
2. **Ajusta y predice en memoria.** Predice los partidos de los próximos días que todavía no tienen predicción para la versión actual del modelo. Un partido de hoy solo se predice si el ciclo corre antes de las 10:00 UTC.
3. **Registra** resultados y cuotas de cierre de lo jugado, y recalcula las métricas en vivo.
4. **Recién entonces escribe**, con reemplazos atómicos: JSON por liga, `live.json`, el almacén y la web. El bot commitea y `pages.yml` publica.

**El almacén** (`data/predictions/predicciones.csv`) tiene una fila por (partido, versión del modelo). La regla central: **una predicción guardada nunca se sobrescribe**. `store.save` compara contra el archivo en disco antes de escribir y se niega a borrar, cambiar una probabilidad o contradecir un resultado. Si el modelo cambia, entra otra fila con otra versión. Solo se completan después el resultado y la cuota de cierre. El historial de git del archivo es la prueba pública de que cada predicción existía antes del partido.

**Versión del modelo = hash git del árbol `src/clubs/`.** Cambia solo si cambia el código del modelo, no con cualquier commit del bot.

**Métricas en vivo:** se evalúa la **primera** predicción de cada partido, sobre los mismos partidos que la cuota de cierre. Es la única evaluación sin ninguna posibilidad de fuga. Las primeras predicciones son del 20-oct-2026 a las 19:12 UTC; al 21-oct había 52 predicciones y ningún partido evaluado todavía. **Con pocas semanas no es concluyente**: el backtest de §12.4 necesitó temporadas enteras para separar al modelo del mercado.

> [!example] Tests del ciclo
> `test_fetch_es_todo_o_nada`, `test_un_fallo_a_mitad_no_deja_nada_escrito`, `test_check_append_only_rechaza_cualquier_reescritura` y `test_metricas_en_vivo_usan_la_primera_prediccion`. Prueban justamente lo que haría falso al almacén si fallara.

### 14.2 CI y publicación

- **`ci.yml`**, en cada push y PR, sobre Python 3.11 y 3.12: `ruff check .`, `mypy` (src/ y tools/, en cero errores) y `pytest`, más un job que construye las imágenes de Docker y corre la suite adentro.
- **Tests herméticos:** `test_hermetic.py` asegura que la suite no toque la red.
- **`pages.yml`** publica la web y los JSON en GitHub Pages después de cada ciclo diario exitoso.

### 14.3 Docker: dos imágenes reproducibles

Un `Dockerfile` multi-stage sobre `python:3.11-slim` (la misma versión que CI) arma dos targets. Los dos corren con un usuario sin privilegios y no llevan datos ni secretos:

| Imagen | Para qué | Tamaño medido |
|---|---|---|
| `wc-predictor` | ciclo diario, web, ligas, partido y cuotas (solo numpy, pandas, pydantic) | 439 MB |
| `wc-predictor:ml` | entrenamiento y suite de tests (suma scikit-learn y pytest) | 742 MB |

La primera versión pesaba 826 MB. Bajó al sacar dependencias declaradas que nadie importaba y separar `scikit-learn` y `anthropic` en extras opcionales. Además, las métricas pasaron a `src/ml/metrics.py`, que solo usa numpy, para que el ciclo diario no cargue scikit-learn.

**Prueba de reproducibilidad:** se reconstruyeron los datos del commit oficial con `git archive` (misma huella, `0a9df3af955e`) y se corrió el entrenamiento completo dentro de `:ml`. Contra el `metrics.json` oficial, la diferencia máxima fue **2,6·10⁻¹⁴**, redondeo de punto flotante entre Linux y macOS, con los mismos modelos elegidos. Tardó 54 minutos calculando las features desde cero.

Dentro del contenedor no hay `.git`: `make docker-build` graba en la imagen la versión del modelo y el commit, así una predicción hecha desde Docker no se duplica con las del bot. Comandos: `make docker-build docker-test docker-daily docker-train docker-serve`.

---

## 15. Limitaciones honestas (para tu defensa)

**Clubes y modelo supervisado:**
1. **El modelo pierde contra el mercado** en las cinco ligas (§12.4), y el supervisado no lo cambia (§13.3). Para cerrar la brecha haría falta información que el mercado sí ve: lesiones y alineaciones. El calendario europeo ya se probó y no alcanzó (§13.5); las copas nacionales siguen sin fuente.
2. **Las métricas en vivo recién empiezan** (§14.1): con pocas semanas no permiten conclusiones.
3. **El xG de clubes solo existe desde 2026-27**, así que no entra al supervisado.
4. **2020-21 se jugó mayormente sin público**: su ventaja de local es atípica y está en el entrenamiento.
5. **El entrenamiento en Docker es lento sin la caché de features** (54 min contra unos 3 en local con la caché).

**Selecciones (Parte I):**
6. **El xG base sigue siendo curado.** ELO, historial y valor de plantilla se scrapean, y StatsBomb cubre 40 de las 48 selecciones, pero el resto del xG es manual.
7. **Cobertura limitada a 48 selecciones:** los scrapers solo mapean los equipos del Mundial 2026; otros rivales se estiman desde su ELO.
8. **El "Bayes" es una combinación lineal** inspirada en el marco bayesiano, no inferencia formal (§4.1).
9. **El backtest del Mundial tiene poca muestra:** en 80 partidos limpios la ventaja sobre ELO no es significativa (§10.1).

Saber nombrar tus limitaciones es la señal más fuerte de madurez técnica en una entrevista.

---

## 16. Roadmap

### 16.1 Hecho

- [x] Dixon-Coles con ρ (§5.2); ρ, μ, localía y decaimiento temporal estimados por máxima verosimilitud sobre muestra grande en clubes (§12.2)
- [x] Fuentes en vivo para selecciones: ELO de eloratings.net, historial desde 1872, valor de plantilla y xG de StatsBomb, con degradación elegante
- [x] Calibración formal contra los 104 partidos del Mundial, con bootstrap contra ELO (§10.1)
- [x] Clubes con football-data: las cinco grandes ligas y sus calendarios (§12)
- [x] Cuotas de casas de apuestas como benchmark, nunca como feature (§12.4, §13.1)
- [x] Modelo entrenado (logística y gradient boosting) en vez de pesos a mano, comparado con IC (§13)
- [x] Refresco automático con GitHub Actions, predicciones auditables y métricas en vivo (§14.1)
- [x] CI con ruff, mypy, pytest y Docker; dos imágenes reproducibles (§14.2, §14.3)
- [x] Champions y Europa League en el descanso, medido en validación y test (§13.5)

### 16.2 Pendiente

- **Información que el mercado ve y el modelo no:** lesiones y alineaciones como features con fecha, tanto en clubes como en el contexto del 30% de selecciones (hoy se elige a mano).
- **xG como feature** del supervisado cuando 2026-27 tenga suficiente muestra; mientras tanto, el Dixon-Coles ya lo usa.
- **Copas nacionales y Conference** en el descanso, si aparece una fuente con fecha (Europa ya entró en la fase 6 y no mejoró, §13.5).
- **Métricas en vivo:** volver a leerlas cuando haya temporadas enteras, no semanas.
- **Caché de features en Docker** para no recalcular 54 minutos en cada entrenamiento.
- **Selecciones:** ampliar los mapeos más allá de las 48 y estimar ρ y el modelo de empates sobre el historial completo.
- **Otros torneos:** un `tournament.py` con el cuadro de la Euro o la Copa América reutiliza `match_engine.py` sin cambios.
- **Infraestructura**, solo si hace falta: una base de datos (el brief pide aprobación antes de agregar Postgres o Supabase) o una API. Hoy el CSV versionado es más auditable que una base de datos.

---

## 17. Glosario rápido

- **ETL**: Extract-Transform-Load, el pipeline que lleva datos crudos a datos listos para el modelo.
- **xG (expected goals)**: calidad de las ocasiones creadas, medida en goles esperados.
- **Prior / Likelihood / Posterior**: creencia previa / evidencia / creencia actualizada (marco bayesiano).
- **Poisson**: distribución de conteo de eventos raros en un intervalo fijo.
- **Dixon-Coles**: Poisson con una corrección ρ para los marcadores bajos (0-0, 1-0, 0-1, 1-1).
- **Monte Carlo**: estimar probabilidades muestreando muchas veces un proceso aleatorio.
- **Seed**: semilla del generador pseudoaleatorio; fija el "universo" simulado.
- **Brier score**: error cuadrático entre las probabilidades y lo que pasó (0 = perfecto).
- **RPS (Ranked Probability Score)**: como el Brier, pero sobre probabilidades acumuladas. Castiga menos decir "empate" cuando gana el local que decir "gana el visitante". Es la métrica estándar en fútbol.
- **Log-loss**: −log de la probabilidad dada a lo que pasó. Castiga mucho la confianza equivocada.
- **Walk-forward**: validar entrenando solo con el pasado y prediciendo el bloque siguiente, en orden.
- **No-vig (sin margen)**: probabilidades implícitas de las cuotas, normalizadas para que sumen 1 y sin el margen de la casa.
- **Bootstrap pareado**: remuestrear los mismos partidos para ambos modelos y mirar la distribución de la diferencia. Da un intervalo de confianza.
- **Calibración**: que cuando el modelo dice 30%, pase cerca del 30%.
- **Append-only**: almacén donde solo se agregan filas; lo escrito no se modifica.
- **Huella del dataset**: hash SHA-256 de los datos de entrada. Dos corridas con la misma huella usaron exactamente los mismos datos.
- **Fail fast**: fallar temprano y ruidosamente en vez de propagar datos corruptos.
- **Graceful degradation**: el sistema pierde features opcionales, nunca la funcionalidad base.
