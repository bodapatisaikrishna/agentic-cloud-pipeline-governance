"""Unit tests for the approval workflow (mocked db + executor.apply_action)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from acde.human import approvals


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(approvals, "db", fake)
    return fake


def test_create_pending_inserts_and_returns_id(fake_db):
    fake_db.fetch_one.return_value = {"approval_id": 42}
    action = SimpleNamespace(
        agent="schema",
        action_type="quarantine_partition",
        target="ds",
        params={"k": "v"},
        justification="drift",
        confidence=0.9,
    )
    aid = approvals.create_pending(action, SimpleNamespace(reason="contained"), "prod")
    assert aid == 42
    assert "action_approvals" in fake_db.fetch_one.call_args.args[0]


def test_approve_executes_and_marks_executed(fake_db, monkeypatch):
    fake_db.fetch_one.return_value = {
        "approval_id": 1,
        "experiment_run": "prod",
        "agent": "recovery",
        "action_type": "replay",
        "target": "dag",
        "params": {},
        "justification": "j",
        "confidence": 0.8,
    }
    monkeypatch.setattr(
        "acde.policy.executor.apply_action",
        lambda action, run: SimpleNamespace(executed=True, outcome="triggered dag"),
    )
    result = approvals.approve(1, actor="alice")
    assert result["status"] == "executed"
    # status update ran
    assert any(
        "status = %s" in c.args[0] and c.args[1][0] == "executed"
        for c in fake_db.execute.call_args_list
    )


def test_approve_missing_is_not_found(fake_db):
    fake_db.fetch_one.return_value = None
    assert approvals.approve(999, actor="bob")["status"] == "not_found"


def test_reject_marks_rejected(fake_db):
    fake_db.fetch_one.return_value = {"approval_id": 2}
    result = approvals.reject(2, actor="carol", note="too risky")
    assert result["status"] == "rejected"
    assert any("status = 'rejected'" in c.args[0] for c in fake_db.execute.call_args_list)


def test_reject_missing_is_not_found(fake_db):
    fake_db.fetch_one.return_value = None
    assert approvals.reject(999, actor="x")["status"] == "not_found"
