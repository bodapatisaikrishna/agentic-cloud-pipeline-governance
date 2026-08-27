"""Tenant/environment scope stamped onto every telemetry write (D-085).

Resolved from server-side config only — never from a request or an agent's proposed action — so a
client can never claim to be a different tenant. Today every deployment is exactly one tenant and
one environment (self-hosted, one Postgres); this is deliberately not a multi-tenant control plane
(no tenant registry, no per-request routing) — see DEVIATIONS D-085 for the scope this establishes
versus the SaaS control plane it does not build yet.
"""

from __future__ import annotations

from acde.config import get_settings


def current_scope() -> tuple[str, str]:
    """(tenant_id, environment) for the running process, from config only."""
    s = get_settings()
    return s.tenant_id, s.environment
