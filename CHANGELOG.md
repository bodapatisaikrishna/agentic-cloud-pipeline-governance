# Changelog

All notable changes to ACDE. Format loosely follows Keep a Changelog; versions are tagged
per phase, `v1.0.0` at Phase 9.

## [Unreleased] — Phase A: scientific credibility (baselines + decision quality)

### Added
- **Credible non-agent baselines (D-058):** `rule_based` (predefined-remediation automation) and
  `autoscale` (resource-only, data-blind) configs in `experiments/baselines.py`, alongside the
  static+human baseline — answering "do agents beat cheap automation, not just a slow human?".
  Matrix grows to quick=96 / paper=480 runs. Verified ordering agents ≪ rule/autoscale ≪ human.
- **Decision-quality metric (D-059):** `experiments/decision_quality.py` ground-truth optimal
  mitigations per scenario; runner harvests `decision_correct` into `raw.csv`; added to analysis
  `METRICS`. Measures whether the agent picked the *correct* action, not just how fast.
- **Config:** `rule_remediation_s`, `autoscale_reaction_s`. **Tests:** +9 unit (baselines coverage +
  escalation, decision-quality ground truth, runner harvest w/ decision_correct). 304 unit @95%.

## [1.2.0] — 2026-07-17 — Generic OpenAI-compatible LLM provider (NVIDIA NIM / GLM-5.2)

### Added
- **`LLM_PROVIDER=openai_compatible` (D-057):** live agent calls through the `openai` SDK against a
  configurable `OAI_BASE_URL` (default NVIDIA NIM) with `OAI_API_KEY` + `OAI_MODEL_REASONING`/`_FAST`
  (defaults `z-ai/glm-5.2` / `meta/llama-3.1-8b-instruct`). One provider covers NVIDIA NIM, Groq,
  OpenRouter, and z.ai. `LLMClient._live_call` gains an `_openai_compatible_once` branch under the
  shared retry-then-degrade wrapper.
- **`OAI_MAX_TOKENS_PER_CALL` (default 8192):** larger cap so "thinking" models (GLM-5.2) can reach
  the JSON, which `_extract_json` extracts from the surrounding reasoning text. temperature=0 kept.
- **Dep:** `openai`. **Tests:** +2 unit (openai_compatible routing + dispatch). `.env.example`,
  README, Makefile smoke help updated. `MOCK_LLM=1` stays the default; live path is opt-in / off-gate.

## [1.1.0] — 2026-07-15 — Multi-provider live LLM (Anthropic + Gemini)

### Added
- **Gemini live LLM provider (D-056):** `LLM_PROVIDER=gemini` routes real agent calls through the
  Google `google-genai` SDK (`gemini-2.5-pro` / `gemini-2.5-flash`, overridable via `GEMINI_MODEL_*`;
  key via `GEMINI_API_KEY`). `LLMClient._live_call` now dispatches to a per-provider `_once()` behind
  a shared retry-then-degrade wrapper; the Anthropic path is unchanged and remains the default.
- **Config:** `llm_provider`, `gemini_api_key`, `gemini_model_reasoning`, `gemini_model_fast`;
  `.env.example` documents them. **Dep:** `google-genai`.
- **Tests:** +5 unit (provider routing, live-call dispatch, unknown-provider guard, shared degrade,
  mock provider-independence). Live Gemini call stays opt-in / user-run (paid), like the Anthropic
  path; `MOCK_LLM=1` remains the default everywhere and the automated gate stays offline.

## [1.0.0] — 2026-07-15 — Phase 9: hardening & reproducibility package

### Added
- **Executor fault tolerance (D-052):** Airflow-REST side effects now retry with bounded backoff
  (`executor_retry_attempts`, `executor_retry_backoff_s`); on exhaustion `execute()` escalates to a
  human and returns an `execution_failed` outcome instead of letting the exception crash the agent
  cycle. Mirrors the gate's existing OPA-down fail-safe.
- **Failure-mode tests (D-053):** unit coverage for all three degrade paths (Airflow-down, OPA-down,
  DB-blip) plus `tests/integration/test_failure_modes.py`, which stops the real `opa` container and
  asserts end-to-end escalation (restarting OPA in teardown).
- **`DATA_LICENSES.md` (D-054):** provenance + licensing for TPC-DS (synthetic, not `dsdgen`) and
  NYC TLC (official public data, opt-in). No code license shipped.
- **README:** full-system architecture diagram (D-055), a clone→figures **Reproduction** guide, and a
  **Fault tolerance** section.

### Changed
- Phase table: Phase 9 ✅; project tagged **`v1.0.0`** (all 9 phases complete).

## [0.9.0] — 2026-07-14 — Phase 8: analysis, figures, report

### Added
- **`src/acde/analysis/`**:
  - `stats.py` — median/IQR, seeded bootstrap CI (10k), paired Wilcoxon, Holm–Bonferroni, Cliff's
    delta (pure; unit-tested on known-answer fixtures).
  - `analyze.py` — loads `raw.csv` → per-metric per-config median/IQR/CI, paired baseline-vs-full
    Wilcoxon + Cliff's delta with Holm–Bonferroni across metrics, ablation table → `analysis.json`.
  - `figures.py` — MTTR/cost/interventions bars with CI error bars, MTTR CDF, ablation heatmap
    (headless matplotlib Agg) → `results/figures/*.png`.
  - `report.py` — `results/results.md`: per-metric tables, embedded figures, the vs-paper (45/25/70)
    comparison, and an appended DEVIATIONS dump.
- **Config**: `bootstrap_resamples`, `paper_{mttr,cost,intervention}_pct`. **Runner**: harvests
  `freshness_s`. **Makefile**: `analyze`, `report`. New deps: `scipy`, `matplotlib`.
- **Tests**: +30 unit (stats known answers, analyze on synthetic data, report+figures render).
  288 unit tests, 95% coverage.
- **Docs**: DEVIATIONS D-047…D-051.

### Result
Full pipeline verified on synthetic data: significant baseline-vs-full MTTR (Wilcoxon p=0.008,
Holm p=0.039, Cliff's δ=1.0), the vs-paper table, and all figures render.

## [0.8.0] — 2026-07-14 — Phase 7: baseline & resumable experiment runner

### Added
- **`src/acde/experiments/`**:
  - `configs.py` — profile matrices: `quick` (6×4×3 = 72 runs), `paper` (baseline/full N=20 +
    4 ablations N=10 = 320), `smoke` (2).
  - `scenarios.py` — per-profile `RunTimings`.
  - `baseline.py` — `resolve_via_human`: fixed-monitor detection + seeded human resolution of every
    open fault (back-fills `failure_events.resolved_ts`).
  - `runner.py` — `run_one` (reset → warmup → inject → control loop / baseline → fallback human →
    cost → harvest → CSV + manifest) and `run_profile` (resumable via `manifest.jsonl`); metrics
    `mttr_s`, `cost_units`, `manual_interventions`, `llm_tokens`, `wall_clock_s`.
- **Agents**: schema + optimization now stamp `resolved_ts` for their fault types (MTTR closure).
- **Config**: `results_dir`. **Makefile**: `experiment-smoke` / `experiment-quick` /
  `experiment-paper`.
- **Tests**: +40 unit (profiles, runner I/O + harvest + resumability, baseline, agent lifecycle);
  integration `test_experiment_runner.py` (smoke profile writes `raw.csv` + manifest, resumable,
  agents recover faster than the human baseline). 263 unit tests, 94% coverage.
- **Docs**: DEVIATIONS D-042…D-046.

### Result
First real signal reproduced: on `upstream_delay`, **baseline MTTR ≈ 312 s** (human) vs
**full MTTR ≈ 0.2 s** (recovery agent) — the agentic control plane recovers ~1500× faster.

## [0.7.0] — 2026-07-14 — Phase 6: control-loop orchestrator

### Added
- **`src/acde/orchestrator/`**:
  - `loop.py` — `ControlLoop`: async scheduler running monitoring every `monitoring_interval_s`
    and the reactive agents (`schema → recovery → optimization`) only when open faults exist; each
    action guarded by a per-target advisory lock; SIGTERM-aware graceful shutdown; agents run via
    `asyncio.to_thread`.
  - `locks.py` — `target_advisory_lock` (non-blocking `pg_try_advisory_lock` over a held pooled
    connection) so no two agents act on the same target concurrently; recovery outranks optimization
    by act order + shared lock.
  - `configs.py` — ablation map (`baseline`, `monitor_only`, `*_only`, `full`).
  - `soak.py` — inject two overlapping chaos scenarios then run the loop.
- **Config**: `monitoring_interval_s`, `soak_duration_s`. **Makefile**: `orchestrator`, `soak`.
- **Tests**: +30 unit (configs, advisory locks, loop scheduling/lock decisions/ablation ordering);
  integration `test_orchestrator_e2e.py` (short soak closes the lifecycle across agents; ablation
  gating; kill-and-restart resumes). 243 unit tests, 94% coverage.
- **Docs**: DEVIATIONS D-037…D-041.

## [0.6.0] — 2026-07-14 — Phase 5: agents & LLM layer

### Added
- **LLM layer** (`src/acde/llm/`): `client.py` (`LLMClient` with monitoring→`MODEL_FAST` /
  others→`MODEL_REASONING` routing, temperature=0, per-run `BudgetTracker`, in-run cache, 429/5xx
  retry → `no_action`/`llm_unavailable`), `mock.py` (deterministic per agent × scenario), and four
  `prompts/*.md` system templates (§5.6). New dep: `anthropic`.
- **Agents** (`src/acde/agents/`): `detection.py` (z-score + thresholds), `base.py`
  (observe→reason→propose→gate→execute→`agent_actions`), the four agents, and a `run.py` cycle CLI.
  Monitoring stamps `failure_events.detected_ts`; recovery stamps `resolved_ts` (MTTR endpoints).
- **Config**: anomaly thresholds. **Makefile**: `agents` (MOCK_LLM=1) and `agents-live-smoke`
  (MOCK_LLM=0, user-run).
- **Tests**: +48 unit (detection, mock coverage of every agent × scenario, client budget/cache/
  routing, agents observe/invalid/act); integration `test_agents_e2e.py` (each scenario → owning
  agent → agent_actions + side effect; lifecycle closed). 223 unit tests, 95% coverage.
- **Docs**: DEVIATIONS D-031…D-036.

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

### Fixed
- `schema_drift` is now a validator-detectable breaking change: `pipeline.validate` gained a
  numeric-dtype check, `DRIFT_COLUMNS` is restricted to the pipeline's validated numeric columns,
  and `run_tpcds` declares them numeric — so both drift ops (drop → missing, retype → non-numeric)
  fail validation. (Surfaced by the live chaos integration gate.)

### Verified
Live gate (desktop-linux context): lint clean; 190 unit tests; `opa test` 20/20; 14 integration
tests incl. all four chaos scenarios writing `failure_events`.

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
