-- D-086: indexes matching the actual predicates of the 3 hottest queries in the system, found by
-- an audit (docs/specs/2026-08-27-production-hardening-design.md) that only 2 indexes covered 13
-- tables. `tenant_id` is not the leading column here despite D-085: it is constant across every
-- row in a single-tenant deployment today (the only real deployment shape that exists), so it
-- would give the planner nothing to select on -- leading with `experiment_run`, which is what
-- every one of these queries actually filters by, is what makes the index useful right now. See
-- analysis/bench_hot_paths.py for the measured before/after this migration produces.

-- orchestrator/control.py::blast_radius_exceeded -- runs before every executed action.
CREATE INDEX IF NOT EXISTS agent_actions_run_target_ts_idx
  ON telemetry.agent_actions (experiment_run, target, ts DESC) WHERE executed;

-- orchestrator/loop.py::_open_faults -- runs every control-loop tick.
CREATE INDEX IF NOT EXISTS failure_events_open_idx
  ON telemetry.failure_events (experiment_run) WHERE resolved_ts IS NULL;

-- server/app.py's /audit and /proposals -- ORDER BY ts DESC LIMIT n, avoids a full sort.
CREATE INDEX IF NOT EXISTS agent_actions_ts_idx
  ON telemetry.agent_actions (ts DESC);

-- server/metrics.py::snapshot's policy_decision counts. Its executed-count and unfiltered
-- proposals_total are NOT indexed here: measured (analysis/bench_hot_paths.py) and confirmed via
-- EXPLAIN that ~85% of real rows have executed=TRUE, far too poor a selectivity for the planner to
-- ever choose an index over a seq scan -- a partial index on `executed` was built, benchmarked,
-- proven dead (planner ignored it, verified with EXPLAIN), and removed before ever being committed
-- rather than shipped as write overhead with zero read benefit. See DEVIATIONS D-086.
CREATE INDEX IF NOT EXISTS agent_actions_policy_decision_idx
  ON telemetry.agent_actions (policy_decision);

-- agents/base.py::observe -- every agent cycle.
CREATE INDEX IF NOT EXISTS resource_usage_run_ts_idx
  ON telemetry.resource_usage (experiment_run, ts DESC);
CREATE INDEX IF NOT EXISTS pipeline_metrics_run_metric_ts_idx
  ON telemetry.pipeline_metrics (experiment_run, metric, ts DESC);
