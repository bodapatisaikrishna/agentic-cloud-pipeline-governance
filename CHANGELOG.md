# Changelog

All notable changes to ACDE. Format loosely follows Keep a Changelog; versions are tagged
per phase, `v1.0.0` at Phase 9.

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
