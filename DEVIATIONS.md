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

---

## Phase 3 — Policy plane & executor

## D-021 — The gate assembles the policy context; OPA stays a pure decision function

- **Decision:** `policy/gate.py` computes `projected_marginal_cost`, `has_prior_version`, and
  `actions_last_10min` from settings + DB state and passes them in `input.context`. Rego never
  reads DB/HTTP state — it decides purely from `input`.
- **Alternatives:** Push data into OPA and evaluate against `data`; give OPA a DB pull.
- **Rationale:** Keeps policies pure, hermetically testable (`opa test` needs no services), and
  reusable across baseline/experiment modes; the gate is the single place that reads live state.

## D-022 — One aggregating Rego entrypoint

- **Decision:** `data.acde.policy.decision` (`main.rego`) dispatches by agent/action_type to four
  sub-packages (`acde.cost_budget`, `acde.recovery`, `acde.schema`, `acde.rate_limit`), returning
  `{allowed, escalate, reason, policy_id}`. The rate-limit runaway guard is checked first for all
  agents; `no_action` is always allowed; unmatched inputs hit a fail-safe `escalate` default.
- **Rationale:** A single query path for the gate, one decision object matching
  `contracts.PolicyDecision`, and clean per-policy `_test.rego` suites (20 tests).

## D-023 — Gate fail-safe = escalate on OPA failure

- **Decision:** If OPA is unreachable/errors or returns an empty result, `gate.evaluate` returns
  `allowed=false, escalate=true` (`policy_id="gate_failsafe"`), after bounded retries.
- **Rationale:** Brings the Phase 9 "OPA down → all actions escalate" resilience behavior forward;
  never silently allows an ungoverned action.

## D-024 — Human latency: seeded lognormal(median 360s, σ 0.5)

- **Decision:** `human/simulator.py` samples latency deterministically from
  `(default_seed, intervention id)`; assigns it once per pending row, resolves when
  `now ≥ requested_ts + latency`, and stamps `completed_ts = requested_ts + latency`.
- **Rationale:** The §6 baseline specifies this distribution; seeding by row id makes the whole
  intervention timeline reproducible across runs while keeping the simulator stateless.

## D-025 — Executor scope: side effects + escalation rows only

- **Decision:** `policy/executor.py` performs the §5.2 side effects for allowed actions and writes
  `manual_interventions` on escalation, returning an `ExecutionOutcome`. Writing
  `telemetry.agent_actions` (with LLM token counts) is deferred to the agents (Phase 5). Airflow
  network handlers (`clearTaskInstances`, `dagRuns`, `PATCH /pools`) are integration-verified;
  control-plane and DB side effects are unit-tested via the dispatch map.
- **Rationale:** Keeps the executor a pure "apply the decision" component; the agents own the
  audit trail so token/confidence/justification live in one place next phase.

---

## Phase 4 — Failure-injection harness

## D-026 — resource_contention uses a host CPU stressor by default

- **Decision:** `chaos/stressor.py` runs N seeded multiprocessing busy-loops on the host for the
  fault window; a stress-ng container is opt-in via `STRESS_USE_CONTAINER=1` + `stress_image`.
- **Alternatives:** Always run a stress-ng container (spec's literal wording).
- **Rationale:** Self-contained and deterministic (no external image pull), so the gate is
  reliable; host CPU pressure still degrades the co-located Docker containers (they share the VM's
  CPU). The container path remains available for a faithful stress-ng run.

## D-027 — The injector self-publishes the degraded/burst stream

- **Decision:** `upstream_delay` and `ingress_burst` publish their (dropped+delayed / surged)
  streams directly via `JsonProducer`, rather than only setting a flag a separate producer honors.
- **Rationale:** A `make chaos-<scenario>` visibly degrades freshness on its own, with no
  separately-running producer; the record-building is pure and unit-tested.

## D-028 — schema_drift mutates the batch source CSV

- **Decision:** Drop or retype a seeded column in `DATA_DIR/tpcds/store_sales.csv` so the next
  DAG run's `validate()` rejects it; `make seed` regenerates the clean source.
- **Alternatives:** Publish a drifting schema to a registry.
- **Rationale:** Directly exercises the Phase 1 validator and the schema agent's future path;
  the corruption is deterministic (`corrupt_frame`) and trivially reversible.

## D-029 — The injector records injection only

- **Decision:** `FaultInjector` writes `failure_events` with `injected_ts`/`fault_type`/`scenario`;
  `detected_ts`/`resolved_ts` stay NULL until the monitoring/recovery agents fill them (Phase 5).
- **Rationale:** Phase 4 is fault *creation*; the full lifecycle (detection latency, MTTR) belongs
  to the agents that observe and remediate.

## D-030 — Fault timeline is a pure seeded plan

- **Decision:** `plan_timeline(scenario, seed)` is a pure function returning a `FaultPlan`; all I/O
  follows the plan. Determinism is guaranteed and unit-tested at the plan level (same seed ⇒
  byte-identical plan; the `--plan-only` CLI prints it).
- **Rationale:** The experiment runner (Phase 7) replays identical fault conditions across configs
  for paired statistics, so the seed→plan mapping must be exactly reproducible and inspectable.

---

## Phase 5 — Agents & LLM layer

## D-031 — Statistical detection, LLM triage

- **Decision:** `agents/detection.py` detects anomalies with a z-score + static thresholds
  (task failed, freshness > SLA, cpu high, open fault, breaking drift); the LLM only
  classifies/proposes. Detection never calls the LLM.
- **Rationale:** Matches §5.6 ("LLM as bounded reasoning"); detection stays cheap, deterministic,
  and testable, and the LLM spend is bounded to triage/proposal.

## D-032 — `llm/mock.py` is the single deterministic response source

- **Decision:** Under `MOCK_LLM=1`, `mock_propose(agent, snapshot)` inspects the snapshot (open
  faults, schema_compat, freshness) and returns a scenario-appropriate `ProposedAction` per agent,
  covering every agent × scenario, with fixed token counts. All tests use it; no API calls anywhere.
- **Rationale:** Deterministic, offline, CI-safe verification of the whole agent loop; the live
  path is exercised only by the opt-in smoke.

## D-033 — Agents own the audit trail and the failure lifecycle

- **Decision:** Each cycle writes a `telemetry.agent_actions` row (action, params, justification,
  confidence, policy decision/reason, executed, outcome, llm_model, tokens_in/out). Monitoring
  stamps `failure_events.detected_ts` on `raise_anomaly`; recovery stamps `resolved_ts` +
  `resolution` on a successful remediating action — defining MTTR (§5.4) as
  `resolved_ts − detected_ts`.
- **Rationale:** Consolidates the audit trail (deferred from the Phase 3 executor) with the agents
  that generate it, and closes the fault lifecycle the analysis pipeline needs.

## D-034 — Live smoke shipped, not gated

- **Decision:** The live Anthropic path (routing, temperature=0, budget guard, retry) is fully
  implemented; `make agents-live-smoke` runs one `MOCK_LLM=0` cycle. It is never run in the
  automated gate — the user runs it with their key.
- **Rationale:** The gate must stay free and deterministic; a paid external call is the user's
  explicit choice.

## D-035 — Budget guard, in-run cache, routing, retry→no_action

- **Decision:** Per-run caps (`LLM_MAX_CALLS_PER_RUN=60`, `LLM_MAX_TOKENS_PER_RUN=150000`) →
  degrade to `no_action`; in-run cache keyed on `hash(agent, snapshot.cache_key_material())` (a
  cache hit is not re-charged); routing monitoring→`MODEL_FAST`, others→`MODEL_REASONING`; retry
  429/5xx ×3 then `no_action` + `llm_unavailable`. Invalid LLM output → `no_action` +
  `agent_output_invalid`.
- **Rationale:** §5.6 verbatim; keeps live cost bounded and failures graceful.

## D-036 — Model IDs kept (already current-valid)

- **Decision:** `MODEL_REASONING=claude-sonnet-4-6`, `MODEL_FAST=claude-haiku-4-5` — the spec's
  §5.6 routing. Verified against the current model list: both are valid current IDs and both accept
  `temperature=0`, so no change was needed.
- **Rationale:** Honors the spec's explicit cost-conscious routing (Sonnet for reasoning, Haiku for
  fast triage) while remaining valid for the live smoke.

---

## Phase 6 — Control-loop orchestrator

## D-037 — Per-target Postgres advisory locks

- **Decision:** `orchestrator/locks.py::target_advisory_lock` holds one pooled connection and runs a
  non-blocking `pg_try_advisory_lock(hashtext(target))`; on failure the agent skips that target this
  tick. Real cross-process locks, released on unlock/disconnect.
- **Alternatives:** In-process `asyncio.Lock` per target (single-process only); `pg_advisory_xact_lock`
  (would need the whole act in one transaction).
- **Rationale:** The spec calls for Postgres advisory locks; a held connection gives genuine
  cross-process mutual exclusion so two agents never act on the same target concurrently, and it
  survives a future multi-process runner.

## D-038 — Conflict rule via act order + shared lock

- **Decision:** Reactive agents run `schema → recovery → optimization`; contending on the same
  target's advisory lock, recovery (earlier) wins and optimization (later) skips — implementing
  "recovery outranks optimization on the same target" with no special case. Distinct targets run
  independently.
- **Rationale:** Simple, correct, and emergent from the locking primitive rather than bespoke
  priority bookkeeping.

## D-039 — Event-driven reactive scheduling

- **Decision:** Monitoring runs every `monitoring_interval_s` (detect + `detected_ts`); the reactive
  agents run in a tick only when open `failure_events` exist. `no_action` proposals are not executed
  or logged (no no-op `agent_actions` rows).
- **Rationale:** Bounds LLM spend to ticks that have something to react to and keeps the audit trail
  meaningful; matches §5.6 "others event-driven off anomalies".

## D-040 — Ablation via enabled-agent sets

- **Decision:** `orchestrator/configs.py` maps config → enabled agents. `baseline` runs no agents;
  every single-agent config also enables `monitoring` (the detector) so MTTR stays measurable;
  `full` enables all four. Phase 7's experiment configs build on this.
- **Rationale:** One switch drives the whole ablation matrix; keeping monitoring on preserves the
  `detected_ts` needed for MTTR in single-agent runs.

## D-041 — Sync agents under an async loop; stateless ⇒ resumable

- **Decision:** Agent cycles run via `asyncio.to_thread` (the db/gate/executor stack is sync). The
  loop keeps no durable state — everything is in Postgres and advisory locks are session-scoped — so
  SIGTERM/kill then restart resumes cleanly. A failing tick is logged and swallowed (the loop never
  dies).
- **Rationale:** Reuses the Phase 5 sync agents unchanged, and makes the orchestrator restart-safe,
  which the experiment runner (Phase 7) relies on.

---

## Phase 7 — Baseline & experiment runner

## D-042 — Profile-scaled per-run timings

- **Decision:** `paper` uses the §6 timeline (120s warmup / 180s fault / 120s recovery); `quick`
  uses short seconds-scale timings so 72 runs finish in ~15–25 min; `smoke` (2 runs) is the automated
  gate.
- **Alternatives:** Use the full §6 timeline for `quick` (≈8 h).
- **Rationale:** Keeps the quick smoke usable interactively and the CI/integration gate fast, while
  `paper` preserves the real timeline for the publication run. Disclosed vs the spec's "~2 h quick".

## D-043 — Per-run isolation + manifest resumability

- **Decision:** `experiment_run = f"{config}__{scenario}__r{replicate}"`; `_reset_run` deletes that
  run's rows before it starts; each completed run appends to `results/manifest.jsonl`, and
  `run_profile` skips any run_id already there.
- **Rationale:** Clean per-run isolation keyed strictly by `experiment_run` (§8 Phase 7) and a
  resumable matrix — kill mid-run, re-run, finished cells are skipped.

## D-044 — Baseline = fixed resources + human-resolved failures

- **Decision:** `baseline` runs no agents; `experiments/baseline.resolve_via_human` stamps
  `detected_ts` (fixed monitor) and resolves every fault through the seeded `HumanSimulator`
  (lognormal 360 s). Agent configs also call it as a fallback for anything unresolved at run end.
- **Rationale:** Matches §6's baseline (static + on-call human), and makes MTTR reflect human latency
  exactly where the agents don't help — the paired-comparison signal (verified: baseline MTTR ≈312 s
  vs full ≈0.2 s on upstream_delay).

## D-045 — Lifecycle-closing extended to schema + optimization agents

- **Decision:** Recovery already stamped `resolved_ts`; schema (quarantine/block/apply_mapping) and
  optimization (scale/adjust/reprioritize) now do too, scoped to their fault types (schema_drift;
  ingress_burst/resource_contention).
- **Rationale:** Makes MTTR well-defined for every scenario under its owning agent, so the ablation
  isolates each agent's contribution.

## D-046 — Cost harvested per run; long-format CSV

- **Decision:** Per run the runner samples `resource_usage` and runs `compute_cost_windows`;
  `raw.csv` rows are `(run_id, config, scenario, replicate, seed, metric, value)` — one row per
  metric (`mttr_s`, `cost_units`, `manual_interventions`, `llm_tokens`, `wall_clock_s`).
- **Rationale:** Reuses the Phase 2 cost pipeline and gives the Phase 8 analysis a tidy long table.

---

## Phase 8 — Analysis, figures, report

## D-047 — Analysis lives in the package, not a bare `analysis/` dir

- **Decision:** The analysis code is `src/acde/analysis/` (importable), not a top-level `analysis/`
  scripts dir; the Makefile calls `python -m acde.analysis.{analyze,report}`.
- **Rationale:** Makes the statistics unit-testable and consistent with the rest of the `src/acde`
  package layout; the spec's `analysis/` maps 1:1 to `acde.analysis`.

## D-048 — Paper-claim mapping (45/25/70) and honest cost reporting

- **Decision:** The report compares our full-vs-baseline reductions to MTTR ↓45%, operational
  cost ↓25%, manual interventions ↓70% (my reading of the paper's abstract). Constants live in
  `config.py`. Because our cost model is compute-only (D-006), agent scaling can *raise* cost —
  reported as measured, with the caveat printed in the report.
- **Rationale:** The exact claim-to-metric mapping isn't specified; disclosing it (and the cost
  caveat) keeps the comparison honest.

## D-049 — Statistics choices

- **Decision:** `stats.py` — seeded bootstrap CI (10k resamples, deterministic), paired Wilcoxon
  signed-rank (baseline vs full, paired on scenario+replicate), Holm–Bonferroni across metrics,
  Cliff's delta. Undefined tests (tiny N, all-equal pairs) return a non-significant sentinel rather
  than crashing.
- **Rationale:** Matches §6; graceful degradation keeps the pipeline robust on small/`quick` data.

## D-050 — Headless figures; report appends DEVIATIONS

- **Decision:** `matplotlib` Agg backend → `results/figures/*.png`; `report.py` embeds them and
  appends the full `DEVIATIONS.md` to `results/results.md`.
- **Rationale:** Renders in CI/servers without a display; the report is a self-contained artifact.

## D-051 — `freshness_s` added to the per-run harvest; gate runs on synthetic data

- **Decision:** `harvest_metrics` also records `freshness_s` (latest run `pipeline_metrics`), so the
  freshness CDF has data. The automated gate runs analyze/figures/report on a synthetic `raw.csv`
  fixture (stats are unit-tested against known answers); the full quick-profile analysis is the
  manual checklist.
- **Rationale:** Keeps the gate fast and deterministic while still exercising the whole pipeline
  end-to-end (including matplotlib rendering).

## D-052 — Executor degrades gracefully on infra failure

- **Decision:** The Airflow-REST side effects (`_trigger_dag`, `_clear_task_instances`, `_patch_pool`)
  are wrapped in a bounded retry (tenacity; `executor_retry_attempts=3`,
  `executor_retry_backoff_s=0.5`, mirroring `db._db_retry`). If Airflow stays unreachable, `execute()`
  catches the `httpx.HTTPError`, escalates to a human (`telemetry.manual_interventions`), logs
  `action_execution_failed`, and returns `ExecutionOutcome(executed=False, outcome="execution_failed:
  …; escalated_to_human")` — it never lets the exception crash the agent cycle / control loop.
- **Rationale:** Matches the gate's existing fail-safe philosophy (OPA down ⇒ escalate). An
  operational agent must survive a transient dependency outage and hand off to a human, not die.

## D-053 — Failure-mode test strategy

- **Decision:** The three degrade paths are proven mostly by fast, offline unit tests — Airflow-down
  (`test_executor.py::TestInfraDegrade`, mocked `httpx.ConnectError`), OPA-down
  (`test_gate.py::test_opa_error_fails_safe_escalate`), and DB-blip (`test_db.py`, retried
  `OperationalError`). One marked integration test (`tests/integration/test_failure_modes.py`) stops
  the real `opa` container and asserts end-to-end escalation, restarting OPA in teardown.
- **Rationale:** Unit tests give a deterministic, zero-infra gate; one live container-stop test
  confirms the wiring without the flakiness of stopping every dependency on the colima/desktop split.

## D-054 — Data-license notes only (no code license)

- **Decision:** Ship `DATA_LICENSES.md` documenting the two data sources — TPC-DS (a TPC trademark;
  our data is synthetic and schema-faithful, not `dsdgen` output — see D-009) and NYC TLC (official
  public trip data, opt-in via `USE_REAL_TLC=1` — see D-012, used under the TLC terms of use). No
  source-code `LICENSE` file is added.
- **Rationale:** The paper-replication brief calls for dataset license notes specifically; the code
  license is the repository owner's call and is intentionally left unset (all rights reserved).

## D-055 — Full-system architecture diagram

- **Decision:** The README's Phase-0-slice mermaid is replaced with a full-system diagram spanning the
  data plane → telemetry → agents → gate → executor → experiment runner → analysis.
- **Rationale:** Phase 9 ships the reproducibility package; the diagram should reflect the finished
  system, not the Phase-0 scaffold.

## D-056 — Multi-provider live LLM path (Anthropic + Gemini)

- **Decision:** The live LLM call is provider-selectable via `llm_provider` (`"anthropic"` default |
  `"gemini"`). `LLMClient._live_call` dispatches to `_anthropic_once` (unchanged Claude path) or
  `_gemini_once` (Google `google-genai` SDK: `generate_content` with `system_instruction`,
  `temperature=0`, `max_output_tokens=llm_max_tokens_per_call`), sharing one retry-then-degrade
  wrapper. Gemini defaults `gemini-2.5-pro` / `gemini-2.5-flash`, overridable via `GEMINI_MODEL_*` in
  `.env`; key via `GEMINI_API_KEY` only. `MOCK_LLM=1` stays the default and is provider-independent.
- **Rationale:** User-requested — they have a Gemini key and want the agents to run live without an
  Anthropic key. This is a deviation from the otherwise Claude-standardized replication; Anthropic
  remains the default (honoring CLAUDE.md), Gemini is strictly opt-in and never touches the automated
  gate (which is mock-only). Model IDs are config-driven because provider model names change over
  time — a rejected ID is fixed in `.env`, not in code.

## D-057 — Generic OpenAI-compatible live LLM provider

- **Decision:** `llm_provider="openai_compatible"` routes live calls through the `openai` SDK against a
  configurable `oai_base_url` (default NVIDIA NIM `https://integrate.api.nvidia.com/v1`) with
  `oai_api_key` and `oai_model_reasoning`/`oai_model_fast` (defaults `z-ai/glm-5.2` /
  `meta/llama-3.1-8b-instruct`). One provider covers NVIDIA NIM, Groq, OpenRouter, and z.ai — any
  vendor exposing the OpenAI `chat/completions` API — by changing base_url + key in `.env`. A separate
  `oai_max_tokens_per_call` (default 8192, vs 1024 for the other providers) gives "thinking" models
  (e.g. GLM-5.2) room to emit their reasoning and still reach the JSON, which the existing
  `_extract_json` pulls out of the surrounding text. temperature=0 is kept (Rule 5).
- **Rationale:** User has an NVIDIA NIM key and wanted GLM-5.2; a generic OpenAI-compatible branch is
  the same effort as a vendor-specific one but avoids lock-in and unlocks the many free open models
  (Llama/GLM/DeepSeek/Qwen). Anthropic stays the default; this path is opt-in and never in the gate.

## D-058 — Credible non-agent baselines (rule-based + autoscaling)

- **Decision:** Beyond the paper's single static+human baseline, add two stronger, non-LLM baselines
  drawn from the paper's own related work: `rule_based` (threshold → predefined remediation, §II.C —
  auto-resolves `upstream_delay`/`resource_contention`/`ingress_burst` at a fixed `rule_remediation_s`,
  escalates schema drift to the human) and `autoscale` (§II.B — resolves only resource-pressure faults
  at `autoscale_reaction_s`, is data-blind so schema/upstream faults escalate). Both stamp fixed
  detection and hand uncovered faults to the existing `resolve_via_human`. Now in `ALL_CONFIGS`
  (quick=96 runs, paper=480). Verified ordering: agents ≪ rule/autoscale on covered faults ≪ human.
- **Rationale:** A reviewer's first objection is "agents only beat a *slow human*." These baselines
  answer "do agents beat cheap automation too?" — the single most likely rejection reason, front-loaded.

## D-059 — Decision-quality metric (correct mitigation, not just fast)

- **Decision:** Add a per-scenario ground-truth set of acceptable optimal mitigations
  (`decision_quality.EXPECTED_ACTIONS`) and harvest `decision_correct` (1.0 if the run logged an
  executed agent action in that set). Only meaningful for agent configs; non-agent baselines score 0
  by construction (they resolve without an agentic decision).
- **Rationale:** MTTR/cost measure *speed*, never whether the agent chose the *right* action. The paper
  never measures decision quality; adding it is both a gap-fix and a novel, honest contribution.

## D-060 — Freshness modeled as ingestion-stall duration

- **Decision:** For streaming (ingestion-stall) faults (`upstream_delay`, `ingress_burst`),
  `freshness_s` = the fault's open duration (`resolved_ts − injected_ts`); batch faults don't degrade
  streaming freshness → 0. Derived from independently-measured resolution timing (not fabricated).
- **Rationale:** Data-freshness lag *is* how long ingestion was stalled; this makes the previously
  trivially-zero metric meaningful without circularity.

## D-061 — Cost model v2: avoided over-provisioning

- **Decision:** Add a provisioning cost term: static configs hold `provisioned_units_static` for a
  fixed horizon; right-sizing configs (`autoscale`, `optimization_only`, `full`) hold
  `provisioned_units_rightsized`. Total cost = measured compute/storage (D-006) + provisioning.
- **Rationale:** The paper's cost reduction comes from the optimization agent right-sizing during low
  utilization, which the compute-only model (D-006) couldn't capture. v2 makes the ↓cost claim
  testable. The result depends on the provisioning gap assumption (disclosed), not tuned to the paper.

## D-062 — Adversarial safety evaluation

- **Decision:** `eval/adversarial.py` injects unsafe proposals and measures the OPA gate's containment
  rate (contained = denied or escalated, never silently allowed), plus contract-layer rejection of
  out-of-allowlist action types. Live result vs real OPA: containment = 1.0.
- **Rationale:** Operationalizes the paper's central "policy-bounded ⇒ safe" thesis, which the paper
  asserts but never stress-tests.

## D-063 — Cross-LLM reasoning study

- **Decision:** `eval/cross_model.py` runs each scenario through many models and scores decision
  correctness / latency / tokens, empirically testing the paper's §VI.A "model-agnostic" claim.
  Injectable probe (unit-tested); live sweep is opt-in/user-run.
- **Rationale:** The paper asserts model-agnosticism with zero data; this provides the data.

## D-064 — Bounded adaptation from logged outcomes

- **Decision:** `agents/adaptation.py` blends the empirical success prior of a (fault_type,
  action_type) pair into proposal confidence within fixed clamps; off by default
  (`adaptation_enabled=False`) so the benchmark stays deterministic.
- **Rationale:** Concretizes the paper's §V "outcomes incorporated into future reasoning cycles"
  claim, which it never specifies or evaluates. Gate still bounds every action.

## D-065 — Production trust core: execution modes, approvals, kill switch (v2, P1)

- **Decision:** Add a graduated-autonomy layer so companies can adopt safely. `acde_mode`:
  `shadow` (log proposals, never touch the pipeline), `approval` (queue allowed actions to
  `telemetry.action_approvals`; a human `approve`/`reject`, and approval re-runs via
  `executor.apply_action`), `autonomous` (execute). Side-effect-free acks always run; high-blast
  action types (`approval_required_action_types`) force approval even in autonomous. A durable kill
  switch (`control.desired_state['acde.paused']`, checked each loop tick) and a per-target hourly
  blast-radius cap bound the agents independent of policy. Slack-compatible webhook notifications
  fire on a daemon thread (never block the loop) with `params` redacted.
- **Code default stays `autonomous`** so the research benchmark's determinism and existing tests are
  unchanged; the production env template and `acde run` entrypoint select `shadow`. This is a
  deliberate split between the research default and the safe *production* default.
- **Rationale:** No company grants agents prod write-access on day one. Shadow → approval →
  autonomous is the standard trust ladder for AI ops tooling; the kill switch and blast-radius cap
  are non-negotiable production safety controls.

## D-066 — Connector boundary (attach to their orchestrator)

- **Decision:** External systems are reached only through a `Connector` (`src/acde/connectors/`):
  Airflow (configurable base_url, basic/bearer auth, TLS-verify) and noop (observe-only). Selected by
  `connector_kind`. `acde doctor` (`ops/health.py`) validates DB/OPA/connector/LLM/mode/webhook.
- **Rationale:** A production tool must attach to the *company's* stack, not require ours. The narrow
  interface makes Dagster/Prefect a new class, not a rewrite.

## D-067 — Product / research dependency split + Apache-2.0 license

- **Decision:** The lean production core (agents, gate, connectors, server, CLI) depends only on
  pydantic/psycopg/httpx/LLM SDKs/fastapi. The benchmark, chaos harness, analysis, and demo data
  plane move to the optional `acde[research]` extra (pandas/scipy/matplotlib/pyarrow/confluent-kafka),
  kept in the dev group so the full test suite still runs. The code is licensed **Apache-2.0**
  (LICENSE + NOTICE), **superseding D-054's "no code license"** now that this is a product companies
  adopt. Version bumped to 2.0.0.
- **Rationale:** A smaller, dependency-light image and a permissive, patent-granting license remove
  the two biggest blockers to enterprise adoption; the research artifact remains fully reproducible
  via the extra.

## D-068 — Differentiators: game-day rehearsal + ROI report

- **Decision:** `acde gameday` (`ops/gameday.py`) injects a controlled fault into a **staging**
  connector (hard-guarded by `connector_is_production`) and reports how the agents responded on the
  customer's own pipelines. `acde report` (`ops/roi.py`) summarizes the audit trail into an ROI
  artifact (auto-resolutions, MTTR p50/p90, tokens, an explicitly-labeled operator-hours-saved
  estimate). ROI is core; game-day needs the research extra (chaos harness).
- **Rationale:** These are the moat vs. observability tools (which only detect) and opaque AIOps
  (which act without evidence): a policy-bounded rehearsal + a renewal-grade ROI report, both on the
  customer's data. Reuses the existing chaos/agents/telemetry — high value, low new surface.
