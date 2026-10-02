# Gap Analysis vs. the Base Paper (Phase 3)

The spine of the rewritten Introduction's contribution list and the mirror image of the Limitations
section. Built from `ANALYSIS.md` (what's implemented) and `results_filled.md` (what's evaluated).
Checkpoint 2 decision (confirmed with the user): contributions #3 and #6 are framed as
implemented-but-not-evaluated architectural contributions / future work — not measured results.

| # | Contribution | Implemented? | Evaluated by the live campaign? | Evidence location | Paper framing |
|---|---|---|---|---|---|
| 1 | Credible non-LLM baselines (`rule_based`, `autoscale`) | Yes — `src/acde/experiments/baselines.py` | **Yes** — n=80 each, full statistical comparison | `paper/data/paper-baselines/`, `paper/generated/tab_main.tex`/`tab_effects.tex` | Foreground. Both beat `full` on MTTR and manual interventions — the sharpest result in the paper. |
| 2 | Decision-quality metric (`decision_correct`) | Yes — `src/acde/experiments/decision_quality.py` | **Yes** — n=80 (`full`) / n=40 (each ablation) | `paper/generated/tab_effects.tex`, `results_filled.md` §3 | Foreground. The one metric only the live agent system can claim at all; still <50% correct for `full`. |
| 3 | Cross-LLM reasoning study | Yes — `src/acde/eval/cross_model.py`, unit-tested | **No** — live sweep never run; no artifact exists anywhere in the repo (`DEVIATIONS.md` D-063: "opt-in/user-run") | `ANALYSIS.md` §4, `results_filled.md` §4 (`[NO DATA]`) | **Future work.** Describe the harness and what it's designed to test; state plainly no live comparison was run. Never imply a cross-model result exists. |
| 4 | Adversarial safety evaluation (generated corpus + independent oracle) | Yes — `src/acde/eval/adversarial_corpus.py` | **Yes** — 5,547 cases graded, containment ≥0.999 (Wilson 95%) | `paper/data/adversarial.json`, `paper/generated/tab_adversarial.tex` | Foreground. Found and fixed two real contract-layer gaps before reaching that number — the fixing, not just the final rate, is part of the contribution. |
| 5 | Disclosed cost model (v1 compute-only, v2 provisioning-aware) | Yes — `src/acde/telemetry/cost.py` | **Yes** — `full` total cost measured (↓56%); compute/storage sub-breakdown not harvested into committed data | `paper/generated/numbers.tex` (`\NRelpctCostUnitsFull` etc.), `results_filled.md` §6 | Foreground the total (the one headline claim that survives at or above the base paper's reported magnitude), with the honest caveat that two ablations *increase* cost sharply and the sub-component breakdown is unavailable at this evidence tier. |
| 6 | Graduated-autonomy trust core (shadow/approval/autonomous, kill switch, blast-radius cap) | Yes, substantially — `src/acde/orchestrator/control.py`, `src/acde/human/approvals.py` | **No** — the campaign ran in one fixed mode throughout; no transition or kill-switch-latency measurement exists | `ANALYSIS.md` §6, `results_filled.md` §7 (`[NO DATA]`) | **Architectural contribution, not an evaluated one.** Describe fully (it's real, substantial, and directly answers a safety question the base paper never addresses), but never report a transition-latency or kill-switch number that wasn't measured. |

## What this table implies for the manuscript

- **Introduction's contribution list**: contributions 1, 2, 4, 5 stated as measured results with their
  headline numbers; contributions 3 and 6 stated as implemented capabilities, explicitly marked as not
  yet evaluated, with a forward pointer to the Discussion/Limitations section rather than silently
  omitted or inflated into a claim the data doesn't support.
- **Limitations section**: should read as close to the mirror image of this table as the
  `paper_structure_template.md` instructs — name exactly these two gaps (cross-LLM, trust-core
  evaluation) plus the cost sub-breakdown gap, each with what evidence would be needed to close it
  (already stated precisely in `results_filled.md`'s "Missing Evidence" section, reusable near-verbatim).
- **A seventh, cross-cutting finding that isn't one of the six numbered contributions but belongs at
  the same level of prominence**: the mock-vs-live divergence. Not a "contribution" in the
  roadmap sense — it's a methodological finding about how the *whole* evaluation should be read. `full`
  run under the deterministic mock shows near-instant MTTR (0.193s) and perfect decision-correctness
  (1.00); the identical configuration run live shows 235s MTTR and 0.42 decision-correctness. This
  should be the paper's central thesis, not a subsection — it explains why the base paper's own mock
  (or mock-adjacent) evaluation produced flattering numbers that don't survive a live, real-latency
  evaluation, and it's the load-bearing reason a "replication" of this kind of system needs to be done
  at the base paper's own real timings, not a simulation of them.
- **What NOT to foreground**: `agents/adaptation.py` (bounded adaptation from logged outcomes, D-064)
  is implemented but off by default and not part of the six-contribution list or the campaign's
  measured results — mention briefly as a concretization of the base paper's vague "adaptation" claim,
  not as a headline contribution.
