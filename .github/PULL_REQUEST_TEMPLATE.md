## What & why

<!-- What does this change do, and why? Link an issue if there is one. -->

## Checklist

- [ ] `make lint` passes (ruff check, ruff format, mypy)
- [ ] `make test-unit` passes (coverage stays ≥ 80%)
- [ ] Added/updated tests for the behavior change
- [ ] If this touches the data plane, policy gate, or orchestrator: ran `make test-integration`
      (and `make opa-test` if a Rego policy changed) against a live stack
- [ ] If this is a design decision (not just a bug fix), added a `DEVIATIONS.md` entry
- [ ] No secrets, API keys, or real credentials in the diff (including examples/tests)
- [ ] Docs updated if user-facing behavior changed (`README.md`, `docs/*.md`, `CHANGELOG.md`)

## How was this tested?

<!-- Commands you ran, or describe the manual verification. -->
