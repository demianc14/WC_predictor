# Atajos del proyecto. Sin Docker: make test / make daily / make train.
# Con Docker: make docker-build y después make docker-test / docker-daily / docker-serve.
# (docker-test y docker-train usan la imagen :ml; docker-daily y docker-serve, la liviana)

PY ?= python
IMAGE ?= wc-predictor
# hilos de OpenMP para hgb en Docker: con todas las CPU visibles se traba (bitácora §14.3)
OMP ?= 4
# los datos viven fuera de la imagen; corre con tu usuario para que los archivos sean tuyos
DOCKER_RUN = docker run --rm --user $$(id -u):$$(id -g) -v "$$PWD/data:/app/data"

.PHONY: test lint daily train leagues serve docker-build docker-test docker-daily docker-train docker-serve

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

daily:
	$(PY) -m src.pipeline.daily

train:
	$(PY) -m src.ml.train --leagues all

leagues:
	$(PY) -m src.clubs.run

serve:
	$(PY) -m http.server 8000 --directory app

BUILD_ARGS = --build-arg MODEL_VERSION=$$(git rev-parse --short HEAD:src/clubs) \
	--build-arg GIT_COMMIT=$$(git rev-parse --short HEAD)

# dos imágenes: $(IMAGE) (ciclo diario y web, liviana) y $(IMAGE):ml (entrenamiento y tests)
docker-build:
	docker build --target app -t $(IMAGE) $(BUILD_ARGS) .
	docker build --target ml -t $(IMAGE):ml $(BUILD_ARGS) .

docker-test:
	docker run --rm $(IMAGE):ml pytest -q

docker-daily:
	$(DOCKER_RUN) -v "$$PWD/app:/app/app" $(IMAGE) python -m src.pipeline.daily

docker-train:
	$(DOCKER_RUN) -e OMP_NUM_THREADS=$(OMP) -v "$$PWD/docs:/app/docs" $(IMAGE):ml \
		python -m src.ml.train --leagues all

docker-serve:
	docker run --rm -p 8000:8000 $(IMAGE) python -m http.server 8000 --directory app
