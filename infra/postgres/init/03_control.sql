-- Control-plane desired state (spec §5.1). Optimization actions write here; services poll.
-- e.g. key='streaming.workers' value='{"n":4}', key='airflow.pool.batch_pool' value='{"slots":6}'

CREATE TABLE IF NOT EXISTS control.desired_state (
  key TEXT PRIMARY KEY, value JSONB, updated_ts TIMESTAMPTZ DEFAULT now());
