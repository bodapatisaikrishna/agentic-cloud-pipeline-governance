# Changelog

All notable changes to ACDE. Format loosely follows Keep a Changelog; versions are tagged
per phase, `v1.0.0` at Phase 9.

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
