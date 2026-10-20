# Imagen reproducible del predictor: pipeline, entrenamiento, tests y web.
# Misma versión de Python que CI. Los datos viven fuera (volumen en /app/data).

# ── 1. dependencias en un venv aparte ──
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[test]"

# ── 2. imagen final: venv + código, sin compiladores ni caché de pip ──
FROM python:3.11-slim
# sin .git en la imagen: la versión del modelo y el commit entran al construir
# (make docker-build los toma de git) y src/pipeline/daily.py los lee de aquí
ARG MODEL_VERSION=desconocida
ARG GIT_COMMIT=desconocido
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WCP_MODEL_VERSION=$MODEL_VERSION \
    WCP_COMMIT=$GIT_COMMIT
RUN useradd --create-home --uid 10001 app && mkdir /app && chown app:app /app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app . .
USER app
EXPOSE 8000
# cualquier comando del proyecto: docker run --rm wc-predictor python -m src.clubs.run
CMD ["pytest", "-q"]
