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
    # /metrics reads the loop heartbeat cross-process via orchestrator.control -- a separate `db`
    # reference from metrics.py's own, and otherwise unmocked, would silently hit a real database
    # if one happens to be running (tests/unit is meant to need neither docker nor network).
    monkeypatch.setattr("acde.orchestrator.control.db", fake)
    # D-095: /costs and /metrics' per-tenant gauge both go through acde.telemetry.cost's own `db`
    # import -- a third separate reference from app_mod's and metrics.py's, same pitfall as above.
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
    return TestClient(app_mod.create_app())


def test_refuses_to_start_without_api_key(monkeypatch):
    monkeypatch.setattr(app_mod, "get_settings", lambda: Settings(_env_file=None, api_key=""))
    with pytest.raises(RuntimeError, match="refusing to start"):
        app_mod.create_app()


def test_health_is_unauthenticated_and_shallow(client, monkeypatch):
    # D-087: /health never calls doctor() at all -- it must not leak deployment internals to an
    # unauthenticated caller, so this asserts the shape, not just a 200.
    monkeypatch.setattr(
        app_mod, "doctor", lambda: (_ for _ in ()).throw(AssertionError("must not be called"))
    )
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready_requires_auth_and_returns_full_report(client, monkeypatch):
    monkeypatch.setattr(
        app_mod, "doctor", lambda: {"checks": [{"name": "database"}], "all_ok": True}
    )
    assert client.get("/health/ready").status_code == 401
    r = client.get("/health/ready", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json()["all_ok"] is True
    assert r.json()["checks"]


def test_protected_routes_require_key(client):
    assert client.get("/proposals").status_code == 401
    assert client.get("/metrics").status_code == 401
    assert client.get("/audit").status_code == 401
    assert client.get("/health/ready").status_code == 401
    assert client.get("/costs").status_code == 401
    assert client.get("/compliance-report").status_code == 401


def test_docs_and_openapi_require_auth(client):
    # D-092: FastAPI's built-in docs_url/redoc_url/openapi_url are unauthenticated by
    # construction -- disabled and re-added as regular routes; this is the regression test.
    assert client.get("/docs").status_code == 401
    assert client.get("/redoc").status_code == 401
    assert client.get("/openapi.json").status_code == 401


def test_docs_and_openapi_work_with_a_valid_key(client):
    assert client.get("/docs", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/redoc", headers={"X-API-Key": "secret"}).status_code == 200
    r = client.get("/openapi.json", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "ACDE Operator API"


def test_valid_key_grants_access(client):
    r = client.get("/proposals", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json() == []


def test_audit_since_and_until_filter_the_query(client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    r = client.get(
        "/audit",
        params={"since": "2026-01-01T00:00:00Z", "until": "2026-01-02T00:00:00Z"},
        headers={"X-API-Key": "secret"},
    )
    assert r.status_code == 200
    sql, params = fake.fetch_all.call_args.args
    assert "ts >= %s" in sql
    assert "ts <= %s" in sql
    assert params[:2] == ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")


def test_audit_without_filters_has_no_range_clause(client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    r = client.get("/audit", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    sql, params = fake.fetch_all.call_args.args
    assert "ts >=" not in sql
    assert "ts <=" not in sql
    assert params == (100,)


def test_audit_export_requires_auth(client):
    assert client.get("/audit/export").status_code == 401


def test_audit_export_csv_has_header_and_rows(client, monkeypatch):
    import datetime as dt

    fake = MagicMock()
    row = {
        "action_id": "a1",
        "agent": "schema",
        "action_type": "quarantine_partition",
        "target": "store_sales",
        "policy_decision": "allowed",
        "policy_reason": "ok",
        "executed": True,
        "outcome": "quarantined",
        "status": "executed",
        "llm_model": "mock",
        "tenant_id": "default",
        "environment": "default",
        "ts": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
    }
    fake.fetch_all.return_value = [row]  # one batch, fewer than the page size -> stops after one
    monkeypatch.setattr(app_mod, "db", fake)
    r = client.get("/audit/export", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].split(",")[0] == "action_id"
    assert "quarantine_partition" in lines[1]


def test_audit_export_json_format(client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = [{"action_id": "a1", "agent": "schema"}]
    monkeypatch.setattr(app_mod, "db", fake)
    r = client.get("/audit/export", params={"format": "json"}, headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == [{"action_id": "a1", "agent": "schema"}]


def test_audit_export_paginates_past_the_batch_size(client, monkeypatch):
    from acde.server.app import _EXPORT_BATCH_SIZE

    full_batch = [{"action_id": f"a{i}", "ts": "t"} for i in range(_EXPORT_BATCH_SIZE)]
    partial_batch = [{"action_id": "last", "ts": "t"}]
    fake = MagicMock()
    fake.fetch_all.side_effect = [full_batch, partial_batch]
    monkeypatch.setattr(app_mod, "db", fake)
    r = client.get("/audit/export", params={"format": "json"}, headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert len(r.json()) == _EXPORT_BATCH_SIZE + 1
    assert fake.fetch_all.call_count == 2
    second_sql, second_params = fake.fetch_all.call_args_list[1].args
    assert "(ts, action_id) > (%s, %s)" in second_sql
    assert second_params[-3:-1] == ("t", "a999")


def test_metrics_prometheus_format(client):
    r = client.get("/metrics", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert "acde_proposals_total" in r.text
    assert "acde_stale_executing_actions" in r.text
    assert r.headers["content-type"].startswith("text/plain")


def test_metrics_omits_loop_heartbeat_gauge_when_never_recorded(client):
    # the shared fake's fetch_one returns {"n": 0} for every query, including the heartbeat
    # lookup -- no "updated_ts" key, so heartbeat_age_s() must degrade to None, not KeyError.
    r = client.get("/metrics", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert "acde_loop_last_tick_timestamp_seconds" not in r.text


def test_metrics_includes_loop_heartbeat_gauge_when_recorded(client, monkeypatch):
    import datetime as dt

    fake = MagicMock()
    fake.fetch_one.return_value = {"updated_ts": dt.datetime.now(dt.UTC)}
    monkeypatch.setattr("acde.orchestrator.control.db", fake)
    r = client.get("/metrics", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert "acde_loop_last_tick_timestamp_seconds" in r.text


def test_costs_requires_auth(client):
    assert client.get("/costs").status_code == 401


def test_costs_returns_per_tenant_breakdown(client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.side_effect = [
        [
            {
                "tenant_id": "acme",
                "cost_units": 12.5,
                "compute_unit_seconds": 200.0,
                "storage_gb_hours": 1.0,
            }
        ],
        [{"tenant_id": "acme", "llm_tokens": 500}],
    ]
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = client.get("/costs", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json() == [
        {
            "tenant_id": "acme",
            "cost_units": 12.5,
            "compute_unit_seconds": 200.0,
            "storage_gb_hours": 1.0,
            "llm_tokens": 500.0,
        }
    ]


def test_metrics_includes_per_tenant_cost_gauge(client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.side_effect = [
        [
            {
                "tenant_id": "acme",
                "cost_units": 3.0,
                "compute_unit_seconds": 0.0,
                "storage_gb_hours": 0.0,
            }
        ],
        [],
    ]
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = client.get("/metrics", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert 'acde_cost_units_by_tenant{tenant_id="acme"} 3.0' in r.text


def test_compliance_report_requires_auth(client):
    assert client.get("/compliance-report").status_code == 401


def test_compliance_report_returns_the_report_shape(client, monkeypatch):
    monkeypatch.setattr(
        "acde.server.app.compliance_report",
        lambda since_hours, tenant_id: {
            "window_hours": since_hours,
            "availability": {"healthy": True},
        },
    )
    r = client.get(
        "/compliance-report", params={"since_hours": 48}, headers={"X-API-Key": "secret"}
    )
    assert r.status_code == 200
    assert r.json() == {"window_hours": 48.0, "availability": {"healthy": True}}


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
    # /metrics reads the loop heartbeat cross-process via orchestrator.control -- a separate `db`
    # reference from metrics.py's own, and otherwise unmocked, would silently hit a real database
    # if one happens to be running (tests/unit is meant to need neither docker nor network).
    monkeypatch.setattr("acde.orchestrator.control.db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
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


@pytest.fixture
def role_client(monkeypatch):
    """D-093: viewer, approver, admin, each with a distinct key."""
    monkeypatch.setattr(
        app_mod,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            api_keys="viv:viv-key:viewer,approver_al:approver-key:approver,admin_amy:admin-key:admin",
        ),
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    monkeypatch.setattr("acde.orchestrator.control.db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
    return TestClient(app_mod.create_app())


def test_viewer_can_read_but_not_approve_or_reject(role_client):
    assert role_client.get("/proposals", headers={"X-API-Key": "viv-key"}).status_code == 200
    assert role_client.get("/audit", headers={"X-API-Key": "viv-key"}).status_code == 200
    r_approve = role_client.post("/approvals/1/approve", headers={"X-API-Key": "viv-key"})
    r_reject = role_client.post("/approvals/1/reject", headers={"X-API-Key": "viv-key"})
    assert r_approve.status_code == 403
    assert r_reject.status_code == 403


def test_approver_can_approve_and_reject(role_client, monkeypatch):
    monkeypatch.setattr("acde.human.approvals.approve", lambda i, actor: {"status": "executed"})
    monkeypatch.setattr(
        "acde.human.approvals.reject", lambda i, actor, note="": {"status": "rejected"}
    )
    r_approve = role_client.post("/approvals/1/approve", headers={"X-API-Key": "approver-key"})
    r_reject = role_client.post("/approvals/2/reject", headers={"X-API-Key": "approver-key"})
    assert r_approve.status_code == 200
    assert r_reject.status_code == 200


def test_admin_can_approve_too(role_client, monkeypatch):
    monkeypatch.setattr("acde.human.approvals.approve", lambda i, actor: {"status": "executed"})
    r = role_client.post("/approvals/1/approve", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 200


def test_legacy_single_key_deployment_keeps_full_access(client, monkeypatch):
    # the regression test that matters most: no role syntax at all, the config every existing
    # deployment already has, must keep working exactly as before this feature landed.
    monkeypatch.setattr("acde.human.approvals.approve", lambda i, actor: {"status": "executed"})
    r = client.post("/approvals/1/approve", headers={"X-API-Key": "secret"})
    assert r.status_code == 200


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


def test_non_ascii_basic_password_401s_rather_than_erroring(multi_actor_client):
    # Non-ASCII credentials must resolve to a clean 401, never a 500. FastAPI decodes the Basic
    # header as ASCII and rejects it before _authenticate runs, so this locks in that end-to-end
    # contract (the key comparison itself encodes its operands as a second line of defence).
    r = multi_actor_client.get("/proposals", auth=("alice", "café-clé"))
    assert r.status_code == 401


def test_refuses_to_start_with_neither_key_configured(monkeypatch):
    monkeypatch.setattr(
        app_mod, "get_settings", lambda: Settings(_env_file=None, api_key="", api_keys="")
    )
    with pytest.raises(RuntimeError, match="refusing to start"):
        app_mod.create_app()


# --- D-097: multi-tenant SaaS layer ---------------------------------------------------------


@pytest.fixture
def tenant_client(monkeypatch):
    """``viv`` is bound to tenant ``acme``; ``admin_amy`` is unbound (sees everything, the
    zero-regression default)."""
    monkeypatch.setattr(
        app_mod,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            api_keys="viv:viv-key:viewer:acme,admin_amy:admin-key:admin",
        ),
    )
    fake = MagicMock()
    fake.fetch_all.return_value = []
    # get_tenant("acme") -> active, unless a test overrides fetch_one itself.
    fake.fetch_one.return_value = {
        "tenant_id": "acme",
        "display_name": "Acme Inc",
        "status": "active",
        "created_ts": "t",
    }
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr(app_mod.metrics, "db", fake)
    monkeypatch.setattr("acde.human.approvals.db", fake)
    monkeypatch.setattr("acde.orchestrator.control.db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)
    monkeypatch.setattr("acde.tenancy.db", fake)
    return TestClient(app_mod.create_app())


def test_bound_actor_gets_a_tenant_filter_on_proposals(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = []
    monkeypatch.setattr(app_mod, "db", fake)
    r = tenant_client.get("/proposals", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 200
    sql, params = fake.fetch_all.call_args.args
    assert "tenant_id = %s" in sql
    assert "acme" in params


def test_unbound_actor_gets_no_tenant_filter_zero_regression(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = []
    monkeypatch.setattr(app_mod, "db", fake)
    r = tenant_client.get("/proposals", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 200
    sql, _params = fake.fetch_all.call_args.args
    assert "tenant_id = %s" not in sql


def test_audit_gets_a_tenant_filter_too(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = []
    monkeypatch.setattr(app_mod, "db", fake)
    r = tenant_client.get("/audit", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 200
    sql, params = fake.fetch_all.call_args.args
    assert "tenant_id = %s" in sql
    assert "acme" in params


def test_audit_export_and_costs_and_compliance_report_are_also_scoped(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_all.return_value = []
    fake.fetch_one.return_value = {"n": 0}
    monkeypatch.setattr(app_mod, "db", fake)
    monkeypatch.setattr("acde.telemetry.cost.db", fake)

    r = tenant_client.get("/audit/export", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 200
    export_sql = fake.fetch_all.call_args.args[0]
    assert "tenant_id = %s" in export_sql

    r = tenant_client.get("/costs", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 200
    cost_sql = fake.fetch_all.call_args_list[-1].args[0]
    assert "tenant_id = %s" in cost_sql

    r = tenant_client.get("/compliance-report", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 200
    assert r.json()["policy_verdicts"]["total"] == 0  # ran without error, scoped or not


def test_suspended_tenant_gets_403(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = {
        "tenant_id": "acme",
        "display_name": "Acme Inc",
        "status": "suspended",
        "created_ts": "t",
    }
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = tenant_client.get("/proposals", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 403


def test_active_tenant_passes(tenant_client):
    # sanity counterpart to the suspended test -- proves the check isn't just always-403.
    r = tenant_client.get("/proposals", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 200


def test_unbound_actor_never_hits_the_tenant_table(tenant_client, monkeypatch):
    # mutation-test proof for the "skip the DB read entirely when unbound" claim in
    # _check_tenant_active's own docstring.
    fake = MagicMock()
    fake.fetch_one.side_effect = AssertionError("must not be called for an unbound actor")
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = tenant_client.get("/proposals", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 200


def test_admin_can_create_list_suspend_activate_a_tenant(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_one.side_effect = [
        None,  # create: pre-check, no existing row
        {"tenant_id": "beta", "display_name": "Beta LLC", "status": "active", "created_ts": "t"},
        {  # suspend
            "tenant_id": "beta",
            "display_name": "Beta LLC",
            "status": "suspended",
            "created_ts": "t",
        },
    ]
    fake.fetch_all.return_value = [
        {"tenant_id": "beta", "display_name": "Beta LLC", "status": "active", "created_ts": "t"}
    ]
    monkeypatch.setattr("acde.tenancy.db", fake)

    r = tenant_client.post(
        "/tenants",
        params={"tenant_id": "beta", "display_name": "Beta LLC"},
        headers={"X-API-Key": "admin-key"},
    )
    assert r.status_code == 200
    assert r.json()["tenant_id"] == "beta"

    r = tenant_client.get("/tenants", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 200
    assert r.json()[0]["tenant_id"] == "beta"

    r = tenant_client.post("/tenants/beta/suspend", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"


def test_viewer_cannot_manage_tenants(tenant_client):
    r = tenant_client.post(
        "/tenants",
        params={"tenant_id": "beta", "display_name": "Beta LLC"},
        headers={"X-API-Key": "viv-key"},
    )
    assert r.status_code == 403
    r = tenant_client.get("/tenants", headers={"X-API-Key": "viv-key"})
    assert r.status_code == 403


def test_tenants_routes_require_auth(client):
    assert client.get("/tenants").status_code == 401
    assert (
        client.post("/tenants", params={"tenant_id": "x", "display_name": "X"}).status_code == 401
    )


def test_create_duplicate_tenant_is_409(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = {
        "tenant_id": "acme",
        "display_name": "Acme Inc",
        "status": "active",
        "created_ts": "t",
    }
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = tenant_client.post(
        "/tenants",
        params={"tenant_id": "acme", "display_name": "Acme Again"},
        headers={"X-API-Key": "admin-key"},
    )
    assert r.status_code == 409


def test_admin_can_reactivate_a_suspended_tenant(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = {
        "tenant_id": "acme",
        "display_name": "Acme Inc",
        "status": "active",
        "created_ts": "t",
    }
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = tenant_client.post("/tenants/acme/activate", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_suspend_unknown_tenant_is_404(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = None
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = tenant_client.post("/tenants/nope/suspend", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 404


def test_activate_unknown_tenant_is_404(tenant_client, monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = None
    monkeypatch.setattr("acde.tenancy.db", fake)
    r = tenant_client.post("/tenants/nope/activate", headers={"X-API-Key": "admin-key"})
    assert r.status_code == 404
