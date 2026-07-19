# Authoring policies

ACDE's safety comes from **your** policies, not the LLM. Every proposed action is evaluated by Open
Policy Agent (OPA) before anything happens. Policies are versioned Rego in `infra/opa/policies/`,
hot-reloaded by OPA (`--watch`), and testable with `make opa-test`.

## The decision contract

The gate sends OPA an `input` (the proposed action + context) and expects a decision:

```json
{ "allowed": true, "escalate": false, "reason": "...", "policy_id": "cost_budget" }
```

- `allowed=false, escalate=false` → **denied** (nothing happens).
- `allowed=false, escalate=true` → **escalated** to a human.
- `allowed=true` → subject to the execution mode (shadow / approval / autonomous).

**Fail-safe:** if OPA is unreachable, the gate escalates — it never allows.

## Shipped policy packs (`infra/opa/policies/`)

- `cost_budget.rego` — deny/escalate actions whose projected marginal cost exceeds the remaining
  budget.
- `recovery_approval.rego` — high-impact recovery (e.g. rollback) requires a prior version / escalates.
- `schema_compat.rego` — gate schema actions on backward/breaking compatibility.
- `rate_limit.rego` — cap actions per agent per 10 minutes (runaway-loop guard).
- `main.rego` — aggregates the packs into the final decision.

## Common policies to add

- **Change-freeze windows:** deny/escalate all actions during a release freeze (check a
  timestamp/tag in `input`).
- **Environment tiers:** stricter rules for `input.pipeline_criticality == "critical"`.
- **Per-team budgets / allowed action types.**
- **Require approval** for specific action types (also expressible via `APPROVAL_REQUIRED_ACTION_TYPES`
  without Rego).

## Testing policies

Write `*_test.rego` alongside each policy and run:

```bash
make opa-test        # 20+ cases ship green
```

The adversarial safety eval (`python -m acde.eval.adversarial`) additionally proves your live policy
set contains malicious/out-of-policy proposals — run it in staging after editing policies. In our
reference policy set it reports **containment = 1.0**.
