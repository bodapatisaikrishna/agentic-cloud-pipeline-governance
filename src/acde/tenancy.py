"""Tenant/environment scope stamped onto every telemetry write (D-085), and the tenant registry
D-085 named as the missing piece for a real multi-tenant SaaS layer (D-097).

``current_scope()`` is resolved from server-side config only — never from a request or an agent's
proposed action — so a client can never claim to be a different tenant; it is what the control
loop's *write* path (one process per deployment, still single-tenant, see DEVIATIONS D-097's scope
note) stamps onto every telemetry row. The registry functions below are the admin-provisioned
*read*-path counterpart: they let an operator create/list/suspend tenants, and let
``server/app.py`` check a bound actor's tenant status before granting a request.
"""

from __future__ import annotations

from typing import Any

from acde import db
from acde.config import get_settings

_VALID_STATUSES = ("active", "suspended")


def current_scope() -> tuple[str, str]:
    """(tenant_id, environment) for the running process, from config only."""
    s = get_settings()
    return s.tenant_id, s.environment


def create_tenant(tenant_id: str, display_name: str) -> dict[str, Any]:
    """Register a new tenant (admin-provisioned, D-097). Raises on a duplicate ``tenant_id`` —
    the caller (CLI/API) is expected to surface that as a clean 409/error, not silently upsert."""
    existing = get_tenant(tenant_id)
    if existing is not None:
        raise ValueError(f"tenant {tenant_id!r} already exists")
    row = db.fetch_one(
        "INSERT INTO control.tenants (tenant_id, display_name) VALUES (%s, %s) "
        "RETURNING tenant_id, display_name, status, created_ts",
        (tenant_id, display_name),
    )
    assert row is not None  # INSERT ... RETURNING always returns exactly one row
    return row


def list_tenants() -> list[dict[str, Any]]:
    return db.fetch_all(
        "SELECT tenant_id, display_name, status, created_ts FROM control.tenants "
        "ORDER BY created_ts"
    )


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    row = db.fetch_one(
        "SELECT tenant_id, display_name, status, created_ts FROM control.tenants "
        "WHERE tenant_id = %s",
        (tenant_id,),
    )
    return row


def set_tenant_status(tenant_id: str, status: str) -> dict[str, Any]:
    """Suspend/reactivate a tenant. Raises ``ValueError`` for an unknown tenant or an invalid
    status, rather than a silent no-op UPDATE — the caller needs to know which one happened."""
    if status not in _VALID_STATUSES:
        raise ValueError(f"status must be one of {_VALID_STATUSES}, got {status!r}")
    row = db.fetch_one(
        "UPDATE control.tenants SET status = %s WHERE tenant_id = %s "
        "RETURNING tenant_id, display_name, status, created_ts",
        (status, tenant_id),
    )
    if row is None:
        raise ValueError(f"no such tenant {tenant_id!r}")
    return row
