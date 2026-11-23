# Decisiones de arquitectura (ADR)

Un ADR es un registro corto de una decisión: contexto, decisión, alternativa descartada y
consecuencia. Sale de la [bitácora](../PROYECTO_OBSIDIAN.md) y del historial de git, y cita su
fuente. Lo que el repo no explica queda marcado "pendiente de Demian". `tests/test_adr.py`
verifica que cada ADR tenga las cuatro secciones y que el README principal lo enlace.

| ADR | Decisión |
|---|---|
| [0001](0001-walk-forward.md) | Walk-forward sin fuga de datos |
| [0002](0002-cuotas-nunca-feature.md) | Las cuotas de cierre nunca son feature |
| [0003](0003-almacen-solo-agregar.md) | Almacén solo-para-agregar, auditado por git |
| [0004](0004-csv-versionado.md) | CSV y JSON versionados en vez de una base de datos |
| [0005](0005-supervisado-no-adoptado.md) | El modelo supervisado no reemplaza al Dixon-Coles |
| [0006](0006-empates-ucl-rechazado.md) | Corrección de empates de la Champions rechazada con un umbral fijado antes |
| [0007](0007-cron-respaldo.md) | Cron de respaldo por el retraso medido del cron diario |
