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
