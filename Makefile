# Atajos del proyecto. Sin Docker: make test / make daily / make train.
# Con Docker: make docker-build y después make docker-test / docker-daily / docker-serve.

PY ?= python
IMAGE ?= wc-predictor
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

docker-build:
	docker build -t $(IMAGE) \
		--build-arg MODEL_VERSION=$$(git rev-parse --short HEAD:src/clubs) \
		--build-arg GIT_COMMIT=$$(git rev-parse --short HEAD) .

docker-test:
	docker run --rm $(IMAGE) pytest -q

docker-daily:
	$(DOCKER_RUN) -v "$$PWD/app:/app/app" $(IMAGE) python -m src.pipeline.daily

docker-train:
	$(DOCKER_RUN) -v "$$PWD/docs:/app/docs" $(IMAGE) python -m src.ml.train --leagues all

docker-serve:
	docker run --rm -p 8000:8000 $(IMAGE) python -m http.server 8000 --directory app
