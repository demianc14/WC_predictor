# 🏆 World Cup Predictor — Bitácora del Proyecto

> [!info] Metadatos
> **Autor:** Demian · **Stack:** Python 3.11+, Pydantic, pandas, pytest, HTML/JS vanilla
> **Objetivo:** Simular la Copa del Mundo 2026 fase a fase con un modelo probabilístico inspirado en inferencia bayesiana, un motor de eventos ("Breaking News Engine") y una interfaz web para compartir con amigos.
> **Nivel:** explicado para Ing. en Cs. de la Computación, 7mo semestre.

> [!note] Nota histórica
> El proyecto se llamó originalmente "World Cup LLM Simulator". Se renombró a **World Cup Predictor** porque el LLM (`src/agents/narrator.py`, §9) es un narrador opcional con degradación elegante, no parte del motor de predicción — el nombre anterior sobrevendía el rol del LLM.

---

## 1. La idea en una frase

Convertir datos históricos y de forma reciente de las 48 selecciones del Mundial 2026 en una **distribución de probabilidad sobre resultados**, y luego muestrear esa distribución miles de veces (Monte Carlo) para responder preguntas como *"¿qué probabilidad tiene Marruecos de eliminar a Brasil si Neymar se lesiona?"*

```
Datos crudos → ETL → Fuerzas por equipo → Motor de partido (Poisson)
            → Torneo completo → Monte Carlo → Probabilidades
```

---

## 2. Arquitectura del repositorio

```
world_cup_predictor/
├── data/
│   ├── raw/teams_2026.csv          ← datos crudos, INTOCABLES
│   ├── raw/wc2026_results.csv      ← los 104 resultados reales (congelados)
│   ├── snapshots/                  ← entradas del modelo al 15-jun (backtest)
│   └── processed/strengths_2026.json ← salida del ETL
├── src/
│   ├── etl/
│   │   ├── models.py               ← contratos Pydantic
│   │   └── pipeline.py             ← Extract → Transform → Load
│   ├── simulation/
│   │   ├── match_engine.py         ← Poisson, prórroga, penales
│   │   └── tournament.py           ← grupos, terceros, llaves, Monte Carlo
│   ├── agents/
│   │   ├── breaking_news.py        ← Eventos Canónicos (contexto 30%)
│   │   └── narrator.py             ← crónicas (LLM opcional)
│   ├── evaluation/
│   │   ├── elo.py                  ← ELO reconstruido con fecha de corte
│   │   └── backtest.py             ← calibración vs resultados reales (§10.1)
│   └── cli.py                      ← interfaz de línea de comandos
├── app/index.html                  ← interfaz web autocontenida
├── tests/                          ← 46 tests con pytest
└── docs/                           ← este archivo
```

> [!tip] Principio de diseño: separación de capas
> El ETL no sabe que existe un simulador. El simulador no sabe de dónde vienen los datos. El Breaking News Engine no sabe de Poisson. Cada capa se puede testear y reemplazar de forma independiente. Esto es **bajo acoplamiento / alta cohesión**, el corazón de la ingeniería de software.

---

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

> [!warning] Los tests del ETL tocan la red
> `transform()` llama a los scrapers de resiliencia y forma, que refrescan `data/cache/` cuando vence el TTL semanal. Correr `pytest` puede reemplazar los cachés por datos posteriores al torneo. Por eso el backtest solo lee `data/snapshots/` y `data/raw/`.

---

## 11. Cómo correr todo

```bash
# setup (una vez)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# pipeline ETL
python -m src.cli etl

# una copa completa, fase a fase
python -m src.cli simulate --seed 2026

# probabilidades de campeón (2000 mundiales)
python -m src.cli montecarlo -n 2000

# el cruce que le mostrarás a tus amigos
python -m src.cli h2h BRA MAR -n 10000
python -m src.cli h2h BRA MAR --ctx-home 0.25 --ctx-away 0.6   # con drama

# ¿qué tan bien predijo? (§10.1)
python -m src.cli backtest
python -m src.cli backtest --refit   # + reajuste de K/BASE/ρ validado en eliminatorias

# tests
pytest
```

**La interfaz para amigos (v2):** abre `app/index.html` en cualquier navegador (doble clic, sin servidor). Cinco vistas con navegación fija arriba:
- **Inicio**: landing con los colores tri-sede del Mundial (verde México, rojo Canadá, azul EE.UU.), tipografía Anton y fondo animado en `<canvas>`.
- **Partido**: cualquier cruce en modo *eliminación directa* o *fase de grupos* (con probabilidad de empate). Las noticias pre-partido se eligen de un menú y aparecen como chips. Salida: barra de probabilidad estilo cancha + tabla compacta de los marcadores más frecuentes con sus λ.
- **Mundial**: una copa completa con el cuadro oficial M73–M104, tablas de grupo compactas, terceros resaltados y confeti en canvas para el campeón. Sin noticias: contexto neutro.
- **Monte Carlo**: 500 o 2.000 mundiales, tabla compacta Campeón/Finalista/Semis con barras.
- **Pronóstico**: ingresa marcadores reales que ya se jugaron (o tus predicciones) en los 72 partidos de grupos; lo vacío se simula. Completa el mundial una vez o corre 300 mundiales **condicionados** a tus resultados — probabilidad condicional aplicada, literalmente.

Puedes subirla gratis a GitHub Pages o Netlify Drop y mandarles el link.

---

## 12. Limitaciones honestas (para tu defensa)

1. **El xG base sigue siendo curado.** ELO, historial y valor de plantilla ya se scrapean (§13.1), pero el xG del CSV es una estimación manual porque FBref bloquea el scraping. El punto de extensión es `extract()`: cambiar la fuente y el resto del pipeline no se entera (gracias a la separación de capas).
2. ~~Poisson asume independencia entre goles~~ → **resuelto en v3** con la corrección Dixon-Coles (ρ=−0.13). Estimar ρ por máxima verosimilitud sobre el Mundial 2026 da −0.20, pero la mejora no es significativa (§10.1).
3. El "Bayes" es una combinación lineal inspirada en el marco bayesiano, no inferencia formal (§4.1).
4. **La validación tiene poca muestra.** En el backtest (§10.1) el modelo supera al azar con claridad y al ELO en la estimación puntual, pero en los 80 partidos fuera de muestra esa ventaja sobre ELO no es significativa. Subestima un poco los empates (21% vs 27.8%) y se confía de más en los favoritos del 80–100%.

Saber nombrar tus limitaciones es la señal más fuerte de madurez técnica en una entrevista.

---

## 13. Roadmap: cómo escalar el proyecto

### 13.1 Ya implementado (v4 — no está descrito en §4, léelo como el estado actual)

El prior y el likelihood de §4 ya no dependen solo del CSV curado: el ETL enriquece cada equipo con fuentes en vivo *antes* de calcular fuerzas, con el mismo patrón de **degradación elegante** del narrador (§9) — si una fuente falla, cae al valor del CSV y el pipeline nunca se rompe.

- [x] **ELO en vivo** (`src/etl/scrapers/elo.py`, fuente eloratings.net): domina el prior (peso 0.55) sobre el ranking FIFA, que queda como fallback
- [x] **Historial de partidos desde 1872** (`src/etl/scrapers/history.py`, dataset martj42/international_results): alimenta `resilience.py` (no_loss_rate vs top, clean sheets, comebacks, winrate competitivo) y `form.py` (att/def dinámico ponderado por recencia y calidad del rival, en vez del xG fijo del CSV)
- [x] **Valor de plantilla y edad** (`src/etl/scrapers/transfermarkt.py`): entra al likelihood como proxy de calidad individual (peso 0.30 cuando está disponible)
- [x] Modelo Dixon-Coles con ρ=−0.13 (v3) → siguiente paso: estimar ρ por máxima verosimilitud (ver 13.3)

### 13.2 Importar más resultados / más datos

- **Ampliar cobertura**: `FIFA_TO_ELO`, `FIFA_TO_HISTORY` y `FIFA_TO_QUERY` hoy solo mapean las 48 selecciones del Mundial 2026; extenderlos a todas las selecciones FIFA permite simular cualquier amistoso o clasificatorio, no solo el torneo oficial
- **Ventanas configurables**: la ventana de resiliencia (4 años) y de forma dinámica (últimos N partidos) están hardcodeadas; exponerlas como parámetro permite comparar "forma últimos 3 meses" vs "últimos 2 años"
- **Lesiones/convocatorias automatizadas**: sumar una fuente (API de plantillas o scraping de prensa deportiva) para alimentar el contexto del 30% en vez de elegirlo a mano desde el menú de Breaking News
- **Cuotas de casas de apuestas** (p.ej. una Odds API) como benchmark externo para calibrar el modelo — nunca para reemplazarlo, ver 13.3
- **Refresco automático**: un cron/GitHub Action que corra `python -m src.cli etl` en cada fecha FIFA y commitee el JSON actualizado, en vez de correrlo a mano

### 13.3 Escalar el modelo estadístico

- [x] **Calibración formal** contra los 104 partidos reales del Mundial 2026 (Brier, RPS, log-loss, bootstrap vs ELO): ver §10.1
- Estimar ρ y un decaimiento temporal ξ por máxima verosimilitud sobre el **historial completo** (miles de partidos), no solo sobre el Mundial: con 72 partidos la superficie es demasiado plana para decidir (§10.1)
- Corregir la subestimación de empates: un parámetro de inflación de empates o un ρ ajustado sobre muestra grande, validado con el mismo backtest
- Reemplazar la combinación lineal 20/50/30 (§4.1) por un modelo entrenado (regresión logística o gradient boosting) sobre partidos históricos, usando prior/likelihood/contexto como *features* en vez de pesos fijados a mano
- Extender Maher/Dixon-Coles con decaimiento temporal en el att/def (un gol de hace 2 años no debería pesar igual que uno del mes pasado — hoy eso solo se aplica en `resilience.py`/`form.py`, no en el att/def base del CSV)

### 13.4 Escalar a otros torneos

Gracias a la separación de capas (§2), el motor de partido (Maher + Dixon-Coles) no sabe nada de "Mundial": solo consume fuerzas y un cuadro. Escalar a otro torneo es sobre todo trabajo de **datos y cuadro**, no de reescribir el motor:

- Un `tournament.py` alternativo con el cuadro de la Eurocopa o la Copa América reutiliza `match_engine.py` sin cambios
- Simular clubes (Champions League) requiere cambiar la fuente en `extract()` — el dataset martj42 es de selecciones; para clubes hace falta otra fuente (p.ej. football-data.co.uk)

### 13.5 Escalar la infraestructura

- Persistir simulaciones en SQLite/Postgres para comparar escenarios en el tiempo en vez de recalcular cada vez
- Exponer el pipeline y el motor de partido como API (FastAPI) para que `app/index.html` consulte datos frescos en vez de tener el JSON embebido y estático
- Compartir la caché de los scrapers (hoy es un archivo local por máquina) si el proyecto pasa de "uso personal" a varios usuarios simultáneos
- Narrador LLM que genere "diarios del mundial" completos por simulación (crónica de cada fase, no solo partido a partido) — pendiente desde la v2, sigue siendo una extensión natural del patrón de §9

---

## 14. Glosario rápido

- **ETL**: Extract-Transform-Load, el pipeline que lleva datos crudos a datos listos para el modelo.
- **xG (expected goals)**: calidad de las ocasiones creadas, medida en goles esperados.
- **Prior / Likelihood / Posterior**: creencia previa / evidencia / creencia actualizada (marco bayesiano).
- **Poisson**: distribución de conteo de eventos raros en un intervalo fijo.
- **Monte Carlo**: estimar probabilidades muestreando muchas veces un proceso aleatorio.
- **Seed**: semilla del generador pseudoaleatorio; fija el "universo" simulado.
- **Fail fast**: fallar temprano y ruidosamente en vez de propagar datos corruptos.
- **Graceful degradation**: el sistema pierde features opcionales, nunca la funcionalidad base.
