# Contributing to ACDE

Thanks for considering a contribution. ACDE is both a production tool and a research artifact, so
the bar is a bit stricter than a typical repo — please read this before opening a PR.

## Dev setup

```bash
git clone https://github.com/bodapatisaikrishna/agentic-cloud-pipeline-governance.git
cd agentic-cloud-pipeline-governance
uv sync --extra research        # full dev environment (core + benchmark/chaos/analysis)
cp .env.example .env
make lint && make test-unit     # the gate every PR must pass
```

For changes that touch the Airflow/Redpanda data plane, the policy gate, or the experiment runner,
bring up the full stack and run the integration suite too:

```bash
make up && make seed
make test-integration
make opa-test                   # Rego policy test suite (needs the stack up)
```

## The project's conventions

This codebase was built under a strict phase-gated workflow (see `CLAUDE.md`), and PRs are expected
to follow the same spirit even though the formal "phase" ceremony is for the original build:

- **Determinism.** `MOCK_LLM=1` is the default everywhere (tests, CI, local runs). Any stochastic
  component takes an explicit seed. Live-LLM code paths must degrade gracefully (see
  `src/acde/llm/client.py`) and must never be required for tests to pass.
- **No secrets in code or git.** Configuration goes through `.env` (git-ignored) and
  `src/acde/config.py`'s `Settings`. Never commit a real API key, even in an example file.
  `.env.example` / `.env.prod.example` must only ever contain placeholders.
- **Document deviations.** If you make a design decision that isn't obviously forced by the code
  (a new default, a modeling choice, a tradeoff), add an entry to `DEVIATIONS.md`: what you decided
  and why. This file is a first-class research/audit artifact, not an afterthought.
- **Agents never execute code or bypass the policy gate.** Every operational action must go through
  `policy/gate.py` → OPA → `policy/executor.py`. If you're adding a new agent action type, it needs
  an entry in the relevant Rego policy and in `contracts/actions.py`'s allow-list.
- **Type hints + docstrings on public functions.** `ruff` (lint + format) and `mypy` must pass —
  `make lint` runs both.

## Pull requests

1. Fork, branch from `main`, keep the change focused (one logical change per PR).
2. Run `make lint && make test-unit` locally before opening the PR — CI runs the same gate plus
   OPA policy tests, a Docker image build, and a dependency vulnerability scan.
3. Add or update tests for any behavior change. New modules need unit tests; changes that touch
   the live stack should have an integration test where practical.
4. If your change is a design decision (not just a bug fix), add a `DEVIATIONS.md` entry.
5. Fill out the PR template — it mirrors the CI gate so reviewers can see at a glance what's covered.

## Reporting bugs / requesting features

Use the issue templates (bug report / feature request). For anything you believe is a security
issue, please see [`docs/SECURITY.md`](docs/SECURITY.md) rather than opening a public issue.

## License

By contributing, you agree your contributions are licensed under the project's
[Apache License 2.0](LICENSE).
