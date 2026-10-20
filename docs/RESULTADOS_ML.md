# Resultados del modelo supervisado (1X2, clubes)

> Generado por `python -m src.ml.train --leagues all`. No editar a mano.

- Fecha: 2026-10-20 · commit `84fdeb2` · huella del dataset `0a9df3af955e` · semilla 2627
- Ligas: Premier League, LaLiga, Bundesliga, Serie A, Ligue 1
- Partidos jugados con features: 11079
- Temporadas: historia previa 2019-20; entrenamiento 2020-21, 2021-22, 2022-23; validación 2023-24, 2024-25; test 2025-26, 2026-27
- Versiones: scikit-learn 1.9.1, numpy 2.4.6, pandas 3.0.3
- Artefactos: `data/ml/runs/2026-10-20_0a9df3af955e/` (predicciones, métricas, modelos)

## Conclusión

El mejor supervisado en test, «Logística + Dixon-Coles» (RPS 0.2019), no se distingue del Dixon-Coles (diferencia de RPS -0.0008, IC 95% -0.0019 a +0.0003) y queda por detrás del mercado (diferencia +0.0048, IC 95% +0.0027 a +0.0069).

## Test: todas las ligas juntas

Misma muestra para todos: 2097 partidos de test con Dixon-Coles y cuotas de cierre. Brier (0 a 2), RPS (0 a 1) y log-loss: menor es mejor. Entre corchetes, el intervalo bootstrap al 95%.

| Modelo | n | Brier | RPS | Log-loss |
|---|---|---|---|---|
| Base (frecuencias 1X2) | 2097 | 0.6480 [0.6414, 0.6542] | 0.2294 [0.2265, 0.2324] | 1.0716 [1.0620, 1.0809] |
| Logística sin Dixon-Coles | 2097 | 0.5901 [0.5765, 0.6036] | 0.2019 [0.1960, 0.2075] | 0.9914 [0.9718, 1.0111] |
| Logística + Dixon-Coles | 2097 | 0.5900 [0.5769, 0.6033] | 0.2019 [0.1961, 0.2073] | 0.9908 [0.9721, 1.0094] |
| Gradient boosting | 2097 | 0.5931 [0.5794, 0.6066] | 0.2031 [0.1973, 0.2086] | 0.9954 [0.9756, 1.0148] |
| Dixon-Coles | 2097 | 0.5920 [0.5797, 0.6039] | 0.2027 [0.1977, 0.2076] | 0.9936 [0.9760, 1.0108] |
| Mercado (cierre, sin margen) | 2097 | 0.5796 [0.5661, 0.5922] | **0.1970 [0.1916, 0.2022]** | 0.9740 [0.9551, 0.9920] |

### Diferencias pareadas (negativo = el primero es mejor)

| Comparación | ΔRPS [IC 95%] | ΔLog-loss [IC 95%] |
|---|---|---|
| Logística sin Dixon-Coles − Dixon-Coles | -0.0008 [-0.0025, 0.0010] | -0.0022 [-0.0082, 0.0042] |
| Logística sin Dixon-Coles − Mercado (cierre, sin margen) | 0.0049 [0.0026, 0.0073] | 0.0174 [0.0098, 0.0253] |
| Logística + Dixon-Coles − Dixon-Coles | -0.0008 [-0.0019, 0.0003] | -0.0028 [-0.0068, 0.0010] |
| Logística + Dixon-Coles − Mercado (cierre, sin margen) | 0.0048 [0.0027, 0.0069] | 0.0168 [0.0100, 0.0234] |
| Gradient boosting − Dixon-Coles | 0.0004 [-0.0011, 0.0018] | 0.0018 [-0.0042, 0.0077] |
| Gradient boosting − Mercado (cierre, sin margen) | 0.0060 [0.0036, 0.0084] | 0.0213 [0.0132, 0.0296] |
| Dixon-Coles − Mercado (cierre, sin margen) | 0.0056 [0.0035, 0.0078] | 0.0196 [0.0128, 0.0263] |

## Test por liga y temporada

| Liga | Temporada | Modelo | n | Brier | RPS | Log-loss |
|---|---|---|---|---|---|---|
| Bundesliga | 2025-26 | Base (frecuencias 1X2) | 306 | 0.6480 | 0.2315 | 1.0710 |
| Bundesliga | 2025-26 | Logística sin Dixon-Coles | 306 | 0.5663 | 0.1922 | 0.9583 |
| Bundesliga | 2025-26 | Logística + Dixon-Coles | 306 | 0.5677 | 0.1926 | 0.9611 |
| Bundesliga | 2025-26 | Gradient boosting | 306 | 0.5677 | 0.1927 | 0.9614 |
| Bundesliga | 2025-26 | Dixon-Coles | 306 | 0.5748 | 0.1955 | 0.9725 |
| Bundesliga | 2025-26 | Mercado (cierre, sin margen) | 306 | **0.5618** | **0.1901** | **0.9510** |
| Bundesliga | 2026-27 | Base (frecuencias 1X2) | 54 | 0.6225 | 0.2290 | 1.0343 |
| Bundesliga | 2026-27 | Logística sin Dixon-Coles | 54 | 0.5833 | 0.2077 | 0.9715 |
| Bundesliga | 2026-27 | Logística + Dixon-Coles | 54 | 0.5831 | 0.2064 | 0.9733 |
| Bundesliga | 2026-27 | Gradient boosting | 54 | 0.5910 | 0.2079 | 0.9948 |
| Bundesliga | 2026-27 | Dixon-Coles | 54 | **0.5726** | **0.2033** | **0.9574** |
| Bundesliga | 2026-27 | Mercado (cierre, sin margen) | 54 | 0.5908 | 0.2115 | 0.9845 |
| Premier League | 2025-26 | Base (frecuencias 1X2) | 380 | 0.6569 | 0.2281 | 1.0857 |
| Premier League | 2025-26 | Logística sin Dixon-Coles | 380 | 0.6260 | 0.2125 | 1.0402 |
| Premier League | 2025-26 | Logística + Dixon-Coles | 380 | 0.6246 | 0.2122 | 1.0379 |
| Premier League | 2025-26 | Gradient boosting | 380 | 0.6295 | 0.2139 | 1.0428 |
| Premier League | 2025-26 | Dixon-Coles | 380 | 0.6230 | 0.2120 | 1.0361 |
| Premier League | 2025-26 | Mercado (cierre, sin margen) | 380 | **0.6077** | **0.2045** | **1.0118** |
| Premier League | 2026-27 | Base (frecuencias 1X2) | 70 | 0.6636 | 0.2285 | 1.0952 |
| Premier League | 2026-27 | Logística sin Dixon-Coles | 70 | 0.6087 | 0.2022 | 1.0147 |
| Premier League | 2026-27 | Logística + Dixon-Coles | 70 | 0.6012 | 0.1993 | 1.0047 |
| Premier League | 2026-27 | Gradient boosting | 70 | 0.5994 | 0.1984 | 1.0016 |
| Premier League | 2026-27 | Dixon-Coles | 70 | **0.5971** | **0.1968** | **0.9988** |
| Premier League | 2026-27 | Mercado (cierre, sin margen) | 70 | 0.6008 | 0.1982 | 1.0055 |
| Ligue 1 | 2025-26 | Base (frecuencias 1X2) | 306 | 0.6447 | 0.2298 | 1.0665 |
| Ligue 1 | 2025-26 | Logística sin Dixon-Coles | 306 | 0.5969 | 0.2074 | 0.9992 |
| Ligue 1 | 2025-26 | Logística + Dixon-Coles | 306 | 0.5974 | 0.2070 | 0.9993 |
| Ligue 1 | 2025-26 | Gradient boosting | 306 | 0.5987 | 0.2073 | 1.0013 |
| Ligue 1 | 2025-26 | Dixon-Coles | 306 | 0.5973 | 0.2067 | 0.9991 |
| Ligue 1 | 2025-26 | Mercado (cierre, sin margen) | 306 | **0.5820** | **0.2003** | **0.9755** |
| Ligue 1 | 2026-27 | Base (frecuencias 1X2) | 63 | 0.6458 | 0.2321 | 1.0675 |
| Ligue 1 | 2026-27 | Logística sin Dixon-Coles | 63 | 0.5922 | 0.2061 | 0.9900 |
| Ligue 1 | 2026-27 | Logística + Dixon-Coles | 63 | 0.5905 | 0.2055 | 0.9901 |
| Ligue 1 | 2026-27 | Gradient boosting | 63 | 0.5832 | 0.2029 | 0.9802 |
| Ligue 1 | 2026-27 | Dixon-Coles | 63 | 0.5904 | 0.2055 | 0.9926 |
| Ligue 1 | 2026-27 | Mercado (cierre, sin margen) | 63 | **0.5788** | **0.1998** | **0.9757** |
| Serie A | 2025-26 | Base (frecuencias 1X2) | 380 | 0.6592 | 0.2332 | 1.0870 |
| Serie A | 2025-26 | Logística sin Dixon-Coles | 380 | 0.5950 | 0.2014 | 0.9979 |
| Serie A | 2025-26 | Logística + Dixon-Coles | 380 | 0.5956 | 0.2019 | 0.9988 |
| Serie A | 2025-26 | Gradient boosting | 380 | 0.6006 | 0.2046 | 1.0075 |
| Serie A | 2025-26 | Dixon-Coles | 380 | 0.5980 | 0.2030 | 1.0011 |
| Serie A | 2025-26 | Mercado (cierre, sin margen) | 380 | **0.5830** | **0.1961** | **0.9784** |
| Serie A | 2026-27 | Base (frecuencias 1X2) | 70 | 0.6358 | 0.2421 | 1.0516 |
| Serie A | 2026-27 | Logística sin Dixon-Coles | 70 | 0.5499 | 0.2005 | 0.9385 |
| Serie A | 2026-27 | Logística + Dixon-Coles | 70 | 0.5553 | 0.2032 | 0.9459 |
| Serie A | 2026-27 | Gradient boosting | 70 | **0.5373** | **0.1963** | **0.9219** |
| Serie A | 2026-27 | Dixon-Coles | 70 | 0.5632 | 0.2075 | 0.9574 |
| Serie A | 2026-27 | Mercado (cierre, sin margen) | 70 | 0.5421 | 0.1990 | 0.9246 |
| LaLiga | 2025-26 | Base (frecuencias 1X2) | 380 | 0.6328 | 0.2237 | 1.0503 |
| LaLiga | 2025-26 | Logística sin Dixon-Coles | 380 | 0.5766 | 0.1990 | 0.9784 |
| LaLiga | 2025-26 | Logística + Dixon-Coles | 380 | 0.5760 | 0.1988 | 0.9743 |
| LaLiga | 2025-26 | Gradient boosting | 380 | 0.5850 | 0.2021 | 0.9864 |
| LaLiga | 2025-26 | Dixon-Coles | 380 | 0.5787 | 0.1997 | 0.9767 |
| LaLiga | 2025-26 | Mercado (cierre, sin margen) | 380 | **0.5717** | **0.1958** | **0.9650** |
| LaLiga | 2026-27 | Base (frecuencias 1X2) | 88 | 0.6530 | 0.2246 | 1.0789 |
| LaLiga | 2026-27 | Logística sin Dixon-Coles | 88 | 0.5512 | 0.1804 | 0.9338 |
| LaLiga | 2026-27 | Logística + Dixon-Coles | 88 | 0.5516 | 0.1809 | 0.9346 |
| LaLiga | 2026-27 | Gradient boosting | 88 | 0.5544 | 0.1814 | 0.9396 |
| LaLiga | 2026-27 | Dixon-Coles | 88 | 0.5622 | 0.1832 | 0.9526 |
| LaLiga | 2026-27 | Mercado (cierre, sin margen) | 88 | **0.5382** | **0.1739** | **0.9128** |

## Calibración

![Curvas de calibración](ml/calibracion.svg)

Tramos de 0.1 con al menos 15 partidos. Sobre la diagonal punteada, el modelo dice lo que después pasa.

### Empates

| Modelo | P(X) media predicha | Empates reales |
|---|---|---|
| Base (frecuencias 1X2) | 0.254 | 0.252 |
| Logística sin Dixon-Coles | 0.253 | 0.252 |
| Logística + Dixon-Coles | 0.254 | 0.252 |
| Gradient boosting | 0.255 | 0.252 |
| Dixon-Coles | 0.248 | 0.252 |
| Mercado (cierre, sin margen) | 0.252 | 0.252 |

## Validación: elección de hiperparámetros

Walk-forward mensual en 2023-24 y 2024-25 (filas con Dixon-Coles). En cada familia gana el de menor log-loss; el test no se usa para elegir.

| Candidato | n | Brier | RPS | Log-loss |
|---|---|---|---|---|
| ✓ base | 3504 | 0.6521 | 0.2307 | 1.0769 |
| logit_basic (C=0.01) | 3504 | 0.5855 | 0.1981 | 0.9816 |
| ✓ logit_basic (C=0.1) | 3504 | 0.5855 | 0.1981 | 0.9815 |
| logit_basic (C=1.0) | 3504 | 0.5856 | 0.1981 | 0.9815 |
| ✓ logit_dc (C=0.01) | 3504 | 0.5847 | 0.1979 | 0.9806 |
| logit_dc (C=0.1) | 3504 | 0.5848 | 0.1979 | 0.9807 |
| logit_dc (C=1.0) | 3504 | 0.5849 | 0.1980 | 0.9808 |
| ✓ hgb (learning_rate=0.03, max_leaf_nodes=8, min_samples_leaf=40) | 3504 | 0.5922 | 0.2007 | 0.9927 |
| hgb (learning_rate=0.03, max_leaf_nodes=8, min_samples_leaf=120) | 3504 | 0.5924 | 0.2007 | 0.9937 |
| hgb (learning_rate=0.03, max_leaf_nodes=16, min_samples_leaf=40) | 3504 | 0.5972 | 0.2022 | 1.0020 |
| hgb (learning_rate=0.03, max_leaf_nodes=16, min_samples_leaf=120) | 3504 | 0.5977 | 0.2026 | 1.0026 |
| hgb (learning_rate=0.06, max_leaf_nodes=8, min_samples_leaf=40) | 3504 | 0.5982 | 0.2025 | 1.0023 |
| hgb (learning_rate=0.06, max_leaf_nodes=8, min_samples_leaf=120) | 3504 | 0.5973 | 0.2024 | 1.0027 |
| hgb (learning_rate=0.06, max_leaf_nodes=16, min_samples_leaf=40) | 3504 | 0.6077 | 0.2054 | 1.0205 |
| hgb (learning_rate=0.06, max_leaf_nodes=16, min_samples_leaf=120) | 3504 | 0.6093 | 0.2063 | 1.0229 |
| Dixon-Coles | 3504 | 0.5853 | 0.1985 | 0.9819 |

### Ablación (logística, features agregadas de a una, validación)

| Features | n | Brier | RPS | Log-loss |
|---|---|---|---|---|
| ELO | 3504 | 0.5861 | 0.1983 | 0.9828 |
| + forma | 3504 | 0.5855 | 0.1980 | 0.9817 |
| + descanso | 3504 | 0.5855 | 0.1979 | 0.9817 |
| + liga | 3504 | 0.5855 | 0.1981 | 0.9816 |
| + Dixon-Coles | 3504 | 0.5847 | 0.1979 | 0.9806 |

## Método y límites

- **Sin fuga de datos**: cada fila usa solo partidos de días anteriores; lo verifica `tests/test_ml_features.py` cambiando resultados futuros y comprobando que las features no se mueven. El walk-forward entrena solo con meses anteriores al que predice.
- **Las cuotas no son feature**: solo se usan como benchmark.
- **Features**: ELO de clubes (K=20, +60 de localía), forma de los últimos 5 (puntos, goles a favor y en contra), días de descanso (tope 21), liga y, en los modelos con Dixon-Coles, sus probabilidades y λ reajustados cada lunes.
- **No entran**: xG (solo existe desde 2026-27), partidos de copa y de Europa (el descanso solo ve la liga), lesiones y alineaciones.
- **2020-21 se jugó mayormente sin público**: la ventaja de local de ese año es atípica y forma parte del entrenamiento.
- **2026-27 está en curso**: su muestra es chica y sus métricas se mueven cada semana.
