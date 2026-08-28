"""Unit tests for the compliance/audit evidence report (D-096) -- mocked db."""

from unittest.mock import MagicMock

from acde.config import Settings
from acde.ops import compliance


class TestPolicyVerdictDistribution:
    def test_counts_and_percentages(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = [
            {"policy_decision": "allowed", "n": 8},
            {"policy_decision": "denied", "n": 1},
            {"policy_decision": "escalated", "n": 1},
        ]
        monkeypatch.setattr(compliance, "db", fake)
        dist = compliance._policy_verdict_distribution("now() - interval '1.0 hours'")
        assert dist["total"] == 10
        assert dist["counts"] == {"allowed": 8, "denied": 1, "escalated": 1}
        assert dist["percentages"] == {"allowed": 80.0, "denied": 10.0, "escalated": 10.0}

    def test_no_rows_gives_zero_percentages_not_a_zerodivisionerror(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = []
        monkeypatch.setattr(compliance, "db", fake)
        dist = compliance._policy_verdict_distribution("now() - interval '1.0 hours'")
        assert dist == {"counts": {}, "percentages": {}, "total": 0}


class TestIncidents:
    def test_mttr_and_open_count(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = [{"mttr": 10.0}, {"mttr": 30.0}]
        fake.fetch_one.side_effect = [{"n": 2}, {"n": 1}]  # detected, open_now
        monkeypatch.setattr(compliance, "db", fake)
        inc = compliance._incidents("now() - interval '1.0 hours'")
        assert inc["detected"] == 2
        assert inc["resolved"] == 2
        assert inc["open_now"] == 1
        assert inc["mttr_median_s"] == 20.0

    def test_no_resolved_incidents_gives_zero_mttr_not_a_crash(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = []
        fake.fetch_one.side_effect = [{"n": 0}, {"n": 0}]
        monkeypatch.setattr(compliance, "db", fake)
        inc = compliance._incidents("now() - interval '1.0 hours'")
        assert inc["mttr_median_s"] == 0.0
        assert inc["mttr_p90_s"] == 0.0


class TestAvailability:
    def test_healthy_when_recent_tick(self, monkeypatch):
        monkeypatch.setattr(compliance, "heartbeat_age_s", lambda: 5.0)
        monkeypatch.setattr(
            compliance, "get_settings", lambda: Settings(_env_file=None, monitoring_interval_s=15.0)
        )
        avail = compliance._availability()
        assert avail["healthy"] is True
        assert avail["last_tick_seconds_ago"] == 5.0
        assert "not a measured historical uptime" in avail["note"]

    def test_unhealthy_when_stale(self, monkeypatch):
        monkeypatch.setattr(compliance, "heartbeat_age_s", lambda: 999.0)
        monkeypatch.setattr(
            compliance, "get_settings", lambda: Settings(_env_file=None, monitoring_interval_s=15.0)
        )
        assert compliance._availability()["healthy"] is False

    def test_never_recorded_is_unhealthy_not_a_crash(self, monkeypatch):
        monkeypatch.setattr(compliance, "heartbeat_age_s", lambda: None)
        monkeypatch.setattr(
            compliance, "get_settings", lambda: Settings(_env_file=None, monitoring_interval_s=15.0)
        )
        avail = compliance._availability()
        assert avail["healthy"] is False
        assert avail["last_tick_seconds_ago"] is None


class TestComplianceReport:
    def test_assembles_all_three_sections(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = []
        fake.fetch_one.side_effect = [{"n": 0}, {"n": 0}]
        monkeypatch.setattr(compliance, "db", fake)
        monkeypatch.setattr(compliance, "heartbeat_age_s", lambda: 1.0)
        monkeypatch.setattr(
            compliance, "get_settings", lambda: Settings(_env_file=None, monitoring_interval_s=15.0)
        )
        report = compliance.compliance_report(since_hours=1.0)
        expected_keys = {"window_hours", "policy_verdicts", "incidents", "availability"}
        assert set(report.keys()) == expected_keys
        assert report["window_hours"] == 1.0
