-- 001_baseline.sql — the schema as of the pre-migration era (ACDE <= 2.2).
-- Generated from infra/postgres/init/*.sql. Every statement is IF NOT EXISTS, so this is
-- safe both on a fresh database and on one already created by the docker init mount.

-- ---- from 00_schemas.sql ----
-- ACDE schemas (spec §5.1). Idempotent: safe to re-run.
CREATE SCHEMA IF NOT EXISTS telemetry;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS control;

-- ---- from 01_telemetry.sql ----
-- Telemetry tables (spec §5.1, verbatim content; IF NOT EXISTS added for idempotency).

CREATE TABLE IF NOT EXISTS telemetry.task_runs (
  id BIGSERIAL PRIMARY KEY, run_id TEXT, dag_id TEXT, task_id TEXT,
  state TEXT, start_ts TIMESTAMPTZ, end_ts TIMESTAMPTZ,
  duration_s DOUBLE PRECISION, try_number INT, error TEXT, experiment_run TEXT);
-- Enables idempotent upsert from the telemetry collector polling the Airflow REST API.
CREATE UNIQUE INDEX IF NOT EXISTS task_runs_uident
  ON telemetry.task_runs (dag_id, run_id, task_id, try_number);

CREATE TABLE IF NOT EXISTS telemetry.pipeline_metrics (
  id BIGSERIAL PRIMARY KEY, pipeline_id TEXT, metric TEXT,
  value DOUBLE PRECISION, ts TIMESTAMPTZ DEFAULT now(), experiment_run TEXT);

CREATE TABLE IF NOT EXISTS telemetry.schema_versions (
  id BIGSERIAL PRIMARY KEY, dataset TEXT, version INT, schema_json JSONB,
  compat TEXT CHECK (compat IN ('backward','breaking','unknown')), ts TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS telemetry.resource_usage (
  id BIGSERIAL PRIMARY KEY, component TEXT, cpu_pct DOUBLE PRECISION,
  mem_mb DOUBLE PRECISION, workers INT, ts TIMESTAMPTZ DEFAULT now(), experiment_run TEXT);

CREATE TABLE IF NOT EXISTS telemetry.failure_events (
  event_id UUID PRIMARY KEY, experiment_run TEXT, scenario TEXT, fault_type TEXT,
  injected_ts TIMESTAMPTZ, detected_ts TIMESTAMPTZ, resolved_ts TIMESTAMPTZ, resolution TEXT);

CREATE TABLE IF NOT EXISTS telemetry.agent_actions (
  action_id UUID PRIMARY KEY, experiment_run TEXT, agent TEXT, action_type TEXT,
  target TEXT, params JSONB, justification TEXT, confidence DOUBLE PRECISION,
  policy_decision TEXT, policy_reason TEXT, executed BOOL, outcome TEXT,
  llm_model TEXT, llm_tokens_in INT, llm_tokens_out INT, ts TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS telemetry.manual_interventions (
  id BIGSERIAL PRIMARY KEY, experiment_run TEXT, reason TEXT,
  requested_ts TIMESTAMPTZ, completed_ts TIMESTAMPTZ, simulated_latency_s DOUBLE PRECISION);

CREATE TABLE IF NOT EXISTS telemetry.cost_ledger (
  id BIGSERIAL PRIMARY KEY, experiment_run TEXT, component TEXT,
  compute_unit_seconds DOUBLE PRECISION, storage_gb_hours DOUBLE PRECISION,
  cost_units DOUBLE PRECISION, window_start TIMESTAMPTZ, window_end TIMESTAMPTZ);

-- ---- from 02_warehouse.sql ----
-- Warehouse tables (spec §5.1). partition_versions enables rollback = pointer flip.

CREATE TABLE IF NOT EXISTS warehouse.partition_versions (
  dataset TEXT, partition_key TEXT, version INT, table_name TEXT,
  active BOOL, created_ts TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (dataset, partition_key, version));

-- Streaming window aggregates (Phase 1). event_ts = max event time in the window;
-- materialized_ts = when the window was written (freshness = materialized_ts - event_ts).
CREATE TABLE IF NOT EXISTS warehouse.stream_aggregates (
  id BIGSERIAL PRIMARY KEY, pipeline_id TEXT, agg_key TEXT,
  window_start TIMESTAMPTZ, window_end TIMESTAMPTZ,
  event_count BIGINT, sum_value DOUBLE PRECISION,
  event_ts TIMESTAMPTZ, materialized_ts TIMESTAMPTZ DEFAULT now(),
  experiment_run TEXT,
  UNIQUE (pipeline_id, agg_key, window_start, experiment_run));

-- Quarantine sink for schema-drift partitions (Phase 3 routes here; created now so the
-- warehouse schema is complete and migrations are a no-op later).
CREATE TABLE IF NOT EXISTS warehouse.quarantine_events (
  id BIGSERIAL PRIMARY KEY, dataset TEXT, partition_key TEXT,
  reason TEXT, payload JSONB, quarantined_ts TIMESTAMPTZ DEFAULT now(),
  experiment_run TEXT);

-- ---- from 03_control.sql ----
-- Control-plane desired state (spec §5.1). Optimization actions write here; services poll.
-- e.g. key='streaming.workers' value='{"n":4}', key='airflow.pool.batch_pool' value='{"slots":6}'

CREATE TABLE IF NOT EXISTS control.desired_state (
  key TEXT PRIMARY KEY, value JSONB, updated_ts TIMESTAMPTZ DEFAULT now());

-- ---- from 04_approvals.sql ----
-- Production trust core (v2, P1): human-approval queue for gated agent actions.
-- A pending row is a self-contained, re-executable ProposedAction awaiting sign-off (approval mode),
-- so approving it later can reconstruct and run the action without the original agent cycle.
CREATE TABLE IF NOT EXISTS telemetry.action_approvals (
  approval_id   BIGSERIAL PRIMARY KEY,
  experiment_run TEXT,
  agent         TEXT,
  action_type   TEXT,
  target        TEXT,
  params        JSONB,
  justification TEXT,
  confidence    DOUBLE PRECISION,
  policy_reason TEXT,
  status        TEXT DEFAULT 'pending',   -- pending | approved | rejected | executed | failed
  requested_ts  TIMESTAMPTZ DEFAULT now(),
  decided_ts    TIMESTAMPTZ,
  decided_by    TEXT,
  decision_note TEXT,
  outcome       TEXT
);

CREATE INDEX IF NOT EXISTS action_approvals_status_idx
  ON telemetry.action_approvals (status, requested_ts);

