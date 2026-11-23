# ADR 0007. Cron de respaldo por el retraso medido del cron diario

**Estado:** vigente, con la medición del respaldo pendiente. **Fuente:** bitácora §14.1
("Horario real" y "Cron de respaldo"); PR #22 (T3, 12-nov-2026), commits 976ba63, 8da0dc9 y
b4f36bf; `docs/ROADMAP.md` (T3).

## Contexto

`daily.yml` tenía un cron a las 05:30 UTC, y un partido del mismo día solo se predice antes de
las 10:00 UTC (`CUTOFF_HOUR_UTC`). En 23 corridas (21-oct a 12-nov) GitHub lo arrancó entre
las 09:39 y las 14:08, mediana 11:50: un atraso de 4 h 09 min a 8 h 38 min. Solo 2 corridas
arrancaron antes del corte. No se perdió ningún partido, pero uno reprogramado para el mismo
día se perdería. Comando: `gh run list --workflow daily.yml --limit 60 --json event,createdAt
-q '.[] | select(.event=="schedule") | .createdAt'`.

## Decisión

Se suma un segundo cron a las 00:17 UTC y se conserva el de las 05:30. Con el peor atraso
medido arrancaría a las 08:55, antes del corte. Una segunda corrida el mismo día no agrega ni
cambia filas del almacén (`test_una_segunda_corrida_el_mismo_dia_no_duplica_nada`).

## Alternativa descartada

Mover el cron actual a una hora más temprana, que el ROADMAP proponía como opción. Por qué se
prefirió el respaldo: pendiente de Demian, porque el repo no lo explica.

## Consecuencia

Puede quedar un segundo commit diario del bot, porque `live.json` lleva la hora de
actualización. **OJO:** el horario real del respaldo no está medido, y no se sabe si el atraso
de GitHub se mantiene a otra hora. Falta releerlo con el mismo comando (T3, desde el 20-nov).
Si tampoco arranca antes de las 10:00 UTC, se adelanta o se quita.
