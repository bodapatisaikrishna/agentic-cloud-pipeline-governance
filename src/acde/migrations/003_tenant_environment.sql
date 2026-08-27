-- D-085: tenant/environment boundary. Fast-default add-column (PG 11+, no table rewrite) on every
-- scoped telemetry table, so existing rows are unambiguously 'default'/'default' -- exactly what a
-- single self-hosted deployment already is -- and no data is moved or reinterpreted.
ALTER TABLE telemetry.agent_actions
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';

ALTER TABLE telemetry.failure_events
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';

ALTER TABLE telemetry.resource_usage
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';

ALTER TABLE telemetry.pipeline_metrics
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';

ALTER TABLE telemetry.cost_ledger
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';

ALTER TABLE telemetry.manual_interventions
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';

ALTER TABLE telemetry.task_runs
  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'default';
