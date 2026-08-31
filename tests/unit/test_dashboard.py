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
    # D-102: the dashboard now calls cost/compliance/decision_quality/tenancy directly, each with
    # its own separate `db` import -- the same "patch every module's own reference" pitfall this
    # session has hit repeatedly (D-091, D-095, D-097). Unpatched, /ui would hang or time out
    # against a real, unmocked connection pool instead of using this fixture's fake.
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.ops.compliance.db", fake)
    monkeypatch.setattr("acde.ops.decision_quality.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
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


def test_dashboard_shows_new_report_cards_with_real_values(client, monkeypatch):
    monkeypatch.setattr(
        "acde.server.dashboard.costs_by_tenant",
        lambda since_hours, tenant_id: [{"tenant_id": "default", "cost_units": 12.5}],
    )
    monkeypatch.setattr(
        "acde.server.dashboard.compliance_report",
        lambda since_hours, tenant_id: {
            "policy_verdicts": {"total": 10, "percentages": {"allowed": 80.0}}
        },
    )
    monkeypatch.setattr(
        "acde.server.dashboard.live_decision_quality",
        lambda since_hours, tenant_id: {"accuracy": 0.75},
    )
    r = client.get("/ui", auth=("operator", "secret"))
    assert r.status_code == 200
    assert "12.50" in r.text
    assert "80%" in r.text
    assert "75%" in r.text


def test_dashboard_shows_dash_not_zero_when_theres_no_data(client, monkeypatch):
    # D-102's own honesty rule: a verdict/accuracy with no underlying data must render as "—",
    # never a fabricated 0% that would misleadingly imply "always denied"/"always wrong."
    monkeypatch.setattr("acde.server.dashboard.costs_by_tenant", lambda since_hours, tenant_id: [])
    monkeypatch.setattr(
        "acde.server.dashboard.compliance_report",
        lambda since_hours, tenant_id: {"policy_verdicts": {"total": 0, "percentages": {}}},
    )
    monkeypatch.setattr(
        "acde.server.dashboard.live_decision_quality",
        lambda since_hours, tenant_id: {"accuracy": None},
    )
    r = client.get("/ui", auth=("operator", "secret"))
    assert r.status_code == 200
    # exact card-value match -- the page <title> also has an em-dash ("ACDE — Dashboard"),
    # unrelated to data availability, so a bare substring count would over-count.
    assert r.text.count('<span class="n">—</span>') == 2  # allow rate + decision accuracy


def test_dashboard_zero_percent_allow_rate_is_a_real_zero_not_a_dash(client, monkeypatch):
    # the bug this guards against: a verdict key missing from `percentages` (because "allowed"
    # never happened) must not be confused with "no data at all" when total > 0.
    monkeypatch.setattr(
        "acde.server.dashboard.compliance_report",
        lambda since_hours, tenant_id: {"policy_verdicts": {"total": 5, "percentages": {}}},
    )
    r = client.get("/ui", auth=("operator", "secret"))
    assert r.status_code == 200
    assert "0%" in r.text
    assert "policy allow rate" in r.text


def test_dashboard_tenants_table_hidden_for_non_admin(monkeypatch):
    # the legacy single api_key actor ("operator") defaults to role "admin" (D-093's own
    # zero-regression rule) -- a genuinely non-admin actor needs an explicit viewer/approver role.
    monkeypatch.setattr(
        app_mod, "get_settings", lambda: Settings(_env_file=None, api_keys="viv:viv-key:viewer")
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.ops.compliance.db", fake)
    monkeypatch.setattr("acde.ops.decision_quality.db", fake)
    monkeypatch.setattr(
        "acde.tenancy.list_tenants",
        lambda: (_ for _ in ()).throw(AssertionError("must not be called for a non-admin")),
    )
    client = TestClient(app_mod.create_app())
    r = client.get("/ui", auth=("viv", "viv-key"))
    assert r.status_code == 200
    assert "Tenants" not in r.text


def test_dashboard_tenants_table_hidden_for_a_single_tenant_deployment(monkeypatch):
    # avoids cluttering the common single-tenant case with a pointless one-row table.
    monkeypatch.setattr(
        app_mod, "get_settings", lambda: Settings(_env_file=None, api_keys="amy:amy-key:admin")
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.ops.compliance.db", fake)
    monkeypatch.setattr("acde.ops.decision_quality.db", fake)
    monkeypatch.setattr(
        "acde.tenancy.list_tenants",
        lambda: [{"tenant_id": "default", "display_name": "Default Tenant", "status": "active"}],
    )
    client = TestClient(app_mod.create_app())
    r = client.get("/ui", auth=("amy", "amy-key"))
    assert r.status_code == 200
    assert "Tenants" not in r.text


def test_dashboard_tenants_table_shown_for_admin_with_multiple_tenants(monkeypatch):
    monkeypatch.setattr(
        app_mod, "get_settings", lambda: Settings(_env_file=None, api_keys="amy:amy-key:admin")
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.ops.compliance.db", fake)
    monkeypatch.setattr("acde.ops.decision_quality.db", fake)
    monkeypatch.setattr(
        "acde.tenancy.list_tenants",
        lambda: [
            {"tenant_id": "default", "display_name": "Default Tenant", "status": "active"},
            {"tenant_id": "acme", "display_name": "Acme Inc", "status": "suspended"},
        ],
    )
    client = TestClient(app_mod.create_app())
    r = client.get("/ui", auth=("amy", "amy-key"))
    assert r.status_code == 200
    assert "Tenants" in r.text
    assert "acme" in r.text
    assert "status-suspended" in r.text


def test_dashboard_scopes_reports_to_the_callers_bound_tenant(monkeypatch):
    monkeypatch.setattr(
        app_mod,
        "get_settings",
        lambda: Settings(_env_file=None, api_keys="viv:viv-key:viewer:acme"),
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    # separate fake: _check_tenant_active (viv is bound to "acme") calls tenancy.get_tenant,
    # which expects a tenant-row shape, not metrics'/approvals' {"n": 0}.
    tenancy_fake = MagicMock()
    tenancy_fake.fetch_one.return_value = {
        "tenant_id": "acme",
        "display_name": "Acme Inc",
        "status": "active",
        "created_ts": "t",
    }
    monkeypatch.setattr("acde.tenancy.db", tenancy_fake)
    captured = {}
    monkeypatch.setattr(
        "acde.server.dashboard.costs_by_tenant",
        lambda since_hours, tenant_id: captured.update(tenant_id=tenant_id) or [],
    )
    monkeypatch.setattr(
        "acde.server.dashboard.compliance_report",
        lambda since_hours, tenant_id: {"policy_verdicts": {"total": 0, "percentages": {}}},
    )
    monkeypatch.setattr(
        "acde.server.dashboard.live_decision_quality",
        lambda since_hours, tenant_id: {"accuracy": None},
    )
    client = TestClient(app_mod.create_app())
    r = client.get("/ui", auth=("viv", "viv-key"))
    assert r.status_code == 200
    assert captured["tenant_id"] == "acme"


def test_ui_viewer_cannot_approve_or_reject_but_can_view(monkeypatch):
    # D-093: the dashboard's write actions go through the same approver_dep as the JSON API --
    # a viewer role can see the page but not act from it either.
    monkeypatch.setattr(
        app_mod, "get_settings", lambda: Settings(_env_file=None, api_keys="viv:viv-key:viewer")
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    # D-102: the dashboard now calls cost/compliance/decision_quality/tenancy directly, each with
    # its own separate `db` import -- the same "patch every module's own reference" pitfall this
    # session has hit repeatedly (D-091, D-095, D-097). Unpatched, /ui would hang or time out
    # against a real, unmocked connection pool instead of using this fixture's fake.
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.ops.compliance.db", fake)
    monkeypatch.setattr("acde.ops.decision_quality.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
    client = TestClient(app_mod.create_app())
    assert client.get("/ui", auth=("viv", "viv-key")).status_code == 200
    r = client.post("/ui/approvals/7/approve", auth=("viv", "viv-key"), follow_redirects=False)
    assert r.status_code == 403
