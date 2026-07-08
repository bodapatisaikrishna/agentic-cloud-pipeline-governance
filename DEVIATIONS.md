# DEVIATIONS.md

Every assumption or departure from the paper (arXiv:2512.23737) or the project spec,
with alternatives and rationale. This file is a first-class research artifact and is
auto-included in the final report.

---

## D-001 — Repo root is the working directory, not a nested `acde/` folder

- **Decision:** The repository root is `/Users/bodapati/Downloads/cloudagent` (the directory
  the project was started in); the spec's tree shows a top-level `acde/` folder.
- **Alternatives:** Create a nested `acde/` subdirectory matching the spec tree literally.
- **Rationale:** The user created and launched the session in this directory; a nested root
  adds a pointless path level. The Python package is still `acde` (`src/acde/`), so all
  spec-internal paths are unchanged.

## D-002 — Postgres driver: psycopg 3 + psycopg-pool; retries via tenacity

- **Decision:** `psycopg[binary]` v3 with `psycopg_pool.ConnectionPool` (dict rows) and
  tenacity for bounded exponential-backoff retries.
- **Alternatives:** psycopg2, SQLAlchemy, asyncpg; hand-rolled retry loops.
- **Rationale:** Spec pins Postgres 16 but not a driver. psycopg3 is the maintained
  successor with native pooling; tenacity gives declarative, testable retry policy reused
  later for HTTP (Airflow/OPA/Anthropic) clients.

## D-003 — §5.1 DDL made idempotent with IF NOT EXISTS

- **Decision:** The spec's SQL is applied verbatim in content, but every
  `CREATE SCHEMA`/`CREATE TABLE` gains `IF NOT EXISTS`.
- **Alternatives:** A migration tool (alembic/dbmate); DROP-and-recreate.
- **Rationale:** Global rule requires idempotent migrations; the spec snippet lacked the
  guards. Full migration tooling is overkill for a fixed research schema applied at
  container init.

## D-004 — OPA image pinned to `openpolicyagent/opa:0.68.0-debug`

- **Decision:** Pin 0.68.0 (a "latest stable 0.6x" per spec) and use the `-debug` variant.
- **Alternatives:** plain distroless `0.68.0` (no shell → no in-container healthcheck);
  newer 0.6x patch releases; OPA 1.x.
- **Rationale:** The compose healthcheck needs a shell + wget inside the container; the
  distroless production image has neither. The `-debug` variant only adds busybox. Rego
  semantics are identical.

## D-005 — `TelemetrySnapshot` / `FailureEvent` field shapes defined by us

- **Decision:** §5.2 names these models but doesn't enumerate fields; they are implemented
  as minimal faithful mirrors of the §5.1 telemetry tables
  (`src/acde/contracts/telemetry.py`), including a `cache_key_material()` on the snapshot
  that excludes window timestamps so identical pipeline states hit the §5.6 LLM cache.
- **Alternatives:** Defer definition to Phase 2; include every table column.
- **Rationale:** Contracts are a Phase 0 deliverable; agents need a stable observation
  shape. Fields may be extended (never repurposed) in Phase 2.

## D-006 — Cost model constants (restating spec §5.5 disclosure requirement)

- **Decision:** `cost_units = compute_unit_seconds × 0.05 + storage_gb_hours × 0.01`,
  constants in `Settings` (`cost_rate_compute_unit_second`, `cost_rate_storage_gb_hour`).
- **Rationale:** The original paper never defines its cost model; ours is normalized and
  fully disclosed (spec §5.5 mandates this entry).

## D-007 — Coverage gate (≥80%) enforced from Phase 0, not Phase 9

- **Decision:** `--cov-fail-under=80` on `src/acde` in `make test-unit` and CI from day one.
- **Alternatives:** Report-only until the Phase 9 hardening pass.
- **Rationale:** Ratcheting from the start avoids a painful backfill; Phase 0 surface is
  small and fully testable (currently 97%).
