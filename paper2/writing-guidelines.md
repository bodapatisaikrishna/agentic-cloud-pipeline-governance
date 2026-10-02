# Writing Guidelines (ground rules + skill usage)

## Non-negotiable ground rules (from `PAPER_WRITING_PROMPT.md`, carried forward verbatim in spirit)

1. **No invented facts.** Every architectural claim, number, or figure must trace to something real
   in this repository or a verified external source. If a claim can't be verified, write
   `[NEEDS VERIFICATION: <what's needed>]` rather than guessing. This repository's whole culture
   already works this way — `paper/generated/numbers.tex` exists specifically so the manuscript
   contains zero hand-typed numbers; keep that discipline in the rewrite.
2. **Distinguish "designed" from "evaluated."** `GAP_ANALYSIS.md` is the enforcement mechanism:
   contributions 3 (cross-LLM) and 6 (trust core) are implemented but not evaluated by the live
   campaign — legitimate content as future work / architectural contribution, never reported as
   measured.
3. **Cite the base paper correctly and often**, and make the delta explicit every section — never let
   a section read as a restatement of the base paper's own architecture description.
4. **Checkpoint rhythm.** Phases 0–4 (context, analysis, results, gap analysis, outline) are done and
   approved. Phase 5 (full draft) and Phase 6 (polish) get their own checkpoints before finalizing.
5. **Report what the data shows, including unflattering results**, without reconciling them away —
   the manual-intervention increase and the mock-vs-live divergence are the paper's most important
   findings, not things to soften.
6. **Save every phase's output as its own file** — already done (`context.md`, `ANALYSIS.md`,
   `results_filled.md`, `GAP_ANALYSIS.md`, `paper-outline.md`, `references.md`, this file).

## How the three named skills apply

- **`academic-research-skills`** (the `academic-paper` subskill, or whichever of its subskills best
  fits a given drafting task — `academic-paper-reviewer` is useful for a self-critique pass before the
  Phase 6 checkpoint, `deep-research`/its literature tools for filling the unverified leads in
  `references.md`): use this to structure and draft each section from `paper-outline.md` +
  `results_filled.md`, and to verify new citations before they're added to `refs.bib`. This is the
  primary drafting skill for Phase 5.
- **`academic-humanizer`**: run as a pass over drafted prose to fix AI-sounding tells — not-X-but-Y
  contrasts, forced triads, staged openers, one-line closers — while explicitly preserving every
  number, citation, and claim exactly as written. This skill is designed not to touch results/claims,
  which matches ground rule #1 exactly; prefer it as the primary humanizing pass for this reason.
- **`humanizer`** (the `~/.agents/skills/` one): a second, more general humanizing pass, used only if
  `academic-humanizer`'s output still reads stiff after its own pass. Don't run both redundantly on
  the same text — pick whichever produces the better result and move on.
- **Order of operations per section**: draft with `academic-research-skills` → self-check against
  `GAP_ANALYSIS.md`/`results_filled.md` for any unevidenced claim that crept in → run
  `academic-humanizer` (and `humanizer` only if needed) → verify every number still traces to a
  `paper/generated/numbers.tex` macro (no hand-typed literals introduced during humanizing).

## Style notes specific to this paper

- Match the archived draft's established voice where it already worked (hedged, precise, cites exact
  figures via LaTeX macros, no unearned confidence) — the independent verification agent that
  fact-checked the archived draft found it "unusually consistent and self-critical" and "defensively
  hedged rather than overclaiming." That's the right register; the rewrite should meet or exceed it,
  not drift toward more confident/promotional language.
- Every table/figure caption must be self-contained (a reader shouldn't need the body text to
  understand what's plotted, what N is, what error bars represent) — carried forward from the
  already-completed journal-quality pass on the figures themselves (Okabe-Ito colorblind palette,
  vector PDF, embedded fonts — `src/acde/analysis/paper_figures.py` already meets this bar and does
  not need to change).
- Statistics: state Cliff's δ with its standard interpretation thresholds on first use (Method
  section), then just report the number afterward without re-explaining.
- No "Limitations" as a gesture — per `paper_structure_template.md`, Limitations should read as the
  mirror image of `GAP_ANALYSIS.md`, naming exactly which contributions lack empirical evaluation and
  why, not generic hedging language.

## Verification before calling any section done

Same discipline already proven out twice this session: after drafting, run (or have a fresh-context
agent run) an independent check that re-derives a sample of the section's numbers directly from
`paper/data/`, confirms every citation resolves to a real source, and confirms the LaTeX compiles with
zero undefined references. Do not skip this because it was already done for the archived draft — the
rewrite is a new text and needs its own verification pass before the Phase 6 checkpoint.
