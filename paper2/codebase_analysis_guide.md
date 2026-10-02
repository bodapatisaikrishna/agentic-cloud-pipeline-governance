# Codebase Analysis Guide (Phase 1)

Goal: produce `ANALYSIS.md`, a factual inventory of what ACDE actually is
today, that Phases 2–6 can be grounded in. This is not the paper — it's the
evidence base for the paper. Be exhaustive and literal; if something is
unclear from the code, say so rather than assuming intent.

## What to inventory

### 1. Repository shape
- Directory tree (top two or three levels), with a one-line purpose per
  top-level folder.
- Language(s), frameworks, and package manager(s) in use (read
  `requirements.txt`/`pyproject.toml`/`package.json`/etc.).
- Size signals: rough LOC per major module, number of source files, number
  of test files.

### 2. Architecture, as actually implemented
For each of the three planes described in the base paper (Data Plane,
Policy & Governance Plane, Agentic Control Plane) and ACDE's added Trust
Core:
- Which files/modules implement it?
- Is it real logic or a stub/mock/TODO?
- What are the actual inputs/outputs and interfaces between planes (function
  calls, message queues, APIs, shared state store, etc.)?

For each of the four agents (Monitoring, Optimization, Schema, Recovery):
- Locate the implementing module(s).
- What telemetry/metadata does it actually consume (real schema, or
  placeholder)?
- What does it actually propose, and how — hardcoded logic, an LLM call, a
  hybrid?
- Confirm whether the observe → reason → propose → evaluate loop from the
  base paper is genuinely present, or simplified.

### 3. LLM integration (needed for the cross-LLM contribution)
- Which LLM providers/models are actually wired into the code right now
  (look for API client imports, model name strings, config files, env vars)?
- Is model choice pluggable/config-driven, or hardcoded to one provider?
- Is there an existing harness that runs the same scenario against multiple
  models and records their outputs for comparison? If yes, where; if no,
  say so explicitly — this directly determines whether contribution #3 in
  `context.md` §4 is real yet.

### 4. Policy / governance layer
- How are policies represented (YAML/JSON config, DSL, code)?
- Is there an actual enforcement point that can reject/veto an agent's
  proposed action, or is enforcement only implied by convention?
- Any versioning/audit trail (git history of policy files, an audit log
  table/file, etc.)?

### 5. Trust core / graduated autonomy / kill switch (contribution #6)
- Is there a distinct module for this? What autonomy levels/states exist in
  code (enum, state machine, config)?
- Is there an actual kill-switch mechanism (a function/endpoint/flag that
  halts agent action execution), and is it tested?
- Any logs or tests demonstrating a transition between autonomy levels?

### 6. Adversarial safety evaluation (contribution #4)
- Is there a test suite, script, or notebook that deliberately feeds
  adversarial/malformed inputs (bad telemetry, conflicting policies,
  injected instructions) to agents and checks what the Policy Plane does?
- If yes: what attack/scenario classes are covered, and what were the
  pass/fail outcomes? (Do not summarize outcomes yet if numbers aren't
  final — just record what's there.)
- If no: say so plainly for `GAP_ANALYSIS.md`.

### 7. Cost model (contribution #5)
- Is there code that tracks/estimates operational cost (compute, storage)
  separately from LLM/token cost?
- Any existing cost report, log, or dashboard output?

### 8. Experiments, benchmarks, and results
- Locate anything under likely paths (`experiments/`, `eval/`, `benchmarks/`,
  `notebooks/`, `results/`, `scripts/run_*`, CI artifacts).
- For each, note: what workload/dataset it uses, what it measures, whether
  it has actually been executed (look for output files, timestamps, logged
  metrics), and how recent that run is (git log / file mtime).
- Cross-reference against the base paper's own workloads (TPC-DS, open
  government data, NYC Taxi records, synthetic streaming) — is ACDE reusing
  these, substituting others, or not yet running comparable workloads at all?

### 9. Tests
- Test framework, number of test files/cases, rough coverage if measurable.
- Which of the six novel contributions (if any) have dedicated tests —
  this is evidence of maturity beyond "it runs once in a notebook."

### 10. Development history (for a methods/timeline narrative, and honesty
about scope)
- `git log --oneline` summarized into a short timeline: when did major
  components (each agent, the trust core, the eval harness) land?
- Any large single commits that suggest scaffolded/generated code vs.
  iteratively developed code — not to judge, just to describe accurately if
  the paper discusses methodology/development process at all.

### 11. Docs already in the repo
- README, any design docs, ADRs, or the professor-facing proposal document
  mentioned in project notes — read these for the *author's own* framing of
  scope, since it may be more current than `context.md`.

## Output format for `ANALYSIS.md`

Use these headings (fill each with what you actually found — "not present"
is a valid, useful answer):

```markdown
# ACDE Codebase Analysis

## 1. Repository overview
## 2. Architecture as implemented
## 3. Agent-by-agent status (Monitoring / Optimization / Schema / Recovery)
## 4. LLM backend integration
## 5. Policy & governance layer
## 6. Trust core / graduated autonomy / kill switch
## 7. Adversarial safety evaluation
## 8. Cost model
## 9. Experiments and results present in-repo
## 10. Test coverage
## 11. Development timeline
## 12. Discrepancies vs. context.md (flag anything that doesn't match)
```

Keep it factual and cite file paths for every claim (e.g. "implemented in
`agents/schema_agent.py:42-110`") so Phase 5 drafting can trace every
architectural sentence in the paper back to a real location.
