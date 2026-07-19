"""Unit tests for execution modes: shadow / approval / autonomous (mocked db + settings)."""

from unittest.mock import MagicMock

import pytest

from acde.config import Settings
from acde.contracts import PolicyDecision, ProposedAction
from acde.policy import executor


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(executor, "db", fake)
    return fake


def _mode(monkeypatch, mode, **kw):
    monkeypatch.setattr(
        executor, "get_settings", lambda: Settings(_env_file=None, acde_mode=mode, **kw)
    )


def _action(action_type="scale_workers", agent="optimization", **params):
    return ProposedAction(
        agent=agent,
        action_type=action_type,
        target="tgt",
        justification="x",
        confidence=0.9,
        params=params,
    )


ALLOW = PolicyDecision(allowed=True, escalate=False, reason="ok", policy_id="p")


def test_shadow_does_not_execute(fake_db, monkeypatch):
    _mode(monkeypatch, "shadow")
    handler = MagicMock()
    monkeypatch.setitem(executor._HANDLERS, "scale_workers", handler)
    out = executor.execute(_action("scale_workers", n_workers=5), ALLOW, "prod")
    assert not out.executed
    assert "shadow: would execute scale_workers" in out.outcome
    handler.assert_not_called()  # NO side effect on the pipeline


def test_shadow_still_runs_side_effect_free_acks(fake_db, monkeypatch):
    _mode(monkeypatch, "shadow")
    out = executor.execute(_action("no_action", agent="monitoring"), ALLOW, "prod")
    assert out.executed  # acks always run regardless of mode
    assert "acknowledged" in out.outcome


def test_approval_mode_queues_not_executes(fake_db, monkeypatch):
    _mode(monkeypatch, "approval")
    created = {}
    monkeypatch.setattr(
        "acde.human.approvals.create_pending",
        lambda a, d, r: (created.setdefault("type", a.action_type) and None) or 77,
    )
    handler = MagicMock()
    monkeypatch.setitem(executor._HANDLERS, "scale_workers", handler)
    out = executor.execute(_action("scale_workers", n_workers=5), ALLOW, "prod")
    assert not out.executed
    assert "pending_approval:77" in out.outcome
    handler.assert_not_called()  # queued, not executed
    assert created["type"] == "scale_workers"


def test_autonomous_executes(fake_db, monkeypatch):
    _mode(monkeypatch, "autonomous")
    out = executor.execute(_action("scale_workers", n_workers=5), ALLOW, "prod")
    assert out.executed
    assert "streaming.workers" in out.outcome or "workers" in out.outcome


def test_autonomous_upgrades_high_blast_action_to_approval(fake_db, monkeypatch):
    _mode(monkeypatch, "autonomous", approval_required_action_types="rollback,quarantine_partition")
    monkeypatch.setattr("acde.human.approvals.create_pending", lambda a, d, r: 5)
    out = executor.execute(_action("quarantine_partition", agent="schema"), ALLOW, "prod")
    assert not out.executed
    assert "pending_approval:5" in out.outcome  # forced to approval even in autonomous
