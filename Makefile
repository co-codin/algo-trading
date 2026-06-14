PYTHON ?= python3
IMAGE ?= binance-algo-trading:local
PORT ?= 8765
SMOKE_PORT ?= 8766
RUNS_DIR ?= $(CURDIR)/runs
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help test typecheck compile js-check check docker-build docker-run docker-smoke compose-up compose-down clean

help:
	@printf '%s\n' \
		'Targets:' \
		'  make check          Run unit tests, mypy, compileall, and JS syntax check' \
		'  make docker-build   Build the local Docker image' \
		'  make docker-run     Run the UI container on PORT=8765 by default' \
		'  make docker-smoke   Build and smoke-test the UI container on SMOKE_PORT=8766' \
		'  make compose-up     Start the UI with docker compose' \
		'  make compose-down   Stop compose services' \
		'  make clean          Remove Python/tool caches'

test:
	$(PYTHON) -m unittest discover -v

typecheck:
	mypy algo_trading tests

compile:
	$(PYTHON) -m compileall -q algo_trading tests

js-check:
	node --check algo_trading/web/app.js

check: test typecheck compile js-check

docker-build:
	docker build -t $(IMAGE) .

docker-run: docker-build
	mkdir -p "$(RUNS_DIR)"
	docker run --rm -it -p 127.0.0.1:$(PORT):8765 -v "$(RUNS_DIR):/app/runs" $(IMAGE)

docker-smoke: docker-build
	mkdir -p "$(RUNS_DIR)"
	@container=$$(docker run -d -p 127.0.0.1:$(SMOKE_PORT):8765 -v "$(RUNS_DIR):/app/runs" $(IMAGE)); \
	trap 'docker rm -f $$container >/dev/null' EXIT; \
	for attempt in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS "http://127.0.0.1:$(SMOKE_PORT)/api/runs" >/dev/null 2>&1; then \
			curl -fsS "http://127.0.0.1:$(SMOKE_PORT)/api/live-chart?symbol=BTCUSDT&interval=1m&limit=40" >/dev/null; \
			echo "docker smoke passed on http://127.0.0.1:$(SMOKE_PORT)"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	docker logs "$$container"; \
	exit 1

compose-up:
	mkdir -p "$(RUNS_DIR)"
	PORT=$(PORT) $(COMPOSE) up --build

compose-down:
	$(COMPOSE) down

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache
