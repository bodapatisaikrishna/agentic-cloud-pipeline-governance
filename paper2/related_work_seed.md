# Related Work — Seed Bibliography

This is a starting point, not a finished bibliography. It was compiled by
searching the web outside the repository, before the codebase was analyzed.
Claude Code should: (1) verify every citation below actually resolves before
using it, (2) add anything the codebase's own imports/design point to that
isn't here, and (3) run fresh literature searches for Phase 5 — this field
moves fast enough that a search done before this document existed will
already be stale by the time the paper is drafted.

## The paper being extended

> A. Muthukrishnan Kirubakaran, A. Parthasarathy, N. Saksena, R. S. Bodala,
> A. Deshpande, S. Malempati, S. Carimireddy, and A. Mazumder, "Governing
> Cloud Data Pipelines with Agentic AI," arXiv:2512.23737v1.
> https://arxiv.org/abs/2512.23737

Full summary and its own limitations are in `context.md` §2 — don't
duplicate that here. **Positioning note for the Related Work section:** this
paper's own "Positioning of This Work" subsection already stakes out
"policy-bounded agentic control" as its differentiator from unconstrained
LLM-driven automation. ACDE's job in Related Work is to show that
"policy-bounded" is *asserted* in that paper, not *adversarially tested* —
that's the opening for contribution #4.

## Categories the base paper itself organizes Related Work into
(useful as a starting skeleton — verify/update each with current sources
rather than reusing the base paper's own citation list wholesale, since a
paper shouldn't just cite its predecessor's bibliography secondhand):

1. **Cloud data engineering & workflow orchestration** — Airflow, Prefect,
   Dagster, managed cloud schedulers. Known as execution-centric: they
   schedule and retry, but don't reason about *how* to adapt to failures,
   load shifts, or schema change.
2. **Infrastructure autoscaling** — reacts to CPU/memory-level signals, not
   pipeline-semantic signals (data freshness, downstream dependency
   criticality, governance constraints).
3. **Rule-based/heuristic automation** — predictable and auditable but
   brittle; can't be hand-coded to cover the diversity of real failure modes.
4. **LLM-based/agentic infrastructure automation** — expressive but raises
   safety/compliance risk from unconstrained action generation in regulated
   environments. This is the category ACDE's trust core and adversarial
   eval directly respond to.

## New material for ACDE-specific contributions (found, needs verification
before final citation — treat titles/URLs below as leads to chase down
proper bibliographic entries for, not as final references)

**Graduated autonomy / kill-switch architectures for AI agents**
(contribution #6 — the "trust core"):
- Industry pattern literature increasingly frames agent safety as a
  *graduated* response system (a "traffic-light"/staged model — shadow,
  advisory, bounded auto-approve, full autonomy) rather than a binary
  full-autonomy-vs-kill-switch choice, because pure kill-switches waste the
  investment in the agent while pure full autonomy accumulates risk. This
  is a strong practitioner-literature framing to cite for *why* a graduated
  model is the right design, distinct from [BASE]'s simpler
  propose-then-validate boundary.
- There's active discussion (2026, including proposed U.S. legislation
  requiring preserved kill-switch capability for powerful AI systems) of
  kill switches as a governance/regulatory requirement, not just an
  engineering nicety — useful for motivating why "disclosed, testable
  kill-switch behavior" is a publishable contribution rather than a minor
  implementation detail.
- Formal/academic treatments of execution-time authorization for agentic
  systems exist (compositional authorization frameworks for delegation and
  scope in agentic AI) — relevant if ACDE's policy/trust layer does anything
  resembling scoped delegation or bounded permission inheritance.

**Adversarial/safety evaluation of agentic systems** (contribution #4):
- Real, documented incidents of agent "kill switches" failing to catch
  escapes in time (logging/attribution lag rather than the switch itself
  failing) are a good motivating example for *why* an adversarial
  evaluation needs to test detection latency and escalation paths, not just
  whether a policy check exists in code.
- General practitioner consensus: production agent safety depends on
  monitoring/observability plus layered containment (risk monitors,
  human-in-the-loop escalation, scoped credentials) more than on the
  agent's own prompt/instructions — relevant framing for why ACDE's
  adversarial eval should target the *policy/governance layer's* robustness,
  not just the LLM's behavior.

**Agentic AI in cloud computing generally** (broader context for
Introduction/Related Work, not a specific contribution):
- Survey-level material on agentic AI's relationship to cloud service
  models (IaaS/PaaS/SaaS) and where agent workloads get placed (cloud vs.
  edge vs. on-prem) is useful for framing the Introduction's "why cloud, why
  now" paragraph.

## Target-journal thematic fit

Note (see `target_venues.md` for detail): Journal of Cloud Computing:
Advances, Systems and Applications currently runs an open call on "next
generation cloud computing driven by artificial intelligence" — Related
Work should be written in a way that visibly speaks to that thematic framing
if that's the chosen venue.

## Reminder on citation integrity

- Never fabricate a DOI, page range, or venue name to make a citation look
  more complete. If you found a claim via web search but can't pin down a
  formal citation, either keep looking or cite it as a web source
  (organization + URL + access date) rather than inventing a paper-style
  entry.
- Per the copyright rule this author's other work already follows: paraphrase
  everything; do not reproduce more than a short (<15 word) quoted phrase
  from any single source, and attribute it.
