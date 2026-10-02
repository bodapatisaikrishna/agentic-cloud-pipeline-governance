# PROMPT: Write the ACDE Journal Paper (Evidence-Grounded, Phased)

You are Claude Code, working directly inside the ACDE repository
(`agentic-cloud-pipeline-governance`). Your job is to produce a submission-ready
journal manuscript about **Agentic Cloud Data Engineering (ACDE)** — but only
after you have actually understood this codebase. Do not draft a single
sentence of the paper before Phase 1 is complete and approved.

Read these files in this folder before doing anything else:
- `context.md` — everything already known about this project, the paper it
  extends, and the author's constraints and preferences.
- `codebase_analysis_guide.md` — how to inventory this repo.
- `paper_structure_template.md` — the target manuscript outline.
- `related_work_seed.md` — a starting related-work bibliography.
- `experiment_results_template.md` — the exact metrics the paper needs, and the
  rule that every number must come from this repo.
- `target_venues.md` — candidate journals and their formatting constraints.

## Ground rules (non-negotiable, apply to every phase)

1. **No invented facts.** Every architectural claim, every number, every
   figure in the final paper must trace to something you actually found in
   this repository (code, config, logs, test output, commit history,
   README, or a file the user hands you directly). If you cannot verify a
   claim, write `[NEEDS VERIFICATION: <what you need>]` instead of guessing.
   This mirrors how this author works — real data with proper attribution,
   never illustrative or placeholder figures presented as if real.
2. **Distinguish "designed" from "evaluated."** ACDE's roadmap (see
   `context.md` §4) lists six intended extensions over the base paper. Some
   of these may exist only as code/design and not yet as run experiments.
   The paper must say so explicitly — a described-but-unevaluated
   contribution is still legitimate content for a paper (as future work or
   as an architectural contribution), but it must never be reported as if
   it were measured.
3. **Cite the base paper correctly and often**, but never present ACDE's
   work as a restatement of it. Every section should make the *delta* over
   [BASE] explicit (see `related_work_seed.md` for the full citation and a
   short summary).
4. **Work in phases with a checkpoint after each one.** Stop and summarize
   what you found/produced, then wait for the user's go-ahead before moving
   to the next phase. Do not silently chain all phases together — the
   author works in Plan Mode → approval → auto-accept, with explicit
   go/no-go checkpoints between build stages, and expects the same rhythm
   here.
5. **Keep your own commentary to the user short** (5–10 lines, plain
   English) at each checkpoint, even though the manuscript text itself
   should be full, formal academic prose. Don't confuse "be concise with
   me" with "write a short paper."
6. Save every phase's output as its own file in `paper/` (not just chat
   output), so nothing is lost between sessions: `ANALYSIS.md`,
   `GAP_ANALYSIS.md`, `results_filled.md`, `outline_v1.md`,
   `manuscript_draft_v1.md`, etc.

## Phase 0 — Load context (no output needed, just confirm)

Read the six files listed above plus the repo's own `README.md` and any
existing docs. Reply with a 3–5 line confirmation of what you now understand
the project to be, and name anything in `context.md` that already looks
stale or contradicted by what's in the repo. Wait for acknowledgment.

## Phase 1 — Codebase inventory (produces `ANALYSIS.md`)

Follow `codebase_analysis_guide.md` exactly. Produce `ANALYSIS.md` covering:
real architecture (agents, trust core, policy engine, data plane), what's
implemented vs. stubbed, LLM backends actually wired in, test coverage, and
a development timeline from git history.

**CHECKPOINT 1:** Present a short summary of `ANALYSIS.md`. Explicitly flag
anything that doesn't match `context.md`'s description of the project (e.g.
if a claimed feature isn't in the code, or the repo is further along / less
far along than expected). Ask the user to confirm before continuing.

## Phase 2 — Experiment & results audit (produces `results_filled.md`)

Search the repo for experiment scripts, benchmark configs, logs, notebooks,
CSV/JSON result dumps, and any evaluation harness. Fill in
`experiment_results_template.md` with real numbers only, renamed as
`results_filled.md`. For every metric you cannot find real data for, list it
under a `## Missing Evidence` heading with exactly what would need to be run
to produce it.

**CHECKPOINT 2:** Report which of the paper's required metrics have real
data behind them and which don't. If major metrics are missing (e.g. no
actual MTTR comparison, no adversarial safety eval run), **stop and ask the
user whether to (a) run the missing experiments first, (b) scope the paper
down to what's actually measured, or (c) reframe unmeasured items as
proposed/future work.** Do not proceed to drafting until this is resolved —
this is exactly the kind of go/no-go decision the user wants surfaced, not
silently papered over.

## Phase 3 — Gap analysis vs. the base paper (produces `GAP_ANALYSIS.md`)

Using `ANALYSIS.md` + `results_filled.md`, build a table mapping each of
ACDE's six claimed extensions (in `context.md` §4) to: implemented?
evaluated? evidence location (file/commit)? This table becomes the spine of
the paper's "Contributions" framing — don't let the manuscript claim more
than this table supports.

**CHECKPOINT 3:** Share the table. Confirm with the user which contributions
to foreground vs. soften to "future work" before outlining the paper.

## Phase 4 — Outline (produces `outline_v1.md`)

Instantiate `paper_structure_template.md` for this specific paper: real
section titles, one-paragraph description of what each section will argue,
and which artifact (`ANALYSIS.md`, `results_filled.md`, `GAP_ANALYSIS.md`,
`related_work_seed.md`) it draws from. No manuscript prose yet.

**CHECKPOINT 4:** Get outline approval. This is the last checkpoint before
full drafting — treat it as the "no going back without a conversation" gate.

## Phase 5 — Full draft (produces `manuscript_draft_v1.md`)

Write the full manuscript at journal length (see `target_venues.md` for the
chosen venue's expectations — confirm venue choice with the user if not
already settled). Ground every section strictly in the phase 1–3 artifacts.
Related Work should extend `related_work_seed.md` with any additional
literature you can verify (real citations only — flag anything you can't
fully verify a DOI/venue for rather than inventing one).

Do not add a "Limitations" section that merely gestures at humility — make
it specific and load-bearing: name exactly which of the six contributions
lack empirical evaluation, and why (per `GAP_ANALYSIS.md`).

**CHECKPOINT 5:** Deliver the draft for review. Ask whether the user wants
it exported as `.docx` (formal submission-ready) or kept as Markdown/PDF for
further iteration.

## Phase 6 — Polish pass

Check citation consistency, section cross-references, figure/table
numbering, adherence to the chosen venue's formatting rules (word count,
citation style, structure), and that no unverified numbers slipped in
during drafting. Produce a final `manuscript_final.md` (or `.docx` per the
venue skill) plus a short cover-letter-ready summary of contributions.

---

**If at any point the repository doesn't support a claim this prompt or
`context.md` assumes, trust the repository, not this document.** Flag the
discrepancy to the user rather than quietly reconciling it either direction.
