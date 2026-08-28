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


def test_decision_quality_report_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.ops.decision_quality.live_decision_quality",
        lambda since_hours: {"window_hours": since_hours, "accuracy": 0.75},
    )
    rc = cli.main(["decision-quality-report", "--since-hours", "48"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"window_hours": 48.0' in out
    assert '"accuracy": 0.75' in out


def test_tenants_create(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.tenancy.create_tenant",
        lambda tenant_id, name: {
            "tenant_id": tenant_id,
            "display_name": name,
            "status": "active",
        },
    )
    rc = cli.main(["tenants", "create", "acme", "--name", "Acme Inc"])
    assert rc == 0
    assert "created tenant" in capsys.readouterr().out


def test_tenants_create_duplicate_prints_error_and_exits_1(monkeypatch, capsys):
    def _raise(tenant_id, name):
        raise ValueError(f"tenant {tenant_id!r} already exists")

    monkeypatch.setattr("acde.tenancy.create_tenant", _raise)
    rc = cli.main(["tenants", "create", "acme", "--name", "Acme Inc"])
    assert rc == 1
    assert "error" in capsys.readouterr().out


def test_tenants_list(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.tenancy.list_tenants",
        lambda: [{"tenant_id": "acme", "status": "active", "display_name": "Acme Inc"}],
    )
    rc = cli.main(["tenants", "list"])
    assert rc == 0
    assert "acme" in capsys.readouterr().out


def test_tenants_suspend_and_activate(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.tenancy.set_tenant_status",
        lambda tenant_id, status: {"tenant_id": tenant_id, "status": status},
    )
    rc = cli.main(["tenants", "suspend", "acme"])
    assert rc == 0
    assert "'suspended'" in capsys.readouterr().out
    rc = cli.main(["tenants", "activate", "acme"])
    assert rc == 0
    assert "'active'" in capsys.readouterr().out


def test_tenants_suspend_unknown_prints_error_and_exits_1(monkeypatch, capsys):
    def _raise(tenant_id, status):
        raise ValueError(f"no such tenant {tenant_id!r}")

    monkeypatch.setattr("acde.tenancy.set_tenant_status", _raise)
    rc = cli.main(["tenants", "suspend", "nope"])
    assert rc == 1
    assert "error" in capsys.readouterr().out


def test_backup_prints_the_written_path(monkeypatch, capsys):
    from pathlib import Path

    monkeypatch.setattr("acde.ops.backup.backup", lambda output_dir=None: Path("/tmp/x.dump"))
    rc = cli.main(["backup"])
    assert rc == 0
    assert "/tmp/x.dump" in capsys.readouterr().out


def test_backup_error_prints_and_exits_1(monkeypatch, capsys):
    def _raise(output_dir=None):
        raise RuntimeError("pg_dump not found")

    monkeypatch.setattr("acde.ops.backup.backup", _raise)
    rc = cli.main(["backup"])
    assert rc == 1
    assert "error" in capsys.readouterr().out


def test_restore_without_yes_refuses_and_never_calls_restore(monkeypatch, capsys):
    monkeypatch.setattr(
        "acde.ops.backup.restore",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called without --yes")),
    )
    rc = cli.main(["restore", "some.dump"])
    assert rc == 1
    assert "refusing" in capsys.readouterr().out


def test_restore_with_yes_calls_restore(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(
        "acde.ops.backup.restore",
        lambda dump_path, target_db=None: captured.update(path=dump_path, target_db=target_db),
    )
    rc = cli.main(["restore", "some.dump", "--yes", "--target-db", "drill"])
    assert rc == 0
    assert str(captured["path"]) == "some.dump"
    assert captured["target_db"] == "drill"


def test_restore_error_prints_and_exits_1(monkeypatch, capsys):
    def _raise(dump_path, target_db=None):
        raise RuntimeError("no such dump file")

    monkeypatch.setattr("acde.ops.backup.restore", _raise)
    rc = cli.main(["restore", "some.dump", "--yes"])
    assert rc == 1
    assert "error" in capsys.readouterr().out


def test_unknown_command_errors():
    import pytest

    with pytest.raises(SystemExit):
        cli.main(["nonsense"])
