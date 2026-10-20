# Prompt Fase 3: modelo supervisado (1X2)

Pega esto en una sesión de Claude Code abierta en la raíz de `WC_predictor`. Requisito: la Fase 2 está mergeada (las 5 ligas funcionan y hay backtest por liga). Los principios están en `docs/PROMPT_AGENTE_FASE1.md`, sección "Principios".

---

## Objetivo

Construir un modelo de aprendizaje supervisado reproducible que prediga el resultado de un partido de club (1 = local, X = empate, 2 = visitante) y compararlo de forma honesta contra (a) el modelo Dixon-Coles actual de `src/clubs/` y (b) las cuotas de cierre sin margen. La meta realista es igualar al mercado con buena calibración. Superarlo en una temporada completa es muy improbable (el README ya muestra 0.623 contra 0.608 en 2025-26), así que no prometas lo contrario.

## Diseño

1. **Dataset.** Una fila por partido, construida solo con información disponible antes del pitazo inicial. Guarda la fecha y el id del partido. Escribe un test que verifique que ninguna feature de un partido usa datos de ese partido ni posteriores (test anti-fuga).
2. **Features candidatas** (empieza pocas, agrega una por vez y mide):
   - ataque y defensa del modelo Maher/Dixon-Coles calculados solo con partidos anteriores,
   - diferencia de ELO de clubes si decides calcularlo (impleméntalo simple y con test),
   - forma de los últimos N partidos (goles a favor y en contra, puntos),
   - días de descanso,
   - localía,
   - xG reciente cuando la liga lo tenga; si no, déjalo fuera, no lo imputes inventando.
   **No uses cuotas como feature.** Solo como benchmark.
3. **Modelos**, en este orden:
   - baseline trivial: frecuencias históricas de 1/X/2,
   - regresión logística multinomial (scikit-learn),
   - gradient boosting (LightGBM o `HistGradientBoostingClassifier` de scikit-learn; prefiere el segundo si no hay diferencia, porque agrega cero dependencias),
   - opcional: stacking simple de la logística con las probabilidades del Dixon-Coles como feature.
   Agrega las dependencias nuevas a `pyproject.toml` con versiones mínimas y justifica cada una en el PR.
4. **Validación walk-forward.** Reentrena por bloques temporales (por ejemplo cada semana o mes de temporada) y predice el bloque siguiente. Nada de `train_test_split` aleatorio ni cross-validation que mezcle fechas. Para los hiperparámetros usa validación temporal anidada o fija un conjunto de temporadas de validación distinto al de test final, y deja documentado cuál es cuál.
5. **Métricas**, siempre sobre la misma muestra para todos los modelos y el mercado: Brier 1X2, RPS, log-loss, y número de partidos. Agrega intervalos con bootstrap al 95%. Incluye una curva de calibración por clase y una nota sobre empates (el Dixon-Coles actual de selecciones subestima empates; revisa si aquí también).
6. **Reproducibilidad.** Semilla fija, comando único (`python -m src.ml.train --leagues all`), artefactos guardados con la fecha y el hash del dataset, y un reporte `docs/RESULTADOS_ML.md` generado por código, no escrito a mano.

## Estructura sugerida

`src/ml/` con `dataset.py`, `features.py`, `models.py`, `evaluate.py`, `train.py`. Tests en `tests/test_ml_*.py`, herméticos y con datos de juguete.

## Criterios de aceptación

- Tabla en el reporte con modelo, liga, temporada, n, Brier, RPS y log-loss, para: baseline, logística, boosting, Dixon-Coles y mercado.
- Test anti-fuga pasando.
- Una conclusión honesta de una o dos frases: si el supervisado ayuda o no, y con qué incertidumbre. Si no mejora al Dixon-Coles, el resultado igual es válido y se documenta.
- CI en verde. PR con lo hecho, lo verificado y lo pendiente (marca OJO).

## Fuera de alcance

Apuestas o estrategias de valor, redes neuronales, ajuste fino masivo de hiperparámetros, y cualquier uso de un LLM para predecir. "El LLM propone, el código verifica": aquí el LLM no entra en la predicción.
