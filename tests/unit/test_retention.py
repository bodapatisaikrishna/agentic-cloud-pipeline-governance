"""Unit tests for opt-in telemetry retention (D-086)."""

from unittest.mock import MagicMock

from acde.config import Settings
from acde.telemetry import retention


class TestPurge:
    def test_disabled_by_default_is_a_noop(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(retention, "db", fake)
        monkeypatch.setattr(retention, "get_settings", lambda: Settings(_env_file=None))
        result = retention.purge()
        assert result == {}
        fake.fetch_one.assert_not_called()

    def test_explicit_zero_days_is_still_a_noop(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(retention, "db", fake)
        result = retention.purge(days=0)
        assert result == {}
        fake.fetch_one.assert_not_called()

    def test_enabled_purges_every_retainable_table(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"n": 5}
        monkeypatch.setattr(retention, "db", fake)
        result = retention.purge(days=30)
        assert result == {
            "telemetry.resource_usage": 5,
            "telemetry.pipeline_metrics": 5,
            "telemetry.task_runs": 5,
        }
        assert fake.fetch_one.call_count == 3
        for call in fake.fetch_one.call_args_list:
            sql, params = call.args
            assert "DELETE FROM" in sql
            assert params == (30,)

    def test_agent_actions_is_never_touched(self):
        # the audit trail is exempt by design -- assert it directly against the retainable set,
        # not just "we didn't happen to test it".
        tables = {t for t, _ in retention._RETAINABLE}
        assert "telemetry.agent_actions" not in tables

    def test_settings_value_used_when_days_not_passed(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"n": 0}
        monkeypatch.setattr(retention, "db", fake)
        monkeypatch.setattr(
            retention, "get_settings", lambda: Settings(_env_file=None, retention_days=90)
        )
        retention.purge()
        _, params = fake.fetch_one.call_args_list[0].args
        assert params == (90,)
