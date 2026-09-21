# ACDE — single entrypoint for every workflow.
# Targets marked "Phase N" are stable interfaces implemented in that phase.

COMPOSE := docker compose
UV := uv run

.PHONY: up up-core down logs lint fmt test-unit test-integration clean \
        seed migrate stream agents experiment-smoke experiment-quick experiment-paper campaign-pilot campaign campaign-smoke campaign-status campaign-stop adversarial-corpus analyze report \
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

migrate:  ## Apply pending schema migrations (adds tables to existing volumes, D-083)
	MOCK_LLM=1 $(UV) python -m acde.migrations

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

agents-live-smoke:  ## One live LLM cycle (MOCK_LLM=0) — needs the provider key (ANTHROPIC_API_KEY / GEMINI_API_KEY / OAI_API_KEY per LLM_PROVIDER); you run this
	MOCK_LLM=0 $(UV) python -m acde.agents.run --experiment-run $${EXPERIMENT_RUN:-live-smoke}

## --- Orchestrator (Phase 6) ---

orchestrator:  ## Run the control loop (CONFIG, DURATION, EXPERIMENT_RUN)
	MOCK_LLM=1 $(UV) python -m acde.orchestrator.loop \
	  --config $${CONFIG:-full} --experiment-run $${EXPERIMENT_RUN:-adhoc} --duration $${DURATION:-1200}

soak:  ## Inject two overlapping chaos scenarios and run the loop (DURATION seconds)
	MOCK_LLM=1 $(UV) python -m acde.orchestrator.soak \
	  --config $${CONFIG:-full} --experiment-run $${EXPERIMENT_RUN:-soak} --duration $${DURATION:-1200}

experiment-smoke:  ## Tiny 2-run profile (baseline+full) — used by the integration gate
	MOCK_LLM=1 $(UV) python -m acde.experiments.runner --profile smoke

experiment-quick:  ## Quick matrix: 8 configs x 4 scenarios x N=3 = 96 runs (resumable)
	MOCK_LLM=1 $(UV) python -m acde.experiments.runner --profile quick

experiment-paper:  ## Paper matrix (MOCK LLM): 3 baselines + full at N=20, 4 ablations at N=10 = 480 runs (resumable)
	MOCK_LLM=1 $(UV) python -m acde.experiments.runner --profile paper

## --- Paper campaign (D-104) — real API spend, multi-day; see docs/CAMPAIGN.md ---

campaign-pilot:  ## LIVE pilot: 8 runs at paper timings (~1-2h) to measure cost/time; needs MAX_TOKENS
	@test -n "$(MAX_TOKENS)" || (echo "set MAX_TOKENS=<live-arm token ceiling>"; exit 2)
	caffeinate -i $(UV) python -m acde.experiments.campaign --profile pilot --max-tokens $(MAX_TOKENS)

campaign:  ## LIVE paper campaign (~49h; arms A live agents, B baselines, C mock full); needs MAX_TOKENS
	@test -n "$(MAX_TOKENS)" || (echo "set MAX_TOKENS=<live-arm token ceiling>"; exit 2)
	caffeinate -i $(UV) python -m acde.experiments.campaign --profile paper --max-tokens $(MAX_TOKENS)

campaign-smoke:  ## Free 2-run mock drill of the supervisor (kill it mid-run, re-run: it resumes)
	MOCK_LLM=1 $(UV) python -m acde.experiments.campaign --profile smoke --results-root $${ROOT:-results}

campaign-status:  ## Show the campaign heartbeat
	@cat results/campaign_status.json

campaign-stop:  ## Ask a running campaign to stop after the current run (resumable)
	touch results/CAMPAIGN_STOP

adversarial-corpus:  ## D-104: generated adversarial corpus vs the live (pinned) OPA -> results/adversarial.json
	MOCK_LLM=1 $(UV) python -m acde.eval.adversarial_corpus --out results/adversarial.json

analyze:  ## Phase 8: compute statistics from results/raw.csv
	MOCK_LLM=1 $(UV) python -m acde.analysis.analyze

report:  ## Phase 8: analyze + figures + results/results.md
	MOCK_LLM=1 $(UV) python -m acde.analysis.report
