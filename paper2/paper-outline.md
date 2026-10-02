# Manuscript Outline (Phase 4)

Instantiates `paper_structure_template.md` for this specific paper. One paragraph per section: what it
argues and which `paper2/` artifact grounds it. No prose yet — Phase 5 turns this into
`paper/sections/*.tex`. Central organizing thesis, confirmed with the user: **the mock-vs-live
divergence** — governance claims about this class of system depend on which evaluation path produced
them, and a mock/simulated evaluation is not a conservative stand-in for a live one; it is a
categorically different, far more favorable experiment. Everything else in the paper (the six
contributions, the production lessons) is organized as evidence for or against that thesis, not as a
flat list of unrelated results.

## Title

Working title: **"Which Evaluation Path? Live-Model Evidence for Policy-Gated Agentic Cloud Pipeline
Governance"** — foregrounds the thesis (evaluation path matters) rather than leading with the system
name. Alternative, closer to the two options `paper_structure_template.md` proposed: "Do Policy-Gated
LLM Agents Govern Cloud Data Pipelines? A Live-Model Replication and the Mock-vs-Live Divergence."
Finalize once Phase 5 drafting shows which reads better; both are grounded in `GAP_ANALYSIS.md`.

## Abstract (150–250 words)

States: the base paper's claim (45%/25%/70%, no statistics, mock-adjacent evaluation); what this work
does (a 560-run live campaign at the base paper's own real timings, plus credible baselines, decision
quality, adversarial safety, disclosed cost, all four measured); the headline result (`full` beats
static orchestration on MTTR ↓38% and cost ↓56%, but *increases* manual interventions ↑500%, and is
beaten on speed by cheap non-LLM automation); the central finding (the identical `full` configuration
run under a deterministic mock instead of the live model diverges by roughly three orders of magnitude
on MTTR and decision quality — Table/Figure `tab_live_mock`/`fig_live_mock`); and the practical
implication (evaluation-path disclosure is not optional for this class of system). Ground in:
`results_filled.md` §1, §3; `GAP_ANALYSIS.md`'s "seventh finding" note.

## Keywords

LLM agents; cloud data pipeline governance; policy-as-code; Open Policy Agent; AIOps; replication
study; adversarial evaluation; mock-vs-live evaluation validity. (Reuses the archived draft's keyword
line, `paper/_archive_v1/00_abstract.tex` — still accurate, no change needed.)

## 1. Introduction

- Motivation reusing the base paper's own framing of reactive pipeline ops (cite, don't restate as
  original) — `context.md` §1.
- Explicit statement of what this paper adds over the base paper, organized around the thesis: not
  just "we ran it live," but "we show *why* running it live changes the answer, and by how much."
- Contribution list drawn directly from `GAP_ANALYSIS.md`'s table — 1/2/4/5 as measured, 3/6 as
  architectural/future work, stated with that distinction explicit in the list itself, not buried in
  Limitations.
- What is NOT novel: the architecture (three planes, four agents, policy gate) is the base paper's;
  restated from `context.md` §1 almost verbatim, since that framing already tested well in the
  archived draft.
- Ground in: `context.md` §1–4, `GAP_ANALYSIS.md`.

## 2. Related Work

- Cloud data engineering & workflow orchestration (Airflow/Prefect/Dagster) — execution-centric,
  doesn't reason about adaptation.
- Infrastructure autoscaling — reacts to resource signals, not pipeline-semantic ones.
- Rule-based/heuristic automation — predictable, brittle. (Directly relevant here: this paper's own
  `rule_based` baseline sits in this category and beats the LLM system on two metrics — Related Work
  should set this up rather than treat rule-based automation as a strawman.)
- LLM-based/agentic infrastructure automation — expressive, raises safety/compliance risk from
  unconstrained action generation.
- Statistics: bootstrap resampling, Mann-Whitney rank-sum, Wilcoxon signed-rank, Holm correction,
  Cliff's δ, Wilson intervals — same citations already verified in `paper/refs.bib`
  (`efron1979`, `mann1947`, `wilcoxon1945`, `holm1979`, `cliff1993`, `wilson1927`).
- Explicit positioning paragraph: the base paper asserts "policy-bounded ⇒ safe" and "model-agnostic";
  this work adversarially tests the first and honestly reports not yet testing the second live.
- Ground in: `related_work_seed.md` (verify/supplement each citation per its own instruction — it was
  compiled before the codebase was analyzed), `paper/refs.bib`'s existing 10 verified entries.

## 3. System

- Three planes + the contract + policy plane + execution/audit + simulated human, as actually
  implemented — reuse the archived draft's structure (`paper/_archive_v1/03_system.tex`) and its
  already-fixed architecture figure (`paper/generated/fig_arch.pdf`, still valid — built from the same
  codebase, no change needed), re-deriving the prose rather than copying it verbatim.
- Ground in: `ANALYSIS.md` §2, §5, §6.

## 4. Method

- Testbed, scenarios (4 injected faults), configurations (8: baseline, rule_based, autoscale, full,
  4 ablations), the three campaign arms (live-agents/baselines/mock-full) and why they're split.
- Live model and billing-accurate accounting (real calls vs. cache hits vs. degraded vs. invalid,
  counted at the moment a call is or is not made).
- Metrics: MTTR, cost, manual interventions, freshness, decision correctness (with its exact
  definition — `results_filled.md` §3's rubric, stated precisely since novel metrics draw reviewer
  scrutiny).
- Seeds, provenance, and the nominal-vs-paired seed-matching caveat (rank-sum as primary test).
- Statistics: medians/IQR, bootstrap CIs, Cliff's δ with standard interpretation thresholds
  (negligible/small/medium/large), Holm-corrected Mann-Whitney, Wilson intervals; explicit
  exploratory-not-pre-registered framing.
- Adversarial evaluation method: the generated corpus, independent-oracle design.
- Sensitivity method: human-latency scale-family argument, cost-model provisioning sweep.
- Ground in: `ANALYSIS.md` §1, §9; ACDE's own campaign runbook (`docs/CAMPAIGN.md`).

## 5. Results

Organized around the thesis, not as a flat metric dump:

- 5.1 Does `full` beat static orchestration? (Table `tab_main`/`tab_effects`, Fig `fig_mttr`/
  `fig_effects`) — MTTR ↓38%, cost ↓56%, manual interventions ↑500% (the honest reversal).
- 5.2 Does it beat cheap automation? (`results_filled.md` §2) — no, on two of four metrics.
- 5.3 Decision quality (`results_filled.md` §3) — the one axis only the live system can claim, still
  <50%.
- 5.4 Per-scenario heterogeneity (Table `tab_scenarios`, Fig `fig_scenarios`) — no config dominates
  every fault type.
- **5.5 The central finding: mock vs. live** (Table `tab_live_mock`, Fig `fig_live_mock`) — given its
  own prominent subsection, not folded in as one more comparison; this is where the thesis is proven
  with numbers, not just asserted.
- 5.6 LLM accounting (Table `tab_llm`) — zero degraded/invalid in the final campaign, with the
  cache-poisoning defect found and fixed during the *pilot* named explicitly as why the accounting
  exists.
- 5.7 Sensitivity (Table `tab_sensitivity`, Fig `fig_human_sensitivity`/`fig_cost`) — break-even points
  make the headline numbers' conditionality explicit, reinforcing the thesis from a different angle
  (even the live numbers are conditional on modeling choices).
- 5.8 Adversarial containment (Table `tab_adversarial`) — measured *after* two real fixes the corpus
  itself forced.
- Ground in: `results_filled.md` in full, `GAP_ANALYSIS.md`.

## 6. Production-Hardening Lessons

- L1–L7 as in the archived draft (`paper/_archive_v1/06_lessons.tex`), re-derive from
  `DEVIATIONS.md`'s actual entries rather than copy: concurrency-unsafe shared resource (D-074),
  write-ahead audit trail (D-084), the detector with no callers (D-091), taxonomy mismatch (D-100),
  hermeticity-by-enumeration (D-103), what the adversarial corpus found (L6, tie to §5.8), the dead
  live model the pilot caught (L7).
- Ground in: `DEVIATIONS.md` D-074/D-084/D-091/D-100/D-103/D-104(various)/D-062, `ANALYSIS.md`.

## 7. Discussion

- 7.1 The manual-intervention mechanism is measured, not explained (honest open question).
- 7.2 Limitations and threats to validity — **the mirror image of `GAP_ANALYSIS.md`**: simulated
  human, one live model family, unequal replicate counts, nominal seed matching, one node/one policy
  pin/four scenarios, **and explicitly the three genuine evidence gaps** (cross-LLM sweep never run;
  trust core never exercised by the campaign; cost sub-breakdown not harvested) — each with what
  would close it, reusing `results_filled.md`'s "Missing Evidence" section near-verbatim.
- 7.3 Ethics and autonomy — the decision-quality and manual-intervention results argue against full
  autonomy at these settings; the trust core (contribution #6, architectural) is the answer, not yet
  the evidence.
- 7.4 What would change our mind — a cross-model repetition finding the same order-of-magnitude gap
  would strengthen the thesis; one that didn't would be evidence the gap is model-specific, reported
  just as plainly.
- Ground in: `GAP_ANALYSIS.md` directly, `results_filled.md`'s Missing Evidence section.

## 8. Conclusion and Future Work

- Restate the thesis plainly: which evaluation path produced a number matters as much as the number.
- Confirmed contributions (1/2/4/5) restated briefly; contributions 3/6 and the base paper's own
  unaddressed future-work items (multi-agent coordination beyond static-priority bidding, policy
  learning beyond the disabled-by-default adaptation mechanism, multi-cloud, formal verification)
  named as the remaining open problems, citing the base paper for the ones it already flagged.
- Ground in: `GAP_ANALYSIS.md`, `context.md` §4.

## Back matter (kept from the archived draft, re-verified rather than rewritten from scratch)

- **Data and Code Availability, CRediT Author Contributions, Conflict of Interest, Funding, Ethics and
  Broader Impact, AI-Assistance Disclosure** — the archived `09_statements.tex` is substantively sound
  (already independently verified this session); re-derive its factual claims against the current
  state rather than assume it's still accurate, but it does not need to be rebuilt from zero.
- **Claims-audit appendix** — rebuild from the new section numbering once Phase 5 drafting is complete;
  same discipline as before (claim → evidence artifact → generating script), now also pointing back to
  the relevant `paper2/` artifact where useful.
- **Design-deviation log appendix, Reproduction guide appendix** — unchanged (`B_deviations.tex`,
  `C_reproduction.tex` were never archived, still in `paper/sections/`).

## References

`related_work_seed.md`'s categories, supplemented with independently verified sources found during
Phase 5 drafting; the base paper (`kirubakaran2025governing`) cited throughout, never restated as if
this paper's own architecture. Every entry checked against a real DOI/arXiv ID/venue before use — the
existing `refs.bib`'s 10 entries are already verified and reusable as-is.

## Venue (decision deferred, not needed to shape this outline)

`target_venues.md` recommends Journal of Cloud Computing: Advances, Systems and Applications
(JoCCASA) as primary target, given its live thematic call on AI-driven cloud computing. The outline
above is venue-agnostic (generic IMRaD-plus-governance structure, no page-limit assumptions baked in)
so this doesn't block drafting; venue choice — and whatever formatting/word-count constraints it
implies — is a decision for before final polish (Phase 6), per `target_venues.md`'s own note to
re-verify current guidelines immediately before formatting.
