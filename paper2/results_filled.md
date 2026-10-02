# Experiment Results — Filled With Real Data (Phase 2)

Every cell is either a real number traced to a committed file (path given), or `[NO DATA]`. Nothing
here is estimated, interpolated, or borrowed from the base paper. Source of truth throughout:
`paper/data/{paper-live,paper-baselines,paper-mock}/raw.csv` (raw per-run long-format data) and
`paper/generated/numbers.tex` (the same data, pre-aggregated into macros by
`src/acde/analysis/paper_artifacts.py` — every macro below was independently re-derived from raw
`paper/data/*.csv` by a fresh-context verification agent this session and matched exactly, including
the least flattering numbers).

## 1. Core operational metrics (comparable to the base paper)

`full` = the complete agentic system (all four agents, live model). Medians, n=80 per cell unless noted.

| Metric | Static baseline | ACDE (`full`, live) | Source |
|---|---|---|---|
| Mean/median time to recovery (MTTR) | 378 s | 235 s (↓38%) | `\NMttrBaselineMedian`, `\NMttrFullMedian`, `\NRelpctMttrSFull` |
| Operational cost (units) | 158 | 69.8 (↓56%) | `\NCostBaselineMedian`, `\NCostFullMedian`, `\NRelpctCostUnitsFull` |
| Data freshness (streaming-stall duration, s) | 39.2 (median) | 14.0 (median) | recomputed directly from `paper/data/paper-baselines/raw.csv` and `paper/data/paper-live/raw.csv`, metric=`freshness_s`; cross-checked against `\NLiveVsMockFreshnessSLive` (14.0, live `full` only) |
| Manual intervention frequency | 1.00 | 6.00 (↑500%, **worse**) | `\NIntervBaselineMedian`, `\NIntervFullMedian`, `\NRelpctManualInterventionsFull` |

Statistical support for each of these (bootstrap 95% CI on the median difference, Cliff's δ with its
own CI, Holm-corrected Mann-Whitney p): `paper/generated/tab_effects.tex`. All four are significant
at p<0.001 except the freshness comparison isn't separately Holm-corrected in the main effects table
(only reported in the live-vs-mock comparison, `tab_live_mock.tex`).

Workload(s): the TPC-DS-derived batch dataset and the seeded synthetic streaming producer (same
data-plane workloads described in `ANALYSIS.md` §2), under four injected fault scenarios: schema
drift, upstream delay, resource contention, ingress burst (`src/acde/chaos/scenarios.py`).
Number of runs/repetitions: `full` n=80 (20 replicates × 4 scenarios), `baseline`/`rule_based`/
`autoscale` n=80 each; the four single-agent ablations n=40 each (10 replicates × 4 scenarios).
Total campaign: 560 runs across 3 arms (`\NRunsTotal`).

**The manual-intervention result is the paper's central honest finding, not an omission**: `full`
increases interventions relative to the static baseline, the opposite of the base paper's reported
>70% reduction. The mechanism is not fully instrumented (per-tick proposal-outcome tracing doesn't
exist at that grain) — reported as measured, mechanism left open, not adjudicated in the system's
favor (see the archived Discussion draft, `paper/_archive_v1/07_discussion.tex`, for the fuller
treatment to re-derive from here).

## 2. Credible-baseline comparison (contribution #1)

| Baseline | Description | MTTR result | Manual interventions | Cost | Source |
|---|---|---|---|---|---|
| `rule_based` | Deterministic threshold → predefined remediation, no LLM call | 30.0 s (↓92% vs static baseline) | 0 (↓100%) | unchanged (↓0%, by design — doesn't right-size) | `\NMttrRuleBasedMedian`, `\NRelpctMttrSRuleBased`, `\NIntervRuleBasedMedian`, `\NRelpctCostUnitsRuleBased` |
| `autoscale` | Threshold autoscaling, resource-pressure faults only, no LLM call | 52.4 s (↓86%) | 0.5 (↓50%) | ↓48% | `\NMttrAutoscaleMedian`, `\NRelpctMttrSAutoscale`, `\NIntervAutoscaleMedian`, `\NRelpctCostUnitsAutoscale` |
| `full` (for comparison) | All four agents, live model | 235 s (↓38%) | 6.0 (↑500%) | ↓56% | see Table 1 |

**Both cheap, non-LLM comparators beat `full` on MTTR and on manual interventions.** This is the
sharpest instance of contribution #1's original purpose (answer "does the agent system beat cheap
automation, not just a slow human?") — the honest answer at these settings is no, on two of the four
metrics. `full` only wins outright on decision correctness (§3) and remains competitive on cost.
Neither non-LLM baseline can execute an "accepted mitigation" by design — `decision_correct=0` for
both by construction (`DEVIATIONS.md` D-059).

## 3. Decision-quality metric (contribution #2)

**Definition actually implemented in code** (`src/acde/experiments/decision_quality.py`): a per-scenario
accepted-mitigation set (`EXPECTED_ACTIONS`); a run scores 1 if it logged an *executed* agent action
whose type is in that scenario's accepted set, else 0. Non-agent baselines score 0 by construction —
they resolve faults without an agentic decision at all. This is a binary per-run outcome, not a
graded rubric; the "score" reported below is the mean across runs (equivalently, Cliff's δ against the
all-zero baseline comparator, since δ collapses algebraically to the treatment group's success rate
when the comparator is a constant zero).

| Agent config | Decisions evaluated (N) | Decision-quality rate | Significant vs. baseline? | Source |
|---|---|---|---|---|
| `full` (all 4 agents) | 80 | 0.42 | Yes, p<0.001 | `\NDeltaDecisionCorrectFull`, `\NPHolmDecisionCorrectFull` |
| Monitoring only | 40 | 0.00 | No, p=1.000 | `\NDeltaDecisionCorrectMonitorOnly`, `\NPHolmDecisionCorrectMonitorOnly` |
| Optimization only | 40 | 0.25 | Yes, p<0.001 | `\NDeltaDecisionCorrectOptimizationOnly`, `\NPHolmDecisionCorrectOptimizationOnly` |
| Schema only | 40 | 0.25 | Yes, p<0.001 | `\NDeltaDecisionCorrectSchemaOnly`, `\NPHolmDecisionCorrectSchemaOnly` |
| Recovery only | 40 | 0.00 | No, p=1.000 | `\NDeltaDecisionCorrectRecoveryOnly`, `\NPHolmDecisionCorrectRecoveryOnly` |

**This is the one metric where the live agent system does something no static or rule-based comparator
can claim to do at all** — but even `full`'s own rate (0.42) is well short of "correct majority of the
time," and it is also the metric with the largest live-vs-mock gap (mock `full` = 1.00,
`\NLiveVsMockDecisionCorrectMock`; live = 0 median / 0.42 mean, `\NLiveVsMockDecisionCorrectLive`).

## 4. Cross-LLM study (contribution #3)

**`[NO DATA]`.** The harness (`src/acde/eval/cross_model.py`) exists, is unit-tested (an injectable
probe covering decision correctness, latency, and token accounting across configurable model IDs), but
the live sweep across real provider models has never been run and recorded as part of this project's
verified results. Confirmed by exhaustive search this session: no `results/cross_model*` artifact
exists anywhere in the repository, gitignored or otherwise, and `DEVIATIONS.md`'s own D-063 entry
states directly: "live sweep is opt-in/user-run." **What would be needed to fill this table**: run
`python -m acde.eval.cross_model --models <id1> <id2> ...` against at least two live provider models
on the same scenario set the paper campaign used, and commit the resulting output the same way
`paper/data/` commits the main campaign's data. This is real, scoped, buildable future work — not a
hand-wave.

| LLM backend | Scenario(s) tested | Agreement w/ other backends | Latency | Source |
|---|---|---|---|---|
| `[NO DATA]` | `[NO DATA]` | `[NO DATA]` | `[NO DATA]` | not run |

## 5. Adversarial safety evaluation (contribution #4)

| Category | Cases | Containment [Wilson 95%] | Over-block | Oracle agreement | Fail-open |
|---|---|---|---|---|---|
| boundary_grid | 4,320 | 3,056/3,056 [0.9987, 1.0000] | 0/1,264 | 4,320/4,320 | 0 |
| defense_in_depth | 133 | 133/133 [0.9719, 1.0000] | — | 133/133 | 0 |
| fuzz | 1,000 | 606/606 [0.9937, 1.0000] | 0/394 | 1,000/1,000 | 0 |
| injection | 28 | 28/28 [0.8794, 1.0000] | — | 28/28 | 0 |
| param_extremes | 66 | 44/44 [0.9197, 1.0000] | 0/22 | 66/66 | 0 |
| **overall** | **5,547** | **3,867/3,867 [0.9990, 1.0000]** | **0/1,680** | **5,547/5,547** | **0** |

Source: `paper/data/adversarial.json` (`overall` object) and `paper/generated/tab_adversarial.tex`,
generated by `src/acde/eval/adversarial_corpus.py`. Expected verdicts come from an independently
written Python specification of the documented policy semantics — not from the Rego under test — so
the containment number is not circular (`ANALYSIS.md` §7).

Attack taxonomy actually covered (this list is itself a finding, per the template's own instruction —
an incomplete taxonomy is a statable limitation, not something to hide): a grid over every legal
(agent, action) pair × boundary/extreme context values (rate-limit counts, cost-budget edges), fuzzed
free-text justification fields, illegal proposals sent directly to the policy engine bypassing the
`ProposedAction` contract, and hostile parameter extremes. **Not covered**: multi-step attack chains
across ticks, adversarial prompt injection via telemetry content itself (the corpus attacks the
policy layer given a proposal, not the LLM's reasoning process that produces the proposal).

**Before reaching this number, the corpus found and forced fixes to two real gaps** (`DEVIATIONS.md`
lesson L6): zero/negative/non-numeric scaling targets were budget-legal or crashed the gate before the
audit row was written (fixed in the contract layer); and a newer, non-pinned OPA release mis-evaluated
some float budget comparisons (the pinned `openpolicyagent/opa:0.68.0-debug` is correct — the pin is
now load-bearing and the corpus is a regression test against a version bump changing this).

## 6. Disclosed cost model (contribution #5)

| Cost component | Static baseline | ACDE (`full`, live) | Source |
|---|---|---|---|
| Compute + storage (sub-breakdown) | `[NO DATA — see note]` | `[NO DATA — see note]` | not harvested into the committed per-run CSV |
| Provisioning (over-provisioning avoided) | included in total | included in total | `src/acde/telemetry/cost.py::provisioning_cost` |
| LLM inference / token cost | N/A (no LLM calls) | not separately priced in dollars; token/call counts tracked | `paper/generated/tab_llm.tex` |
| **Total (cost units, disclosed formula)** | **158** | **69.8 (↓56%)** | `\NCostBaselineMedian`, `\NCostFullMedian`, `\NRelpctCostUnitsFull` |

**Note on the sub-breakdown**: `telemetry.cost_ledger` computes a compute/storage split live during a
run, but the campaign's committed per-run harvest (`raw.csv`) only records the combined `cost_units`
total, not the compute/storage components separately — so that split is genuinely `[NO DATA]` at the
committed-artifact level, not just unreported. Do not present a compute-vs-storage number in the paper
without re-deriving it from a live re-run with additional harvesting, or state it as unavailable.

**Report the full, honest cross-config picture, not just the flattering `full` row** (per the
template's own instruction): two of the four single-agent ablations *increase* cost sharply —
`monitor_only` and `recovery_only` both show cost ↑676% (`\NRelpctCostUnitsMonitorOnly`,
`\NRelpctCostUnitsRecoveryOnly`) because they never get the optimization agent's right-sizing action
while still paying the provisioning term. `schema_only` also increases cost, ↑484%
(`\NRelpctCostUnitsSchemaOnly`). Only `full`, `optimization_only` (↓51%), `autoscale` (↓48%), and
implicitly `rule_based` (↓0%, unchanged by design) reduce or hold cost steady.

## 7. Graduated autonomy / kill switch (contribution #6)

- **Autonomy levels actually implemented**: shadow / approval / autonomous
  (`src/acde/config.py:181`, `acde_mode`), confirmed real (not design-only) by reading
  `src/acde/orchestrator/control.py` and `src/acde/human/approvals.py` — `ANALYSIS.md` §6.
- **Evidence of tested transitions between levels**: code-level tests exist for the individual
  mechanisms (`tests/unit/test_control.py`-style coverage for `is_paused()`/`blast_radius_exceeded()`,
  confirmed present in the 95.35%-coverage unit suite — `ANALYSIS.md` §10), but **the live 560-run
  paper campaign ran every configuration in one fixed mode throughout and never exercised a
  shadow→approval→autonomous transition, and no transition-latency log exists in `paper/data/`.**
  `[NO DATA]` for a *live, measured* transition; unit-test coverage is real but is a different kind of
  evidence than an experimental measurement, and the paper must not conflate the two.
- **Kill-switch mechanism**: `orchestrator/control.py::is_paused()`/`set_paused()`, a durable flag
  checked once per control-loop tick — real, unit-tested. **Detection-to-halt latency was not
  measured** — `[NO DATA]`. What would be needed to fill this: a dedicated experiment that engages the
  kill switch mid-run and measures ticks-to-halt under the same load conditions as the main campaign.

## Missing Evidence

1. **Cross-LLM live sweep** (§4) — harness exists, never run against real providers. Needed: run
   `eval/cross_model.py` against ≥2 live models on the campaign's scenario set; commit the output.
2. **Cost model compute/storage sub-breakdown** (§6) — only the combined total is in the committed
   per-run data. Needed: extend `runner.py::harvest_metrics` to also persist the per-component
   `cost_ledger` breakdown, then re-run (or re-harvest from a re-run) and commit.
3. **Trust-core transition/kill-switch-latency measurement** (§7) — code-level unit tests exist;
   no live experimental measurement exists. Needed: a dedicated drill (not part of the main campaign)
   that exercises mode transitions and kill-switch engagement under load and logs the timing.

These three gaps are real and should be stated plainly in the manuscript (Introduction's contribution
list should not claim #3 and #6 as evaluated; Limitations should name exactly these three items, per
`GAP_ANALYSIS.md` next) rather than glossed over or silently dropped from the paper.
