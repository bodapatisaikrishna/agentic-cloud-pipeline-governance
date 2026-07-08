-- Warehouse tables (spec §5.1). partition_versions enables rollback = pointer flip.

CREATE TABLE IF NOT EXISTS warehouse.partition_versions (
  dataset TEXT, partition_key TEXT, version INT, table_name TEXT,
  active BOOL, created_ts TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (dataset, partition_key, version));
