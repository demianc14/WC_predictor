# Prompt Fase 4: automatización diaria (GitHub Actions)

Pega esto en una sesión de Claude Code abierta en la raíz de `WC_predictor`. Requisito: Fases 1 a 3 mergeadas. Principios en `docs/PROMPT_AGENTE_FASE1.md`, sección "Principios".

---

## Objetivo

Que el sistema corra solo cada día sin intervención: descarga datos nuevos, genera predicciones de los próximos partidos, guarda esas predicciones antes de que se jueguen, y cuando los partidos terminan registra el resultado real y actualiza las métricas en vivo. Esto produce una evaluación verificable sin posibilidad de fuga de datos, que es lo más valioso del proyecto para el portafolio.

## Tareas

1. **Almacén de predicciones.** Empieza con lo más simple que funcione: SQLite (un archivo) o CSV versionado en el repo. Esquema mínimo: `match_id`, liga, fecha del partido, equipos, fecha y hora en que se hizo la predicción, versión del modelo (hash de commit), probabilidades 1/X/2, resultado real (nulo hasta que se juegue). Regla: una predicción ya guardada **nunca se sobrescribe**; si el modelo cambia, se agrega otra fila con otra versión. Escribe tests de esta regla.
2. **Comando de ciclo.** `python -m src.pipeline.daily` que: (a) actualiza datos, (b) registra resultados de partidos ya jugados, (c) predice los partidos de los próximos días que aún no tienen predicción para la versión actual, (d) recalcula métricas acumuladas en vivo (Brier, RPS, número de partidos) contra las cuotas de cierre cuando existan, (e) exporta el JSON para la web. Cada paso debe poder fallar sin dejar el almacén a medias: si una fuente cae, el ciclo termina con código distinto de cero y **no modifica nada**.
3. **Workflow `daily.yml`.** `schedule` con cron (una vez al día, fuera de horas pico) más `workflow_dispatch` para correrlo a mano. Python fijo, caché de pip, `concurrency` para que no se pisen dos ejecuciones. Que el bot haga commit del almacén y de los JSON solo si hubo cambios, con un mensaje claro y permisos `contents: write` limitados a ese job. Sé respetuoso con football-data.co.uk: una descarga por ejecución, con el caché que ya existe, sin bucles de reintentos agresivos.
4. **Publicación.** Publica `app/` y los JSON en GitHub Pages con un workflow separado o un job de despliegue. La web debe mostrar la fecha de la última actualización y las métricas en vivo (partidos evaluados, Brier del modelo y del mercado) con el tamaño de muestra bien visible. Cambios mínimos a `app/index.html`.
5. **Alertas simples.** Si el ciclo falla, el workflow falla y GitHub avisa por correo. No agregues Slack, n8n ni servicios externos.
6. **Documentación.** Sección nueva en el README: qué hace el ciclo diario, dónde viven las predicciones, cómo correrlo a mano, y cómo se interpreta la métrica en vivo. Marca claramente que con pocas semanas de datos la métrica no es concluyente.

## Criterios de aceptación

- `workflow_dispatch` corre de punta a punta y deja un commit del bot (muéstralo en el PR con el enlace de la ejecución).
- Test de que no se sobrescriben predicciones y de que un fallo a mitad no deja estado parcial.
- CI en verde. PR con lo hecho, lo verificado, lo pendiente (OJO).

## Decisión que NO tomas solo

Si crees que SQLite o CSV se quedan cortos y propones Supabase o Postgres, no lo implementes: escribe en el PR por qué (qué consulta o carga no se puede con lo simple) y espera la aprobación de Demian.

## Fuera de alcance

Docker (Fase 5), n8n, MCP, VPS, y cualquier notificación externa.
