# ADR 0004. CSV y JSON versionados en vez de una base de datos

**Estado:** vigente. **Fuente:** brief de la fase 1 (fuera de alcance), brief de la fase 4
(paso 1 y nota final), `docs/ROADMAP.md` ("Después") y bitácora §14.1.

## Contexto

El ciclo diario necesita guardar predicciones, resultados y métricas, y publicarlos en una web
estática (GitHub Pages). El brief de la fase 1 dejó la base de datos para una fase posterior, y
el de la fase 4 pidió "lo más simple que funcione: SQLite (un archivo) o CSV versionado".

## Decisión

El almacén es un CSV versionado en el repo (`data/predictions/predicciones.csv`) y las salidas
son JSON en `data/processed/`, también versionados, que la web lee. Las fuentes descargadas
van en `data/cache/` para reproducir las cifras sin red.

## Alternativa descartada

Una base de datos (SQLite, o Supabase y Postgres). El brief de la fase 4 pedía justificar
"qué consulta o carga no se puede con lo simple" antes de proponer Postgres o Supabase, y el
ROADMAP dice que "hoy el CSV versionado es más auditable". Por qué se eligió CSV y no SQLite,
que el brief también permitía: pendiente de Demian, más allá de lo de "más auditable".

## Consecuencia

Cada cambio del almacén es un diff de git legible y auditable (ADR 0003), y la web no
necesita un servidor. Una base de datos o una API queda como infraestructura "solo si hace
falta" en el ROADMAP.
