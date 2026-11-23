# ADR 0001. Walk-forward sin fuga de datos

**Estado:** vigente. **Fuente:** bitácora §2.1 (principio 4), §12.4, §13.1 y §13.2; brief de la fase 1.

## Contexto

Un modelo de fútbol se evalúa prediciendo partidos. Si el entrenamiento ve partidos posteriores
a los que predice, o features calculadas con ellos, la métrica sale mejor de lo que el modelo
rinde de verdad (fuga de datos).

## Decisión

Toda evaluación es walk-forward: se entrena con el pasado y se predice el bloque siguiente, en
orden. El Dixon-Coles se reajusta cada lunes (§12.4), el supervisado se entrena mes a mes con
meses anteriores (§13.2) y las features solo usan partidos de días anteriores (§13.1). Lo
verifican `test_walk_forward_entrena_solo_con_meses_anteriores`,
`test_cambiar_el_futuro_no_mueve_las_features_del_pasado` y
`test_partidos_del_mismo_dia_no_se_ven_entre_si`.

## Alternativa descartada

Pendiente de Demian. El repo fija la regla ("nunca se mezclan fechas entre train y test") pero
no nombra qué esquema de validación se descartó ni por qué, por ejemplo una validación cruzada
con partidos mezclados al azar.

## Consecuencia

Las cifras de los backtests son las que el modelo habría tenido en su momento. El costo es más
cómputo (un reajuste por semana o por mes) y muestras de validación y test más chicas, porque
las primeras temporadas solo sirven de historia previa.
