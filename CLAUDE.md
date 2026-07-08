# CLAUDE.md — ACDE repo conventions

ACDE (Agentic Cloud Data Engineering): research-grade replication of arXiv:2512.23737
"Governing Cloud Data Pipelines with Agentic AI". Four bounded LLM agents (monitoring,
optimization, schema, recovery) propose actions gated by OPA before execution.
The full spec lives in the original project brief; this file condenses the rules.

## Non-negotiable rules

1. **Plan Mode first, every phase.** Present files/decisions/test plan; wait for approval.
2. **Phase gates.** After a phase: `make lint && make test-unit` + that phase's integration
   check, paste results, STOP with a Manual Verification Checklist. Never continue unasked.
3. **No secrets in code or git.** Everything via `.env` (git-ignored); keep `.env.example` current.
4. **MOCK_LLM=1 is the default.** All tests and CI pass with zero API calls.
5. **Determinism.** Every stochastic component takes an explicit seed; LLM temperature=0.
   Seed policy: `run_seed = sha256(f"{config}:{scenario}:{replicate}") % 2**32`.
6. **Underspecified decision → simplest defensible option + DEVIATIONS.md entry**
   (decision, alternatives, rationale). DEVIATIONS.md is a research artifact.
7. **Agents never emit or execute code.** Only output: `ProposedAction` validated by pydantic
   (`src/acde/contracts/actions.py`). Invalid output → rejected, logged, counted as
   `agent_output_invalid`.
8. **Every phase updates** README.md, CHANGELOG.md, and (if decisions made) DEVIATIONS.md.

## Code standards

- Python 3.11, full type hints, pydantic v2 for all cross-boundary data.
- ruff (lint + format, line length 100) and mypy must pass: `make lint`; fix with `make fmt`.
- Files ≤ ~400 lines (split modules), docstrings on public functions, no dead code.
- All config through `acde.config.Settings` — no literals scattered in code.
- All logging through `acde.logging.get_logger(component)` — JSON lines with
  `ts/level/component/event` + structured extras (always include `experiment_run` when known).
- All DB access through `acde.db` helpers (dict rows, bounded retry).
- Dependencies: `uv add ...` (never pip); `uv.lock` is committed; deps are added in the
  phase that needs them.

## Layout

- `src/acde/` — package (contracts, llm, agents, policy, dataplane, telemetry, chaos,
  human, orchestrator, experiments per the spec tree).
- `infra/postgres/init/` — idempotent DDL (schemas: telemetry, warehouse, control).
- `infra/opa/policies/` — Rego policies + `*_test.rego` (Phase 3).
- `tests/unit/` — no docker, no network, MOCK_LLM=1, coverage ≥80% on src/acde (enforced).
- `tests/integration/` — `@pytest.mark.integration`, requires `make up`.
- `analysis/` — scripts, not notebooks. `results/` is git-ignored.

## Commands

`make up|down|logs|clean` (stack) · `make lint|fmt|test-unit|test-integration` (quality)
· future targets (`seed`, `chaos-*`, `agents`, `baseline`, `experiment-*`, `analyze`,
`report`) are stubbed until their phase lands.

## Phase status

Track progress in README.md's phase table; current phase and gates live there.
