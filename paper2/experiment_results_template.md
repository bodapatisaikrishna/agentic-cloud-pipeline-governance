# Experiment Results — Fill With Real Data Only

**Rule for every table below: a cell is either a real number traced to a
file/log/run in the repository (cite the path), or it is left as
`[NO DATA]`. Never estimate, interpolate, or borrow a plausible-sounding
number from the base paper's results to fill a gap.** If a whole table can't
be filled, keep it empty and describe what's missing under "Missing
Evidence" at the bottom — that's a normal, useful output of this phase, not
a failure.

Rename this file `results_filled.md` once populated.

## 1. Core operational metrics (comparable to the base paper)

| Metric | Static baseline | ACDE | Source (file/log path) |
|---|---|---|---|
| Mean pipeline recovery time (MTTR) | | | |
| Operational cost (aggregate) | | | |
| Data freshness (streaming) | | | |
| Manual intervention frequency | | | |

Workload(s) these numbers come from: `[NAME EXACT DATASET/WORKLOAD USED]`
Number of runs / repetitions: `[N]`
Failure scenarios injected: `[schema drift / upstream delay / resource
contention / other — list exactly which, and how many of each]`

## 2. Credible-baseline comparison (contribution #1)

List every baseline actually compared against (not just "static
orchestration" — if ACDE adds rule-based heuristic automation or vanilla
autoscaling as additional baselines, list each):

| Baseline | Description | Result summary | Source |
|---|---|---|---|
| | | | |

## 3. Decision-quality metric (contribution #2)

- **Definition actually implemented in code:** `[paste/describe the actual
  scoring rubric or ground-truth comparison method — do not restate an
  aspirational definition if the code implements something narrower]`
- **Results:**

| Agent | Decisions evaluated (N) | Decision-quality score | Source |
|---|---|---|---|
| Monitoring | | | |
| Optimization | | | |
| Schema | | | |
| Recovery | | | |

## 4. Cross-LLM study (contribution #3)

| LLM backend | Scenario(s) tested | Agreement w/ other backends | Latency | Source |
|---|---|---|---|---|
| | | | | |

Note: "agreement" needs a concrete operationalization (e.g. % of scenarios
where two backends proposed the same action class) — record whatever the
code actually measures, don't paraphrase this into something fuzzier or
more impressive-sounding than what's implemented.

## 5. Adversarial safety evaluation (contribution #4)

| Attack/scenario class | # attempts | # caught by policy layer | # bypassed | Source |
|---|---|---|---|---|
| | | | | |

Attack taxonomy actually covered: `[list explicitly — this list itself is
a finding to report, since an incomplete taxonomy is a legitimate,
statable limitation rather than something to hide]`

## 6. Disclosed cost model (contribution #5)

| Cost component | Static baseline | ACDE | Source |
|---|---|---|---|
| Compute (execution) | | | |
| Storage | | | |
| LLM inference / token cost | | N/A (baseline has none) | |
| **Total** | | | |

If ACDE's total cost is *higher* than the baseline once LLM cost is
included even though compute cost is lower, **report that honestly** — it's
a more credible and more interesting result than a paper that only reports
the flattering half of the comparison.

## 7. Graduated autonomy / kill switch (contribution #6)

- Autonomy levels actually implemented: `[list, e.g. shadow / advisory /
  bounded-auto / full — or "not yet implemented, design only"]`
- Evidence of tested transitions between levels: `[test file / log]`
- Kill-switch mechanism: `[how it's invoked, whether it's tested, whether
  detection-to-halt latency was measured]`

## Missing Evidence

List every metric/table above that could not be filled, and exactly what
running/logging would be needed to fill it. This section is what Phase 2's
checkpoint (in `PAPER_WRITING_PROMPT.md`) is built around — it drives a real
decision with the user about scope before any drafting starts.
