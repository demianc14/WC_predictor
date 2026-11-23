# ADR 0002. Las cuotas de cierre nunca son feature

**Estado:** vigente. **Fuente:** bitácora §2.1 (principio 5), §12.4 y §13.1.

## Contexto

Las cuotas de cierre son el mejor predictor disponible: en el backtest 2025-26 le ganan al
modelo en las cinco ligas (§12.4). El proyecto quiere saber si su modelo alcanza al mercado.

## Decisión

Las cuotas de cierre solo se usan como benchmark, sin margen (no-vig), sobre la misma muestra
que el modelo y la base. Nunca entran como feature. `test_las_cuotas_nunca_son_feature` lo
hace cumplir.

## Alternativa descartada

Usar las cuotas como feature del supervisado. Se descartó porque, según la bitácora §2.1, "el
modelo aprendería a copiar al mercado y la comparación no diría nada".

## Consecuencia

La comparación modelo contra mercado mide algo real, y el resultado es negativo: el mercado
gana (§12.4, §13.3). Por eso la web muestra dónde discrepa el modelo y nunca "valor". La
Champions queda sin benchmark de mercado, porque football-data no publica sus cuotas (§12.5).
