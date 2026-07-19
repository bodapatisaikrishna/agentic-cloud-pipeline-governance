"""Unit tests for the acde CLI dispatch (no real services)."""

from acde import cli


def test_doctor_returns_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.ops.health.doctor",
        lambda: {"checks": [{"name": "db", "ok": True, "detail": "ok"}], "all_ok": True},
    )
    rc = cli.main(["doctor"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_doctor_nonzero_when_unhealthy(monkeypatch):
    monkeypatch.setattr(
        "acde.ops.health.doctor",
        lambda: {"checks": [{"name": "db", "ok": False, "detail": "down"}], "all_ok": False},
    )
    assert cli.main(["doctor"]) == 1


def test_pause_calls_control(monkeypatch):
    called = {}
    monkeypatch.setattr("acde.orchestrator.control.set_paused", lambda p, actor: called.update(p=p))
    assert cli.main(["pause"]) == 0
    assert called["p"] is True


def test_resume_calls_control(monkeypatch):
    called = {}
    monkeypatch.setattr("acde.orchestrator.control.set_paused", lambda p, actor: called.update(p=p))
    assert cli.main(["resume"]) == 0
    assert called["p"] is False


def test_approvals_list(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.human.approvals.list_pending",
        lambda: [
            {
                "approval_id": 1,
                "agent": "schema",
                "action_type": "quarantine_partition",
                "target": "ds",
                "justification": "drift",
            }
        ],
    )
    assert cli.main(["approvals", "list"]) == 0
    assert "quarantine_partition" in capsys.readouterr().out


def test_approvals_approve(monkeypatch):
    monkeypatch.setattr("acde.human.approvals.approve", lambda i, actor: {"status": "executed"})
    assert cli.main(["approvals", "approve", "7"]) == 0


def test_unknown_command_errors():
    import pytest

    with pytest.raises(SystemExit):
        cli.main(["nonsense"])
