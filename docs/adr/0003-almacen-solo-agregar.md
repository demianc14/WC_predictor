# ADR 0003. Almacén solo-para-agregar, auditado por git

**Estado:** vigente. **Fuente:** brief de la fase 4 (paso 1), bitácora §14.1, commits
29b5f74 (20-oct-2026) y a3b3685 (PR #27, 22-nov-2026), docstring de `src/pipeline/audit.py`.

## Contexto

Las métricas en vivo solo valen si cada predicción existía antes del partido. Un almacén que se
puede reescribir no lo prueba: una fila podría corregirse después de conocer el resultado.

## Decisión

`data/predictions/predicciones.csv` tiene una fila por (partido, versión del modelo) y una
predicción guardada nunca se sobrescribe. `store.save` compara contra el archivo en disco y se
niega a borrar, cambiar una probabilidad o contradecir un resultado. Solo se completan después
el resultado y la cuota de cierre. Si el modelo cambia, entra otra fila con otra versión.
Desde la PR #27, `python -m src.pipeline.audit` recorre cada commit de `main` que tocó el
archivo y exige la misma regla entre versiones consecutivas. Corre en CI y antes de cada commit
del bot.

## Alternativa descartada

Confiar solo en `store.save`. La auditoría existe porque ese chequeo compara contra el disco:
"una edición a mano seguida de un `save` pasa sin error" (`src/pipeline/audit.py`).

## Consecuencia

El historial de git del archivo es la prueba pública de que cada fila existía antes del
partido. Límite escrito en el código: una reescritura del propio historial (force-push) no se
ve desde la auditoría. Las métricas en vivo usan la primera predicción de cada partido.
