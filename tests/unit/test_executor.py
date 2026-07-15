"""Unit tests for the action executor (mocked acde.db + Airflow helpers)."""

from unittest.mock import MagicMock

import httpx
import pytest

from acde.config import Settings
from acde.contracts import PolicyDecision, ProposedAction
from acde.policy import executor


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(executor, "db", fake)
    return fake


def _action(agent, action_type, **params) -> ProposedAction:
    return ProposedAction(
        agent=agent,
        action_type=action_type,
        target=params.pop("target", "tgt"),
        justification="because",
        confidence=0.9,
        params=params,
    )


ALLOW = PolicyDecision(allowed=True, escalate=False, reason="ok", policy_id="p")
DENY = PolicyDecision(allowed=False, escalate=False, reason="over budget", policy_id="cost_budget")
ESCALATE = PolicyDecision(allowed=False, escalate=True, reason="needs human", policy_id="recovery")
ALLOW_ESCALATE = PolicyDecision(allowed=True, escalate=True, reason="contained", policy_id="schema")


class TestDispatch:
    def test_scale_workers_upserts_desired_state(self, fake_db):
        out = executor.execute(
            _action("optimization", "scale_workers", n_workers=5), ALLOW, "run-1"
        )
        assert out.executed
        sql = fake_db.execute.call_args.args[0]
        assert "control.desired_state" in sql
        assert fake_db.execute.call_args.args[1][0] == "streaming.workers"

    def test_rollback_calls_partition_manager(self, fake_db, monkeypatch):
        mgr = MagicMock()
        mgr.return_value.rollback.return_value = 2
        monkeypatch.setattr(executor, "PartitionVersionManager", mgr)
        out = executor.execute(
            _action("recovery", "rollback", dataset="d", partition_key="p"), ALLOW, "run-1"
        )
        mgr.return_value.rollback.assert_called_once_with("d", "p")
        assert "v2" in out.outcome

    def test_retry_triggers_dag(self, fake_db, monkeypatch):
        monkeypatch.setattr(executor, "_trigger_dag", lambda dag: "run_123")
        out = executor.execute(_action("recovery", "replay", target="tpcds_ingest"), ALLOW, "run-1")
        assert "run_123" in out.outcome

    def test_quarantine_deactivates_and_records(self, fake_db):
        executor.execute(
            _action("schema", "quarantine_partition", dataset="d", partition_key="p"),
            ALLOW_ESCALATE,
            "run-1",
        )
        sqls = [c.args[0] for c in fake_db.execute.call_args_list]
        assert any("partition_versions SET active = FALSE" in s for s in sqls)
        assert any("quarantine_events" in s for s in sqls)
        assert any("manual_interventions" in s for s in sqls)  # escalate notification too


class TestOtherHandlers:
    def test_apply_mapping_upserts(self, fake_db):
        executor.execute(
            _action("schema", "apply_mapping", dataset="d", mapping={"a": "b"}), ALLOW, "run-1"
        )
        assert fake_db.execute.call_args.args[1][0] == "schema.mapping.d"

    def test_block_ingestion_upserts(self, fake_db):
        out = executor.execute(_action("schema", "block_ingestion", dataset="d"), ALLOW, "run-1")
        assert "blocked" in out.outcome
        assert fake_db.execute.call_args.args[1][0] == "ingestion.blocked.d"

    def test_reprioritize_upserts(self, fake_db):
        executor.execute(
            _action("optimization", "reprioritize_pipeline", target="p", priority=3), ALLOW, "run-1"
        )
        assert fake_db.execute.call_args.args[1][0] == "pipeline.priority.p"

    def test_partial_recompute_clears_tasks(self, fake_db, monkeypatch):
        called = {}
        monkeypatch.setattr(
            executor,
            "_clear_task_instances",
            lambda dag, tasks: called.update(dag=dag, tasks=tasks),
        )
        executor.execute(
            _action("recovery", "partial_recompute", target="tpcds_ingest", task_ids=["ingest"]),
            ALLOW,
            "run-1",
        )
        assert called == {"dag": "tpcds_ingest", "tasks": ["ingest"]}

    def test_adjust_pool_slots_patches_pool(self, fake_db, monkeypatch):
        called = {}
        monkeypatch.setattr(
            executor, "_patch_pool", lambda pool, slots: called.update(p=pool, s=slots)
        )
        executor.execute(
            _action("optimization", "adjust_pool_slots", target="default_pool", slots=6),
            ALLOW,
            "run-1",
        )
        assert called == {"p": "default_pool", "s": 6}

    def test_noop_action_acknowledged(self, fake_db):
        out = executor.execute(_action("monitoring", "no_action"), ALLOW, "run-1")
        assert out.executed
        assert "acknowledged" in out.outcome


class TestDecisionSemantics:
    def test_denied_action_has_no_side_effect(self, fake_db):
        out = executor.execute(_action("optimization", "scale_workers", n_workers=9), DENY, "run-1")
        assert not out.executed
        assert "denied" in out.outcome
        fake_db.execute.assert_not_called()

    def test_escalation_writes_manual_intervention(self, fake_db):
        out = executor.execute(_action("recovery", "escalate_to_human"), ESCALATE, "run-1")
        assert not out.executed
        assert "escalated_to_human" in out.outcome
        assert "manual_interventions" in fake_db.execute.call_args.args[0]

    def test_allowed_and_escalate_does_both(self, fake_db):
        out = executor.execute(
            _action("schema", "quarantine_partition", dataset="d"), ALLOW_ESCALATE, "run-1"
        )
        assert out.executed
        assert "escalated_to_human" in out.outcome


class TestInfraDegrade:
    """Airflow unreachable: bounded retry, then degrade to escalate instead of crashing (D-052)."""

    def _install_down_airflow(self, monkeypatch, attempts=2):
        monkeypatch.setattr(
            executor,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                executor_retry_attempts=attempts,
                executor_retry_backoff_s=0.0,
            ),
        )
        client = MagicMock()
        client.__enter__.return_value.post.side_effect = httpx.ConnectError("airflow down")
        client.__enter__.return_value.patch.side_effect = httpx.ConnectError("airflow down")
        monkeypatch.setattr(executor, "_airflow_client", lambda: client)
        return client

    def test_airflow_down_retries_then_escalates(self, fake_db, monkeypatch):
        client = self._install_down_airflow(monkeypatch, attempts=2)
        out = executor.execute(_action("recovery", "replay", target="tpcds_ingest"), ALLOW, "run-1")
        assert not out.executed
        assert "execution_failed" in out.outcome
        assert "escalated_to_human" in out.outcome
        # bounded retry actually retried before giving up
        assert client.__enter__.return_value.post.call_count == 2
        # degraded by escalating to a human
        assert any("manual_interventions" in c.args[0] for c in fake_db.execute.call_args_list)

    def test_airflow_down_on_pool_patch_degrades(self, fake_db, monkeypatch):
        self._install_down_airflow(monkeypatch, attempts=1)
        out = executor.execute(
            _action("optimization", "adjust_pool_slots", target="default_pool", slots=6),
            ALLOW,
            "run-1",
        )
        assert not out.executed
        assert "execution_failed" in out.outcome
