"""Unit tests for the agents (mocked db/gate/executor; mock LLM for reasoning)."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

from acde.agents import base
from acde.agents.base import BaseAgent
from acde.agents.monitoring import MonitoringAgent
from acde.agents.optimization import OptimizationAgent
from acde.agents.recovery import RecoveryAgent
from acde.agents.schema import SchemaAgent
from acde.contracts import PolicyDecision, TelemetrySnapshot
from acde.llm.client import LLMResult

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def _snap(fault=None, compat="unknown", freshness=0.0):
    return TelemetrySnapshot(
        experiment_run="t",
        window_start=NOW,
        window_end=NOW,
        open_anomalies=[{"fault_type": fault, "scenario": fault}] if fault else [],
        schema_compat=compat,
        pipeline_metrics={"freshness_s": freshness},
    )


class FakeLLM:
    def __init__(self, action_json):
        self._aj = action_json

    def propose(self, agent, snapshot, system_prompt):
        return LLMResult(action_json=self._aj, tokens_in=100, tokens_out=20, model="mock")


class TestObserve:
    def test_builds_snapshot_from_db(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.side_effect = [
            [
                {"event_id": "e1", "scenario": "schema_drift", "fault_type": "schema_drift"}
            ],  # faults
            [{"metric": "freshness_s", "value": 42.0}],  # metrics
            [{"component": "streaming", "cpu_pct": 5.0, "mem_mb": 10.0, "workers": 3, "ts": NOW}],
        ]
        monkeypatch.setattr(base, "db", fake)
        agent = SchemaAgent(experiment_run="t")
        snap = agent.observe()
        assert snap.schema_compat == "breaking"  # schema_drift fault open
        assert snap.pipeline_metrics["freshness_s"] == 42.0
        assert snap.open_anomalies[0]["fault_type"] == "schema_drift"


class TestReason:
    def test_valid_output_becomes_proposed_action(self):
        agent = SchemaAgent(
            experiment_run="t",
            llm=FakeLLM(
                {
                    "action_type": "quarantine_partition",
                    "target": "ds",
                    "params": {},
                    "justification": "breaking",
                    "confidence": 0.9,
                }
            ),
        )
        action, result = agent.reason(_snap("schema_drift", "breaking"))
        assert action.action_type == "quarantine_partition"
        assert result.tokens_in == 100

    def test_invalid_output_degrades_to_no_action(self, caplog):
        # rollback is not a valid schema action -> validation fails -> no_action
        agent = SchemaAgent(
            experiment_run="t",
            llm=FakeLLM(
                {
                    "action_type": "rollback",
                    "target": "ds",
                    "params": {},
                    "justification": "x",
                    "confidence": 0.9,
                }
            ),
        )
        action, _ = agent.reason(_snap())
        assert action.action_type == "no_action"


class TestAct:
    def _patch(self, monkeypatch, decision):
        # Patch the shared acde.db.execute attribute so both base.act and the agents'
        # on_after_act hooks (which each `from acde import db`) are intercepted.
        import acde.db as dbmod

        exec_mock = MagicMock()
        monkeypatch.setattr(dbmod, "execute", exec_mock)
        monkeypatch.setattr(base.gate, "build_context", lambda *a, **k: {})
        monkeypatch.setattr(base.gate, "evaluate", lambda *a, **k: decision)
        outcome = MagicMock(executed=True, outcome="did it")
        monkeypatch.setattr(base.executor, "execute", lambda *a, **k: outcome)
        return exec_mock

    def test_writes_agent_actions_row_with_tokens(self, monkeypatch):
        exec_mock = self._patch(
            monkeypatch, PolicyDecision(allowed=True, escalate=False, reason="ok", policy_id="p")
        )
        agent = OptimizationAgent(
            experiment_run="t",
            llm=FakeLLM(
                {
                    "action_type": "scale_workers",
                    "target": "streaming",
                    "params": {"n_workers": 6},
                    "justification": "burst",
                    "confidence": 0.8,
                }
            ),
        )
        action, result = agent.reason(_snap("ingress_burst", freshness=120))
        agent.act(action, result, _snap("ingress_burst", freshness=120))
        insert = next(c.args for c in exec_mock.call_args_list if "agent_actions" in c.args[0])
        # tokens + policy decision recorded
        assert "allowed" in insert[1]
        assert result.tokens_in in insert[1]

    def test_monitoring_sets_detected_ts(self, monkeypatch):
        exec_mock = self._patch(
            monkeypatch, PolicyDecision(allowed=True, escalate=False, reason="ok", policy_id="m")
        )
        agent = MonitoringAgent(
            experiment_run="t",
            llm=FakeLLM(
                {
                    "action_type": "raise_anomaly",
                    "target": "p",
                    "params": {},
                    "justification": "anomaly",
                    "confidence": 0.9,
                }
            ),
        )
        action, result = agent.reason(_snap("schema_drift"))
        agent.act(action, result, _snap("schema_drift"))
        assert any("detected_ts = now()" in c.args[0] for c in exec_mock.call_args_list)

    def test_recovery_sets_resolved_ts_on_remediation(self, monkeypatch):
        exec_mock = self._patch(
            monkeypatch, PolicyDecision(allowed=True, escalate=False, reason="ok", policy_id="r")
        )
        agent = RecoveryAgent(
            experiment_run="t",
            llm=FakeLLM(
                {
                    "action_type": "replay",
                    "target": "tpcds_ingest",
                    "params": {},
                    "justification": "replay",
                    "confidence": 0.85,
                }
            ),
        )
        action, result = agent.reason(_snap("upstream_delay"))
        agent.act(action, result, _snap("upstream_delay"))
        assert any("resolved_ts = now()" in c.args[0] for c in exec_mock.call_args_list)


class TestAgentProposalsMatchScenario:
    @pytest.mark.parametrize(
        ("agent_cls", "snapshot", "expected"),
        [
            (SchemaAgent, _snap("schema_drift", "breaking"), "quarantine_partition"),
            (RecoveryAgent, _snap("upstream_delay"), "replay"),
            (OptimizationAgent, _snap("ingress_burst", freshness=120), "scale_workers"),
            (MonitoringAgent, _snap("resource_contention"), "raise_anomaly"),
        ],
    )
    def test_owning_agent_proposes_expected(self, agent_cls, snapshot, expected):
        agent = agent_cls(experiment_run="t")  # real mock LLM
        action, _ = agent.reason(snapshot)
        assert action.action_type == expected


def test_base_agent_requires_agent_attr():
    with pytest.raises((AttributeError, TypeError)):
        BaseAgent(experiment_run="t")
