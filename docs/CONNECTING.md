# Connecting ACDE to your stack

ACDE attaches to **your** orchestrator through a connector — it does not require running ours.

## Apache Airflow (first-class)

Set in `.env.prod`:

```bash
CONNECTOR_KIND=airflow
AIRFLOW_URL=https://airflow.your-company.com/api/v1
AIRFLOW_USER=acde-service        # a least-privilege service account (see below)
AIRFLOW_PASSWORD=...
# or, instead of basic auth:
# AIRFLOW_AUTH_TOKEN=<bearer token>
AIRFLOW_VERIFY_TLS=true
```

Verify:

```bash
acde doctor        # the connector:airflow check must be OK (HTTP 200)
```

### What ACDE calls on Airflow

Only the Airflow **stable REST API** (v2.x), for the remediation actions the agents propose:

| Agent action | Airflow REST |
|---|---|
| replay / retry a pipeline | `POST /dags/{dag_id}/dagRuns` |
| clear failed tasks | `POST /dags/{dag_id}/clearTaskInstances` |
| resize a pool | `PATCH /pools/{pool}` |
| read task-run state | `GET /dags/{dag_id}/dagRuns` |

### Least-privilege service account

Grant the ACDE service account only: read DAGs/DAG runs, trigger DAG runs, clear task instances, and
edit pools. It never needs admin. In **shadow** or **noop** mode it needs no write access at all.

## Prefect (Server or Cloud)

Set in `.env.prod`:

```bash
CONNECTOR_KIND=prefect
PREFECT_API_URL=https://your-prefect-server/api    # or Prefect Cloud's account/workspace API URL
# Prefect Cloud only — a self-hosted Prefect Server typically needs no auth:
# PREFECT_API_KEY=<api key>
```

Verify: `acde doctor` — the `connector:prefect` check must be OK.

`pipeline_id` maps to a Prefect **deployment id** throughout. What ACDE calls:

| Agent action | Prefect REST |
|---|---|
| replay / retry a pipeline | `POST /deployments/{id}/create_flow_run` |
| clear failed tasks | `POST /flow_runs/{id}/set_state` (retries the **whole** flow run — see note below) |
| resize a pool | `PATCH /work_pools/{name}` (`concurrency_limit`) |
| read run state | `POST /flow_runs/filter` |

**Known gap vs. Airflow:** Prefect has no per-task "clear failed tasks" concept — a flow run either
succeeds or doesn't, so `clear_tasks` retries the whole flow run rather than individual tasks. This
is a deliberate, documented limitation of the Prefect connector, not a bug.

## Observe-only (no write access)

```bash
CONNECTOR_KIND=noop
```

ACDE proposes, gates, logs, and notifies — but performs no side effects. Use this for evaluation or a
permanently-advisory deployment.

## Other orchestrators

Dagster / dbt connectors are on the roadmap (Dagster's primary control surface is GraphQL rather
than REST, so it needs a differently-shaped client than Airflow/Prefect). The connector interface
(`src/acde/connectors/base.py`) is small — a new integration is one class implementing
`get_task_runs` / `trigger_pipeline` / `clear_tasks` / `set_pool_slots` / `health`, registered in
`registry.py`.

## Database & warehouse

ACDE stores its own audit/telemetry in a Postgres it controls (`POSTGRES_*`). Warehouse-level actions
(partition rollback/quarantine) operate on the schemas ACDE manages; point these at your warehouse via
the same connector pattern as the roadmap expands.
