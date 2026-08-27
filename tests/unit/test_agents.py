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

    def test_status_is_denied_when_policy_denies(self, monkeypatch):
        import acde.db as dbmod

        exec_mock = MagicMock()
        monkeypatch.setattr(dbmod, "execute", exec_mock)
        monkeypatch.setattr(base.gate, "build_context", lambda *a, **k: {})
        monkeypatch.setattr(
            base.gate,
            "evaluate",
            lambda *a, **k: PolicyDecision(
                allowed=False, escalate=False, reason="over budget", policy_id="cost_budget"
            ),
        )
        monkeypatch.setattr(
            base.executor,
            "execute",
            lambda *a, **k: MagicMock(executed=False, outcome="denied: over budget"),
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
        update_params = exec_mock.call_args_list[1].args[1]
        assert "denied" in update_params

    def test_status_is_escalated_when_policy_escalates_without_allowing(self, monkeypatch):
        import acde.db as dbmod

        exec_mock = MagicMock()
        monkeypatch.setattr(dbmod, "execute", exec_mock)
        monkeypatch.setattr(base.gate, "build_context", lambda *a, **k: {})
        monkeypatch.setattr(
            base.gate,
            "evaluate",
            lambda *a, **k: PolicyDecision(
                allowed=False, escalate=True, reason="needs human", policy_id="recovery"
            ),
        )
        monkeypatch.setattr(
            base.executor,
            "execute",
            lambda *a, **k: MagicMock(executed=False, outcome="escalated_to_human"),
        )
        agent = RecoveryAgent(
            experiment_run="t",
            llm=FakeLLM(
                {
                    "action_type": "rollback",
                    "target": "tpcds_ingest",
                    "params": {},
                    "justification": "corrupted",
                    "confidence": 0.7,
                }
            ),
        )
        action, result = agent.reason(_snap("upstream_delay"))
        agent.act(action, result, _snap("upstream_delay"))
        update_params = exec_mock.call_args_list[1].args[1]
        assert "escalated" in update_params

    def test_write_ahead_row_committed_before_execute_is_called(self, monkeypatch):
        """D-083: the intent row must exist before the side effect runs, not after."""
        import acde.db as dbmod

        exec_mock = MagicMock()
        monkeypatch.setattr(dbmod, "execute", exec_mock)
        monkeypatch.setattr(base.gate, "build_context", lambda *a, **k: {})
        monkeypatch.setattr(
            base.gate,
            "evaluate",
            lambda *a, **k: PolicyDecision(
                allowed=True, escalate=False, reason="ok", policy_id="p"
            ),
        )
        call_order: list[str] = []
        exec_mock.side_effect = lambda *a, **k: call_order.append("db.execute")
        monkeypatch.setattr(
            base.executor,
            "execute",
            lambda *a, **k: (
                call_order.append("executor.execute") or MagicMock(executed=True, outcome="did it")
            ),
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
        # write-ahead INSERT commits before the side effect; the outcome UPDATE comes right after.
        # (a later db.execute from on_after_act's own bookkeeping is a separate concern.)
        assert call_order[:2] == ["db.execute", "executor.execute"]
        insert_sql, insert_params = exec_mock.call_args_list[0].args
        assert "INSERT INTO telemetry.agent_actions" in insert_sql
        assert "executing" in insert_params
        update_sql, update_params = exec_mock.call_args_list[1].args
        assert "UPDATE telemetry.agent_actions" in update_sql
        assert "executed" in update_params  # final status once the side effect succeeded

    def test_crash_during_execute_leaves_a_recoverable_row_not_nothing(self, monkeypatch):
        """The defect this fixes: a crash between gate decision and outcome used to lose the
        action from the audit trail entirely. Now the write-ahead INSERT has already committed."""
        import acde.db as dbmod

        exec_mock = MagicMock()
        monkeypatch.setattr(dbmod, "execute", exec_mock)
        monkeypatch.setattr(base.gate, "build_context", lambda *a, **k: {})
        monkeypatch.setattr(
            base.gate,
            "evaluate",
            lambda *a, **k: PolicyDecision(
                allowed=True, escalate=False, reason="ok", policy_id="p"
            ),
        )
        monkeypatch.setattr(
            base.executor, "execute", MagicMock(side_effect=RuntimeError("host died mid-call"))
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
        with pytest.raises(RuntimeError, match="host died mid-call"):
            agent.act(action, result, _snap("ingress_burst", freshness=120))
        # exactly one write happened -- the write-ahead insert -- and it says 'executing', not
        # nothing at all (the pre-fix behavior: zero rows, the action untraceable).
        assert exec_mock.call_count == 1
        insert_sql, insert_params = exec_mock.call_args_list[0].args
        assert "INSERT INTO telemetry.agent_actions" in insert_sql
        assert "executing" in insert_params

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
