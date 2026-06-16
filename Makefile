PYTHON ?= python3
NPM ?= npm
IMAGE ?= binance-algo-trading:local
PORT ?= 8765
SMOKE_PORT ?= 8766
RUNS_DIR ?= $(CURDIR)/runs
HISTORICAL_DATA_DIR ?= $(CURDIR)/historical_data
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help lint lint-python test typecheck compile frontend-install frontend-build frontend-check js-check check docker-build docker-run docker-smoke compose-up compose-down clean

help:
	@printf '%s\n' \
		'Targets:' \
		'  make lint           Run Ruff Python lint checks' \
		'  make check          Run unit tests, mypy, compileall, and Vue build check' \
		'  make frontend-build Build the Vue frontend into algo_trading/web/dist' \
		'  make docker-build   Build the local Docker image' \
		'  make docker-run     Run the UI container on PORT=8765 by default' \
		'  make docker-smoke   Build and smoke-test the UI container on SMOKE_PORT=8766' \
		'  make compose-up     Start the UI with docker compose' \
		'  make compose-down   Stop compose services' \
		'  make clean          Remove Python/tool caches'

lint: lint-python

lint-python:
	$(PYTHON) -m ruff check algo_trading tests

test:
	$(PYTHON) -m unittest discover -v

typecheck:
	mypy algo_trading tests

compile:
	$(PYTHON) -m compileall -q algo_trading tests

frontend-install:
	$(NPM) ci

frontend-build:
	$(NPM) run frontend:build

frontend-check:
	$(NPM) run frontend:check

js-check: frontend-check

check: lint test typecheck compile frontend-check

docker-build:
	docker build -t $(IMAGE) .

docker-run: docker-build
	mkdir -p "$(RUNS_DIR)" "$(HISTORICAL_DATA_DIR)"
	docker run --rm -it --user "$$(id -u):$$(id -g)" -p 127.0.0.1:$(PORT):8765 -v "$(RUNS_DIR):/app/runs" -v "$(HISTORICAL_DATA_DIR):/app/historical_data" $(IMAGE)

docker-smoke: docker-build
	mkdir -p "$(RUNS_DIR)" "$(HISTORICAL_DATA_DIR)"
	@container=$$(docker run -d --user "$$(id -u):$$(id -g)" -p 127.0.0.1:$(SMOKE_PORT):8765 -v "$(RUNS_DIR):/app/runs" -v "$(HISTORICAL_DATA_DIR):/app/historical_data" $(IMAGE)); \
	cookie_jar=$$(mktemp); \
		trap 'rm -f "$$cookie_jar"; docker rm -f $$container >/dev/null' EXIT; \
		for attempt in 1 2 3 4 5 6 7 8 9 10; do \
			if curl -fsS "http://127.0.0.1:$(SMOKE_PORT)/api/auth/me" >/dev/null 2>&1; then \
				curl -fsS -c "$$cookie_jar" -H 'Content-Type: application/json' -d '{"username":"cuiyeqing960904@gmail.com","password":"Vladimir960904"}' "http://127.0.0.1:$(SMOKE_PORT)/api/auth/login" >/dev/null; \
				curl -fsS "http://127.0.0.1:$(SMOKE_PORT)/live" >/dev/null; \
				curl -fsS "http://127.0.0.1:$(SMOKE_PORT)/breadth" >/dev/null; \
				curl -fsS -b "$$cookie_jar" "http://127.0.0.1:$(SMOKE_PORT)/api/strategies" >/dev/null; \
				curl -fsS -b "$$cookie_jar" "http://127.0.0.1:$(SMOKE_PORT)/api/live-chart?symbol=BTCUSDT&interval=1m&limit=40" >/dev/null; \
			echo "docker smoke passed on http://127.0.0.1:$(SMOKE_PORT)"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	docker logs "$$container"; \
	exit 1

compose-up:
	mkdir -p "$(RUNS_DIR)" "$(HISTORICAL_DATA_DIR)"
	PORT=$(PORT) $(COMPOSE) up -d --build

compose-down:
	$(COMPOSE) down

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache node_modules/.tmp
