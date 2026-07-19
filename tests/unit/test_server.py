"""Unit tests for the operator API (FastAPI TestClient, mocked db)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from acde.config import Settings
from acde.server import app as app_mod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_mod, "get_settings", lambda: Settings(_env_file=None, api_key="secret"))
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    return TestClient(app_mod.create_app())


def test_refuses_to_start_without_api_key(monkeypatch):
    monkeypatch.setattr(app_mod, "get_settings", lambda: Settings(_env_file=None, api_key=""))
    with pytest.raises(RuntimeError, match="refusing to start"):
        app_mod.create_app()


def test_health_is_unauthenticated(client, monkeypatch):
    monkeypatch.setattr(app_mod, "doctor", lambda: {"checks": [], "all_ok": True})
    r = client.get("/health")
    assert r.status_code == 200


def test_protected_routes_require_key(client):
    assert client.get("/proposals").status_code == 401
    assert client.get("/metrics").status_code == 401
    assert client.get("/audit").status_code == 401


def test_valid_key_grants_access(client):
    r = client.get("/proposals", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json() == []


def test_metrics_prometheus_format(client):
    r = client.get("/metrics", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert "acde_proposals_total" in r.text
    assert r.headers["content-type"].startswith("text/plain")


def test_approvals_endpoints(client, monkeypatch):
    monkeypatch.setattr("acde.human.approvals.approve", lambda i, actor: {"status": "executed"})
    r = client.post("/approvals/5/approve", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json()["status"] == "executed"
