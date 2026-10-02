# ACDE Codebase Analysis (Phase 1)

Factual inventory only — this is not the paper, it is the evidence base Phases 2–6 are grounded in.
Every claim below cites a file (and line, where the number/detail is precise) so a reviewer or a
later drafting pass can verify it independently rather than trust this document on faith.

## 1. Repository overview

- **Language/tooling**: Python 3.11 (`pyproject.toml:6`, `requires-python = ">=3.11,<3.12"`), `uv`
  package manager (`uv.lock` committed), `ruff` (lint+format, line length 100) and `mypy` for quality
  gates, `pytest` for tests.
- **Size**: 104 source files under `src/acde/`, 68 test files under `tests/`, 752 unit tests, 95.35%
  coverage (`make test-unit`, verified live this session).
- **Top-level module map** (`src/acde/`, one line each, all verified to exist):
  - `contracts/` — pydantic cross-boundary types (`ProposedAction`, `PolicyDecision`, telemetry types).
  - `dataplane/` — batch (Airflow) + streaming (Redpanda) pipeline, synthetic/seeded datasets.
  - `telemetry/` — collector, cost ledger, freshness metrics.
  - `policy/` — the OPA gate and executor.
  - `agents/` — the four bounded agents plus a shared base loop and an adaptation module.
  - `orchestrator/` — the control loop, advisory locks, runtime controls (kill switch, blast radius).
  - `llm/` — the multi-provider LLM client and the deterministic mock.
  - `human/` — the simulated on-call and the real approval-queue logic.
  - `chaos/` — the seeded fault injector (4 scenarios).
  - `experiments/` — the baseline/runner/campaign-supervisor machinery behind every number in this
    paper.
  - `analysis/` — statistics, figures, and the manuscript-artifact generator
    (`paper_artifacts.py`, `paper_figures.py`).
  - `eval/` — adversarial evaluation (both the original suite and the generated corpus) and the
    cross-model harness.
  - `connectors/` — the orchestrator-attachment abstraction (Airflow, Prefect, no-op).
  - `ops/`, `server/`, `notify/`, `migrations/`, `tenancy.py` — the production trust core / operator
    surface (CLI, HTTP API, backup/restore, multi-tenant registry, Slack/PagerDuty).
- **Infra**: `infra/postgres/init/` (idempotent DDL), `infra/opa/policies/` (Rego + tests),
  `docker-compose.yml` (postgres:16.6, `openpolicyagent/opa:0.68.0-debug`,
  `redpandadata/redpanda:v24.2.18`, `apache/airflow:2.10.5-python3.11`).

## 2. Architecture as implemented

The three-plane design (Data / Policy / Agentic Control) from the base paper is real, not a stub, plus
a fourth layer (Trust Core) the base paper does not describe:

- **Data plane**: `dataplane/batch/pipeline.py` (validate→transform→materialize, thin Airflow DAGs),
  `dataplane/streaming/` (windowed aggregator, worker pool, Kafka/Redpanda client), `dataplane/datasets/`
  (seeded synthetic TPC-DS-shaped generator, `tpcds_gen.py`; a real NYC-TLC fetcher, opt-in).
- **Telemetry**: `telemetry/collector.py` (host-side loop over `docker stats` + Airflow REST),
  `telemetry/cost.py` (step-integrates resource usage into cost units), `telemetry/freshness.py`.
- **Policy plane**: `policy/gate.py` builds context and calls OPA; `policy/executor.py` performs side
  effects for allowed actions. Real, not implied-by-convention — every action flows through
  `gate.evaluate()` before `executor.apply_action()` can run (confirmed by reading both modules).
- **Agentic control plane**: `orchestrator/loop.py::ControlLoop` runs the observe→reason→propose→act
  cycle genuinely, not simplified — `_tick()` calls `_run_agent()` per enabled agent, which calls
  `agents/base.py`'s shared `act()` method (`base.py:163-231`) that builds a telemetry snapshot, calls
  the LLM (or mock), validates the resulting `ProposedAction`, evaluates it through the gate, and
  executes or escalates.
- **Trust core** (not in the base paper): `orchestrator/control.py` — durable kill switch
  (`control.desired_state['acde.paused']`, checked each tick) and a per-target hourly blast-radius cap
  (`blast_radius_exceeded()`, `control.py:71`); `config.py:181`'s `acde_mode` (shadow/approval/
  autonomous); `human/approvals.py` (a real approval queue, not just the simulated on-call).

## 3. Agent-by-agent status

All four agents share one base loop (`agents/base.py`, 255 lines) and are real implementations, not
stubs:

| Agent | File | LOC | What it actually proposes |
|---|---|---|---|
| Monitoring | `agents/monitoring.py` | 72 | Detects anomalies statistically (`agents/detection.py`, z-score + static thresholds — detection is never an LLM call, D-031), the LLM only classifies/triages and proposes `raise_anomaly`/`no_action`. |
| Optimization | `agents/optimization.py` | 30 | Scales workers/pool slots or reprioritizes, via the LLM given a telemetry snapshot. |
| Schema | `agents/schema.py` | 29 | Allows compatible schema changes or quarantines/blocks breaking ones. |
| Recovery | `agents/recovery.py` | 24 | Retries, replays, rolls back, partially recomputes, or escalates to a human. |

Each agent module is a thin `enabled_action_types`/prompt-template wrapper around the shared
`base.py::act()` loop, not independent logic — the loop itself (observe telemetry snapshot → call
`llm/client.py` or `llm/mock.py` → validate the `ProposedAction` contract → `policy/gate.py` →
`policy/executor.py`) is genuinely shared and genuinely present, confirmed by reading `base.py` in
full.

`agents/adaptation.py` (63 lines, D-064) blends an empirical success prior into proposal confidence,
off by default (`adaptation_enabled=False`) to keep the benchmark deterministic — implemented, not
evaluated as part of the live campaign (contribution #not in the six-item list; a smaller, disabled-
by-default feature, distinct from the cross-LLM/trust-core gaps below).

## 4. LLM backend integration

Real, pluggable, not hardcoded to one provider (`llm/client.py`):

- **Providers wired in**: `anthropic` (default), `gemini`, `openai_compatible` (generic — covers
  NVIDIA NIM, Groq, OpenRouter, z.ai by changing `base_url`/key), selected via `config.py:85`
  `llm_provider`.
- **Live campaign's actual provider**: `openai_compatible` against NVIDIA NIM, model IDs
  `nvidia/nemotron-3-ultra-550b-a55b` (reasoning) and `nvidia/nemotron-3-super-120b-a12b` (monitoring/
  fast) — recorded per run in `paper/data/*/manifest.jsonl`'s `provenance.llm_models`.
- **Deterministic mock**: `llm/mock.py` — `mock_propose()` returns scenario-appropriate actions per
  agent, used by default (`MOCK_LLM=1`) and by 240 of the 560 campaign runs (the mock-`full` arm).
- **Cross-model harness**: `eval/cross_model.py` exists, is unit-tested (an injectable probe), and can
  run the same scenario through multiple models to compare decision correctness/latency/tokens. **The
  live sweep across real providers has not been run and recorded** — no `results/cross_model*` artifact
  exists anywhere in the repository (checked: git history, `results/`, `paper/data/`). This is
  contribution #3 from `context.md` §4, and it is implemented-not-evaluated. State this precisely in
  the paper; do not imply a live comparison happened.
- **Accounting**: `llm/client.py`'s `LLMStats` counts real calls, cache hits, degraded proposals
  (budget-exhausted, provider-unavailable, or cache-replayed unavailability), invalid outputs, tokens,
  and latency — counted at the moment a call is or is not made (D-104's accounting design). A
  transient-failure cache-poisoning bug was found and fixed in this project's own pilot testing
  (`DEVIATIONS.md` D-104l) — real evidence the accounting exists to catch real failure modes, not a
  theoretical concern.

## 5. Policy & governance layer

- **Representation**: Rego, in `infra/opa/policies/` — `main.rego` (dispatcher), `cost_budget.rego`,
  `recovery_approval.rego`, `schema_compat.rego`, `rate_limit.rego` — exactly four policy packs plus
  the dispatcher, matching the base paper's description. `coverage_test.rego` and `main_test.rego`
  etc. give 24 total test rules (`make opa-test`).
- **Real enforcement point**: `policy/gate.py::evaluate()` calls OPA over HTTP and returns
  allow/deny/escalate/allow-and-notify; `policy/executor.py::apply_action()` only performs a side
  effect if the gate allowed it — confirmed by reading both modules; this is not enforcement-by-
  convention.
- **Fail-safe**: if OPA is unreachable or errors, the gate returns `allowed=false, escalate=true`
  (`policy_id="gate_failsafe"`) after bounded retries — never silently allows.
- **Versioning/audit**: policy files are ordinary git-tracked files (full history via `git log --
  infra/opa/policies/`); every gate decision is written to `telemetry.agent_actions` with the policy
  verdict and reason, and (since a fix this project made, D-084) the intent row is written
  *before* execution (write-ahead), not after — closing a real defect where a crash mid-action could
  leave an executed-but-unaudited action.

## 6. Trust core / graduated autonomy / kill switch

Contribution #6 from `context.md` §4. Implemented, substantively:

- **Autonomy levels**: `config.py:181`, `acde_mode: str = "autonomous"` — a string enum in practice
  (`shadow` | `approval` | `autonomous`), checked in the executor's dispatch path. Code default stays
  `autonomous` deliberately, for the research benchmark's determinism (`config.py:178-180`'s comment);
  the production entrypoint (`cli.py`'s `acde run`) and `.env.prod.example` both default to `shadow`.
- **Kill switch**: `orchestrator/control.py::is_paused()`/`set_paused()` — a durable flag in
  `control.desired_state['acde.paused']`, checked once per control-loop tick (`control.py:26-39`), so
  it takes effect within one tick, not instantly but boundedly.
- **Blast-radius cap**: `orchestrator/control.py::blast_radius_exceeded()` (`control.py:71-85`) — a
  per-target, per-hour action cap, independent of policy.
- **Approval queue**: `human/approvals.py` — a real queued-approval mechanism (distinct from the
  simulated-latency human used in the experiment baselines), with `telemetry.action_approvals` rows and
  an `approve`/`reject` path that re-runs the action through `policy/executor.py::apply_action`.
- **What is NOT true**: the live 560-run campaign ran every configuration in one fixed mode throughout
  (not exercising mode transitions), and the campaign does not measure kill-switch engage-to-halt
  latency or blast-radius-cap trigger behavior under load. This is implemented-not-evaluated, same
  category as the cross-LLM study — the paper must not report trust-core numbers that were never
  measured.

## 7. Adversarial safety evaluation

Contribution #4. Two generations exist:

- **Original suite** (`eval/adversarial.py`) — a small, hand-written set of unsafe-proposal injections
  against the real OPA gate; historically reported containment = 1.0 (`docs/SECURITY.md`,
  `results/results.md`).
- **Generated corpus** (`eval/adversarial_corpus.py`, 557 lines, built this session as part of D-104) —
  an exhaustive grid over legal (agent, action) pairs and boundary context values, attacker-controlled
  parameter extremes, hostile free-text strings, illegal proposals sent directly to the policy engine
  (bypassing the contract), and a seeded fuzz. **Expected verdicts come from an independently written
  Python specification of the documented policy semantics, not from the Rego under test** — the
  independence is of implementation, so the containment number is not circular.
- **Results** (`paper/data/adversarial.json`, verified byte-for-byte against the manuscript's macros
  by an independent verification agent this session): 5,547 total graded cases; overall containment
  3,867/3,867 (rate 1.0, Wilson 95% lower bound 0.9990); over-block rate 0/1,680; exact oracle agreement
  5,547/5,547; 0 fail-opens, 0 gate errors.
- **What the corpus found and fixed before reaching that number** (`DEVIATIONS.md`, lesson L6): a real
  contract-layer gap (zero/negative/non-numeric scaling targets were budget-legal or crashed the gate
  before the audit row was written) and an observation that a newer, non-pinned OPA release
  mis-evaluated some float budget comparisons — the pinned `openpolicyagent/opa:0.68.0-debug` is
  correct, and the pin is now load-bearing and tested.

## 8. Cost model

Contribution #5. `config.py:110-111`, `telemetry/cost.py` (245 lines):

- **v1 (compute-only)**: `cost_units = compute_unit_seconds × 0.05 + storage_gb_hours × 0.01`
  (`cost_rate_compute_unit_second`, `cost_rate_storage_gb_hour`). Under this model, running agents can
  only *add* cost — there is no way to book right-sizing savings, so the base paper's ~25% reduction
  claim cannot reproduce under v1 (this is a real, documented finding, not a design flaw hidden from
  the reader — `DEVIATIONS.md` D-006/D-048).
- **v2 (provisioning-aware, D-061)**: adds a provisioning term — static configurations hold a fixed
  over-provisioned allocation for a fixed horizon (`config.py:137`, `provisioning_horizon_s = 300.0`);
  right-sizing configurations (`autoscale`, `optimization_only`, `full`) hold a smaller one. This makes
  the cost-reduction claim testable, with the explicit caveat (quantified by a sensitivity sweep,
  `analysis/sensitivity.py`) that the magnitude depends on the assumed provisioning gap.
- **Live-campaign result**: `full` reduces cost by 56% vs. static baseline (`\NRelpctCostUnitsFull` in
  `paper/generated/numbers.tex`), the one headline claim that survives at a similar-or-larger magnitude
  than the base paper reports — but two of the four single-agent ablations (`monitor_only`,
  `recovery_only`) *increase* cost by 676% each, because they don't get the optimization agent's
  right-sizing action at all while still paying the provisioning term.

## 9. Experiments and results present in-repo

- **Mock quick matrix** (`results/`, git-ignored but regenerable): 96 runs, 8 configs × 4 scenarios ×
  N=3, deterministic `MOCK_LLM=1`. Historical, superseded for headline claims (see `REPORT.md`'s own
  notice), useful as a fast sanity check.
- **Mock paper matrix** (`make experiment-paper`): 480 runs, same 8-config design at paper timings,
  still mock — a distinct, larger, still-mock dataset, separate from the live campaign.
- **The live paper campaign** (the paper's actual evidence base): 560 runs across three arms —
  live-agents (240: `full` × 20/scenario + 4 ablations × 10/scenario), non-agent baselines (240:
  `baseline`/`rule_based`/`autoscale` × 20/scenario, no LLM calls so identical live-or-mock), and
  mock-`full` (80: the mock twin of arm A's `full`, for the mock-vs-live comparison). Committed at
  `paper/data/{paper-live,paper-baselines,paper-mock}/{raw.csv,manifest.jsonl}`. Launched
  2026-09-22, completed 2026-09-26 (`results/campaign_status.json`'s `updated` timestamp and the
  manifest min/max timestamps, cross-checked by an independent verification agent this session after
  an initial date error was caught and fixed).
- **A pilot preceded the campaign** (`DEVIATIONS.md` D-104j/k/l): found and fixed a retired LLM model
  (HTTP 410), a missing request timeout, an 18-minute hang (fixed defensively, cause not fully
  confirmed), and a live cache-poisoning defect (one transient HTTP 503 replayed 29 times) — all fixed
  before the real campaign, not discovered during it.
- **One real incident during the campaign** (D-104m/n): the campaign supervisor's own health-check
  hung for 2+ hours after Docker crashed on a full host disk; root-caused, fixed
  (`experiments/campaign.py`'s `check_health()` now wrapped in `call_with_deadline`), and the resulting
  `git_sha` split across the campaign's manifests was verified (by diff) to touch only the supervisor's
  own health check, never the execution path, and documented as a deliberate, evidenced provenance
  override rather than a silent one.

## 10. Test coverage

752 unit tests, 95.35% line coverage on `src/acde` (`make test-unit`, ≥80% gate enforced). No Docker,
no network required for the unit suite (`MOCK_LLM=1` default). A separate `tests/integration/` suite
(`@pytest.mark.integration`) requires `make up`. All six roadmap contributions have dedicated test
coverage: `paper_artifacts.py`/`paper_figures.py` (100% each, per the last live coverage run),
`eval/adversarial_corpus.py` (99%), `experiments/campaign.py` (99%), `llm/client.py` (95%,
including the cache-poisoning regression test named in D-104l).

## 11. Development timeline

`git log` (130 commits total, `2026-07-08` → `2026-09-25` for code, campaign data through
`2026-09-26`): began as a phased scaffold (Phase 0 scaffold/foundations, Phase 1 data plane, Phase 2
telemetry, Phase 3 policy plane...) through Phase 9 hardening, then a "v2.0 production tool" pass
(trust core, connectors, operator API), then continuous post-release hardening (concurrency fixes,
audit-trail fixes, multi-tenancy, rate limiting — each tied to a `DEVIATIONS.md` D-number), then a
"Journal-paper readiness" phase (D-104, this evidence campaign and manuscript). Commit history shows
iterative, dated development with substantive individual commits (not one large generated dump) —
each `DEVIATIONS.md` entry is traceable to the commit(s) that implemented it.

## 12. Discrepancies vs. `context.md`

None found. `context.md` was written from this same codebase (this session), so it should match by
construction; this section exists per the template's own instruction and is included for completeness
rather than because a real mismatch was found. If a later drafting pass finds one, record it here.
