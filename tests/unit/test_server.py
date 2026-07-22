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


def test_legacy_single_key_resolves_to_operator_actor(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "acde.human.approvals.approve",
        lambda i, actor: captured.update(actor=actor) or {"status": "executed"},
    )
    r = client.post("/approvals/1/approve", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert captured["actor"] == "operator"


@pytest.fixture
def multi_actor_client(monkeypatch):
    monkeypatch.setattr(
        app_mod,
        "get_settings",
        lambda: Settings(_env_file=None, api_keys="alice:alice-key,bob:bob-key"),
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    return TestClient(app_mod.create_app())


def test_distinct_keys_resolve_to_distinct_actors(multi_actor_client, monkeypatch):
    captured = []
    monkeypatch.setattr(
        "acde.human.approvals.approve",
        lambda i, actor: captured.append(actor) or {"status": "executed"},
    )
    r1 = multi_actor_client.post("/approvals/1/approve", headers={"X-API-Key": "alice-key"})
    r2 = multi_actor_client.post("/approvals/2/approve", headers={"X-API-Key": "bob-key"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert captured == ["alice", "bob"]


def test_http_basic_auth_resolves_actor(multi_actor_client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "acde.human.approvals.approve",
        lambda i, actor: captured.update(actor=actor) or {"status": "executed"},
    )
    r = multi_actor_client.post("/approvals/1/approve", auth=("alice", "alice-key"))
    assert r.status_code == 200
    assert captured["actor"] == "alice"


def test_client_cannot_spoof_actor(multi_actor_client, monkeypatch):
    # a client authenticated as "alice" cannot claim to be "bob" via a request body/query field —
    # the actor comes solely from the authenticated identity, there's no client-writable field left.
    captured = {}
    monkeypatch.setattr(
        "acde.human.approvals.approve",
        lambda i, actor: captured.update(actor=actor) or {"status": "executed"},
    )
    r = multi_actor_client.post(
        "/approvals/1/approve?actor=bob", headers={"X-API-Key": "alice-key"}
    )
    assert r.status_code == 200
    assert captured["actor"] == "alice"  # not "bob"


def test_wrong_password_401s(multi_actor_client):
    r = multi_actor_client.get("/proposals", auth=("alice", "wrong-password"))
    assert r.status_code == 401


def test_no_credentials_401s(multi_actor_client):
    r = multi_actor_client.get("/proposals")
    assert r.status_code == 401


def test_refuses_to_start_with_neither_key_configured(monkeypatch):
    monkeypatch.setattr(
        app_mod, "get_settings", lambda: Settings(_env_file=None, api_key="", api_keys="")
    )
    with pytest.raises(RuntimeError, match="refusing to start"):
        app_mod.create_app()
