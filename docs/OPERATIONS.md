# Operating ACDE in production

ACDE governs your data pipelines with policy-bounded AI agents. This guide covers deploying it,
graduating trust, and running it safely.

## Deploy (Docker Compose, single host)

```bash
cp .env.prod.example .env.prod          # fill in API_KEY, POSTGRES_PASSWORD, AIRFLOW_*, LLM key
docker compose -f deploy/docker-compose.prod.yml up -d --build
curl -s localhost:8099/health           # readiness = full doctor report
```

The prod profile runs **only** `acde-server` + OPA + Postgres. Your orchestrator (Airflow) stays
external — ACDE attaches to it via a connector. Use a **managed Postgres** in real deployments and
put a **TLS-terminating reverse proxy** in front of `acde-server` (the container binds localhost).

> Do not run the stack on Docker Desktop for anything long-running — use a Linux VM or Kubernetes.
> (During development we observed Docker Desktop crashing under sustained load; a self-healing wrapper
> was needed. Production hosts should use a real container runtime.)

## The trust ladder — start in shadow

`ACDE_MODE` controls what happens to an *allowed* action:

| Mode | Behavior | When |
|---|---|---|
| **shadow** (default) | Log the proposal + policy verdict; **never touch the pipeline** | Day 1 — watch and build trust |
| **approval** | Queue the action; a human `approve`/`reject`s; execute on approval | Once proposals look right |
| **autonomous** | Execute allowed actions | Only for action types you fully trust |

Even in autonomous mode, action types in `APPROVAL_REQUIRED_ACTION_TYPES` (e.g. `rollback`) always
require sign-off. Side-effect-free acknowledgements always run.

```bash
acde doctor                       # validate DB, OPA, connector, LLM, mode, notifications
acde run --env prod               # start the control loop (shadow-safe if ACDE_MODE unset)
acde status                       # mode / paused / pending approvals / action count
acde approvals list               # pending human approvals
acde approvals approve 42         # execute a queued action
acde approvals reject 42 --note "change freeze"
```

## Kill switch & blast radius

- **Stop everything now:** `acde pause` — the loop takes no actions within one tick (durable, no
  restart). `acde resume` to re-enable.
- **Bound the damage:** `BLAST_RADIUS_MAX_PER_HOUR` caps executed actions per target per hour,
  independent of policy.

## Observability

- `GET /metrics` (Prometheus): `acde_proposals_total`, `acde_actions_executed_total`,
  `acde_actions_escalated_total`, `acde_actions_denied_total`, `acde_approvals_pending`,
  `acde_llm_tokens_total`. A starter Grafana panel set + alerts live in `deploy/observability/`.
- Every action is an audit row in `telemetry.agent_actions` (agent, action, target, policy verdict +
  reason, executed, outcome, model, tokens). `GET /audit` exposes it.
- **Notifications:** set `WEBHOOK_URL` to a Slack-compatible endpoint; ACDE pings on pending
  approvals, escalations, and execution failures (params redacted).

## Upgrades & data

Schema changes are additive/idempotent — `make migrate` (or restart, which re-applies init SQL) is
safe. State lives entirely in Postgres, so `acde-server` is stateless: kill/restart resumes cleanly.

## Cost control (live LLM)

The loop caches proposals within a cycle and enforces per-run call/token caps
(`LLM_MAX_CALLS_PER_RUN`, `LLM_MAX_TOKENS_PER_RUN`). Tune `MONITORING_INTERVAL_S` for cadence. Use
`MOCK_LLM=1` for staging/CI at zero cost, or an OpenAI-compatible on-prem endpoint for data residency.
