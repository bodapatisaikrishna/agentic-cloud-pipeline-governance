# Context (Phase 0)

This file was referenced by `PAPER_WRITING_PROMPT.md` but did not exist in the original `paper 2/`
folder. Reconstructed from the repository itself (not invented) — every claim below traces to a real
file, commit, or committed data artifact. Where the original templates in this folder assumed a
project state, this file states the actual current state instead and flags the difference explicitly.

## 1. What this project is

**ACDE (Agentic Cloud Data Engineering)** is a research-grade replication and extension of:

> A. Muthukrishnan Kirubakaran, A. Parthasarathy, N. Saksena, R. S. Bodala, A. Deshpande,
> S. Malempati, S. Carimireddy, and A. Mazumder, "Governing Cloud Data Pipelines with Agentic AI,"
> arXiv:2512.23737. https://arxiv.org/abs/2512.23737

(BibTeX key `kirubakaran2025governing` in `paper/refs.bib` — already verified this session by fetching
the live arXiv abstract page and cross-checking title, all 8 authors, and the headline claims
attributed to it.)

The base paper proposes four bounded LLM agents (monitoring, optimization, schema, recovery) that
observe a cloud data pipeline's telemetry, reason via an LLM, and propose structured actions; an OPA
policy gate validates every proposal before anything executes. It reports MTTR reduction ~45%,
operational cost reduction ~25%, and manual-intervention reduction >70% against static orchestration
and a human on-call baseline.

**What ACDE is, concretely**: a real, working implementation of that architecture (`src/acde/`), a
production trust core beyond what the base paper describes (graduated autonomy, kill switch,
multi-tenant operator API — the "v2.0 production tool" half of the repo), and an evidence campaign
that tests the base paper's claims under a live remote model at the base paper's own timings, rather
than only a fast deterministic mock.

## 2. Base paper's own limitations (the opening for this work)

- Reports three point numbers (45%/25%/70%) with **no statistics** — no confidence intervals, no
  significance testing, no effect sizes, no disclosed sample size.
- Compares only against a single baseline (static orchestration + human on-call) — no comparison
  against cheap non-LLM automation (rule-based responders, threshold autoscaling), so "beats a human"
  and "beats automation in general" are conflated.
- Asserts "policy-bounded ⇒ safe" as a design property; never adversarially tests the policy layer.
- Asserts model-agnosticism ("§VI.A") with no cross-model data.
- Never defines a decision-quality metric — only speed/cost/intervention-count, never whether the
  *chosen* mitigation was actually correct for the fault.
- Does not disclose a cost model (compute-only vs. provisioning-aware makes the ~25% claim go either
  direction depending on the assumption — this repository found that ambiguity directly, see
  `DEVIATIONS.md` D-006/D-061).

## 3. Author's working constraints and preferences (observed this session, not assumed)

- **No invented facts.** Every claim must trace to code, data, or a verified external source. This
  project already enforces this rigorously: `paper/generated/numbers.tex` contains every quoted
  statistic as a `\newcommand` macro generated mechanically from `paper/data/`, so the existing
  manuscript (now archived at `paper/_archive_v1/`, see below) had zero hand-typed numbers.
- **Report what the data shows, including unflattering results.** The live campaign found the
  agentic system *increases* manual interventions and is beaten on speed by cheap non-LLM automation —
  this is treated as the paper's central finding, not something to reconcile away.
  `DEVIATIONS.md` and `REPORT.md` are written in this voice throughout; match it.
- **Phased work with explicit checkpoints**, not silently chaining everything through. Confirmed by the
  user's explicit instruction this session to follow `PAPER_WRITING_PROMPT.md`'s phase/checkpoint
  structure for this rewrite.
- **Real citations only** — `refs.bib`'s header comment records that every entry was checked against
  its primary source (Crossref/arXiv/publisher) on a specific date; this discipline continues here.
- **Design-deviation log** (`DEVIATIONS.md`, 103 entries, D-001 through D-104o) — every non-obvious
  decision this project has made is recorded there with alternatives and rationale. Treat it as a
  primary source, not secondary commentary.

## 4. The six roadmap contributions beyond the base paper

(This numbering is the one `related_work_seed.md` and `experiment_results_template.md` already assume;
kept consistent here.)

1. **Credible baselines** (`DEVIATIONS.md` D-058) — `rule_based` and `autoscale`, non-LLM comparators,
   answering "does the agent system beat cheap automation, not just a slow human?"
2. **Decision-quality metric** (D-059) — `decision_correct`: did the executed action match a
   per-scenario accepted-mitigation set, not just "was it fast."
3. **Cross-LLM study** (D-063) — `eval/cross_model.py` exists and is unit-tested; the **live sweep
   across real providers has not been run and recorded** (`DEVIATIONS.md` D-063: "live sweep is
   opt-in/user-run"). This is implemented but not evaluated — must be framed as architecture/future
   work in the paper, never as a measured result.
4. **Adversarial safety evaluation** (D-062, expanded by D-104) — a generated corpus (5,547 cases)
   graded against an independently written specification oracle, containment ≥0.999 (Wilson 95%),
   found and fixed two real contract-layer gaps before reaching that number (`DEVIATIONS.md` L6 /
   `paper/generated/tab_adversarial.tex`).
5. **Disclosed cost model** (D-061) — an explicit compute + storage + provisioning-gap formula
   (`src/acde/telemetry/cost.py`), making the base paper's undisclosed ~25% claim testable and honestly
   caveated (depends on the provisioning-gap assumption, quantified via sensitivity analysis).
6. **Graduated-autonomy trust core** (D-065) — shadow/approval/autonomous execution modes, a durable
   kill switch, per-target blast-radius caps. **Implemented extensively** (`src/acde/orchestrator/control.py`,
   `src/acde/human/approvals.py`) but **not exercised or measured by the live campaign**, which ran in
   one fixed mode throughout. Also an architecture/design contribution, not an evaluated one, in the
   live-campaign paper.

Contributions 1, 2, 4, 5 are both implemented and evaluated by the completed 560-run live campaign.
Contributions 3 and 6 are implemented but not evaluated — `GAP_ANALYSIS.md` (Phase 3) makes this
precise and this must carry through to the manuscript's Introduction and Limitations sections without
softening.

## 5. What already exists that the original `PAPER_WRITING_PROMPT.md` did not anticipate

The prompt was written assuming a near-zero starting state (expecting `results_filled.md` to come back
mostly `[NO DATA]`, gating on "should we run the missing experiments"). That gate is already resolved:

- **The live evidence campaign is complete**: 560/560 runs (live-agents 240, non-agent baselines 240,
  mock-`full` 80), zero aborted runs, 975,570/1,300,000 tokens, launched 2026-09-22, completed
  2026-09-26. Per-run data is committed at `paper/data/` (not git-ignored `results/`), checksummed
  (`paper/data/SHA256SUMS`), and every table/figure/number in `paper/generated/` regenerates
  byte-for-byte from it (`make paper-repro-quick`).
- **Two independent verification passes already ran this session**: one fact-checked every headline
  number in the (now-archived) manuscript by re-deriving it directly from `paper/data/` with a
  standalone script (zero discrepancies found, including the least flattering numbers) and verified
  every bibliography entry against its real source (including fetching the live arXiv abstract for the
  base paper). A second, four-agent pass line-by-line verified every `.md` file in the repository
  against the actual codebase and fixed 9 real staleness bugs found in the process (a wrong license
  claim, a wrong campaign completion date repeated across 5 files, stale test/entry counts, etc.).
- **A previous manuscript draft existed** (all sections, compiled cleanly, journal-quality front/back
  matter added) — now archived at `paper/_archive_v1/`, not deleted, per this rewrite's explicit
  instruction to re-derive rather than trust the prior prose. `paper/data/`, `paper/generated/`, and
  the generator code (`src/acde/analysis/paper_artifacts.py`, `paper_figures.py`) are **not** part of
  that archive and are the ground truth this rewrite draws from.

## 6. Discrepancies vs. the original `paper2/` templates (flag, don't silently reconcile)

- `context.md` itself did not exist — this file.
- `experiment_results_template.md`'s instruction to leave cells `[NO DATA]` where nothing was run no
  longer applies to 4 of 6 contributions — real data exists and should be filled in, cited to
  `paper/data/`/`paper/generated/numbers.tex`, not re-run.
- `related_work_seed.md` was compiled "before the codebase was analyzed" per its own header — it is a
  reasonable starting skeleton but needs verification and supplementing in Phase 4/5, per its own
  instruction.
- `target_venues.md`'s JoCCASA recommendation and the note on Springer's open call for "next generation
  cloud computing driven by artificial intelligence" are unverified against the *current* live call
  page (the file itself says to re-verify before final formatting) — treated as a starting
  recommendation, decision deferred to the outline checkpoint.
