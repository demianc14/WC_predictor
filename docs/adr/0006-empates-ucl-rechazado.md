# ADR 0006. Corrección de empates de la Champions rechazada con un umbral fijado antes

**Estado:** vigente. **Fuente:** bitácora §12.5; PR #23 (T1, 14-nov-2026), commits 4a712ee
(regla), 53a36a8 (c congelado) y d2b21e6 (test); `docs/ucl/validacion.json` y
`docs/ucl/test.json`.

## Contexto

El Dixon-Coles conjunto sobrestima el empate en la Champions: predice 22,2% y hubo 15,7% en el
test (2024-25 y 2025-26, n = 376). Los ajustes probados antes se eligieron mirando el test, así
que no servían como candidatos.

## Decisión

No se adopta la corrección. La regla se escribió en un commit propio antes de tocar el test
(`backtest.adopt`): adoptar solo si el log-loss del test mejora más de 0,012 y el IC pareado
excluye el cero. El único candidato, P(X) × c, se eligió en validación (UCL 2021-22 a 2023-24,
n = 372): c = 0,90, congelado antes del test. En el test, corrido una sola vez, dio
Δlog-loss −0.0059 [−0.0098, −0.0020]: el IC excluye el cero, pero la mejora no llega a 0,012.

## Alternativa descartada

Adoptar c = 0,90 porque el IC excluye el cero, o bajar el umbral después de ver el resultado.
La bitácora dice que cambiar la regla después de ver el test "sería ajustarla al resultado".

## Consecuencia

`src/europe/run.py` no cambia y el sesgo del empate queda como limitación (§15, punto 5). El
comando del test se niega a correr de nuevo. Si el 15,7% viene del formato de 36 clubes o es
ruido sigue abierto: se volverá a medir con la Champions 2026-27, sin reabrir este test.
