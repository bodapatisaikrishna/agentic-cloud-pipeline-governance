# Pre-registered analysis plan: ACDE campaign v2

Status: fixed before any `paper_v2` data was collected. This file is committed to git; the commit
that adds it is its timestamp. Any later change is listed under "Amendments" with its date and
reason, and in DEVIATIONS.md.

## 1. Purpose

v1 (D-104) reported that governed LLM agents (`full`) cut MTTR by 38% and cost by 56% against a
static-plus-human baseline, while manual interventions rose sixfold. Five measurement problems were
found afterwards (D-105, D-106). The largest: the simulated human drew one delay per escalation and
resolved the fault at the fastest, so configurations that re-escalated got a shorter MTTR from the
simulator itself. v2 re-runs the experiment with those problems fixed. It tests whether the v1
effects survive fair measurement. It does not try to improve on v1's numbers.

## 2. Design

- **Configurations (9):** `baseline`, `rule_based`, `autoscale`, `monitor_only`, `recovery_only`,
  `optimization_only`, `schema_only`, `full`, `hybrid` (D-107).
- **Scenarios (4):** `schema_drift`, `upstream_delay`, `resource_contention`, `ingress_burst`.
- **Replicates:** 20 per (configuration, scenario), so 80 per configuration and 720 live or
  LLM-free runs, plus 80 mock-LLM `full` runs (the mock arm). 800 runs in all.
- **Pairing:** run seed = `sha256("{scenario}:{replicate}") % 2**32`, shared by every configuration,
  so matched runs see the same fault parameters and the same simulated-human delay (D-105, D-106).
- **Order:** one fixed shuffle of all 720 cells (seed `DEFAULT_SEED` = 42); the supervisor takes
  runs in that order across arms.
- **Timings:** warm-up 120 s, response loop 300 s, settle 5 s.
- **Isolation:** agent-written state and Airflow pools reset before each run; every run metered
  over the same 305 s window (D-105).
- **Model:** the live arm uses the provider and models recorded in the manifest provenance. The
  model choice is fixed before the campaign starts and recorded in the amendments below.

## 3. Outcomes

Primary (each run contributes one value):

| Metric | Definition |
|---|---|
| `mttr_injection_s` | median over the run's faults of resolved minus injected time |
| `escalated_incidents` | faults that needed a human, each escalation attributed to one fault |
| `cost_units` | metered compute + storage + held provisioning over the fixed window |
| `decision_correct` | 1 if an executed action is a valid mitigation for the scenario |

Secondary: `mttr_s` (from detection, for continuity with v1), `detection_delay_s`,
`manual_interventions` (requests), `cost_compute_units` (metered compute only, the part not set by
the provisioning assumption), `freshness_s`, and the LLM accounting metrics.

## 4. Hypotheses

Stated as two-sided tests; the direction expected from v1 is noted but not assumed.

- **H1 (MTTR):** `mttr_injection_s` differs between `full` and `baseline`. After the D-106 fix,
  v1's gain for `full` is expected to shrink sharply, because 73 of 80 v1 `full` runs were resolved
  by the human.
- **H2 (escalations):** `escalated_incidents` differs between `full` and `baseline`.
- **H3 (cost):** `cost_units` differs between `full` and `baseline`; `cost_compute_units` is
  reported alongside, since most of v1's cost gap was the provisioning assumption.
- **H4 (decisions):** `decision_correct` for `full` differs from the mock arm's `full`.
- **H5 (rules vs agents):** `full` and `hybrid` each differ from `rule_based` on `mttr_injection_s`
  and `escalated_incidents`.
- **H6 (mock vs live):** every primary metric differs between live `full` and mock `full`.

## 5. Analysis

- **Primary test:** paired Wilcoxon signed-rank on the 80 (scenario, replicate) pairs, two-sided.
  The v1 rank-sum test is reported alongside for continuity.
- **Multiplicity:** Holm-Bonferroni within each family at α = 0.05.
  - Family A: 4 primary metrics × 8 configurations against `baseline` (32 tests; H1 to H3).
  - Family B: `full` and `hybrid` against `rule_based`, 2 metrics (4 tests; H5).
  - Family C: live against mock `full`, 4 primary metrics plus `freshness_s` (5 tests; H4, H6).
- **Effect sizes:** median difference with a 95% percentile-bootstrap interval, Cliff's δ with a
  95% bootstrap interval, and relative change of medians (2,000 resamples, seed 20260921).
- **Stratification:** per-scenario medians for every configuration, and a stratified permutation
  test (labels permuted within scenario, 5,000 permutations) for every Family A comparison, as a
  robustness check. A Family A result that is significant pooled but not stratified is reported as
  scenario-dependent.
- **Equivalence (TOST, 90% bootstrap interval):** where a comparison is not significant, it is
  called equivalent only if the interval of the median difference lies within the margin:
  - MTTR: ±30 s (the rule baseline's remediation latency);
  - cost: ±10% of the `baseline` median;
  - escalated incidents: ±0.5;
  - decision correctness: ±0.1 on the difference in proportions (a binary metric has no useful
    median difference).
  Otherwise it is reported as inconclusive, never as "no difference".
- **Decision quality:** a failure taxonomy from the exported actions
  (`results/paper-v2-*/actions/`): for each scenario, the executed and denied action types and
  policy verdicts in runs with `decision_correct = 0`.

## 6. Exclusions and missing data

- **Primary analysis excludes** runs with `state_reset_ok = 0` (pool reset failed), together with
  their paired runs in the other configurations, so pairs stay complete. The number excluded is
  reported per configuration.
- **Sensitivity analysis** also excludes live runs with `llm_degraded >= 10` (the supervisor's
  degraded-run threshold) and their pairs.
- A run that crashes is re-run by the supervisor with the same seed; no other run is dropped or
  repeated.

## 7. Stopping rule

The campaign runs to the full matrix or stops at the token ceiling set before launch. If it stops
early, the analysis uses the completed pairs only and reports n per configuration. Agent results
are not inspected before the matrix completes. The LLM-free arms (baselines and mock) may complete
first; their numbers are checked only for the pipeline's correctness (no crashes, `state_reset_ok`),
not compared against agent configurations.

## 8. Power (from v1 data)

`python -m acde.analysis.power` resamples the v1 `baseline` values and asks which proportional
reduction 80 runs per configuration detect with 80% power (rank-sum test, 400 simulations, which
ignores the pairing and is therefore conservative):

| Metric | v1 baseline median | MDE at α = 0.05 | MDE at α = 0.05 / 32 |
|---|---|---|---|
| MTTR | 378 s | 20% | 30% |
| Cost | 157.5 units | 5% | 5% |

An MTTR effect smaller than about 20% may therefore go undetected; a non-significant MTTR result
is reported with its equivalence interval for that reason.

## 9. Reporting

v1 and v2 are reported side by side, and v1 is not replaced or re-analysed as if it were
confirmatory. Every number in the manuscript is generated by
`python -m acde.analysis.paper_artifacts --protocol v2`, which refuses to build from arms whose
provenance differs (code fingerprint, timings, human model, cost parameters, budgets) or whose LLM
mode does not match the arm.

## Amendments

(none yet)
