# Production hardening: P0/P1 design

Status: approved 2026-08-27. Sequencing and tenancy direction set by the project owner.

## Why

ACDE is a working, tested research replication with a real trust core (OPA gate, graduated
autonomy, kill switch, blast radius). A systematic audit found defects that do not show up in a
demo or in CI but break a real deployment. This document is the design for closing them.

The audit findings, with evidence:

| # | Severity | Finding | Evidence |
|---|---|---|---|
| 1 | P0 | Executed actions can be lost from the audit trail | `agents/base.py:150-158` executes the side effect, *then* writes `telemetry.agent_actions` |
| 2 | P0 | Every hot-path query is a seq scan on an unbounded table | 2 indexes / 13 tables; `control.py:41`, `loop.py:149`, `metrics.py:21-43` |
| 3 | P0 | No data retention or partitioning | `resource_usage` alone: ~6.3M rows/year/component at `TELEMETRY_INTERVAL_S=5` |
| 4 | P1 | No migration framework, and migrations cannot reach production at all | `dataplane/migrate.py:17` resolves to the repo root, absent in the installed wheel |
| 5 | P1 | `/health` is unauthenticated and returns the full `doctor()` report | `server/app.py:71-73` |
| 6 | P1 | Secrets are plain `str`; no `SecretStr` anywhere | `config.py:71-81` |
| 7 | P1 | `/audit` cannot answer "what happened on date X" | `server/app.py:87-93`, `LIMIT` only |
| 8 | P1 | No tenant/environment boundary; `experiment_run` doubles as the production scope key | `cli.py:123` passes `--env` as `experiment_run` |

Explicitly **not** in scope here: Kubernetes (follows this work), multi-cloud, formal verification.

## Sequencing

Bottom-up, because the dependencies are real: nothing else can ship a schema change until (4) exists.

1. Migration framework
2. Write-ahead audit trail
3. Indexes, retention, tenant/environment boundary (+ benchmarks)
4. Security hardening
5. Supervised control loop + `deploy/observability/`

## 1. Migration framework

**Decision: a small forward-only runner in the package, not Alembic.**

Alembic assumes SQLAlchemy, which this project does not use, and would pull an ORM dependency into a
codebase that deliberately hand-rolls (`server/metrics.py` writes Prometheus exposition text rather
than take a client library). A ~120-line versioned runner is well-understood at this scale: one
Postgres, 13 tables, additive changes.

- Migrations live at `src/acde/migrations/NNN_name.sql` — **inside the package**, so they ship in the
  wheel and fix the production-unreachable bug in (4).
- `db.migrations` tracks applied versions in a `control.schema_migrations` table
  (`version`, `applied_ts`, `checksum`).
- **One transaction per migration**, with the version row written in the same transaction: a failed
  migration leaves no partial state and no bogus version record.
- **`pg_advisory_lock`** around the whole run, so two servers starting at once cannot race.
- **Checksum guard**: if an already-applied file has changed on disk, refuse to run and say so.
  Silently skipping an edited migration is how environments drift apart.
- `infra/postgres/init/` stays as the fresh-volume path. `001_baseline.sql` is the same idempotent
  DDL, so a database created either way converges on the same schema.
- Surfaced as `acde migrate` (production) and `make migrate` (development).

## 2. Write-ahead audit trail

The core fix: **the record of intent is durable before the side effect happens.**

`agents/base.py::act()` becomes:

1. `INSERT` the action row with `status='executing'` (policy verdict already known and recorded).
2. Call `executor.execute()`.
3. `UPDATE` the row with the outcome and `status='executed'` / `'failed'` / `'denied'`.

A crash between 1 and 3 leaves a row saying *"this action was authorised and started; outcome
unknown"* — alertable and recoverable. Today it leaves nothing at all.

- New `status` column, defaulting to `'executed'` so existing rows keep their current meaning.
- A stale `executing` row (older than a threshold) is a real operational signal, exposed as a
  Prometheus gauge in step 5.
- `/audit` reports `status`, so an operator can see in-flight and unknown actions, not just
  completed ones.

This is not merely defensive: an unauditable executed action falsifies the product's central claim.

## 3. Indexes, retention, tenant boundary

**Indexes** — composite, matching the actual predicates, leading with the tenant column:

- `agent_actions (tenant_id, target, ts DESC) WHERE executed` — for `blast_radius_exceeded`
- `agent_actions (tenant_id, ts DESC)` — for `/audit`, `/proposals`
- `failure_events (tenant_id, resolved_ts) WHERE resolved_ts IS NULL` — partial, for `_open_faults`
- `resource_usage (tenant_id, ts DESC)`, `pipeline_metrics (tenant_id, ts DESC)`

**Benchmarks, not assertions.** A reproducible script seeds N rows and measures each hot query at
N = 10³, 10⁵, 10⁶, before and after. The claim in the README will be a measured number.

`/metrics` currently issues six `count(*)` scans per scrape. These become indexed or
incrementally-maintained counters; the same benchmark covers scrape cost.

**Retention.** A `retention` job deletes telemetry older than a configurable window
(`RETENTION_DAYS`, default off so nobody loses data by upgrading). `agent_actions` is the audit
trail and is exempt by default — audit records are the compliance artifact and must not silently
vanish; archival for those is a later, deliberate feature.

**Tenant/environment boundary** — establish it now, do not build a SaaS control plane yet:

- Add `tenant_id TEXT NOT NULL DEFAULT 'default'` and `environment TEXT NOT NULL DEFAULT 'default'`
  to the scoped telemetry tables.
- Backfill existing rows to the defaults. **No data is destroyed or rewritten in place**; existing
  `experiment_run` values are preserved exactly as they are.
- `experiment_run` keeps its research meaning (one matrix cell). It stops being overloaded as the
  production scope key.
- **Isolation is server-side.** The tenant is resolved from the authenticated actor, never from a
  client-supplied field — the same principle already used correctly for the audit actor in
  `server/app.py`. API queries filter by the resolved tenant.

That is enough to evolve safely later and cheap enough not to be over-engineering now.

## 4. Security hardening

- **Split `/health`**: unauthenticated shallow liveness (`{"status": "ok"}`, no internals) and
  authenticated `/health/ready` returning the full `doctor()` report. Load balancers get what they
  need; the internals stop being public.
- **`SecretStr`** for every credential in `Settings`, so a `repr()`, traceback, or debug dump cannot
  print an API key or the database password. Call sites use `.get_secret_value()`.
- **`/audit` gains `since` / `until` / cursor pagination**, so the compliance question is answerable.

## 5. Supervised loop + observability

- The control loop writes a liveness heartbeat to `control.desired_state` each tick — the same
  durable, cross-process mechanism the kill switch already uses.
- `acde loop-health` reads it and exits non-zero when stale; wired as the container `HEALTHCHECK`.
- Exposed as `acde_loop_last_tick_timestamp_seconds`, plus a gauge for stale `executing` actions.
- `deploy/observability/` gets built for real: Prometheus scrape config, alert rules, and a
  provisioned Grafana dashboard. `docs/OPERATIONS.md:55` already claims this directory exists; it
  does not. Fixing a documentation lie counts as a defect fix.

Scope boundary, stated honestly: this makes a stuck loop **visible and alertable**. Automatic
restart-on-hang is a Kubernetes `livenessProbe` behaviour and belongs to the Kubernetes work, not
here. The claim is "you can see it is stuck and get paged", not "it heals itself".

## Testing

Every change carries a test that fails without it. The discipline already used in this repo
(D-077 through D-082) continues: for each fix, reintroduce the defect, confirm the new test fails
for the right reason, restore, confirm green.

- **Migrations**: fresh DB, existing DB, re-run idempotency, checksum-drift refusal, concurrent
  runners contending for the advisory lock.
- **Write-ahead audit**: simulated crash between write-ahead and outcome update leaves a recoverable
  `executing` row; the pre-fix code loses the action entirely.
- **Indexes/retention**: the benchmark itself is the evidence, recorded before and after.
- **Security**: unauthenticated `/health` must not leak internals; `repr(Settings)` must not contain
  a secret; audit time-range queries return the right window.
- Gates unchanged: `make lint && make test-unit` green, coverage ≥ 80%, then integration against the
  real stack, then CI.

## Risks

- **Schema changes on a live database.** All changes here are additive (new columns with defaults,
  new indexes). No column is dropped or retyped, no data rewritten. Index creation on a large table
  can lock; migrations that need it will use `CREATE INDEX CONCURRENTLY` outside a transaction.
- **Hand-rolled migration runner.** Accepted deliberately, with the reasoning above; recorded in
  `DEVIATIONS.md`. The checksum guard and advisory lock cover the two failure modes that actually
  bite at this scale.
- **Retention deleting wanted data.** Default off; `agent_actions` exempt.
