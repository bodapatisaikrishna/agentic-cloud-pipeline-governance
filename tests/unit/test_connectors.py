"""Unit tests for the connector boundary + doctor health checks."""

import pytest

from acde.config import Settings
from acde.connectors import registry
from acde.connectors.base import Connector, ConnectorHealth
from acde.connectors.noop import NoopConnector
from acde.ops import health


def test_noop_is_observe_only_and_never_acts():
    c = NoopConnector()
    assert c.can_act is False
    assert c.is_production is False
    assert c.health().ok
    assert c.get_task_runs("dag") == []
    assert c.trigger_pipeline("dag") == "noop"  # no exception, no side effect


def test_registry_selects_by_kind():
    assert isinstance(registry.get_connector("noop"), NoopConnector)
    air = registry.get_connector("airflow")
    assert air.name == "airflow" and air.can_act is True


def test_registry_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown connector_kind"):
        registry.get_connector("frobnicator")


def test_connectors_satisfy_protocol():
    from acde.connectors.airflow import AirflowConnector

    assert isinstance(NoopConnector(), Connector)
    assert isinstance(AirflowConnector(), Connector)


class TestDoctor:
    def test_all_ok_when_deps_healthy(self, monkeypatch):
        monkeypatch.setattr(health, "_check_db", lambda: health.Check("database", True, "ok"))
        monkeypatch.setattr(health, "_check_opa", lambda: health.Check("opa", True, "ok"))
        monkeypatch.setattr(
            health,
            "_check_connector",
            lambda: health.Check("connector:noop", True, "observe-only"),
        )
        monkeypatch.setattr(
            health, "get_settings", lambda: Settings(_env_file=None, mock_llm=True)
        )
        out = health.doctor()
        assert out["all_ok"] is True
        assert any(c["name"] == "llm" and c["ok"] for c in out["checks"])

    def test_flags_missing_llm_key(self, monkeypatch):
        monkeypatch.setattr(
            health,
            "get_settings",
            lambda: Settings(_env_file=None, mock_llm=False, llm_provider="gemini", gemini_api_key=""),
        )
        c = health._check_llm()
        assert not c.ok and "MISSING" in c.detail

    def test_connector_health_dataclass(self):
        h = ConnectorHealth("x", True, "d", can_act=True)
        assert h.ok and h.can_act
