-- Telemetry tables (spec §5.1, verbatim content; IF NOT EXISTS added for idempotency).

CREATE TABLE IF NOT EXISTS telemetry.task_runs (
  id BIGSERIAL PRIMARY KEY, run_id TEXT, dag_id TEXT, task_id TEXT,
  state TEXT, start_ts TIMESTAMPTZ, end_ts TIMESTAMPTZ,
  duration_s DOUBLE PRECISION, try_number INT, error TEXT, experiment_run TEXT);

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
