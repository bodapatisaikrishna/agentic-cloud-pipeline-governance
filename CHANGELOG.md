# Changelog

All notable changes to ACDE. Format loosely follows Keep a Changelog; versions are tagged
per phase, `v1.0.0` at Phase 9.

## [Unreleased]

### Added
- **Richer operator dashboard (D-102)**: `/ui` gains cost, policy-allow-rate, and decision-quality
  summary cards, plus an admin-only tenants table (shown only when more than one tenant exists) —
  four reports that only ever had a JSON/CLI face before are now visible in the browser. Still no
  JS, no external assets. Verified live: the dashboard's rendered numbers matched the JSON API's
  own `/costs`/`/compliance-report`/`/decision-quality` exactly for the same window.
- **Slack rich formatting + PagerDuty integration (D-101)**: outbound notifications gained a
  Slack Block Kit `attachments` block (colored by severity, structured fields) alongside the
  existing plain-text payload, and a new PagerDuty Events API v2 dispatch
  (`PAGERDUTY_ROUTING_KEY`, empty disables). Both channels fire independently off the same
  `WEBHOOK_EVENTS` filter; `shadow_proposal` never pages PagerDuty regardless. Verified live
  over real HTTP against local stand-in listeners for both channels — the real, unmocked
  `notify()` path end to end, not just mocked assertions.
- **Live decision-quality monitoring (D-100)**: `GET /decision-quality`, `acde
  decision-quality-report`, and a trailing-24h `acde_decision_quality_accuracy` `/metrics` gauge
  score real, resolved production incidents against an accepted-mitigation taxonomy — extending
  `experiments/decision_quality.py`'s scoring logic beyond offline chaos experiments for the
  first time. Found and fixed a real taxonomy gap: the research module's `EXPECTED_ACTIONS` is
  keyed by chaos scenario names, not the real live detector's fault-type names, so every real
  incident would have silently scored "incorrect by construction" without the new
  `LIVE_EXPECTED_ACTIONS` mapping. Verified live: the one genuine incident in the dev database
  scored correctly, 101 unrelated chaos-run rows correctly excluded rather than miscounted.
- **Database backup & restore (D-099)**: `acde backup`/`acde restore --yes` wrap real
  `pg_dump`/`pg_restore`; `--target-db` supports a restore drill without touching the live
  database. Fixed a real gap found while planning: the production image never installed
  `postgresql-client`, so these wouldn't have worked in a real deployment at all. Verified live:
  a real dump, restored into a throwaway database, byte-for-byte row-count match against the
  source.
- **Operator API rate limiting (D-098)**: in-process, per-actor/per-source fixed-window limiter,
  `API_RATE_LIMIT_PER_MINUTE` (`0` = unlimited, default). Runs as middleware ahead of auth, so it
  also throttles pre-auth key-guessing floods; `/health` stays exempt. New
  `acde_rate_limited_requests_total` metric + `ACDERateLimitEngaged` alert. Verified live against
  a real running server: 4 requests at limit=3 gave `200,200,200,429` with a real `Retry-After`.
- **Multi-tenant SaaS layer, admin-provisioned (D-097)**: new `control.tenants` registry
  (`acde tenants create|list|suspend|activate`, `POST/GET /tenants*`, admin-only), an optional
  fourth `actor:key:role:tenant_id` API-key field binding an actor to one tenant (missing =
  unscoped, zero regression), and tenant-filtered `/proposals`, `/audit`, `/audit/export`,
  `/costs`, `/compliance-report`. A suspended tenant's keys get `403` at auth time. Verified live:
  a tenant-bound key saw zero cross-tenant rows against the real 198-row dataset; suspend/activate
  flipped `403`/`200` on the real running server.
- **Compliance/audit evidence report (D-096)**: `acde compliance-report` CLI + `GET
  /compliance-report` (`viewer`+) — policy verdict distribution, incident count + MTTR (now real
  thanks to D-091), and a point-in-time availability check that explicitly does not fabricate a
  historical uptime %. Verified live: matched the real DB's audit-trail and open-incident counts
  exactly.
- **Per-tenant cost attribution + budget alert (D-095)**: `GET /costs` (`viewer`+) and a new
  `acde_cost_units_by_tenant{tenant_id="..."}` `/metrics` gauge, both reading D-085's tenant/
  environment columns back grouped for the first time. New `ACDEBudgetExceeded` alert, threshold
  mirroring `Settings.budget_default_units` (the same number the cost OPA policy already
  enforces). Verified live against 2812 real `cost_ledger` rows — the per-tenant sum matched the
  global DB sum exactly, and a real running server's `/costs` and `/metrics` agreed on the same
  number.
- **Bulk audit export (D-094)**: `GET /audit/export` (CSV/JSON, `viewer`+) — no row cap, unlike
  `/audit`. Keyset-paginated on `(ts, action_id)` so CSV streams in bounded batches regardless of
  export size. Verified live against the real 198-row audit trail; both formats matched the
  database count exactly.
- **RBAC: viewer / approver / admin (D-093)**: no role concept existed before this. Optional
  third `actor:key:role` field on `api_keys`; a missing role defaults to `admin`, so no existing
  deployment's access silently changes. `require_role(min_role)` gates
  `/approvals/*/approve|reject` on both the JSON API and the dashboard (previously a weaker,
  unRBAC'd path to the same side effect). Verified live against a real running server: viewer
  `403` on approve, `200` on read; approver's request reaches real approval logic.

### Fixed
- **`/docs` and `/openapi.json` were unauthenticated (D-092)**: FastAPI's built-in docs routes
  aren't subject to the per-route auth pattern every other endpoint uses — confirmed live, `200`
  with zero credentials. Disabled the framework's own routes, re-added them behind the same auth.
- **Real anomaly detection wired into production, was chaos-only (D-091)**: `telemetry.
  failure_events` was only ever written by the chaos injector — a real production anomaly reached
  the audit trail but never became an incident, making MTTR/decision-quality scoring inert outside
  chaos runs. `agents/detection.py`'s deterministic detector (9 tests, zero callers) is now wired
  into `MonitoringAgent.observe()`, creating real `failure_events` rows with same-tick visibility.
  Also fixed `observe()` never populating `task_runs` (a latent LLM-cache-staleness bug too) and a
  pre-existing integration-test isolation gap this fix's own test run surfaced.

### Added
- **Pod-level securityContext hardening for the Helm chart (D-090)**: `runAsNonRoot` +
  `runAsUser` (matching each image's real non-root UID, not guessed), `allowPrivilegeEscalation:
  false`, `capabilities: drop: [ALL]` on all three Deployments. Verified against a real kind
  cluster — all pods still reach `Running 1/1` under the new constraints, and the actual running
  UID was confirmed from inside the pod.
- **Kubernetes/Helm chart, verified against a real cluster (D-089)**: `deploy/helm/acde/` — HPA-
  capable `acde-server`, a hard-enforced singleton `acde-loop` (the chart refuses to render above
  1 replica), bundled OPA, bring-your-own Postgres. Verified against a real `kind` cluster, not
  just `helm template`: caught and fixed two real bugs — `command:` silently bypassing the
  migration-running entrypoint (should be `args:`), and OPA crashing on ConfigMap-mounted policies
  (`rego_type_error: multiple default rules`, from Kubernetes' hidden ConfigMap symlink directory
  being double-loaded; fixed with `--ignore '..*'`). New `helm-lint` CI job.
- **Supervised control loop + real `deploy/observability/` (D-088)**: `docker-compose.prod.yml`
  gained the `acde-loop` service itself — the control loop was previously a manual foreground
  command, now supervised (`restart: unless-stopped`) with its own healthcheck (`acde loop-health`,
  reading a new per-tick heartbeat). Two new Prometheus gauges
  (`acde_loop_last_tick_timestamp_seconds`, `acde_stale_executing_actions`). Built
  `deploy/observability/` for real (scrape config, 4 alert rules, provisioned Grafana dashboard) —
  docs previously claimed this directory existed; it didn't. Verified end-to-end against real
  Prometheus/Grafana containers: real scrape with auth, an alert reaching actual `firing` state
  under a genuine stale condition, and a dashboard panel query returning real data through the
  full Grafana→Prometheus→ACDE chain. Last item in the production-hardening sequence
  (D-083 through D-088).
- **`/health` split + every credential as `SecretStr` (D-087)**: `/health` is now a shallow
  unauthenticated liveness check (`{"status": "ok"}`); the full `doctor()` report moved to the
  authenticated `/health/ready`. All 8 credential fields in `Settings` (postgres/airflow
  passwords, all 3 LLM provider keys, prefect key, operator API keys) converted to `SecretStr` —
  masked in `repr()`/`str()`/logs, unwrapped only at the ~11 real usage sites. Caught two
  integration tests constructing their own auth tuples directly against the raw field, both fixed.
- **Hot-path indexes, benchmarked, and opt-in retention (D-086)**: migration 004 indexes the real
  predicates of the 3 hottest queries (`blast_radius_exceeded`, `_open_faults`, `/audit`'s
  `ORDER BY ts`). Benchmarked before/after at 10³–10⁵ rows (`acde.analysis.bench_hot_paths`); one
  proposed index (`executed=TRUE`, 85% selectivity in real data) was measured, proven dead via
  `EXPLAIN`, and removed before ever being committed. New `acde retention` CLI (opt-in,
  `RETENTION_DAYS=0` by default) purges `resource_usage`/`pipeline_metrics`/`task_runs`; the audit
  trail (`agent_actions`) is never touched, verified live with a seeded old row.
- **Tenant/environment schema boundary (D-085)**: `tenant_id`/`environment` columns (migration
  003, server-side config only, never client-supplied) on every scoped telemetry table. Schema-
  level groundwork for eventual multi-tenant hosting, deliberately not a SaaS control plane yet —
  see DEVIATIONS D-085 for the explicit scope line.
- **Write-ahead audit trail (D-084)**: `agents/base.py::act()` now writes an intent row
  (`status='executing'`) before calling the executor, then updates it with the outcome. Closes a
  real gap where a crash during execution left an executed action with zero audit record. New
  `status` column (migration 002); `/audit` gained `since`/`until` filters, both `/audit` and
  `/proposals` surface `status`.
- **Migration framework (D-083)**: `src/acde/migrations/` — forward-only, checksum-guarded,
  advisory-lock-serialized. Fixes a real production bug: `dataplane.migrate` resolved its SQL
  directory to the repo root, which doesn't exist in the installed wheel, so production had no way
  to apply a schema change to an existing database at all. Wired into `acde doctor` and the
  production Docker entrypoint (migrations now run automatically before the server/loop starts).

### Fixed
- **Recovery agent target hallucination (D-082)**: found by inspecting D-081's live results —
  `decision_correct` for `full` dropped from 100% (mock) to 66.7% (live), traced to the recovery
  agent echoing the `experiment_run` id as `target` instead of a real dag/dataset in 46% of live
  proposals (task_runs too sparse to reason to a real one). Fixed with a deterministic guard in
  `policy/executor.py::apply_action` that rejects `target == experiment_run` before any real infra
  call, plus an explicit prompt rule in `recovery.md`. Verified via mutation test (guard disabled →
  test fails exactly as the real bug reproduced; restored → 392/392 green).

### Added
- **First full live-LLM validation pass (D-081)**: quick profile (96 runs, all 8 configs x 4
  scenarios x N=3) run against the real NVIDIA endpoint end-to-end. 96/96 `status: ok`, zero errors.
  Confirmed the `resource_contention` scenario's ~10x wall-time increase is the scenario's own CPU
  stressor (D-026), not a live-LLM issue. Validates the live path works; the full `paper` profile
  (480 runs, ~28-30h, real ongoing cost) is deliberately not run yet — this was the risk-reducing
  step first.
- **Proactive concurrency fuzzing (D-077)**: `tests/integration/test_concurrency_fuzz.py` turns the
  disposable script that found D-074 into a permanent regression test — 20 real concurrent workers
  hammer `PartitionVersionManager.create_version` across shared targets. Verified both directions:
  passes 3/3 against current code, fails 3/3 against the pre-D-074-fix code.
- **OPA policy audit + exhaustive coverage (D-078)**: fixed real dead code (`rate_limit.rego` was
  never delegated to from `main.rego` — two duplicate copies of the same check, only one reachable),
  added a property test asserting all 18 legitimate `(agent, action_type)` pairs reach a real policy
  branch (7 were previously untested), and closed two boundary-condition gaps (`cost_budget`'s
  exact-equal case, `schema`'s compat-independent containment rule). Verified every new test actually
  catches the bug it targets (each one confirmed to fail against a deliberately reintroduced mutation,
  then restored), and re-verified against the exact CI-pinned `opa:0.68.0` — not just a newer local
  install.

### Fixed
- **Real multi-agent conflict resolution (D-079, corrects D-038)**: found while implementing the
  paper's §X negotiation future-work item that D-038's "recovery outranks optimization" guarantee
  was never actually enforced — reactive agents run sequentially in `orchestrator/loop.py` with a
  lock that releases between them, so both would execute regardless of order. `_tick()` now runs
  explicit propose → resolve → act phases; contested targets resolve by `(agent priority,
  confidence)` bid before anyone acts, not by accident of execution order. Verified the fix actually
  fixes something (reverted to the old no-resolution behavior, confirmed the new tests fail exactly
  as expected, restored). Honestly scoped: no current `MOCK_LLM=1` scenario produces same-target
  contention between agent types, so this is a verified safety net for the live-LLM path, not
  something exercised by today's integration tests.
- **Dead `OAI_MODEL_FAST` default (D-080)**: found on the first real `make agents-live-smoke` run —
  NVIDIA retired `meta/llama-3.1-8b-instruct` the same day (HTTP 410 Gone). Replaced the default with
  `nvidia/nemotron-3-nano-30b-a3b` in `config.py`, `.env.example`, and the hardcoded test assertion
  that had baked in the dead string. Re-verified live: all 4 agents now get real `200 OK` responses.

## [2.2.0] — Dependency refresh + a real concurrency fix

Routine maintenance release: the docker-release `:latest` tag bug, the CI infra found chasing it, and
~20 dependabot bumps — plus one real correctness bug (D-074) found and fixed along the way, not just
dependency churn.

### Fixed
- **`docker-release.yml`'s `:latest` GHCR tag wasn't updating** — `actions/checkout@v4` defaulted to
  `fetch-tags: false`, so the "is this the newest tag" step couldn't see the full tag list. Added
  `fetch-depth: 0` + `fetch-tags: true`; verified live against the GHCR registry API.
- **Unit suite was making real, billed LLM API calls.** `TestBudget`/`TestCache` in
  `test_llm_client.py` constructed `LLMClient()` without patching settings, so a developer's local
  `.env` (`MOCK_LLM=0` + a live provider key) leaked into `pytest tests/unit` runs. Added
  `tests/unit/conftest.py` clearing every `Settings`-derived env var at import time — verified
  hermetic against a hostile environment (`MOCK_LLM=0` + a bogus DB host exported): 382 passed, zero
  outbound HTTP.
- **API key comparison wasn't constant-time.** `_authenticate` used `==`, which leaks how many
  leading characters were correct through response timing. Switched to `secrets.compare_digest`.
- **`cryptography` 49.0.0 HIGH CVE** (CVE-2026-69247 / PYSEC-2026-3552, transitive via
  `google-genai`) — bumped to 50.0.0.
- **Stale `pip`/`setuptools`/`wheel` CVEs in the runtime image, for real this time.** The Tier 1 fix
  (`pip install --upgrade`) didn't actually clear the Trivy findings — pip's own PyPI releases vendor
  a pinned, unfixed `msgpack`, and the base image's original `setuptools` metadata survives the
  upgrade. Since the app runs entirely out of a self-contained `uv`-built venv, system `pip` is never
  needed at runtime — stripped it entirely instead of chasing upgrades release to release.
- **D-074 — concurrent `tpcds_ingest` DAG runs race, root-caused and fixed.**
  `PartitionVersionManager.create_version` read `MAX(version)` and then ran `DROP TABLE`/`CREATE
  TABLE`/insert/register as separate, unlocked statements. Two concurrent writers to the same
  `(dataset, partition_key)` — e.g. the recovery agent's `replay` racing an independently-triggered
  DAG run — could compute the same "next version" and collide. Fixed with a
  `pg_advisory_xact_lock`-scoped transaction around the whole critical section. Verified against a
  real reproduced race on an ephemeral local Postgres (12 concurrent writers: 11/12 failed pre-fix
  with `DuplicateTable`/`UniqueViolation`, 12/12 clean post-fix) and against 4 consecutive clean
  `integration` CI runs post-fix.

### Changed
- Dependency refresh across Python deps (`fastapi`, `openai`, `anthropic`, `uvicorn`, `google-genai`,
  `psycopg`, `ruff`, `mypy`, `pandas`, `matplotlib`) and GitHub Actions (`checkout`, `login-action`,
  `setup-buildx-action`, `build-push-action`, `metadata-action`, `setup-uv`) — ~20 dependabot PRs,
  all merged after re-verifying CI green post-rebase.
- README's Phase status table and unit-test-count claims synced to actual shipped state (was
  showing v2.0.0 and a stale "360 unit tests"; actual is 382). `.env.prod.example` gained the
  `API_KEYS` and Prefect fields that shipped in v2.1.0 but were never added to the template.
- `docs/PAPER_MAPPING.md` / `REPORT.md` updated to reflect the D-074 fix against the paper's §IV.A
  "deterministic and auditable" Data Plane claim.

### Not changed (deliberately)
- **`python:3.11-slim` → `3.14-slim` base image bump** (dependabot PR #5) — closed, not merged. The
  build stage's `uv sync` downloads its own managed Python 3.11 toolchain regardless of the base
  image (per `requires-python = ">=3.11,<3.12"`), so bumping the base image's *system* Python changes
  nothing about what code executes — pure inconsistency with the project's declared support range,
  zero functional gain.

## [2.1.0] — Repo maturity + real capability (Tier 1 & Tier 2 hardening)

Everything needed to go from "a repo that works" to "a repo you'd trust and could actually operate
with more than one person." No breaking changes; the legacy single `api_key` keeps working.

### Added — Tier 1: publish, release, harden CI, OSS hygiene
- **Docker image published** to `ghcr.io/bodapatisaikrishna/agentic-cloud-pipeline-governance`
  (`docker-release.yml`, tag-triggered + manual dispatch) — `docker pull` now actually works.
- **GitHub Releases** backfilled for all tags with real notes from this file.
- **CI hardened**: `opa-test` job (20 Rego cases), `docker-build` job (build validation + Trivy CVE
  scan — caught and fixed two real HIGH-severity CVEs in the base image's bundled pip/setuptools),
  `pip-audit` dependency vulnerability scan.
- **OSS hygiene**: `CONTRIBUTING.md`, issue/PR templates, `dependabot.yml` (uv, github-actions,
  docker).
- **Fixed a real test-isolation bug (D-069)**: `ControlLoop` unit tests were silently hitting a live
  database because the P1 kill-switch check wasn't mocked — invisible locally (a dev stack happened
  to be reachable), would have failed in CI. Verified the fix with the database genuinely
  unreachable, not just re-run against a live one.

### Added — Tier 2: multi-user auth, dashboard, integration tests in CI, second connector
- **Multi-actor operator API auth (D-070)**: `api_keys` (CSV `actor:key,...`) plus a unified
  `_authenticate` dependency (X-API-Key or HTTP Basic) resolves every request to a real actor name —
  `/approvals/*` no longer accept a client-supplied, spoofable `actor` field. Verified live:
  authenticated as `alice`, approved a real action, confirmed `decided_by='alice'` in the database.
- **Web dashboard (D-071)**: `GET /ui` + approve/reject forms — Jinja2, no JS, no external assets
  (air-gapped friendly), same auth and same `acde.human.approvals` functions as the JSON API.
- **Integration tests actually proven in CI (D-072)**: new `integration` job runs `make up && make
  seed && make test-integration && make down` against the real stack on push to `main`. Verified: 26
  passed in 4m11s on a fresh runner — "production ready" is now a CI fact, not just a doc claim.
- **Prefect connector (D-073)**: second `Connector` implementation (deployments, flow runs,
  work-pool concurrency), proving the abstraction generalizes beyond Airflow. One documented gap:
  Prefect has no per-task clear, so `clear_tasks` retries the whole flow run.
- **D-074**: root-caused and documented a pre-existing, intermittent integration-test flake (a
  concurrent-DAG-run race between the recovery agent's `replay` and a Phase 1 test both triggering
  `tpcds_ingest`) — added CI diagnostics (Airflow log dump on failure) and flagged a dedicated
  follow-up rather than patching around it inside this release.

## [2.0.0] — Production release: from research artifact to deployable tool

ACDE becomes a tool companies can deploy to govern their own pipelines. See `docs/OPERATIONS.md`,
`docs/CONNECTING.md`, `docs/POLICY_AUTHORING.md`, `docs/SECURITY.md`.

### Added — trust core (P1, D-065)
- **Execution modes** `shadow` / `approval` / `autonomous` (`acde_mode`); allowed actions are logged,
  queued, or executed accordingly. High-blast action types force approval even in autonomous.
- **Approval workflow** (`human/approvals.py`, `telemetry.action_approvals`): queue → approve/reject →
  execute via the executor core. **Kill switch** (`acde pause/resume`) + per-target **blast-radius**
  cap. **Slack-compatible webhook** notifications (non-blocking, redacted).

### Added — attach to their stack (P2, D-066)
- **Connectors** (`connectors/`): Airflow (basic/bearer auth, TLS-verify) + noop (observe-only),
  selected by `connector_kind`. **`acde doctor`** preflight (`ops/health.py`).

### Added — operational surface (P3)
- **Operator API** (`server/`, FastAPI): `/health`, `/metrics` (Prometheus), `/proposals`, `/audit`,
  `/approvals/*`; mandatory `X-API-Key`, fail-closed. **`acde` CLI** (console script): run/serve/
  status/doctor/pause/resume/approvals.

### Added — packaging (P4, D-067)
- **Apache-2.0** LICENSE + NOTICE (supersedes the research artifact's no-license choice). Lean core
  with `acde[research]` extra. Slim `deploy/Dockerfile.server` + `deploy/docker-compose.prod.yml`
  (server + OPA + Postgres; external orchestrator) + `.env.prod.example`. Version 2.0.0.

### Added — differentiators (P5, D-068)
- **`acde report`** — ROI summary from the audit trail (actions executed, incidents auto-resolved,
  MTTR p50/p90, tokens, estimated operator-hours saved). Always available (no research extra).
- **`acde gameday --scenario …`** — rehearse a controlled incident in staging and get an evidence
  report for *your* pipelines; hard staging-guard (`connector_is_production`), needs `acde[research]`.

## [1.3.0] — Publication-grade extensions (Phases A–F)

Turns the faithful replication into a rigorous, open benchmark that also tests claims the paper
asserted without evidence. See `REPORT.md` and `docs/PAPER_MAPPING.md`.

### Added — scientific credibility (Phase A)
- **Credible non-agent baselines (D-058):** `rule_based` and `autoscale` configs
  (`experiments/baselines.py`), alongside static+human — "beat cheap automation, not just a slow
  human?". Matrix grows to quick=96 / paper=480. Verified ordering agents ≪ rule/autoscale ≪ human.
- **Decision-quality metric (D-059):** `experiments/decision_quality.py`; runner harvests
  `decision_correct`; added to analysis `METRICS`. Correct mitigation, not just fast.
- **Freshness as ingestion-stall (D-060):** streaming faults degrade `freshness_s` by their open
  duration (non-circular), so the metric is no longer trivially zero.

### Added — novel contributions (Phases B–E)
- **Cost model v2 (D-061):** provisioning term credits avoided over-provisioning; makes the paper's
  cost-reduction claim testable (`telemetry/cost.py`).
- **Cross-LLM study (D-063):** `eval/cross_model.py` — decision correctness/latency/tokens per model,
  testing the paper's model-agnostic claim. Injectable probe; live sweep opt-in.
- **Adversarial safety eval (D-062):** `eval/adversarial.py` — OPA-gate containment of unsafe
  proposals. **Live result: containment = 1.0** (denied/escalated) + contract-layer rejection.
- **Bounded adaptation (D-064):** `agents/adaptation.py` — success-prior-blended confidence within
  clamps; off by default to keep the benchmark deterministic.

### Added — packaging (Phase F)
- `docs/PAPER_MAPPING.md` (section-by-section), `REPORT.md` (what reproduces / what doesn't),
  DEVIATIONS D-058…D-064. **Tests:** +21 unit (baselines, decision quality, cost v2, cross-model,
  adversarial, adaptation). 317 unit @95%.

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
