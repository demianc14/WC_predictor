# Dos imágenes desde el mismo archivo (misma versión de Python que CI):
#   app (default): ciclo diario, web, ligas y partido y cuotas; solo el núcleo
#   ml:            entrenamiento del modelo supervisado y la suite de tests
# Los datos viven fuera: se montan en /app/data.

FROM python:3.11-slim AS py
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# ── dependencias, cada imagen en su venv; pip no viaja a la imagen final ──
FROM py AS deps-app
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && rm -rf /opt/venv/bin/pip* /opt/venv/lib/python3.11/site-packages/pip*

FROM py AS deps-ml
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[ml,test]" && rm -rf /opt/venv/bin/pip* /opt/venv/lib/python3.11/site-packages/pip*

# ── base común: usuario sin privilegios y versión del modelo ──
FROM python:3.11-slim AS runtime
# sin .git en la imagen: la versión del modelo y el commit entran al construir
# (make docker-build los toma de git) y daily.py / train.py los leen de aquí
ARG MODEL_VERSION=desconocida
ARG GIT_COMMIT=desconocido
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WCP_MODEL_VERSION=$MODEL_VERSION \
    WCP_COMMIT=$GIT_COMMIT
RUN useradd --create-home --uid 10001 app && mkdir /app && chown app:app /app
WORKDIR /app
EXPOSE 8000

FROM runtime AS ml
COPY --from=deps-ml /opt/venv /opt/venv
COPY --chown=app:app . .
USER app
CMD ["pytest", "-q"]

FROM runtime AS app
COPY --from=deps-app /opt/venv /opt/venv
COPY --chown=app:app . .
USER app
CMD ["python", "-m", "src.pipeline.daily"]
