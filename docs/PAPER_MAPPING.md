# Paper → implementation mapping

Maps each section/claim of arXiv:2512.23737 *"Governing Cloud Data Pipelines with Agentic AI"*
(Kirubakaran et al., 24 Dec 2025) to where ACDE implements it and what our experiments found.
`✅ reproduced · ➕ extended beyond the paper · ⚠️ diverges (disclosed)`.

## Architecture (paper §III–VI)

| Paper element | ACDE implementation | Status |
|---|---|---|
| Three planes: Data / Policy / Agentic Control (§IV) | `dataplane/`, `policy/` (+ `infra/opa`), `agents/` + `orchestrator/` | ✅ |
| Four bounded agents: monitoring, optimization, schema, recovery (§IV.C) | `agents/{monitoring,optimization,schema,recovery}.py` | ✅ |
| Observe → reason → propose → evaluate loop (§V) | `agents/base.py` + `orchestrator/loop.py` | ✅ |
| Agents never execute; all actions validated before execution (§III) | `contracts/actions.py` (pydantic) → `policy/gate.py` (OPA) → `policy/executor.py` | ✅ |
| LLM as bounded reasoner, no code generation (§VI.A) | `llm/` — emits only a validated `ProposedAction` | ✅ |
| Model-agnostic (GPT / Claude / Gemini interchangeable) (§VI.A) | `llm/client.py` provider abstraction: anthropic · gemini · openai_compatible (NVIDIA/Groq/…) | ➕ actually implemented + measured (§C below) |
| "Execution remains deterministic and auditable" (§IV.A, Data Plane) | `dataplane/partitions.py::PartitionVersionManager.create_version` | ➕ paper asserts this, never discusses concurrency safety; ACDE found and closed a real gap (D-074) — two concurrent writers to the same partition (e.g. the recovery agent's `replay` racing a scheduled DAG run) could read the same next-version and collide. Fixed with a `pg_advisory_xact_lock`-scoped transaction; verified against a real reproduced race (11/12 failures pre-fix → 12/12 clean post-fix on an ephemeral Postgres, not just unit mocks) |

## Evaluation (paper §VII)

| Paper element | ACDE implementation | Status |
|---|---|---|
| Static-orchestration + human baseline (§VII.D) | `experiments/baseline.py` (`baseline` config) | ✅ |
| Failure injection: schema drift, upstream delay, resource contention (§VII.E) | `chaos/` — + `ingress_burst` (4 scenarios) | ✅ |
| Metrics: MTTR, cost, freshness, manual interventions (§VII.F) | `experiments/runner.py::harvest_metrics` | ✅ |
| Datasets: TPC-DS, Open-Gov, NYC-TLC, synthetic streams (§VII.C) | `dataplane/datasets/` | ✅ (synthetic TPC-DS, D-009) |

## Headline claims (paper §VII.G) vs measured

**Mock quick-matrix** (96 runs, N=3/cell, deterministic `MOCK_LLM=1` — mock agent resolves
near-instantly):

| Claim | Paper | ACDE (full vs baseline) | Status |
|---|---|---|---|
| MTTR reduction | ↓~45% | ↓~99.98% (mock recovery vs human baseline) | ✅ direction, larger |
| Manual interventions | ↓>70% | ↓~100% | ✅ |
| Data freshness | maintained | maintained (streaming-stall model, D-060) | ✅ |
| Operational cost | ↓~25% | v1 compute-only: ↑ (⚠️); v2 provisioning-aware (D-061): ↓ | ⚠️→✅ with disclosed model |

**Live paper campaign** (560 runs, real remote model at paper timings, D-104, completed
2026-09-26 — see `paper/` for the full manuscript and `paper/generated/` for every table/figure):

| Claim | Paper | ACDE live (full vs baseline) | Status |
|---|---|---|---|
| MTTR reduction | ↓~45% | ↓38% (235 s vs 378 s median), significant | ✅ direction, smaller magnitude |
| Manual interventions | ↓>70% | **↑500%** (6.00 vs 1.00 median), significant | ❌ opposite direction |
| Operational cost | ↓~25% | ↓56% (69.8 vs 158 units), significant | ✅ direction, larger — but see the provisioning-gap sensitivity in `paper/` |
| Decision correctness *(new)* | — | full correct-mitigation rate ≈0.42 | far from perfect; only `full`/`optimization_only`/`schema_only` move it significantly |
| vs. cheap automation | — | `rule_based`/`autoscale` beat `full` on MTTR (↓92%/↓86%) and manual interventions | live results do **not** repeat the mock matrix's "full dominates every baseline" |
| Mock vs. live, same config | — | MTTR 235 s live vs. 0.193 s mock; decision-correct 0 vs. 1.00 | ~1000× divergence — the central methodological finding of the live campaign |

The mock quick-matrix's "full dominates every baseline" and "manual interventions ↓100%" do not
survive contact with a live model at real paper timings. This divergence, not either single dataset,
is the headline result of the D-104 evidence campaign.

## Beyond the paper (our contributions)

| Contribution | Where | Why it matters |
|---|---|---|
| **Credible baselines** — rule-based + autoscaling, not just a slow human (D-058) | `experiments/baselines.py` | Answers "beat cheap automation, not just humans?" — the reviewer's first objection |
| **Decision-quality metric** — correct mitigation, not just fast (D-059) | `experiments/decision_quality.py` | The paper never measures whether the agent chose the *right* action |
| **Cross-LLM study** (D-063) | `eval/cross_model.py` | Data for the paper's unproven model-agnostic claim |
| **Adversarial safety eval** (D-062) | `eval/adversarial.py` | Stress-tests the core policy-bounded thesis; containment = 1.0 vs real OPA |
| **Cost model v2** (D-061) | `telemetry/cost.py` | Makes the cost claim testable |
| **Bounded adaptation** (D-064) | `agents/adaptation.py` | Concretizes the paper's §V adaptation claim |
| **Rigor** — seeds, bootstrap CIs, paired Wilcoxon + Holm–Bonferroni + Cliff's delta, 8-config ablation | `analysis/` | The paper reports three point numbers with no statistics |

## Paper future-work → ACDE status

- Multi-agent coordination (§X) — explicit negotiation protocol **implemented** (D-079):
  same-target proposals resolve by static agent-priority bid (`orchestrator/loop.py`), replacing
  the earlier advisory-lock-order claim (D-038) that turned out not to hold in practice.
- Policy learning (§X) — bounded adaptation mechanism implemented (D-064); full longitudinal
  evaluation is **future work** (E3).
- Multi-cloud, formal verification (§X) — **out of scope** (cited as further work).
