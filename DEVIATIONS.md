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

## D-038 — Conflict rule via act order + shared lock (CORRECTED — see D-079)

- **Original decision (wrong, kept here for the record):** Reactive agents run
  `schema → recovery → optimization`; contending on the same target's advisory lock, recovery
  (earlier) wins and optimization (later) skips — implementing "recovery outranks optimization on
  the same target" with no special case. Distinct targets run independently.
- **Original rationale (wrong):** Simple, correct, and emergent from the locking primitive rather
  than bespoke priority bookkeeping.
- **Why it was wrong:** this was never actually true. `orchestrator/loop.py::_tick()` runs reactive
  agents strictly sequentially — `await`ing one `asyncio.to_thread(self._run_agent, name)` fully
  before starting the next — and `target_advisory_lock` releases the moment `_run_agent` returns,
  before the next agent even begins. There is no temporal overlap within one process's tick, so two
  agents proposing on the same target both acquire the lock in turn and **both would execute** —
  the exact opposite of "optimization skips." The lock is real and still needed (D-037), just not
  for the property this entry claimed it provided; it protects against a *different process* acting
  on the same target concurrently, not intra-tick contention. See D-079 for the fix and how it was
  found and verified.

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

## D-069 — Fixed a real test-isolation gap: `ControlLoop` unit tests were hitting a live database

- **What happened:** The P1 kill-switch/blast-radius integration added `control.is_paused()` (in
  `loop._tick`) and `control.blast_radius_exceeded()` (in `loop._run_agent`) as new calls in the
  control loop. `acde.orchestrator.control` does its own `from acde import db` import, so mocking
  `db` on the `loop` module (as `tests/unit/test_loop.py` already did) never intercepted these new
  calls — they reached a *real* Postgres. Every run during development had a live stack reachable via
  `DOCKER_CONTEXT=desktop-linux`, so the real calls silently succeeded and the bug was invisible
  locally; it would have failed in CI (no live DB there) and in any clean environment — a real
  violation of the project's "unit tests: no docker, no network" rule.
- **Fix:** `test_loop.py` now mocks `control.is_paused` / `control.blast_radius_exceeded` directly,
  plus two new tests exercise the integration itself (`test_paused_runs_nothing`,
  `test_blast_radius_exceeded_skips_action`) — this wiring had zero unit coverage before, only the
  `orchestrator/control.py` functions were tested in isolation. Verified by re-running the full unit
  suite with `POSTGRES_PORT=1` (guaranteed-unreachable), confirming true isolation this time.
- **Lesson:** a local shell with a live dev stack can mask test-isolation bugs that a real CI runner
  would catch immediately. Verifying "tests pass" against a live stack is not sufficient evidence for
  unit-test hygiene — periodically run the suite with the database *actually* unreachable.

## D-070 — Multi-actor operator API auth (Tier 2, T2.1)

- **Decision:** the JSON operator API's `actor` field on `/approvals/*` was client-supplied
  (`actor: str = "api"`) — anyone holding the one shared `X-API-Key` could claim to be anyone in the
  audit trail. New `api_keys` setting (CSV `actor:key,actor:key`) plus a unified `_authenticate`
  dependency (X-API-Key header **or** HTTP Basic, both checked against the same `api_key_map`)
  resolves every request to a real actor name; `/approvals/*` now take `actor: str =
  Depends(actor_dep)` instead of a writable field. The legacy single `api_key` keeps working
  unchanged (maps to actor `"operator"`) — fully backward compatible.
- **Rationale:** "who approved what" only means something if the identity can't be spoofed. Verified
  live against the real stack: authenticated as `alice`, approved a real pending action, confirmed
  `telemetry.action_approvals.decided_by = 'alice'` in the database.

## D-071 — Server-rendered operator dashboard (Tier 2, T2.2)

- **Decision:** `GET /ui` + `POST /ui/approvals/{id}/approve|reject` (Jinja2, no JS, no external
  assets/CDN — works air-gapped), authenticated via the same `_authenticate` dependency as the JSON
  API (HTTP Basic for a native browser credential prompt), calling the exact same
  `acde.human.approvals` functions as the JSON endpoints — no separate, weaker write path. Upgraded
  from a purely read-only dashboard (the original Tier 2 description) to an actionable one, since
  D-070 already ties every request to a real identity, making approve/reject exactly as safe as the
  JSON API.
- **Rationale:** the single feature most likely to make ACDE usable by a non-CLI stakeholder.

## D-072 — Integration tests proven in CI, not just claimed (Tier 2, T2.3)

- **Decision:** new `integration` CI job runs `make up && make seed && make test-integration && make
  down` against the real stack (Postgres/OPA/Redpanda/Airflow) — the exact same Makefile targets as
  local dev, not a reimplementation as native Actions `services:` containers. Runs on push to `main`
  only (not every PR): building the Airflow image and waiting for the full stack takes real minutes
  and is slower/flakier on fork-PR runners with no build cache, so fast PR-blocking checks
  (quality/opa-test/docker-build) stay unaffected.
- **Rationale:** "production ready" was previously a doc claim, never verified by CI. Verified live:
  the job passed in 4m11s on a completely fresh GitHub Actions runner (26/26 integration tests).

## D-073 — Second connector: Prefect, not Dagster (Tier 2, T2.4)

- **Decision:** `connectors/prefect.py` implements the same `Connector` protocol as the Airflow
  connector against Prefect's REST API (deployments, flow runs, work-pool concurrency limits).
  Chosen over Dagster because Dagster's primary control surface is GraphQL, which would need a
  materially different client shape; Prefect maps directly onto the existing REST-shaped protocol.
  One honest, documented gap: Prefect has no per-task "clear failed tasks" concept like Airflow, so
  `clear_tasks` retries the whole flow run instead (not silently faked as finer-grained).
- **Rationale:** proves the `Connector` abstraction generalizes beyond the one system it was
  originally built against, without inventing a second, incompatible integration pattern.

## D-074 — Concurrent `tpcds_ingest` DAG runs race — root-caused, fixed, verified

- **Status: VERIFIED.** Fixed in `90a969a`; the `integration` job (the one this flake lived in) has
  been green on every push since — `90a969a` (the fix itself), `4f305a5`, and `31373812852` — three
  consecutive clean runs with zero recurrence, on top of the local reproduction below.
- **What happened:** `test_batch_dag_materializes_versioned_partition` (`test_dataplane.py`, Phase 1)
  triggers `tpcds_ingest` and polls for a terminal state; it failed with a genuine Airflow `failed`
  DAG state (not a client-side poll timeout) on 2 of 3 fresh CI runs. Diagnostic logs (added in the
  Tier 2 pass) showed the trigger: the recovery agent's `replay` action
  (`policy/executor.py::_trigger_dag`, Phase 3) also triggers `tpcds_ingest` — with a `recovery__`
  run-id prefix — from an earlier test in the suite (`test_agents_e2e.py` / `test_orchestrator_e2e.py`),
  asynchronously, without waiting for completion. When that in-flight run overlapped with
  `test_dataplane.py`'s own trigger of the *same shared DAG*, both `ingest` tasks failed fast
  (~0.3–0.7s, a real exception, not a timeout).
- **Actual root cause (found in this pass):** `PartitionVersionManager.create_version`
  (`dataplane/partitions.py`) read `MAX(version)` and then, in separate unpooled statements,
  `DROP TABLE IF EXISTS` → `CREATE TABLE` → insert → register — with no locking across that
  sequence. Two concurrent callers for the same `(dataset, partition_key)` (`tpcds_daily_revenue`,
  `2026-01` — the only partition either code path ever writes) both read the same `MAX(version)`,
  computed the same "next version", and raced to `DROP`/`CREATE` the *identically-named* physical
  table while the other was still inserting into it, colliding on `partition_versions`' primary key
  or Postgres' internal type catalog. This is exactly the "concurrency-unsafe resource in the
  `ingest` task" suspected in the original diagnosis, now identified precisely rather than left as
  "most likely file I/O".
- **Fix:** `create_version` now runs version assignment, table creation, row insert, and the
  registry insert inside **one transaction** holding a `pg_advisory_xact_lock` keyed on
  `(dataset, partition_key)`. A second concurrent caller for the same partition blocks until the
  first commits, then correctly reads the incremented version — no more collision. The lock is
  transaction-scoped (auto-releases on commit or rollback), so a crash mid-critical-section can't
  leak it the way a session-level lock could. `next_version()` stays as a standalone read for
  callers that just want to peek; `create_version` no longer calls it (its own locked read replaces
  that call site).
- **Verified against a real race, not just unit mocks:** spun up an ephemeral local Postgres
  (`initdb` + `pg_ctl`, no Docker) with the actual `warehouse.partition_versions` DDL, then fired 12
  threads at `create_version` for the exact same `(dataset, partition_key)` simultaneously.
  - **Pre-fix code (reverted to `git show HEAD:...` for the test): 11/12 failed** —
    `DuplicateTable: relation "tpcds_daily_revenue__2026_01__v1" already exists`,
    `UniqueViolation: duplicate key value violates unique constraint "pg_type_typname_nsp_index"` —
    reproducing the exact failure signature (fast, real exceptions) reported by CI.
  - **Post-fix code: 12/12 succeeded**, versions `[1..12]` all unique, zero errors.
- **Kept from the original diagnosis pass:** the CI diagnostics step (dump
  `airflow-scheduler`/`airflow-webserver` logs on `integration` job failure) that made the original
  root-causing possible.

## D-075 — `docker/airflow.Dockerfile` pinned to `uv.lock` instead of resolving live from PyPI

- **What happened:** the Airflow image installed acde via a plain `pip install /opt/acde`, which
  re-resolves every dependency fresh against whatever's newest on PyPI at build time — not pinned to
  `uv.lock` the way `deploy/Dockerfile.server`'s build already is. This broke `integration` in CI:
  once a new `uvicorn` release landed on PyPI, pip's resolver hit `ResolutionImpossible` inside that
  specific install context and the whole stack failed to build.
- **Fix:** added a `lock-export` build stage (`python:3.11-slim` + `uv`, same pattern the server image
  already uses) that runs `uv export --frozen --format requirements-txt --no-emit-project` against the
  committed `uv.lock`, then the Airflow stage installs from that pinned, hashed requirements file
  before installing the acde package itself with `--no-deps`. This image now resolves to the exact
  same dependency versions as every other build in the project, eliminating the "fresh PyPI release
  breaks the build" failure class entirely rather than just patching this one instance of it.
- **Known, pre-existing, non-blocking tension (not introduced by this fix):** pip prints soft
  dependency-conflict warnings on install — several of Airflow's own bundled provider packages
  (`apache-airflow-providers-google`, `-snowflake`, `msal`, `gcloud-aio-*`) declare narrower pins
  (older `pandas`/`cryptography`/`packaging`) than what acde's own pinned versions install. These are
  warnings, not errors; the install completes, `import acde.*` works, all 26 integration tests pass
  against the built image, and `airflow dags list-import-errors` reports zero import errors. The
  original unpinned Dockerfile would have hit this same tension once those provider packages'
  constraints and acde's core deps drifted far enough apart regardless — pinning didn't create it,
  it just surfaced it as a visible (non-fatal) warning instead of letting it fail silently later.

## D-076 — `temperature=0` moved to `extra_body` for the Anthropic provider (SDK v1.0, API-level change)

- **What happened:** `anthropic-sdk-python` v1.0 removed `temperature`/`top_p`/`top_k` as typed
  keyword arguments on `messages.create()` — not an SDK-only deprecation, but reflecting a real API
  change: "current models do not use these sampling parameters" (Anthropic's own migration guide,
  whose own before/after example uses `model="claude-sonnet-4-6"` — this project's `MODEL_REASONING`).
  Passing `temperature=0` directly is now a `TypeError` at the Python call layer, which would have
  broken `_anthropic_once` — the default LLM provider — on the very first live (non-mock) call. CI
  never caught it: this path is `# pragma: no cover - requires the Anthropic API`.
- **Fix:** pass `extra_body={"temperature": 0}` instead of the removed keyword. Per the same migration
  guide, this is a no-op on current models (which have no sampling parameter to set) and is honored on
  older models that predate the change — never an error either way, so it's correct to send
  unconditionally rather than branch on model version. Verified structurally: constructing the same
  call against a real `anthropic.Anthropic()` client with a fake key raises `AuthenticationError`
  (the request reached the server), not `TypeError` (which would mean the client rejected the call
  shape before sending it) — confirms the fix is accepted at the call layer, the deepest check
  possible without spending real API credits.
- **What this means for D-035/D-036 (temperature=0 determinism, "both accept temperature=0"):** those
  entries' premise — that the configured models honor an explicit `temperature=0` — is no longer
  literally true for `claude-sonnet-4-6`/`claude-haiku-4-5` specifically; current Claude models have no
  sampling parameter to set at all, i.e. they're deterministic (or run some fixed, unconfigurable
  decoding) by default rather than by an explicit `temperature=0` request. The *intent* of D-035/D-036
  (deterministic live-path behavior) is unaffected — this is a documentation-of-mechanism correction,
  not a behavior change ACDE asked for or controls.

## D-077 — Proactive concurrency fuzzing, not just a D-074 patch

- **Decision:** `tests/integration/test_concurrency_fuzz.py` turns the disposable script that found
  D-074 into a permanent regression test: `ThreadPoolExecutor` fires 20 real concurrent workers at
  `PartitionVersionManager.create_version` across a small pool of shared `(dataset, partition_key)`
  targets (randomly assigned via a seeded RNG — only the *target assignment* is seeded; real OS
  thread interleaving is deliberately left alone, since genuine non-deterministic scheduling is what
  a concurrency fuzzer needs to exercise the race window at all). Asserts no worker raised, every
  target's version numbers are exactly `{1..N}` with no duplicates, `partition_versions` row counts
  match exactly, and every created physical table is genuinely queryable.
- **Verified both directions**, not just that it passes: ran 3x against the current (fixed) code —
  clean every time — then temporarily reverted `partitions.py` to its pre-D-074-fix state and ran it
  3x again — failed every time with the same collision. Confirms the test actually discriminates
  fixed from broken, not just that it happens to pass.
- **Rationale:** the user asked to go beyond the known-issues list and make the project genuinely
  better, not just keep patching the D-074 instance whenever it resurfaces. A generic, reusable
  concurrency-fuzz *methodology* (extendable to other shared-state mutators if one is ever found)
  is worth more than a second one-off script that gets thrown away again.
- **Disclosed, intentional risk:** if any *other* latent race exists in this code path, this test can
  turn `integration` red on a run unrelated to whatever else changed. That is the point — catching a
  future D-074-class bug before it ships is worth an occasional investigation, not something to
  suppress by weakening the assertions.

## D-078 — OPA policy audit: real dead code found and fixed, exhaustive coverage added

- **Dead code found:** `infra/opa/policies/rate_limit.rego` (package `acde.rate_limit`) was never
  imported or referenced by `main.rego` — the aggregating entrypoint reimplemented the exact same
  `>= 5` threshold check inline instead of delegating. Two byte-identical copies of the same policy
  logic, only one of them ever reachable from the real decision path; `rate_limit_test.rego` was
  faithfully testing code no live request could ever exercise. Fixed: `main.rego` now delegates to
  `data.acde.rate_limit.result`, matching the pattern already used for `cost_budget`/`recovery`/
  `schema`. Verified behavior-preserving: all 20 pre-existing tests passed unchanged before and after.
- **Exhaustive combination coverage added** (`coverage_test.rego`): a property test iterating all 18
  legitimate `(agent, action_type)` pairs from `src/acde/contracts/actions.py::ACTION_TYPES` (the
  actual runtime source of truth — a `ProposedAction` can't be constructed outside this set), asserting
  every one reaches a real policy branch and never falls through to `default decision`. 7 of the 18
  combinations had never been exercised by any test before this. **Verified it actually catches the
  bug it exists for**, not just that it passes: temporarily deleted the `reprioritize_pipeline` branch
  from `main.rego` — the new test failed exactly there (`policy_id == "default"`), confirmed via
  `opa test`'s trace output; restored, re-confirmed 24/24 green.
- **Boundary-condition gaps closed:** (1) `cost_budget`'s exact-equal case
  (`projected_marginal_cost == budget_remaining_units`) was untested — the rule is `<=`, so an
  accidental `<` would silently deny every action that spends a budget down to precisely zero;
  verified the new test catches that exact mutation (`<=` → `<` locally, test failed, reverted). (2)
  `schema.rego`'s `contain` rule (quarantine/block) has **no condition on `schema_compat` at all** —
  it fires on `action_type` alone, allowing pre-emptive quarantine before compat is even classified.
  This was true but never locked in by a test; added one asserting quarantine still allows+escalates
  with `schema_compat: "backward"`, not just `"breaking"`.
- **Verified against the exact CI-pinned OPA version**, not just a newer local install: ran
  `make opa-test` against the live `openpolicyagent/opa:0.68.0-debug` container (same version CI's
  `setup-opa` action installs) — 24/24 pass. Also queried the real running `/v1/data/acde/policy/
  decision` HTTP endpoint directly (what `gate.py` actually calls in production) for the
  `reprioritize_pipeline` case specifically, confirming the fix holds end-to-end, not just inside
  `opa test`'s own test runner.
- **Rationale:** this is the OPA-side counterpart to D-077 — going beyond "the known issues are
  patched" to systematically audit the policy surface itself for the two failure modes a
  hand-maintained decision table is most prone to: dead/duplicated branches, and untested boundary
  conditions at the exact thresholds the logic depends on.

## D-079 — Real bid-based conflict resolution, replacing D-038's non-functional lock-order claim

- **Found while implementing the paper's §X "explicit multi-agent negotiation" future-work item**:
  tracing `orchestrator/loop.py` to build genuine negotiation surfaced that D-038's existing
  "recovery outranks optimization" guarantee was never actually enforced (see D-038's correction
  above) — reactive agents run sequentially with a lock that releases between them, so both would
  execute regardless of order. This was there to fix, not something introduced now.
- **Fix:** `_tick()` now runs three explicit phases instead of one combined observe-reason-lock-act
  call per agent. **Propose** — every enabled reactive agent's `observe()`+`reason()` runs first,
  with no side effects, still in `schema → recovery → optimization` order for deterministic logging
  (order no longer decides anything). **Resolve** (`_resolve_conflicts`) — proposals are grouped by
  `action.target`; a target with one proposal passes through untouched; a target with 2+ resolves by
  bid, `(AGENT_PRIORITY[agent], action.confidence)` compared as a tuple, highest wins. **Act** — only
  winning proposals go through the unchanged lock-then-blast-radius-then-act sequence
  (`_act_on`, extracted verbatim from the old `_run_agent`'s tail — `_run_agent` itself is untouched
  and still used for `monitoring`, which never contends).
- **Priority order** (`recovery=3 > schema=2 > optimization=1`, `confidence` a tiebreaker only): a
  judgment call, not something to leave ambiguous — recovery is fixing a live failure, the most
  time-critical action class in this system; schema is a real data-integrity concern but rarely as
  urgent as an in-progress recovery; optimization is cost/performance, least urgent by construction.
  `confidence` can't actually break a tie today (each reactive slot proposes at most once per tick),
  but it's a real signal already on every `ProposedAction` and the interface is correct if that ever
  changes. Losing proposals get `"outbid by {winner} on {target}"` — never confused with a lock-skip
  or a blast-radius-skip, both of which already existed as separate, distinguishable outcomes.
- **Verified the fix actually fixes something**, not just that it passes: `_resolve_conflicts`'s
  logic was temporarily reverted to trivially return every proposal as a winner (simulating the
  original bug precisely — no resolution at all) and the new negotiation tests failed exactly as
  expected (`recovery`/`schema` no longer beating `optimization` on a shared target); restored,
  re-confirmed 14/14 `test_loop.py` green. `TestRunAgent`'s 4 pre-existing tests needed zero changes
  (pure extraction into `_act_on`, confirmed byte-for-byte behavior-preserving).
- **Honest limitation, not glossed over:** traced `llm/mock.py`'s scenario handlers — `recovery`
  always targets `"tpcds_ingest"`, `schema` always targets `"tpcds_daily_revenue"`,
  `optimization` always targets `"streaming"`/`"default_pool"`. No combination of mock scenarios can
  produce same-target contention between two different agent types, so this negotiation logic,
  correct and unit-tested, is **not exercised by any current `MOCK_LLM=1` integration test** — it's
  a safety net for the live-LLM reasoning path (where a real model could plausibly choose
  overlapping targets that the deterministic mock never does), verified at the unit level with
  hand-built proposals rather than fabricated into an integration scenario that doesn't reflect how
  the mock actually behaves.

## D-080 — `OAI_MODEL_FAST` default was dead on NVIDIA's endpoint, found via first live-LLM smoke run

**What happened:** first `make agents-live-smoke` run (`MOCK_LLM=0`, real NVIDIA NIM endpoint) since
the API key was configured. 3 of 4 agents (schema/optimization/recovery, using
`OAI_MODEL_REASONING=nvidia/nemotron-3-ultra-550b-a55b`) got real `200 OK` responses. The monitoring
agent, which uses `OAI_MODEL_FAST`, got `HTTP 410 Gone`: `meta/llama-3.1-8b-instruct` "has reached
its end of life on 2026-08-26T09:00:00Z and is no longer available" — retired by NVIDIA the same day
this was first exercised live. `llm.client` logged `llm_unavailable` and the agent fell back to
`no_action` rather than crashing — the fail-safe path worked correctly; this was a config staleness
bug, not a code bug.

**Fix:** queried NVIDIA's live `/v1/models` endpoint for available fast-tier models, picked
`nvidia/nemotron-3-nano-30b-a3b` — same family/naming convention as the reasoning model already in
use (`nemotron-3-ultra-550b-a55b`: ultra vs. nano tier), rather than an unrelated provider's model.
Updated the tracked default (`config.py`'s `oai_model_fast`), `.env.example`, and the local `.env`
override to match; fixed `test_llm_client.py::test_openai_compatible_uses_oai_models`, which had
hardcoded the dead model string as an assertion. Re-ran the smoke test: all 4 agents now get real
`200 OK` responses. Full `make lint && make test-unit` green (389/389) after the fix.

**Why this matters beyond the one string:** this is the first evidence that `MOCK_LLM=1` being the
default everywhere (by design, for deterministic zero-cost CI) means model-catalog staleness is
invisible until someone runs live — there is no test that catches a provider retiring a model out
from under a hardcoded default. Not fixing that gap now (would need a scheduled live liveness check
against real provider catalogs, itself a live-API cost and complexity tradeoff); noting it here as
the honest limitation rather than silently patching the one string and moving on.

## D-081 — First full live-LLM validation pass (quick profile, all 8 configs x 4 scenarios x N=3)

**What ran:** `MOCK_LLM=0`, real NVIDIA endpoint (`nemotron-3-ultra-550b-a55b` reasoning /
`nemotron-3-nano-30b-a3b` fast, post D-080), `experiments.runner --profile quick`, isolated into
`results/live-quick/` so it wouldn't collide with the existing mocked manifest (run IDs are
`config__scenario__replicate`, independent of `experiment_run`, so a shared manifest would have
silently skipped every run as "already done" — first attempt did exactly this, 0/96 ran, caught by
checking the manifest before assuming the run itself was broken).

**Result:** 96/96 runs, `status: ok`, zero errors. 60 of those (`monitor_only`/`recovery_only`/
`optimization_only`/`schema_only`/`full`) made real Nemotron calls end-to-end through the full
observe → reason → OPA gate → act pipeline. Per-scenario average wall time: `schema_drift` 23.8s,
`upstream_delay` 20.9s, `ingress_burst` 24.9s, `resource_contention` 207.5s — the last is not a
live-LLM regression; `resource_contention` runs a real in-process CPU stressor (`chaos/stressor.py`,
D-026, `STRESS_USE_CONTAINER=0`) on the same host as the experiment runner and the real HTTPS/TLS
calls to NVIDIA, so contention slows everything sharing that CPU. Confirmed by the same ~200s figure
appearing consistently across every agent config that hit this scenario, not just one.

**Scope, stated plainly:** this validates the live path *works* — real calls, real policy gates,
real actions, no crashes — not decision *quality*. That's what the full `paper` profile (480 runs,
~28-30h live, real ongoing cost) would speak to; deliberately not run yet. This quick pass was
the risk-reducing step before committing to that cost/duration, per plan.

## D-082 — Recovery agent's live-model target hallucination: real infra guard + prompt fix

**What was found**, digging into D-081's live-quick results: `decision_correct` for `full` dropped
from 100% (mock) to 66.7% (live). Traced via `telemetry.agent_actions` and the executor's own
logs: 13 of 28 (46%) real `recovery`-agent proposals set `target` to the run's own `experiment_run`
scaffolding id (e.g. `full__ingress_burst__r0`) instead of a real dag/dataset — the model echoed a
field it saw elsewhere in the `TelemetrySnapshot` JSON rather than reasoning to a real target,
apparently when `task_runs` was too sparse (early in a fault) to give it one. The executor correctly
tried the real Airflow call, got `404 NOT FOUND` on `/dags/{garbage}/dagRuns`, retried per the
bounded-retry policy (pointless for a 404, which is permanent, not transient), then degraded to
`escalate_to_human` — the system never crashed or acted on the bad target, but it wasted a live API
round-trip + retries every time, and it's a real reasoning gap the mock could never surface.

**Fix, two layers (defense in depth, matching this project's existing pattern of never trusting the
model alone):**
- **Prompt** (`llm/prompts/recovery.md`): added an explicit rule — if `task_runs` is empty or no
  real dag_id/dataset is visible, output `escalate_to_human`/`target: none`, and never reuse an id
  from elsewhere in the input. Soft signal; models don't reliably follow prose instructions.
- **Deterministic guard** (`policy/executor.py::apply_action`): before dispatching to any
  infra-touching handler, reject `target == experiment_run` outright — logs `invalid_target`,
  returns `executed=False` immediately, skips the doomed live call. `AUTO_ACTIONS`
  (`no_action`/`raise_anomaly`/`allow_compatible`) are exempt since they never touch a real target.
  This is the layer that actually matters: it holds regardless of whether the model follows the
  prompt fix, closing a semantic gap pydantic's structural `ProposedAction` validation can't catch
  (a non-empty string is still a valid string even when it's the wrong one).

**Verified the fix actually fixes something:** `TestInvalidTarget::test_target_equal_to_...` was
run against the guard temporarily disabled (`if False and ...`) — it failed exactly as expected,
the mocked Airflow client's `_trigger_dag` fired and "succeeded," reproducing the real bug's shape
in miniature; restored, re-confirmed 18/18 `test_executor.py` green, then full `make lint &&
make test-unit` (392/392). Note this does **not** raise `decision_correct` for a run where the
model genuinely had nothing to recover with — correctly escalating with no target *is* correct
behavior, it just doesn't count as a successful recovery under the paper's scoring, which is honest
rather than something to paper over.

## D-083 — Migration framework: production had no way to reach an existing database at all

**Found via systematic production-readiness audit** (`docs/specs/2026-08-27-production-hardening-design.md`),
not a test failure: `dataplane/migrate.py` resolved its SQL directory as `parents[3]` — the repo
root. That path exists in a dev checkout but not inside the installed wheel
(`packages = ["src/acde"]` in `pyproject.toml`), so in the production Docker image it silently
no-opped (`migrate_no_init_dir`, swallowed as a warning). Combined with Postgres only running
`docker-entrypoint-initdb.d` on first volume init: **there was no way to get a schema change into
an existing production database.** Every fix in this session's remaining hardening work needs one.

**Decision: a small forward-only runner (`src/acde/migrations/`), not Alembic.** Alembic assumes
SQLAlchemy, which this project deliberately does not use (see `server/metrics.py`'s hand-rolled
Prometheus exposition, avoiding a client library at this scale) — pulling in an ORM dependency
just for its migration tool would be a bigger footprint than the ~200-line runner this needs.
Simplest defensible option per CLAUDE.md's underspecified-decision rule.

**Guarantees, each proven against the real running stack, not just mocked unit tests:**
- Migrations live *inside the package* (`src/acde/migrations/NNN_name.sql`), so they ship in the
  wheel — fixes the actual bug, not just the symptom.
- One transaction per migration, version row written in the same transaction: verified live —
  re-running `apply()` against an already-migrated database is a genuine no-op (`migrations_up_to_date`).
- Checksum guard: verified live by tampering with the applied `001_baseline.sql` on disk and
  confirming `apply()` refuses with `MigrationError` naming the exact mismatch, then restoring and
  reconfirming clean.
- `pg_advisory_lock` around the whole run, so concurrent replica startups serialize instead of
  racing (unit-tested at the mock level here; the underlying primitive is the same one Postgres
  itself provides and `orchestrator/locks.py` already relies on for per-target locking).
- `001_baseline.sql` is generated verbatim from the existing `infra/postgres/init/*.sql` (still
  the fresh-volume path) — a database created either way converges on the same schema. No table
  was dropped, retyped, or had data moved.
- Wired into `acde doctor` (a new `migrations` check, pending migrations show red) and the
  production Docker entrypoint (`deploy/docker-entrypoint.sh` runs `acde migrate` before `exec`ing
  `acde serve`/`acde run`) — so this is now unavoidable in the actual startup path, not an unused
  CLI command sitting next to the same silent-no-op risk it replaces.

**Bug caught by the test suite itself, not manual review:** the first version of
`log.info("migration_applied", extra={"name": migration.name})` raised `KeyError: Attempt to
overwrite 'name' in LogRecord` — `name` collides with `logging.LogRecord`'s own attribute. Renamed
to `migration_name`. Left here as a reminder that `extra=` dict keys need checking against
`LogRecord`'s reserved names, not just against each other.

**Honest gap**: the local Docker build to verify the new entrypoint could not complete in this
environment — repeated `cannot decrypt peer's message` TLS errors mid-package-download, which is a
local Docker Desktop networking issue (this project's own `docs/OPERATIONS.md` already warns
Docker Desktop isn't reliable for sustained work), not a code defect. `sh -n` confirms the
entrypoint script's syntax; the authoritative check is CI's `docker-build` job on clean runners,
checked after push.

**Two real bugs found by CI itself, not by local review, after push:**
- `python -m acde.migrations` failed with `No module named acde.migrations.__main__` — a package
  doesn't execute its `__init__.py`'s `if __name__ == "__main__"` guard via `-m`; it needs its own
  `__main__.py`. Broke `make migrate`/`make seed` everywhere, caught by the integration job.
- `TestDoctor.test_all_ok_when_deps_healthy` didn't mock the new `_check_migrations`, so it hit a
  real (absent) DB connection in the no-docker unit-test job. Fixed, and used the gap to add direct
  coverage for `_check_migrations`'s three paths (pending / up to date / error), which had none.

## D-084 — Write-ahead audit trail: an executed action could be lost entirely

**The defect** (audit finding #1, `docs/specs/2026-08-27-production-hardening-design.md`):
`agents/base.py::act()` called `executor.execute()` — the real Airflow API call, the real
`control.desired_state` write, the real quarantine — and only *after* it returned did it write the
`telemetry.agent_actions` row. A crash, OOM-kill, or DB blip in that window meant the action really
happened and there was no record of it at all. `orchestrator/loop.py::_tick()` swallows exceptions
("a bad tick must not kill the loop"), so this failure mode is silent. For a product whose central
claim is "every action is policy-gated and auditable," an unauditable executed action falsifies
that claim.

**Fix**: `act()` now writes an intent row (`status='executing'`, policy verdict already known and
recorded — it's decided before the side effect runs) *before* calling `executor.execute()`, then
updates the same row with the outcome and a final status (`executed` / `denied` / `escalated` /
`failed`, derived from `outcome.executed` and the policy verdict). `db.execute()` opens and closes
its own connection per call (confirmed in `db.py`), so the write-ahead INSERT is a fully committed,
independent transaction before execution begins — not something a later crash can unwind.

**New migration** (`002_audit_status.sql`): `status` column, `NOT NULL DEFAULT 'executed'` — a
fast-default add-column (PG 11+, no table rewrite), so every existing row keeps exactly its current
meaning. A partial index on `status = 'executing'` is the query an operator (or an alert, wired in
a later step) uses to find actions stuck mid-flight.

**Verified the fix actually fixes something**, the same discipline as every fix this session:
`executor.execute()` was moved back to *before* the write-ahead insert (simulating the exact
pre-fix ordering) and the new test caught it precisely — `exec_mock.call_count == 0` on a crash
during execution, proving the pre-fix defect exactly as described (the action vanishes, not even a
partial record). Restored, reconfirmed 13/13 (now 15/15 with the denied/escalated branch tests)
green. Also re-verified live: applied the migration against the already-populated real table, ran a
real agent cycle, confirmed the terminal `status='executed'` end-to-end.

**Also fixed while touching this code path** (small, same endpoint, not scope creep): `/audit`
gained `since`/`until` ISO-8601 filters — the design doc's audit finding #7 ("no way to answer
'what happened on date X'") — and both `/audit` and `/proposals` now surface `status`.

## D-085 — Tenant/environment schema boundary, deliberately not a SaaS control plane

**Directed decision, not an underspecified one**: "design for eventual multi-tenant hosted SaaS,
but do not over-engineer it yet; establish clean tenant/environment boundaries now so the schema
can evolve safely" — and "strict server-side isolation." Recorded here anyway per this file's
purpose: what was actually built and why, not just what was asked.

**What exists**: two new `Settings` fields, `tenant_id`/`environment` (both default `"default"`),
resolved only from server-side config (`acde.tenancy.current_scope()`) — never from a request, an
agent's proposed action, or any other client-controllable input. Every scoped telemetry table
(`agent_actions`, `failure_events`, `resource_usage`, `pipeline_metrics`, `cost_ledger`,
`manual_interventions`, `task_runs`) gained both columns via a fast-default add-column migration
(003, no rewrite) and every one of the 9 write sites across 6 modules now stamps them.

**What deliberately does not exist yet, and why**: a tenant registry, per-request tenant
resolution, or any routing that lets one *database* serve multiple tenants. `tenant_id` is
constant for the life of a deployment today — every self-hosted install is exactly one tenant,
which is 100% of current real usage. Building request-level multi-tenancy now (deciding how a
tenant is created, how an API key maps to one, how a shared database enforces row-level isolation)
is the actual SaaS control plane, a materially larger feature with its own auth/billing/routing
model — building it before there's a second tenant to serve would be inventing requirements rather
than serving a real one. This is the schema decision that makes it possible without another
data-touching migration later, not the feature itself.

**"Strict server-side isolation," honestly delivered for what's built now**: `tenant_id` can never
be client-supplied — it comes from the process's own config, the same principle the multi-actor
audit system already applies correctly to the *actor* field (`server/app.py`'s `_authenticate`
resolves the actor server-side; a client cannot claim to be someone else). The isolation claim
here is real but scoped to what's true today: one tenant per deployment, enforced by the fact that
there is one deployment's database, not by a query-time filter that doesn't exist yet.

**Not conflated with the existing multi-actor auth (D-070)**: an "actor" (an API key's named
holder) is a human or service operating a deployment, not a tenant — a multi-actor deployment
today is *one* tenant with several operators sharing full visibility (an ops team), and that
existing, intended behavior would break if actor were silently treated as tenant_id. Kept as two
separate, currently-orthogonal concepts on purpose.

**Verified**: migration 003 applied against the already-populated real database (104 failure
events, 2812 cost_ledger rows, 1365 resource_usage rows, 105 manual interventions, 198 agent
actions from the integration suite) — every existing and new row correctly `tenant_id='default',
environment='default'`, confirmed via direct query, not assumed. Full unit (413) and integration
(27) suites green.

## D-086 — Hot-path indexes, retention, and a benchmark that reported an honest mixed result

**Indexes lead with `experiment_run`, not `tenant_id`** — a deliberate refinement of the design
doc's original wording. `tenant_id` is constant across every row in the single-tenant deployment
that exists today (D-085), so it gives the query planner nothing to select on; `experiment_run` is
what every one of these queries actually filters by. Migration 004 adds indexes matching the real
predicates of the 3 hottest queries: `blast_radius_exceeded` (runs before every action),
`_open_faults` (every control-loop tick), and `/audit`'s `ORDER BY ts DESC`.

**Benchmark methodology** (`acde.analysis.bench_hot_paths`, checkpoints 10³/10⁴/10⁵ — not the
design doc's 10⁶, judged impractical for this environment's Docker Postgres; noted as a scope
reduction, not silently substituted): seeds synthetic rows tagged with a throwaway
`experiment_run`, times the real queries, deletes everything it added. First run exposed a
methodology bug in itself — an even 33/33/33 split across `policy_decision` values doesn't
resemble reality; checked the real table (198 rows: 183 allowed, 11 escalated, 4 denied) and
reweighted the synthetic seed to match (92/6/2) before trusting the results.

**Measured, at 100k rows, honestly including what did NOT improve:**

| Query | Before | After | 
|---|---|---|
| `blast_radius_exceeded` | 18.4ms | 6.9ms |
| `_open_faults` | 7.7ms | 2.8–4.0ms |
| `metrics_escalated_count` (6% selectivity) | n/a (no index existed) | 2.8ms, confirmed via `EXPLAIN` to use `agent_actions_policy_decision_idx` |
| `metrics_executed_count` (**85%** selectivity in real data) | 10.3ms | 10.4–12.6ms — unchanged |
| `metrics_proposals_total` (unfiltered) | 6.1ms | 5.0–11.3ms — noise, not a real regression (re-ran to confirm; an unfiltered aggregate cannot be helped by any index, by definition) |

**A partial index was built, benchmarked, proven dead by `EXPLAIN`, and removed before ever being
committed** — this is the finding worth stating plainly rather than burying: `executed=TRUE` is
85% of real rows (not the 70% the first synthetic seed assumed), far too poor a selectivity for
Postgres to ever choose an index scan over a sequential scan. `agent_actions_executed_true_idx`
was added to migration 004, measured to provide zero benefit, confirmed via `EXPLAIN` that the
planner ignores it unconditionally, and deleted from the migration (never pushed) rather than
shipped as pure write overhead. Caught before commit specifically because the discipline this
session has used throughout — verify against real data, not the assumption that indexing a
boolean column always helps — was applied to a benchmark script too, not just application code.

**No counter-cache table was built for the two unfiltered aggregates**, a deliberate decision, not
an oversight: a hand-maintained counter (incremented on write, read at scrape time) is a real
correctness liability — drift on a crash between the increment and the write it's supposed to
track, double-counting on retry — for a metrics endpoint polled every 15–60s, not a hot request
path. The measured cost (5–12ms at 100k rows) is acceptable at that poll interval. If real-world
scale ever proves otherwise, a Postgres materialized view (refreshed on a schedule, no custom
drift-prone code) is the documented next option — not a hand-rolled counter.

**Retention** (`acde.telemetry.retention.purge`, `acde retention` CLI): off by default
(`RETENTION_DAYS=0`), so upgrading never silently deletes anything. Prunes only the three tables
the audit specifically measured as the volume driver — `resource_usage`, `pipeline_metrics`,
`task_runs` — and never `agent_actions`, the audit trail, enforced by a dedicated table (never a
config flag that could be misconfigured to include it). **Verified live, not just unit-tested**:
seeded one synthetic row 400 days old into both `resource_usage` and `agent_actions`, ran
`acde retention --days 30`, confirmed the `resource_usage` row was deleted and the `agent_actions`
row survived untouched — the exemption is real, demonstrated against the live database, not an
assumption resting on the code reading correctly.

Full unit (418, +5 for retention) and integration (27) suites green.

## D-087 — `/health` split, and every credential converted to `SecretStr`

**`/health` no longer calls `doctor()` at all.** It returned the full deployment-readiness report
— LLM provider, connector identity, execution mode, and raw exception fragments (`str(exc)[:120]`,
which can carry a hostname or DSN piece) — to any unauthenticated caller, since a load balancer's
health check can't carry credentials. Split: `/health` returns `{"status": "ok"}` unauthenticated;
the full report moved to `/health/ready`, now behind the same auth as every other operator
endpoint. `docs/OPERATIONS.md`'s quickstart curl updated to match.

**Every credential field became `SecretStr`**: `postgres_password`, `airflow_password`,
`prefect_api_key`, `anthropic_api_key`, `gemini_api_key`, `oai_api_key`, `api_key`, `api_keys` — 8
fields, ~11 real call sites across 6 modules plus `config.py`'s own `postgres_dsn` and
`api_key_map`. Pydantic's `SecretStr` accepts a plain string at construction (no test breakage —
confirmed, all 8 fields' existing `Settings(api_key="secret", ...)`-style test fixtures kept
working unmodified) and masks in `str()`/`repr()`/f-strings; every genuine *use* site (an httpx
`auth=` tuple, an SDK's `api_key=` kwarg, the DSN string) needs an explicit `.get_secret_value()`
or it silently sends the literal string `"**********"` as the credential — auth would fail, not
leak, but fail in a confusing way. Traced every one by grep, not by assumption.

**Two real integration-test bugs this itself caught**, both fixed: `tests/integration/test_
telemetry.py` and `test_dataplane.py` each built their own `httpx.Client(auth=(user, password))`
directly against `s.airflow_password` for verification, unaware of the type change — both failed
immediately with `TypeError: ... SecretStr found` the first time the real integration suite ran
after this change, caught by the real test run, not by code review.

**Verified the actual security claim, not just that the type exists**: with the real NVIDIA key
loaded in `.env`, confirmed live — `"nvapi" in repr(get_settings())` is `False`, `str(oai_api_key)`
prints `**********`, and `.get_secret_value()` still returns the real 40+ character key. Also
verified the *other* direction, that real auth still works end-to-end against real infrastructure
with the wrapped values: `acde doctor` against the live stack shows `database: reachable` (proves
`postgres_dsn`'s unwrap) and `connector:airflow: HTTP 200` (proves `airflow_password`'s unwrap
against real Airflow basic auth) — not assumed from the type conversion being mechanically
consistent.

Full unit (419) and integration (27) suites green.

## D-088 — Supervised control loop + `deploy/observability/` built for real

**The gap this closes**: `docker-compose.prod.yml` ran only `acde-server` (the API) + OPA +
Postgres. The actual governing process — the control loop that watches pipelines and proposes/
executes actions — was documented as something an operator runs manually in the foreground
(`acde run --env prod`, `docs/OPERATIONS.md`). Nothing supervised it, restarted it on crash, or
reported whether it was even still running. Separately, `docs/OPERATIONS.md` claimed *"a starter
Grafana panel set + alerts live in `deploy/observability/`"* — that directory did not exist.

**Heartbeat, the same durable pattern as the kill switch**: the loop writes
`control.desired_state['acde.loop_heartbeat']` at the top of every `_tick()` — before the pause
check, deliberately, since "alive but paused" is expected and healthy; only a clock that stops
advancing is the alertable signal. `acde loop-health` (new CLI command) reads it and exits
non-zero past `MONITORING_INTERVAL_S * 3`; wired as `acde-loop`'s container `HEALTHCHECK` (exec
form — no HTTP port to curl, unlike `acde-server`). `docker-compose.prod.yml` gained the
`acde-loop` service itself (same image, `command: ["acde", "run", "--env", "prod"]`,
`restart: unless-stopped`) — the actual fix; `acde-server` also gained a healthcheck against
D-087's now-cheap `/health`.

**Two new Prometheus gauges**, both read cross-process (the API and the loop are separate
containers; `control.desired_state` in shared Postgres is how one learns the other's state — same
mechanism, different question): `acde_loop_last_tick_timestamp_seconds` and
`acde_stale_executing_actions` (D-084's write-ahead rows stuck at `status='executing'` — the exact
crash-mid-execution scenario that fix targets, now alertable, not just queryable).

**`deploy/observability/` built for real, then proven, not just written**: `prometheus.yml`
(scrape config, `X-API-Key` auth via Prometheus's `http_headers`, since `/metrics` is
authenticated like every other operator endpoint on purpose — a metrics endpoint discloses real
operational data, D-070/D-087), `alerts.yml` (4 rules, each keyed to a real measured metric — loop
stalled, stale executing actions, approval backlog, denial spike), and a provisioned Grafana
dashboard (`grafana/dashboards/acde-overview.json` + datasource/dashboard provisioning YAML).
`docker-compose.observability.yml` is the optional overlay for operators without their own stack
(or for the verification below).

**End-to-end verification against real infrastructure, every claim proven, not assumed**:
- Ran the real control loop for 5s (`MOCK_LLM=1`), confirmed `acde loop-health` reports `ok` on the
  fresh heartbeat and `stale` on an old one — both directions, against the live database.
- Stood up a real `prom/prometheus:v2.55.1` container against a locally-running `acde serve`:
  confirmed the scrape target reached `health: up` (proving the `http_headers` X-API-Key auth
  actually works, not just that the config parses), queried `acde_proposals_total` back through
  Prometheus and got the real value (`198`, matching the database), confirmed all 4 alert rules
  loaded with `health: ok`.
- Let `ACDELoopStalled` actually reach **`firing`** state under a genuine stale heartbeat (the
  loop hadn't ticked in 638s) — not just "pending", the full `for: 2m` duration elapsed for real.
- Stood up a real `grafana/grafana:11.3.1` container, imported `acde-overview.json` via the API
  (`status: success` — proves it's valid Grafana schema, not just valid JSON), then queried a
  panel's data through Grafana's own datasource-proxy chain (Grafana → Prometheus → real ACDE
  metric) and got back the real value — the full chain an actual dashboard load exercises.
- All verification infrastructure (2 containers, 1 network, temp files, a scratch API key) torn
  down afterward; nothing left running or modified beyond the intended source changes.

This is the last item in the production-hardening sequence (`docs/specs/2026-08-27-production-
hardening-design.md`): migrations (D-083) → write-ahead audit (D-084) → tenant boundary (D-085) →
indexes/retention (D-086) → security hardening (D-087) → this. Full unit (428) and integration
(27) suites green.

## D-089 — Kubernetes/Helm chart, verified against a real cluster, two real bugs caught

**Sub-project B**, deferred at the start of the production-hardening sequence: docker-compose is
single-host; this is the horizontal-scaling / real-orchestrator story. `deploy/helm/acde/` — chart
for `acde-server` (stateless per the README's own claim, replicas=2 default, optional HPA) and
`acde-loop` (a **hard-enforced singleton**: the chart calls Helm's `fail` if
`loop.replicaCount > 1`, not just a comment — running N independent loop processes would multiply
LLM calls and duplicate governance work, not add capacity). OPA is bundled (lightweight, stateless,
tightly coupled); Postgres is not (bring-your-own managed instance, same philosophy as
`docker-compose.prod.yml` — this chart never runs a database).

**Verified against a real `kind` cluster, not just `helm template`** — every claim below is from
an actual deployed cluster, torn down afterward:

- **Real bug #1**: both Deployments used `command:` to set the container's entrypoint arguments.
  In Kubernetes, `command:` overrides the image's `ENTRYPOINT` entirely — since `docker-entrypoint.sh`
  *is* the entrypoint (it runs `acde migrate` before exec'ing `acde serve`/`acde run`, D-083),
  this would have **silently skipped migrations on every pod start**. Caught by building a
  faithful stand-in image with the same `ENTRYPOINT`/`CMD` shape as the real one and observing the
  entrypoint's log line never appeared. Fixed: `args:`, not `command:` — overrides `CMD` only,
  entrypoint stays in effect. Real acde-server/acde-loop images could not be built locally to test
  directly (see below); this was caught with the same rigor via a stand-in that reproduces the
  exact ENTRYPOINT/CMD contract.
- **Real bug #2**: OPA crashed with `rego_type_error: multiple default rules ... found` when its
  policies came from a Kubernetes ConfigMap volume — but not from a plain directory bind mount of
  the identical files (verified directly: ran `openpolicyagent/opa:0.68.0`, the exact tag
  `docker-compose.prod.yml` pins, against the real `infra/opa/policies/` via `docker run -v`, and
  it started clean). Root cause: a ConfigMap volume mount creates a hidden
  `..<timestamp>/` directory holding the real files plus a `..data` symlink and per-key symlinks
  at the top level; OPA's directory loader doesn't skip hidden directories by default, so it loads
  every file twice — once via the top-level symlink, once by walking into the hidden directory —
  and a file with one `default` rule becomes two. Fixed: `--ignore '..*'` on OPA's `run` args (a
  real, documented OPA flag for exactly this). Verified live: crashed without the flag in the real
  kind cluster, `Running 1/1` with it, using the identical ConfigMap.
- Confirmed via `kubectl describe`/`logs`/`exec` inside the running pods: liveness/readiness
  probes on `/health` (D-087's shallow endpoint) both passing, `POSTGRES_HOST`/`API_KEY`/etc.
  correctly injected from the Secret (never inlined into the pod spec), `OPA_URL` resolving to the
  real Kubernetes Service DNS name and a real pod-to-pod HTTP call succeeding across it, and the
  entrypoint's log line appearing before the `acde` command in both `acde-server` and `acde-loop`
  pod logs — proving bug #1's fix, not just asserting it.
- The `loop.replicaCount` guard was exercised directly: `--set loop.replicaCount=3` refuses to
  render at all (`helm template` exits non-zero with the exact reason), not merely documented.
- New CI job (`helm-lint`): lints the chart, renders it with representative values, and asserts
  the replica-count guard actually refuses invalid input — all three steps run locally first and
  confirmed to match what CI will do.

**Honest limitation**: the real `acde-server`/`acde-loop` production image could not be built in
this environment — the same persistent local Docker Desktop TLS failure documented in D-083's
entrypoint verification (now reproduced again, failing even on `pip install uv` itself, before
touching any project code — confirmed environmental, not a regression, since `docker pull` of
plain registry images works fine throughout). Verification used a purpose-built stand-in image
with the identical `ENTRYPOINT`/`CMD`/probe contract to prove the Kubernetes-level mechanics
(which is what a Helm chart actually governs); it does not substitute for CI's `docker-build` job
actually building the real image on a clean runner, which remains the authoritative build check.

## D-090 — Pod-level securityContext hardening for the Helm chart

**Found by re-auditing D-089's own chart** with the same rigor applied to the rest of the
production-hardening sequence: no template set a Pod- or container-level `securityContext`. The
image already runs non-root (`Dockerfile.server`'s `USER acde`, UID 10001) but nothing enforced
that at the Kubernetes level — a misconfigured or compromised image build could still run as root
with no guard against it.

**Fix**: `runAsNonRoot: true` + `runAsUser` at the Pod level for all three Deployments (10001 for
`acde-server`/`acde-loop`, matching the Dockerfile exactly; 1000 for OPA — confirmed via
`docker run openpolicyagent/opa:0.68.0 id` that this is the official image's own non-root UID, not
guessed), plus `allowPrivilegeEscalation: false` and `capabilities: drop: [ALL]` at the container
level. `readOnlyRootFilesystem` deliberately left off by default and documented as such — not
verified against the real image (only the D-089 stand-in was available) whether it needs a
writable path anywhere; turning it on unverified would be asserting something not actually checked,
which this whole session's discipline has been to avoid.

**Verified against a fresh real `kind` cluster, not assumed from the YAML**: all three Deployments
reached `Running 1/1` with the new constraints in place (proving OPA's non-default UID 1000 and
the dropped capabilities don't break anything), and `uid=10001 gid=10001` printed from inside the
actual running server pod — confirming the constraint is genuinely enforced, not just declared.
Full verification infrastructure torn down after.

## D-091 — Real production anomaly detection was never wired in; `failure_events` was chaos-only

**Found while planning a feature roadmap**, not by a failing test: `telemetry.failure_events` — the
table `ops/roi.py`'s MTTR/incident numbers and `experiments/decision_quality.py`'s scoring both
depend on — was **only ever written by `chaos/injector.py`** (confirmed by grep: the only two
`INSERT INTO telemetry.failure_events` sites in the whole codebase, before this fix, were the
chaos injector and a benchmark script). `agents/monitoring.py`'s `on_after_act` only `UPDATE`d an
*existing* row's `detected_ts`; it never `INSERT`ed one. In a real deployment with no chaos
injector running, a genuinely detected production anomaly reached `agent_actions` (fine, that's
the audit trail) but **never became a `failure_events` row at all** — MTTR, incident counts, and
decision-quality scoring were structurally incapable of reflecting real production incidents,
working only in chaos/research runs.

**Compounding it**: `src/acde/agents/detection.py` is a complete, well-tested (9 unit tests)
deterministic anomaly detector (`detect_anomalies()` — task failures, freshness breaches, CPU
spikes, schema drift, all from real telemetry, no LLM) implementing exactly the paper's own "§5.6,
cheap deterministic pre-filter" design — with **zero callers anywhere in the codebase**. Dead code,
fully built and fully tested, never wired into the live monitoring agent. And `agents/base.py`'s
`observe()` never queried `telemetry.task_runs` at all, so `detect_anomalies()`'s `task_failed`
check would have stayed structurally dead even after wiring the rest in.

**Fix**: `observe()` now also populates `task_runs` (D-091 fixes this as a prerequisite). Rewrote
`MonitoringAgent.observe()` to call `detection.detect_anomalies(snapshot)`; for each anomaly with
no matching open `failure_events` row, `INSERT` one (`tenant_id`/`environment` stamped via
`acde.tenancy.current_scope()`, D-085's pattern) and append it into the *same* snapshot's
`open_anomalies` before returning — same-tick visibility for the LLM, not a 1-tick lag waiting for
the next `observe()` to re-query. Reuses the exact `open_anomalies` field/shape the LLM already
understands (chaos-injected faults arrive the same way), so no prompt-file changes were needed —
simpler than this session's own plan first proposed. `detect_anomalies()`'s `open_fault:*` entries
(echoes of already-open faults, not new detections) are explicitly excluded from ever creating a
row, else every tick would re-insert the same fault it's echoing back.

**A real bug this test suite itself caught, twice**:
- First unit-test run actually wrote a row into the **real live database** — `monkeypatch.setattr
  (base, "db", fake)` only intercepts calls made through `base.py`'s own `db` name; `monitoring.py`
  has its own separate `from acde import db` import, unaffected. The exact lesson
  `TestAct._patch`'s own comment already states, re-learned the hard way. Fixed by patching
  `acde.db`'s actual attributes directly (`import acde.db as dbmod; monkeypatch.setattr(dbmod,
  "fetch_all", ...)`), the correct existing pattern; the stray row was found and deleted
  immediately (`DELETE FROM telemetry.failure_events WHERE experiment_run='t'`).
- The full integration suite then failed for a genuinely different, pre-existing reason:
  `tests/integration/test_agents_e2e.py`'s `_clean_and_restore` fixture only ever cleaned
  `failure_events`/`agent_actions` between tests, never `pipeline_metrics`/`resource_usage`/
  `task_runs`. `test_ingress_burst_triggers_scale_workers` leaves `freshness_s=140` behind
  uncleaned; the newly-wired detector correctly caught this real, pre-existing leftover as a
  genuine `freshness_breach` (140s > the 60s SLA) in the next test, `test_nominal_run_is_no_
  action_and_logged` — which had silently tolerated this exact test-isolation gap for as long as
  nothing consumed `detect_anomalies()`'s output. Fixed the fixture to clean all three tables, not
  the detector (the detector was right; the fixture's incompleteness had just never been visible).

**Mutation-tested**: the new/updated tests were run against the dedup-check deliberately removed —
failed exactly as expected (a duplicate INSERT for an already-open fault), confirming the tests
actually catch the defect they claim to, not just pass by coincidence.

**Verified live against the real running stack, not just mocked tests**: seeded a genuine
CPU-high `resource_usage` row (no chaos injector involved) for a throwaway `experiment_run`, ran a
real `MonitoringAgent.observe()` cycle, confirmed a real `failure_events` row appeared
(`fault_type=cpu_high`, correct `tenant_id`/`environment`) and that the *same* observe() call's
returned snapshot already carried it in `open_anomalies` (same-tick visibility, not next-tick).
Re-ran `observe()` a second time and confirmed no duplicate row (idempotency). All test data
cleaned up afterward. Full unit (432) and integration (27) suites green.

**Side effect worth noting, not a new bug**: `task_runs` being populated for the first time means
`TelemetrySnapshot.cache_key_material()` (the per-run LLM cache key) now correctly differentiates
ticks with different real task states — previously, since `task_runs` was always empty, two ticks
with genuinely different Airflow task states but otherwise-identical other fields would have
produced the *same* cache key and incorrectly reused a stale LLM response. A latent cache-staleness
bug this fix also happens to close, not something newly introduced.

## D-092 — `/docs` and `/openapi.json` were unauthenticated

**Found while researching a feature roadmap**, verified live: `TestClient` against a real `create_
app(require_key=True)` returned `200` for both `/docs` and `/openapi.json` with zero credentials.
FastAPI's `docs_url`/`redoc_url`/`openapi_url` are framework-level routes, added internally by
`FastAPI.__init__`, not subject to the per-route `dependencies=auth` pattern every other endpoint
in this file uses — so anyone could read the full API schema (every route, every parameter shape)
on a deployed instance without a key. Not a credential leak, but real information disclosure, the
same class of finding as D-087's `/health` split.

**Fix**: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` disables the framework's own
unauthenticated routes; `/openapi.json`, `/docs`, `/redoc` re-added as regular `@app.get` routes
with `dependencies=auth` — the documented FastAPI pattern (`fastapi.openapi.utils.get_openapi`,
`fastapi.openapi.docs.get_swagger_ui_html`/`get_redoc_html`).

**Mutation-tested**: reverted to plain `FastAPI(title=..., version=...)` (the original
unauthenticated construction) — the new test failed exactly as expected (`200` where `401` should
be; FastAPI's own built-in route wins over the later custom one when both are registered).
Restored, reconfirmed 21/21 `test_server.py` green.

**Verified live**, the same check that found the bug in the first place, now the other way:
`/docs` and `/openapi.json` both `401` unauthenticated, `/docs` `200` with a real key. Full unit
(434) and integration (27) suites green.

## D-093 — RBAC: viewer / approver / admin

No role concept existed at all before this — every authenticated actor had identical access
(confirmed by grep before starting: no `role` field anywhere). Every B2B SaaS enterprise-readiness
source found while researching this feature roadmap lists RBAC as table-stakes alongside SSO/audit
logs; this closes it for the write path (approve/reject) while every read route stays open to any
authenticated actor (`viewer` is the floor, not an extra gate).

**Design**: `Settings.api_keys` gained an optional third `actor:key:role` field.
`Settings.role_map` (actor → role) parses it; **a missing role — including every deployment that
only has `api_key`/`api_keys` today, with no role syntax at all — defaults to `admin`**, so
upgrading never silently downgrades anyone's existing access. `server/app.py` gained
`require_role(min_role)`, a dependency factory nesting `Depends(_authenticate)` and checking
`_ROLE_RANK[role] >= _ROLE_RANK[min_role]` (403, not 401 — the caller is a real authenticated
actor, just not authorized for *this* action); it returns the actor string, so it drops into any
slot that already expects `Depends(actor_dep)` with zero signature changes elsewhere. Both the
JSON API's `/approvals/*/approve|reject` and the dashboard's `/ui/approvals/*/approve|reject` now
use it — `dashboard.add_routes` gained an optional `approver_dep` parameter (defaults to
`actor_dep` if omitted, so no other caller breaks), closing the finding that the dashboard's own
write actions would otherwise stay a **weaker, unRBAC'd path** to the exact same side effect the
JSON API now gates.

**Mutation-tested**: the role-rank comparison was replaced with `if False:` (always allow) — the
new viewer-403 test failed exactly as expected (the mutated code let the request past the check
into real, unmocked downstream approval logic it should never have reached). Restored, reconfirmed
25/25 `test_server.py` and 8/8 `test_dashboard.py` green.

**Verified live against a real running server, not just `TestClient`**: started `acde serve` with
`API_KEYS="viv:viv-key:viewer,al:al-key:approver"`, confirmed a real `curl -X POST .../approve`
with the viewer key returns `403`, the same viewer's `GET /proposals` returns `200`, and the
approver key's `POST .../approve` against a nonexistent approval id returns
`{"status":"not_found",...}` — proof it passed the role gate and reached real business logic, not
just that the gate itself returns the right status code in isolation.

Full unit (444) and integration (27) suites green.

## D-094 — Bulk audit export

`/audit`'s `LIMIT` cap (1000, D-084) is right for the JSON API's normal use, wrong for the actual
compliance question ("give me everything from Q1") every B2B enterprise-readiness source found
while researching this feature roadmap lists as a standard expectation alongside SSO/RBAC/audit
logs. New `GET /audit/export` (`viewer`+): same `since`/`until` filters as `/audit`, no cap.

**Design**: keyset pagination on `(ts, action_id)`, not `OFFSET` — `OFFSET` degrades on a large
table (Postgres still has to scan and discard every skipped row), and `ts` alone isn't a unique
tiebreaker (two actions can share a timestamp). `action_id` (the primary key) breaks ties and makes
the cursor stable. CSV (default) streams via `StreamingResponse`, one batch (1000 rows) in memory
at a time regardless of export size — the actual point of a bulk-export endpoint. JSON collects the
same generator into one response (still uncapped, just not memory-bounded — a reasonable
simplification since CSV is what carries the "handles a huge export" property).

**Mutation-tested**: removed the pagination stop condition (`if len(rows) < batch_size: return`) —
the test failed exactly as expected (the generator tried to fetch a third, non-existent batch from
a 2-item mock `side_effect`, raising `StopIteration`). Restored, reconfirmed 29/29 `test_server.py`
green.

**Verified live against the real running server and its real 198-row audit trail** (accumulated
across this entire session's work) — both formats matched the real database count exactly. Caught
my own verification mistake along the way: `wc -l` on the CSV output showed 214 lines against a
198-row JSON export and a 198-row `SELECT count(*)`, which looked like a real bug — a proper CSV
parser (`csv.DictReader`) confirmed exactly 198 rows. `wc -l` counts raw newline characters, which
over-counts when `csv.DictWriter` correctly quotes a field containing an embedded newline (e.g. a
multi-line `outcome`/`justification`); the CSV itself was correct, the verification tool was wrong.
Recorded here rather than silently discarded, since catching your own false alarm and saying so is
part of the same honesty this session has held code changes to.

Full unit (448) and integration (27) suites green.

## D-095 — Per-tenant cost attribution + budget alert

D-085 added `tenant_id`/`environment` columns across every scoped telemetry table and
`compute_cost_windows` already stamps them on every `cost_ledger` write — but nothing ever read
them back *grouped*. A per-tenant deployment (or a single deployment tracking cost by environment)
had no way to answer "who/what is actually driving spend," the same gap the market research for
this roadmap flagged against Arthur/Fiddler-style governance platforms.

**Design**: `telemetry/cost.py` gained `costs_by_tenant(since_hours=24.0)` — `SUM(cost_units)`,
`SUM(compute_unit_seconds)`, `SUM(storage_gb_hours)` from `cost_ledger` grouped by `tenant_id` over
the trailing window, joined in Python (not SQL — the two tables share no other key) against a
companion per-tenant `SUM(llm_tokens_in + llm_tokens_out)` from `agent_actions`, since token spend
is the other real per-tenant cost an operator wants next to it even though it isn't a `cost_units`
input. `GET /costs` (`server/app.py`, `viewer`+, plain `auth` — every authenticated actor is
viewer-or-above, so no `require_role` call was needed) exposes it as JSON. `/metrics` gained
`acde_cost_units_by_tenant{tenant_id="..."}`, one gauge line per tenant, same trailing-24h window
as the JSON route's default so the two never quietly disagree; a `_escape_label` helper backslash/
quote/newline-escapes the label value per the Prometheus text-format spec (a tenant ID is
operator-controlled config today, not user input, but the endpoint had no reason to assume that
stays true). New `ACDEBudgetExceeded` alert in `deploy/observability/alerts.yml`, threshold `100`
mirroring `Settings.budget_default_units` — the same number the cost OPA policy already enforces
per-action, not an independently invented alert threshold.

**Bug caught while wiring this up**: `costs_by_tenant` and `/metrics`' new gauge both go through
`acde.telemetry.cost`'s own `db` import — a *third* separate reference from `server/app.py`'s and
`server/metrics.py`'s own `db` bindings, the exact "patch the module you think you're patching,
not the one actually executing the query" pitfall D-091 hit with `agents/monitoring.py`. Caught in
review before it caused a stray-write-style incident this time (a read-only endpoint, so the
failure mode here would have been *tests silently hitting a real database* rather than
corrupting it) — `tests/unit/test_server.py`'s `client`/`multi_actor_client`/`role_client`
fixtures all gained `monkeypatch.setattr("acde.telemetry.cost.db", fake)` alongside the existing
`orchestrator.control.db` patch that already documents the same lesson.

**Mutation-tested**: the token join's `.get(tenant_id, 0.0)` default was replaced with a bare
`[tenant_id]` lookup — the new "a tenant with no `agent_actions` rows" test failed exactly as
expected (`KeyError: 'beta'`). Restored, reconfirmed `test_cost.py`'s `TestCostsByTenant` green.

**Verified live against the real running Postgres** (2812 real `cost_ledger` rows, all
`tenant_id='default'` since this is still a single-tenant deployment): `costs_by_tenant` over an
all-time window returned `cost_units=1798.126...`, matching `SELECT SUM(cost_units) FROM
telemetry.cost_ledger` exactly, and `llm_tokens=247955`, matching `SELECT
SUM(llm_tokens_in+llm_tokens_out) FROM telemetry.agent_actions` exactly. Started a real
`uvicorn` process against the same database (temporary `API_KEY`, stopped and cleaned up after);
`GET /costs` and `GET /metrics`'s new gauge line agreed on the same trailing-24h number
(`43.500000812032006`), confirming the two code paths — one via the JSON route, one via the text
exposition renderer — read the identical live data consistently.

Full unit (453) and integration suites green (see CI).
