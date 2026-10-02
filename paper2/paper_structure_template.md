# Manuscript Structure Template (Phase 4 output shape)

This mirrors the IMRaD-plus-governance structure the base paper itself uses
(so reviewers see a clear lineage), extended with the sections a journal
version needs that a short conference-style paper doesn't. Every section
lists which Phase 1–3 artifact it must be grounded in. Do not fill in prose
here — Phase 4 produces `outline_v1.md` with one paragraph per section
describing *what it will argue and from what evidence*; Phase 5 turns that
into full prose.

## Title
Working options (finalize once contributions are confirmed in Phase 3):
- "Beyond Policy-Bounded Control: Graduated Autonomy, Adversarial Safety,
  and Disclosed Cost in Agentic Cloud Data Engineering"
- "Agentic Cloud Data Engineering Revisited: A Trust-Core Architecture for
  Safe, Cost-Transparent Pipeline Governance"
(Pick one once Phase 3's gap analysis shows which contributions actually
carry the paper.)

## Abstract
150–250 words. Must state: the problem, what the base paper already showed,
what specific gap ACDE closes, the method, and the *actual* headline
result(s) — grounded in `results_filled.md`, not aspirational.

## Keywords
Cloud data engineering; agentic AI; policy-bounded autonomy; LLM agents;
pipeline governance; AI safety evaluation. (Adjust once contributions are
finalized.)

## 1. Introduction
- Motivation (can reuse the base paper's framing of reactive pipeline
  ops — cite it, don't restate it as if original).
- Explicit statement of what this paper adds over [BASE].
- Contribution list — **only list what `GAP_ANALYSIS.md` confirms is
  actually implemented and evaluated**; anything not yet evaluated goes in
  Future Work, not here.
- Ground in: `context.md` §2–4, `GAP_ANALYSIS.md`.

## 2. Related Work
- Cloud data engineering & workflow orchestration (Airflow/Prefect/Dagster)
- Infrastructure autoscaling and its data-semantics blindness
- Rule-based/heuristic automation
- LLM-based and agentic infrastructure systems
- Agent safety/governance (kill switches, graduated autonomy, authorization
  frameworks) — this subsection is ACDE-specific and not in the base paper;
  it's where contribution #4/#6's related work lives.
- Explicit positioning paragraph: how ACDE differs from [BASE] specifically.
- Ground in: `related_work_seed.md`, supplemented with verified new sources.

## 3. System Architecture
- Three planes + Trust Core, as actually implemented (not as originally
  described in [BASE] — note deltas explicitly).
- Architecture diagram (regenerate from real module structure, don't reuse
  [BASE]'s figure).
- Ground in: `ANALYSIS.md` §2–6.

## 4. Contributions Beyond [BASE]
One subsection per confirmed contribution (credible baselines,
decision-quality metric, cross-LLM study, adversarial safety evaluation,
disclosed cost model, graduated-autonomy trust core). Each subsection:
what it is, why it matters (tie to a specific limitation of [BASE] or a
real industry concern from `related_work_seed.md`), how it's implemented.
- Ground in: `GAP_ANALYSIS.md`, `ANALYSIS.md`.

## 5. Implementation
- Tech stack, deployment model, LLM backends actually integrated.
- Ground in: `ANALYSIS.md` §1, §4.

## 6. Experimental Setup
- Workloads/datasets actually used (name them precisely; if reusing [BASE]'s
  choices — TPC-DS, open government data, NYC taxi records — say so and
  cite; if different, describe exactly).
- Baselines actually compared against.
- Failure-injection / adversarial scenarios actually run.
- Metrics, with precise definitions (especially the new decision-quality
  metric — define its rubric/ground truth explicitly, this is a common
  reviewer objection point for novel metrics).
- Ground in: `results_filled.md`, `ANALYSIS.md` §9.

## 7. Results
- One subsection per metric category, each with a real table/figure from
  `results_filled.md`. No narrative claim without a number next to it.
- Where evidence is partial, say so in-line rather than only in Limitations.

## 8. Discussion
- What the results mean, honestly — including where ACDE's improvement over
  [BASE]'s own reported numbers is marginal, absent, or not directly
  comparable (different workloads/baselines should be flagged, not glossed
  over).
- Where governance/safety tradeoffs showed up (conservative policies
  limiting optimization potential — same theme [BASE] already flags).

## 9. Threats to Validity / Limitations
- Explicit, per-contribution: which of the six are evaluated only in
  simulation vs. anything closer to production; sample sizes; whether the
  cross-LLM study covers enough models/scenarios to generalize; whether the
  adversarial eval's attack taxonomy is exhaustive or illustrative.
- Ground in: `GAP_ANALYSIS.md` directly — this section should read like the
  mirror image of that table.

## 10. Conclusion and Future Work
- Restate confirmed contributions plainly.
- Future work: anything from `context.md` §4 that didn't make it to
  "evaluated," plus [BASE]'s own future-work items ACDE didn't address
  (multi-agent coordination, policy learning, hybrid/multi-cloud, formal
  verification) — cite [BASE] for these, framed as the remaining open
  problems this paper doesn't claim to solve.

## References
- [BASE] in full, plus everything pulled into Related Work. Verify every
  entry has a real, checkable citation (DOI/arXiv ID/conference proceedings)
  before final submission — do not include a citation you can't verify.
