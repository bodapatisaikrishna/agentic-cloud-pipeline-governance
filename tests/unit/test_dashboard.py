"""Unit tests for the /ui operator dashboard (FastAPI TestClient, mocked db)."""

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


def test_dashboard_requires_auth(client):
    r = client.get("/ui", follow_redirects=False)
    assert r.status_code == 401


def test_dashboard_renders_with_basic_auth(client, monkeypatch):
    monkeypatch.setattr(
        "acde.human.approvals.list_pending",
        lambda: [
            {
                "approval_id": 3,
                "agent": "schema",
                "action_type": "quarantine_partition",
                "target": "store_sales",
                "justification": "drift",
                "requested_ts": "2026-01-01T00:00:00Z",
            }
        ],
    )
    r = client.get("/ui", auth=("operator", "secret"))
    assert r.status_code == 200
    assert "quarantine_partition" in r.text
    assert "signed in as operator" in r.text


def test_dashboard_empty_state(client, monkeypatch):
    monkeypatch.setattr("acde.human.approvals.list_pending", lambda: [])
    r = client.get("/ui", auth=("operator", "secret"))
    assert r.status_code == 200
    assert "No pending approvals" in r.text


def test_dashboard_shows_metrics_cards(client):
    r = client.get("/ui", auth=("operator", "secret"))
    assert r.status_code == 200
    assert "pending approvals" in r.text
    assert "LLM tokens" in r.text


def test_ui_approve_calls_same_function_as_json_api_and_redirects(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "acde.human.approvals.approve",
        lambda i, actor: (
            captured.update(id=i, actor=actor) or {"status": "executed", "outcome": "done"}
        ),
    )
    r = client.post("/ui/approvals/7/approve", auth=("operator", "secret"), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/ui?flash=")
    assert captured == {"id": 7, "actor": "operator"}


def test_ui_reject_calls_same_function_as_json_api_and_redirects(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "acde.human.approvals.reject",
        lambda i, actor: captured.update(id=i, actor=actor) or {"status": "rejected"},
    )
    r = client.post("/ui/approvals/7/reject", auth=("operator", "secret"), follow_redirects=False)
    assert r.status_code == 303
    assert captured == {"id": 7, "actor": "operator"}


def test_ui_actions_require_auth(client):
    r = client.post("/ui/approvals/7/approve", follow_redirects=False)
    assert r.status_code == 401
