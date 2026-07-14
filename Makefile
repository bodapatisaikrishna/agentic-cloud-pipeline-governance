# ACDE — single entrypoint for every workflow.
# Targets marked "Phase N" are stable interfaces implemented in that phase.

COMPOSE := docker compose
UV := uv run

.PHONY: up up-core down logs lint fmt test-unit test-integration clean \
        seed migrate stream agents baseline experiment-quick experiment-paper analyze report \
        chaos-schema_drift chaos-upstream_delay chaos-resource_contention chaos-ingress_burst

## --- Environment ---

up:  ## Bring up the full stack (postgres, opa, redpanda, airflow); builds the airflow image
	$(COMPOSE) up -d --build --wait

up-core:  ## Bring up only postgres + opa (fast; no data plane)
	$(COMPOSE) up -d --wait postgres opa

down:  ## Stop the stack (keeps volumes)
	$(COMPOSE) down

logs:  ## Tail all service logs
	$(COMPOSE) logs -f --tail=100

clean:  ## Stop the stack and remove volumes + caches
	$(COMPOSE) down -v
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov

## --- Quality gates ---

lint:  ## ruff check + format check + mypy
	$(UV) ruff check src tests
	$(UV) ruff format --check src tests
	$(UV) mypy

fmt:  ## Auto-fix lint + formatting
	$(UV) ruff check --fix src tests
	$(UV) ruff format src tests

test-unit:  ## Unit tests: MOCK_LLM=1, no docker, no network, coverage >= 80%
	MOCK_LLM=1 $(UV) pytest tests/unit --cov --cov-report=term-missing

test-integration:  ## Integration tests (requires `make up` first)
	MOCK_LLM=1 $(UV) pytest tests/integration -m integration

## --- Data plane (Phase 1) ---

migrate:  ## Apply idempotent init SQL to the running DB (adds tables to existing volumes)
	MOCK_LLM=1 $(UV) python -m acde.dataplane.migrate

seed:  ## Generate seeded datasets and migrate the DB
	MOCK_LLM=1 $(UV) python -m acde.dataplane.datasets.tpcds_gen
	MOCK_LLM=1 $(UV) python -m acde.dataplane.datasets.opengov_fetch
	$(MAKE) migrate

stream:  ## Publish a seeded burst, then run the consumer for one 60s session
	MOCK_LLM=1 $(UV) python -m acde.dataplane.streaming.producer --events 2000
	MOCK_LLM=1 $(UV) python -m acde.dataplane.streaming.consumer --duration 60

## --- Telemetry (Phase 2) ---

telemetry:  ## Collect telemetry for DURATION seconds (default 120), then aggregate cost
	MOCK_LLM=1 $(UV) python -m acde.telemetry.collector --duration $${DURATION:-120}
	$(MAKE) cost

cost:  ## Aggregate resource_usage into the cost ledger
	MOCK_LLM=1 $(UV) python -m acde.telemetry.cost

## --- Policy plane (Phase 3) ---

opa-test:  ## Run the OPA Rego policy test suites (requires the stack up)
	$(COMPOSE) exec -T opa opa test /policies -v

## --- Future phases (stable interface, implemented later) ---

chaos-schema_drift chaos-upstream_delay chaos-resource_contention chaos-ingress_burst:  ## Inject a seeded fault
	MOCK_LLM=1 $(UV) python -m acde.chaos.injector --scenario $(subst chaos-,,$@)

agents:  ## Run one agent cycle (all four agents), MOCK_LLM=1
	MOCK_LLM=1 $(UV) python -m acde.agents.run --experiment-run $${EXPERIMENT_RUN:-adhoc}

agents-live-smoke:  ## One live LLM cycle (MOCK_LLM=0) — needs ANTHROPIC_API_KEY; you run this
	MOCK_LLM=0 $(UV) python -m acde.agents.run --experiment-run $${EXPERIMENT_RUN:-live-smoke}

baseline:  ## Phase 7: static-orchestration baseline
	@echo "'baseline' is implemented in Phase 7 (baseline + runner)"; exit 1

experiment-quick experiment-paper:  ## Phase 7: experiment matrix
	@echo "'$@' is implemented in Phase 7 (experiment runner)"; exit 1

analyze report:  ## Phase 8: statistics + figures + report
	@echo "'$@' is implemented in Phase 8 (analysis)"; exit 1
