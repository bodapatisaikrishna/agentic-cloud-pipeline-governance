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


def test_loop_health_ok_when_recent(monkeypatch, capsys):
    monkeypatch.setattr("acde.orchestrator.control.heartbeat_age_s", lambda: 5.0)
    assert cli.main(["loop-health"]) == 0
    assert "ok" in capsys.readouterr().out


def test_loop_health_fails_when_stale(monkeypatch, capsys):
    from acde.config import Settings

    monkeypatch.setattr("acde.orchestrator.control.heartbeat_age_s", lambda: 999.0)
    monkeypatch.setattr(
        "acde.config.get_settings", lambda: Settings(_env_file=None, monitoring_interval_s=15.0)
    )
    assert cli.main(["loop-health"]) == 1
    assert "stale" in capsys.readouterr().out


def test_loop_health_fails_when_never_recorded(monkeypatch, capsys):
    monkeypatch.setattr("acde.orchestrator.control.heartbeat_age_s", lambda: None)
    assert cli.main(["loop-health"]) == 1
    assert "no heartbeat" in capsys.readouterr().out


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


def test_compliance_report_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.ops.compliance.compliance_report",
        lambda since_hours: {"window_hours": since_hours, "availability": {"healthy": True}},
    )
    rc = cli.main(["compliance-report", "--since-hours", "48"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"window_hours": 48.0' in out
    assert '"healthy": true' in out


def test_unknown_command_errors():
    import pytest

    with pytest.raises(SystemExit):
        cli.main(["nonsense"])
