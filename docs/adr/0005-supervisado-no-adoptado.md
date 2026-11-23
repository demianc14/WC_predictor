# ADR 0005. El modelo supervisado no reemplaza al Dixon-Coles

**Estado:** vigente. **Fuente:** bitácora §13.3 y §13.5; `docs/RESULTADOS_ML.md` (generado por
`python -m src.ml.train --leagues all`).

## Contexto

La fase 3 preguntó si un clasificador 1X2 con features (ELO, forma, descanso, liga y las
probabilidades del Dixon-Coles) mejora al Dixon-Coles. El test son 2.098 partidos de las cinco
ligas, la misma muestra para todos los modelos.

## Decisión

El ciclo diario y la web siguen con el Dixon-Coles. Logística + Dixon-Coles contra Dixon-Coles
da ΔRPS −0.0008, IC 95% por bootstrap pareado [−0.0019, +0.0003]: el intervalo incluye el
cero, así que la diferencia no se distingue del ruido. Contra el mercado queda peor: ΔRPS
+0.0048 [+0.0026, +0.0070].

## Alternativa descartada

Adoptar la logística o el gradient boosting. Ninguno se distingue del Dixon-Coles en test, y
sumar Champions y Europa League al descanso tampoco cierra la brecha (§13.5).

## Consecuencia

`src/ml/` queda como un resultado negativo bien medido, con reporte reproducible. Las
predicciones del almacén salen del Dixon-Coles. El xG como feature queda para cuando 2026-27
tenga muestra (ROADMAP, "Después").
