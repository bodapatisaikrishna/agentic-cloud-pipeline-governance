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

## D-008 — Postgres published on host port 5433, not 5432

- **Decision:** The stack publishes Postgres on host port **5433** (`POSTGRES_PORT`
  default) mapped to the container's internal 5432.
- **Alternatives:** Keep 5432 and require the developer to stop any local Postgres;
  ask the user to stop their `postgresql@16` brew service.
- **Rationale:** A locally-installed PostgreSQL on 5432 binds loopback (`127.0.0.1`/`::1`),
  which on macOS shadows Docker's wildcard `*:5432` publish — so clients hit the local DB
  and see `role "acde" does not exist`. Publishing on 5433 lets the research stack coexist
  with a developer's local Postgres without touching their data or services. The container
  port is unchanged (5432 internally).

---

## Phase 1 — Data plane

## D-009 — Synthetic, seeded TPC-DS instead of dsdgen

- **Decision:** Generate schema-faithful, downscaled TPC-DS-shaped tables (`store_sales`,
  `item`) with a seeded NumPy generator (`dataplane/datasets/tpcds_gen.py`).
- **Alternatives:** Build/run the official `dsdgen` C toolchain for true SF1 data.
- **Rationale:** Spec §8 Phase 1 explicitly permits this when dsdgen is painful in-container.
  Synthetic data is deterministic (same seed ⇒ byte-identical CSVs), offline, and sufficient
  for the batch pipeline (validate → daily-revenue → versioned partition). Row shapes follow
  the TPC-DS column names so the pipeline stays faithful.

## D-010 — Airflow lives only in the Docker image, never in the project venv

- **Decision:** `apache-airflow` is installed into a custom image
  (`docker/airflow.Dockerfile`) that `pip install`s the `acde` package; it is **not** a
  `pyproject.toml` dependency. DAG modules are the only code that imports airflow.
- **Alternatives:** Add airflow to the project's uv dependencies.
- **Rationale:** Airflow's dependency tree is huge and constraint-pinned; keeping it out of
  the venv keeps `uv sync`, unit tests, and CI fast and airflow-free. Batch logic lives in
  `dataplane/batch/pipeline.py` (no airflow import) and is unit-tested directly.

## D-011 — Airflow metadata in a separate `airflow` database in the shared Postgres

- **Decision:** A one-shot `airflow-init` service creates an `airflow` database inside the
  existing postgres:16 container (idempotently), then runs `airflow db migrate` and creates
  the admin user. The research `acde` DB is untouched.
- **Alternatives:** A dedicated second Postgres container for Airflow metadata.
- **Rationale:** One fewer container/volume; clean logical separation via a distinct
  database. Airflow reaches it over the compose network as `postgres:5432`.

## D-012 — Synthetic-by-default data sources; real public data is opt-in

- **Decision:** Default streaming source is the seeded bursty synthetic producer; default
  open-gov source is a seeded synthetic NYC-311-shaped CSV. `USE_REAL_TLC=1` /
  `USE_REAL_OPENGOV=1` switch to a real NYC-TLC parquet download / NYC-311 fetch.
- **Alternatives:** Always download real data.
- **Rationale:** Determinism and offline CI. Real datasets are non-deterministic and
  network/disk-bound; keeping them opt-in preserves reproducibility while still shipping the
  real fetchers the spec asks for.

## D-013 — Versioned partitions = one physical table per (dataset, partition, version)

- **Decision:** `PartitionVersionManager` creates a physical `warehouse.<dataset>__<part>__v<n>`
  table per version and records it in `warehouse.partition_versions.table_name`; the active
  version is a boolean pointer, so rollback is a transactional pointer flip (no data movement).
- **Alternatives:** One data table with a `version` column + a filter on active version.
- **Rationale:** Matches the spec's `partition_versions.table_name` column and the §5.2
  "rollback = pointer flip" mapping directly; recovery's rollback reuses `activate()`.

## D-014 — New dependencies: pandas, pyarrow, confluent-kafka, httpx

- **Decision:** Added to core deps in the phase that needs them (data generation/transform,
  TLC parquet, Kafka client, HTTP for downloads + the Airflow REST client).
- **Rationale:** Per the repo rule "deps are added in the phase that needs them"; `uv.lock`
  is committed.

## D-015 / D-016 — Image pins: Airflow 2.10.5, Redpanda v24.2.18

- **Decision:** `apache/airflow:2.10.5-python3.11` and `redpandadata/redpanda:v24.2.18`.
- **Rationale:** Latest patch of the spec-mandated 2.10.x / v24.2.x lines; python3.11 matches
  the project interpreter. Airflow 3.x migration remains future work (spec).

## D-017 — `make migrate` applies init SQL to a running DB

- **Decision:** `acde/dataplane/migrate.py` re-applies every `infra/postgres/init/*.sql`
  (all `IF NOT EXISTS`) to the live DB; wired as `make migrate` and run by `make seed`.
- **Alternatives:** `make clean` to reinitialize the volume; a migration framework (alembic).
- **Rationale:** Postgres only runs `/docker-entrypoint-initdb.d` on first volume init, so new
  tables added in later phases would never reach an existing volume. Idempotent re-apply is
  the simplest way to evolve the fixed research schema without destroying data.

---

## Phase 2 — Telemetry, cost, freshness

## D-018 — Cost compute driven by logical resource-unit series

- **Decision:** §5.5 compute = "(active workers or pool slots) × wall seconds". The collector
  records two logical series into `telemetry.resource_usage`: `component='streaming'`
  (workers = `control.desired_state['streaming.workers']`) and `component='batch'`
  (workers = Airflow `running_slots`). `cost.py` step-integrates these over 1-min windows.
  Storage = live `warehouse`-schema size (`pg_total_relation_size`) → `storage_gb_hours`,
  attributed to `component='postgres'`. Docker-container rows (real cpu/mem, workers=1) are
  also recorded for observability but are not cost drivers.
- **Alternatives:** Derive compute from docker CPU-seconds; treat every container as a worker.
- **Rationale:** Faithful to the paper's "resource units" abstraction (the streaming worker
  pool and Airflow slots are the tunable capacity), and the two logical components map cleanly
  to the optimization agent's `scale_workers` / `adjust_pool_slots` actions in later phases.

## D-019 — Batch freshness = partition staleness (now − created_ts)

- **Decision:** Batch data freshness is `now − active partition.created_ts`; streaming
  freshness is the exact §5.4 metric `materialized_ts − event_ts`.
- **Alternatives:** Track a true source-arrival timestamp per partition.
- **Rationale:** The synthetic batch sources have no distinct "arrival" event separate from
  generation, so staleness of the freshest available partition is the honest available-lag
  proxy. Refined if a real arrival signal is added.

## D-020 — Telemetry collector is a host-side loop

- **Decision:** `telemetry/collector.py` runs on the host (`docker stats` CLI + Airflow REST
  over localhost), invoked by `make telemetry`; it is not a containerized service.
- **Alternatives:** A sidecar container with the docker socket mounted.
- **Rationale:** Matches the Phase 1 streaming runner (also host-side), avoids mounting the
  docker socket into a container, and keeps the collector trivially runnable during experiments.
  A tick never crashes the loop (all I/O is guarded).
