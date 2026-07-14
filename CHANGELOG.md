# Changelog

All notable changes to ACDE. Format loosely follows Keep a Changelog; versions are tagged
per phase, `v1.0.0` at Phase 9.

## [0.5.0] — 2026-07-13 — Phase 4: failure-injection harness

### Added
- **`src/acde/chaos/`** package:
  - `scenarios.py` — `run_seed(config, scenario, replicate)` (`sha256 % 2**32`) and the four §6
    scenarios (`schema_drift`, `upstream_delay`, `resource_contention`, `ingress_burst`) with
    warmup→fault→recovery timelines bounded by a hard cap.
  - `injector.py` — pure, deterministic `plan_timeline(scenario, seed) -> FaultPlan`;
    `FaultInjector.inject` writes `telemetry.failure_events` and applies the degradation
    (CSV corruption / self-published degraded+burst streams / CPU stressor). CLI with
    `--plan-only` for inspecting the seeded plan.
  - `stressor.py` — host multiprocessing CPU stress (default) or opt-in stress-ng container.
- **Config**: chaos timings + stress knobs. **Makefile**: the four `chaos-<scenario>` targets.
- **Tests**: +33 unit incl. the determinism headline (`plan_timeline` same-seed ⇒ identical,
  different-seed ⇒ different) and `corrupt_frame` → `validate` failure; integration `test_chaos.py`
  (each scenario writes a `failure_events` row + visible degradation). 188 unit tests, 97% coverage.
- **Docs**: DEVIATIONS D-026…D-030.

### Note
Live integration gate deferred: the local Docker context was switched to colima (another project),
so the acde stack was down at gate time. Unit suite + `--plan-only` determinism proof pass; the
chaos integration tests run once the acde stack is back on Docker Desktop.

## [0.4.0] — 2026-07-13 — Phase 3: policy plane & executor

### Added
- **OPA Rego policies** (`infra/opa/policies/`): `cost_budget`, `recovery_approval`,
  `schema_compat`, `rate_limit`, and a `main.rego` aggregator (`data.acde.policy.decision`),
  each with `_test.rego` — **20 `opa test` cases**. OPA now runs with `--watch` (live reload).
- **`src/acde/policy/gate.py`** — assembles the policy context (projected marginal cost,
  prior-version existence, recent-action count) and evaluates via OPA REST → `PolicyDecision`;
  fails safe by escalating when OPA is unreachable.
- **`src/acde/policy/executor.py`** — the §5.2 action→side-effect mapping: rollback (pointer
  flip via `PartitionVersionManager`), scale_workers/apply_mapping/block_ingestion/reprioritize
  (`control.desired_state`), retry/replay/partial_recompute + adjust_pool_slots (Airflow REST),
  quarantine (deactivate + `quarantine_events`), and escalation → `manual_interventions`.
- **`src/acde/human/simulator.py`** — seeded lognormal(360s, σ0.5) on-call human that assigns and
  resolves manual interventions deterministically.
- **Config**: `budget_default_units`, `rate_limit_max_per_10min`, `human_latency_median_s`,
  `human_latency_sigma`. **Makefile**: `opa-test`.
- **Tests**: +29 unit (gate, executor dispatch, human simulator); integration `test_policy.py`
  (budget denial, rollback pointer-flip, escalation→resolution). 164 unit tests, 98% coverage.
- **Docs**: DEVIATIONS D-021…D-025.

## [0.3.0] — 2026-07-13 — Phase 2: telemetry, cost ledger, freshness

### Added
- **`src/acde/telemetry/`** package:
  - `collector.py` — host-side loop polling the Airflow REST API (task instances → `task_runs`,
    upserted via a new unique index) and `docker stats` (→ `resource_usage`, incl. logical
    `streaming`/`batch` resource-unit rows). Pure parsers unit-tested.
  - `freshness.py` — streaming freshness (`materialized_ts − event_ts`) and batch staleness →
    `pipeline_metrics`.
  - `cost.py` — disclosed cost model (§5.5): step-integrates worker-seconds and warehouse
    storage into per-component 1-min `cost_ledger` rows; pure math unit-verified.
- **Config**: `experiment_run`, `telemetry_interval_s`, `cost_window_s`.
- **SQL**: unique index `task_runs_uident` for idempotent task-run upserts.
- **Makefile**: `telemetry` (collect for DURATION then aggregate), `cost`.
- **Tests**: +27 unit (cost math vs hand fixture, freshness, docker/airflow parsers, config);
  integration `test_telemetry.py` (all telemetry tables fill; a cost window recomputes by hand).
  135 unit tests, 98% coverage.
- **Docs**: DEVIATIONS D-018…D-020.

### Fixed
- `warehouse_size_gb` coerces psycopg's `Decimal` from `pg_total_relation_size` to `float`
  (caught by the live integration test).

## [0.2.0] — 2026-07-13 — Phase 1: data plane

### Added
- **Datasets** (`src/acde/dataplane/datasets/`): seeded synthetic TPC-DS generator and an
  NYC-311-shaped open-gov generator (both deterministic), plus a real NYC-TLC parquet
  downloader and real open-gov fetch as opt-ins (`USE_REAL_TLC` / `USE_REAL_OPENGOV`).
- **Versioned partitions** (`dataplane/partitions.py`): `PartitionVersionManager` —
  create/activate/get_active/rollback over physical per-version tables; rollback is a
  transactional pointer flip (reused by recovery later).
- **Batch pipeline** (`dataplane/batch/`): pure `validate → transform → materialize` stages
  and thin Airflow DAGs `tpcds_ingest`, `opengov_ingest`.
- **Streaming** (`dataplane/streaming/`): 60s tumbling-window aggregator, worker pool
  resizable 1–8 live from `control.desired_state['streaming.workers']`, lazy confluent-kafka
  wrappers, async consumer session, and a seeded bursty producer (+ TLC replay).
- **Infra**: Redpanda + Airflow (LocalExecutor, metadata in a separate `airflow` DB) added to
  `docker-compose.yml`; `docker/airflow.Dockerfile`; `warehouse.stream_aggregates` +
  `warehouse.quarantine_events` tables.
- **Makefile**: `seed`, `migrate`, `stream`, `up-core`; `up` now brings the full stack.
- **Deps**: pandas, pyarrow, confluent-kafka, httpx (`uv.lock` updated).
- **Tests**: +54 unit tests (datasets, partitions, batch, windows, workers, producer, config,
  migrate); integration tests for the batch DAG and a streaming session. Coverage 98%.
- **Docs**: DEVIATIONS D-009…D-017.

## [0.1.0] — 2026-07-08 — Phase 0: scaffold & foundations

### Added
- Repo skeleton, `pyproject.toml` (uv-managed, hatchling, src layout), committed `uv.lock`.
- `src/acde/config.py`: single pydantic-settings `Settings` covering DB, broker, OPA,
  Airflow, LLM models/budgets, cost-model rates, SLAs, seeds; `MOCK_LLM=1` default.
- `src/acde/logging.py`: structured JSON logging (`ts/level/component/event` + extras).
- `src/acde/db.py`: psycopg3 connection pool + retrying execute/fetch helpers.
- `src/acde/contracts/`: §5.2 contracts — `AgentName`, `ACTION_TYPES`, `ProposedAction`
  (agent↔action_type cross-validation), `PolicyDecision`, `TelemetrySnapshot`,
  `FailureEvent`.
- Idempotent Postgres DDL for `telemetry`/`warehouse`/`control` schemas
  (`infra/postgres/init/`).
- `docker-compose.yml`: postgres:16.6 + OPA 0.68.0 with healthchecks and init mounts.
- Makefile (`up down logs lint fmt test-unit test-integration clean` + stable stubs for
  later phases), `.env.example`, `.gitignore`.
- Unit tests (54, coverage 97% ≥ 80% gate) and marked integration smoke tests.
- CI: GitHub Actions — ruff, mypy, unit tests with MOCK_LLM=1, no docker.
- Docs: README, CLAUDE.md, DEVIATIONS.md (D-001…D-007).
