# Prompt Fase 5: Docker y reproducibilidad

Pega esto en una sesión de Claude Code abierta en la raíz de `WC_predictor`. Requisito: Fases 1 a 4 mergeadas. Principios en `docs/PROMPT_AGENTE_FASE1.md`, sección "Principios".

---

## Objetivo

Que cualquier persona pueda reproducir el pipeline, el entrenamiento y la web con un solo comando, sin instalar Python ni dependencias a mano. Es una capa de empaquetado: no cambia el modelo ni los resultados.

## Tareas

1. **Dockerfile.** Imagen base `python:3.11-slim` (o la versión que use CI; deben coincidir). Instala el proyecto con `pip install .` desde `pyproject.toml`. Usuario sin privilegios (no root), `.dockerignore` que deje fuera `.git`, cachés pesadas, `data/cache/statsbomb/shots/` si no hace falta para correr, y archivos temporales. Si el proyecto lo permite, build en dos etapas para una imagen pequeña. No metas claves en la imagen: `ANTHROPIC_API_KEY` es opcional y entra por variable de entorno en tiempo de ejecución.
2. **Comandos documentados.** Un `ENTRYPOINT` o un `Makefile` simple con objetivos como `make test`, `make daily`, `make train`, `make docker-test`. Debe ser posible: `docker build -t wc-predictor .` y luego `docker run --rm wc-predictor pytest` con los mismos resultados que en CI.
3. **Datos como volumen.** Los datos y el almacén de predicciones viven fuera de la imagen (`-v ./data:/app/data`). Documenta qué se monta y por qué.
4. **docker-compose opcional.** Solo si hace falta para servir `app/` localmente (un servidor estático mínimo). Si basta con `python -m http.server`, no agregues compose.
5. **CI.** Agrega un job que construya la imagen y corra `pytest` dentro. No publiques la imagen en ningún registro sin que Demian lo pida.
6. **README.** Sección "Reproducir con Docker" con los 3 o 4 comandos exactos, probados por ti. Si no pudiste probar algo (por ejemplo no hay Docker en tu entorno), dilo y marca OJO en lugar de escribir comandos sin verificar.

## Criterios de aceptación

- `docker build` y `docker run ... pytest` funcionan, con la salida pegada en el PR.
- La imagen no corre como root y no contiene secretos.
- CI en verde. PR con lo hecho, lo verificado, lo pendiente (OJO).

## Fuera de alcance

Orquestación (Kubernetes), despliegue en VPS o nube, publicación de imágenes, y cualquier cambio al modelo.
