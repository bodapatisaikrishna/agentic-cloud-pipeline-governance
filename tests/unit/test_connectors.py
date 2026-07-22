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
    from acde.connectors.prefect import PrefectConnector

    pf = registry.get_connector("prefect")
    assert isinstance(pf, PrefectConnector)
    assert pf.name == "prefect" and pf.can_act is True


def test_registry_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown connector_kind"):
        registry.get_connector("frobnicator")


def test_connectors_satisfy_protocol():
    from acde.connectors.airflow import AirflowConnector
    from acde.connectors.prefect import PrefectConnector

    assert isinstance(NoopConnector(), Connector)
    assert isinstance(AirflowConnector(), Connector)
    assert isinstance(PrefectConnector(), Connector)


class TestPrefectConnector:
    """Second Connector implementation — proves the protocol generalizes beyond Airflow (T2.4)."""

    def test_is_production_flag_propagates(self):
        from acde.connectors.prefect import PrefectConnector

        assert PrefectConnector(is_production=False).is_production is False
        assert PrefectConnector().is_production is True  # default

    def test_clear_tasks_is_a_noop_with_no_runs(self, monkeypatch):
        # the one piece of real (non-HTTP-passthrough) logic: must not error when there's
        # nothing to retry, and must never call the network layer in that case.
        from acde.connectors.prefect import PrefectConnector

        conn = PrefectConnector()
        monkeypatch.setattr(conn, "get_task_runs", lambda pipeline_id: [])
        monkeypatch.setattr(
            conn, "_client", lambda: (_ for _ in ()).throw(AssertionError("should not connect"))
        )
        conn.clear_tasks("some-deployment-id", task_ids=["ignored"])  # must not raise

    def test_health_reports_unreachable_gracefully(self, monkeypatch):
        from acde.connectors.prefect import PrefectConnector

        conn = PrefectConnector()

        def _boom():
            raise ConnectionError("refused")

        monkeypatch.setattr(conn, "_client", _boom)
        h = conn.health()
        assert h.ok is False and h.can_act is True and "refused" in h.detail


class TestDoctor:
    def test_all_ok_when_deps_healthy(self, monkeypatch):
        monkeypatch.setattr(health, "_check_db", lambda: health.Check("database", True, "ok"))
        monkeypatch.setattr(health, "_check_opa", lambda: health.Check("opa", True, "ok"))
        monkeypatch.setattr(
            health,
            "_check_connector",
            lambda: health.Check("connector:noop", True, "observe-only"),
        )
        monkeypatch.setattr(health, "get_settings", lambda: Settings(_env_file=None, mock_llm=True))
        out = health.doctor()
        assert out["all_ok"] is True
        assert any(c["name"] == "llm" and c["ok"] for c in out["checks"])

    def test_flags_missing_llm_key(self, monkeypatch):
        monkeypatch.setattr(
            health,
            "get_settings",
            lambda: Settings(
                _env_file=None, mock_llm=False, llm_provider="gemini", gemini_api_key=""
            ),
        )
        c = health._check_llm()
        assert not c.ok and "MISSING" in c.detail

    def test_connector_health_dataclass(self):
        h = ConnectorHealth("x", True, "d", can_act=True)
        assert h.ok and h.can_act
