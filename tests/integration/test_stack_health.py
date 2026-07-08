"""Integration smoke tests for the Phase 0 stack (requires `make up`)."""

import urllib.request

import pytest

from acde import db

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    ("telemetry", "task_runs"),
    ("telemetry", "pipeline_metrics"),
    ("telemetry", "schema_versions"),
    ("telemetry", "resource_usage"),
    ("telemetry", "failure_events"),
    ("telemetry", "agent_actions"),
    ("telemetry", "manual_interventions"),
    ("telemetry", "cost_ledger"),
    ("warehouse", "partition_versions"),
    ("control", "desired_state"),
}


def test_all_spec_tables_exist():
    rows = db.fetch_all(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('telemetry', 'warehouse', 'control')"
    )
    found = {(r["table_schema"], r["table_name"]) for r in rows}
    assert found >= EXPECTED_TABLES, f"missing: {EXPECTED_TABLES - found}"


def test_init_sql_is_idempotent():
    from pathlib import Path

    for sql_file in sorted(Path("infra/postgres/init").glob("*.sql")):
        db.execute(sql_file.read_text())  # re-apply: must not raise


def test_opa_health_endpoint():
    from acde.config import get_settings

    with urllib.request.urlopen(f"{get_settings().opa_url}/health", timeout=5) as resp:
        assert resp.status == 200


def test_desired_state_round_trip():
    db.execute(
        "INSERT INTO control.desired_state (key, value) VALUES (%s, %s::jsonb) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_ts = now()",
        ("integration.smoke", '{"ok": true}'),
    )
    row = db.fetch_one(
        "SELECT value FROM control.desired_state WHERE key = %s", ("integration.smoke",)
    )
    assert row is not None and row["value"] == {"ok": True}
