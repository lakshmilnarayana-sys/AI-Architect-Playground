PYTHON ?= .venv/bin/python
SERVICE_NAME ?= sample-payments-api
RUNTIME ?= python
SLO_P95_MS ?= 500
SLO_ERROR_RATE ?= 1
DURATION ?= 10s
ENGINE ?= k6
MODE ?= standard
LOCAL_PORT ?= 8080
LOCAL_TARGET_URL ?= http://localhost:$(LOCAL_PORT)
COMPOSE_TARGET_URL ?= http://demo-http-payments:8080
OPENAPI ?= ./examples/sample-payments-api/openapi.yaml
OUTPUT ?= ./outputs/$(SERVICE_NAME)
COMPOSE ?= docker compose

.PHONY: help setup test test-grpc test-websocket test-ui generate inspect run-sample evaluate-local build compose-config demo-up demo-down dependencies-up dependencies-down evaluate-compose prepare-compose-artifacts locust-run jmeter-run experiment-compose clean

help:
	@printf "PerfAgent AI commands\n\n"
	@printf "  make setup              Create venv and install dev dependencies\n"
	@printf "  make test               Run pytest suite\n"
	@printf "  make test-grpc          Run gRPC demo tests\n"
	@printf "  make test-websocket     Run WebSocket demo tests\n"
	@printf "  make test-ui            Run UI checkout demo tests\n"
	@printf "  make generate           Generate k6 script from sample OpenAPI\n"
	@printf "  make inspect            Validate generated k6 script with k6 inspect\n"
	@printf "  make run-sample         Start HTTP sample app on LOCAL_PORT (default 8080)\n"
	@printf "  make evaluate-local     Run PerfAgent against LOCAL_TARGET_URL\n"
	@printf "  make build              Build PerfAgent container image\n"
	@printf "  make compose-config     Validate docker compose config, including demo/tools profiles\n"
	@printf "  make demo-up            Start demo services with docker compose\n"
	@printf "  make demo-down          Stop demo services\n"
	@printf "  make dependencies-up    Start optional DB/cache/stream/search dependencies\n"
	@printf "  make dependencies-down  Stop optional dependency services\n"
	@printf "  make evaluate-compose   Run PerfAgent container against Compose HTTP demo\n"
	@printf "  make locust-run         Run Locust through Compose and generate PerfAgent report\n"
	@printf "  make jmeter-run         Run JMeter through Compose and generate PerfAgent report\n"
	@printf "  make experiment-compose Build/start/evaluate/stop via Compose\n"
	@printf "  make clean              Remove generated outputs and caches\n"

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest -q

test-grpc:
	$(PYTHON) -m pytest tests/test_grpc_payments_api.py -q

test-websocket:
	$(PYTHON) -m pytest tests/test_websocket_payments_api.py -q

test-ui:
	$(PYTHON) -m pytest tests/test_ui_checkout_app.py -q

generate:
	$(PYTHON) -m perfagent generate \
		--service-name $(SERVICE_NAME) \
		--openapi $(OPENAPI) \
		--target-url $(LOCAL_TARGET_URL) \
		--output ./outputs/generated-$(SERVICE_NAME)

inspect: generate
	k6 inspect ./outputs/generated-$(SERVICE_NAME)/perf_test.js

run-sample:
	PORT=$(LOCAL_PORT) $(PYTHON) examples/sample-payments-api/app.py

evaluate-local:
	$(PYTHON) -m perfagent evaluate \
		--service-name $(SERVICE_NAME) \
		--openapi $(OPENAPI) \
		--target-url $(LOCAL_TARGET_URL) \
		--runtime $(RUNTIME) \
		--slo-p95-ms $(SLO_P95_MS) \
		--slo-error-rate $(SLO_ERROR_RATE) \
		--engine $(ENGINE) \
		--mode $(MODE) \
		--duration $(DURATION) \
		--output $(OUTPUT)

build:
	$(COMPOSE) build perfagent

compose-config:
	$(COMPOSE) --profile demo --profile tools --profile dependencies config

demo-up:
	$(COMPOSE) --profile demo up --build -d demo-http-payments demo-websocket-payments demo-grpc-payments demo-ui-checkout

demo-down:
	$(COMPOSE) --profile demo down

dependencies-up:
	$(COMPOSE) --profile dependencies up -d demo-postgres demo-redis demo-kafka demo-cassandra demo-elasticsearch

dependencies-down:
	$(COMPOSE) --profile dependencies down

evaluate-compose:
	$(COMPOSE) run --rm perfagent evaluate \
		--service-name $(SERVICE_NAME) \
		--openapi $(OPENAPI) \
		--target-url $(COMPOSE_TARGET_URL) \
		--runtime $(RUNTIME) \
		--slo-p95-ms $(SLO_P95_MS) \
		--slo-error-rate $(SLO_ERROR_RATE) \
		--engine $(ENGINE) \
		--mode $(MODE) \
		--duration $(DURATION) \
		--output $(OUTPUT)

prepare-compose-artifacts:
	$(PYTHON) -m perfagent evaluate \
		--service-name $(SERVICE_NAME) \
		--openapi $(OPENAPI) \
		--target-url $(COMPOSE_TARGET_URL) \
		--runtime $(RUNTIME) \
		--slo-p95-ms $(SLO_P95_MS) \
		--slo-error-rate $(SLO_ERROR_RATE) \
		--engine $(ENGINE) \
		--mode $(MODE) \
		--duration $(DURATION) \
		--output $(OUTPUT) \
		--skip-run

locust-run: prepare-compose-artifacts
	SERVICE_NAME=$(SERVICE_NAME) $(COMPOSE) --profile tools run --rm locust
	$(PYTHON) -m perfagent import-results \
		--run-dir $(OUTPUT) \
		--tool locust \
		--result $(OUTPUT)/raw/locust_stats.csv \
		--service-name $(SERVICE_NAME) \
		--runtime $(RUNTIME) \
		--target-url $(COMPOSE_TARGET_URL) \
		--slo-p95-ms $(SLO_P95_MS) \
		--slo-error-rate $(SLO_ERROR_RATE)

jmeter-run: prepare-compose-artifacts
	SERVICE_NAME=$(SERVICE_NAME) $(COMPOSE) --profile tools run --rm jmeter
	$(PYTHON) -m perfagent import-results \
		--run-dir $(OUTPUT) \
		--tool jmeter \
		--result $(OUTPUT)/raw/jmeter_results.jtl \
		--service-name $(SERVICE_NAME) \
		--runtime $(RUNTIME) \
		--target-url $(COMPOSE_TARGET_URL) \
		--slo-p95-ms $(SLO_P95_MS) \
		--slo-error-rate $(SLO_ERROR_RATE)

experiment-compose: build demo-up evaluate-compose demo-down

clean:
	rm -rf outputs .pytest_cache perfagent_ai.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
