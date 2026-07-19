# Security & threat model

ACDE embeds LLM agents into a data-pipeline control plane. Its design goal is that **an unreliable or
compromised model cannot cause an unsafe or unauthorized action** — safety comes from the
architecture, not the model.

## Design guarantees

- **Bounded agency.** Agents emit only a typed `ProposedAction` (pydantic-validated). An action type
  outside an agent's allow-list is rejected at construction — it never reaches execution.
- **Policy gate before every action.** OPA evaluates each action; the executor performs a side effect
  only for an allowed decision. The gate **fails safe** (escalates) if OPA is unreachable.
- **Graduated autonomy.** Shadow → approval → autonomous, per deployment; high-blast action types can
  be forced to human approval even in autonomous mode.
- **Hard limits.** Global kill switch (`acde pause`) and a per-target hourly blast-radius cap bound
  the agents independent of policy.
- **No code generation / execution.** LLMs never produce or run code; they select from a fixed set of
  parameterized actions.

## Verified

The adversarial safety evaluation (`python -m acde.eval.adversarial`, `src/acde/eval/adversarial.py`)
injects unsafe proposals — over-budget scaling, unapproved rollback, rate-limit floods,
breaking-schema "allow" — and measures the gate's containment rate. Against the reference policy set
it reports **containment = 1.0** (every unsafe proposal denied or escalated), plus contract-layer
rejection of out-of-allow-list action types. Re-run it in staging after editing policies.

## Operator responsibilities

- **Secrets** via environment / secret manager only; never commit `.env.prod`. `API_KEY` must be a
  strong random value — the operator API refuses to start without it (fail-closed).
- **Network posture:** bind the API to localhost and front it with a TLS-terminating reverse proxy
  with authn; do not expose it directly. Verify TLS on your Airflow endpoint (`AIRFLOW_VERIFY_TLS`).
- **Least privilege:** give the connector service account only the orchestrator permissions the
  chosen actions require (see `docs/CONNECTING.md`). Use `noop`/shadow to grant no write access.
- **LLM data handling:** telemetry snapshots are sent to the configured LLM provider. For data
  residency, use an on-prem OpenAI-compatible endpoint (`LLM_PROVIDER=openai_compatible`). Webhook
  payloads redact action `params`.

## Attack surface & mitigations

| Surface | Risk | Mitigation |
|---|---|---|
| LLM prompt injection via telemetry | model proposes an unsafe action | policy gate + typed contracts contain it (containment = 1.0) |
| Operator API | unauthorized approvals/reads | mandatory API key, fail-closed; TLS via proxy |
| Connector credentials | pipeline compromise | least-privilege service account; TLS verify; shadow/noop for zero write access |
| Runaway loop | mass actions | rate-limit policy + blast-radius cap + kill switch |

## Reporting

The software is provided "AS IS" under Apache-2.0 (see LICENSE/NOTICE). Validate in a non-production
environment before granting production write access. Report vulnerabilities to the repository owner.
