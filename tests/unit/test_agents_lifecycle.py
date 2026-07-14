"""Unit tests for schema/optimization agents closing the failure lifecycle (D-045)."""

import datetime as dt
from unittest.mock import MagicMock

from acde.agents import optimization as opt_mod
from acde.agents import schema as schema_mod
from acde.agents.optimization import OptimizationAgent
from acde.agents.schema import SchemaAgent
from acde.contracts import ProposedAction, TelemetrySnapshot

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
SNAP = TelemetrySnapshot(experiment_run="t", window_start=NOW, window_end=NOW)


def _action(agent, action_type):
    return ProposedAction(
        agent=agent, action_type=action_type, target="ds", justification="x", confidence=0.9
    )


class TestSchemaLifecycle:
    def test_quarantine_sets_resolved_ts(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(schema_mod, "db", fake)
        SchemaAgent(experiment_run="t").on_after_act(
            _action("schema", "quarantine_partition"), executed=True, snapshot=SNAP
        )
        sql = fake.execute.call_args.args[0]
        assert "resolved_ts = now()" in sql and "fault_type = 'schema_drift'" in sql

    def test_no_action_does_not_resolve(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(schema_mod, "db", fake)
        SchemaAgent(experiment_run="t").on_after_act(
            _action("schema", "no_action"), executed=True, snapshot=SNAP
        )
        fake.execute.assert_not_called()


class TestOptimizationLifecycle:
    def test_scale_workers_sets_resolved_ts(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(opt_mod, "db", fake)
        OptimizationAgent(experiment_run="t").on_after_act(
            _action("optimization", "scale_workers"), executed=True, snapshot=SNAP
        )
        sql = fake.execute.call_args.args[0]
        assert "resolved_ts = now()" in sql
        assert fake.execute.call_args.args[1][2] == ["ingress_burst", "resource_contention"]

    def test_not_executed_does_not_resolve(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(opt_mod, "db", fake)
        OptimizationAgent(experiment_run="t").on_after_act(
            _action("optimization", "scale_workers"), executed=False, snapshot=SNAP
        )
        fake.execute.assert_not_called()
