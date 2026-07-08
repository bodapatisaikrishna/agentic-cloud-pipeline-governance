# ACDE — single entrypoint for every workflow.
# Targets marked "Phase N" are stable interfaces implemented in that phase.

COMPOSE := docker compose
UV := uv run

.PHONY: up down logs lint fmt test-unit test-integration clean \
        seed agents baseline experiment-quick experiment-paper analyze report \
        chaos-schema_drift chaos-upstream_delay chaos-resource_contention chaos-ingress_burst

## --- Environment ---

up:  ## Bring up the stack (waits for healthchecks)
	$(COMPOSE) up -d --wait

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

## --- Future phases (stable interface, implemented later) ---

seed:  ## Phase 1: load datasets
	@echo "'seed' is implemented in Phase 1 (data plane)"; exit 1

chaos-schema_drift chaos-upstream_delay chaos-resource_contention chaos-ingress_burst:  ## Phase 4
	@echo "'$@' is implemented in Phase 4 (failure injection)"; exit 1

agents:  ## Phase 5/6: run the agent control loop
	@echo "'agents' is implemented in Phases 5-6 (agents + orchestrator)"; exit 1

baseline:  ## Phase 7: static-orchestration baseline
	@echo "'baseline' is implemented in Phase 7 (baseline + runner)"; exit 1

experiment-quick experiment-paper:  ## Phase 7: experiment matrix
	@echo "'$@' is implemented in Phase 7 (experiment runner)"; exit 1

analyze report:  ## Phase 8: statistics + figures + report
	@echo "'$@' is implemented in Phase 8 (analysis)"; exit 1
