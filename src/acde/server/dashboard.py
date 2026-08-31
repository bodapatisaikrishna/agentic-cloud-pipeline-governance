"""Minimal server-rendered operator dashboard (T2.2): pending approvals + metrics.

No JS, no external assets (works air-gapped), no session storage — auth is the same
``_authenticate`` dependency the JSON API uses (HTTP Basic here, so a browser gets a native
credential prompt), and POSTing approve/reject calls the exact same ``acde.human.approvals``
functions as ``/approvals/{id}/approve|reject``, so there is no separate, weaker write path.

D-102 surfaces the reports that only ever had a JSON/CLI face before (cost D-095, compliance
D-096, decision-quality D-100, tenants D-097) by calling the exact same functions their routes
call — no new SQL, no new backend computation, purely a presentation layer.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from acde import tenancy
from acde.human import approvals
from acde.ops.compliance import compliance_report
from acde.ops.decision_quality import live_decision_quality
from acde.server import metrics
from acde.telemetry.cost import costs_by_tenant

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def add_routes(
    app: FastAPI,
    actor_dep: Callable[..., str],
    approver_dep: Callable[..., str] | None = None,
    tenant_scope_dep: Callable[..., str | None] | None = None,
    role_dep: Callable[..., str] | None = None,
) -> None:
    """Register the /ui routes on ``app``, authenticated via the same dependency as the JSON API.

    ``approver_dep`` (D-093) gates the write actions (approve/reject) to role ``approver``+; any
    authenticated actor (``viewer``+) can view the dashboard itself. ``tenant_scope_dep`` (D-097)
    resolves the caller's bound tenant, exactly like the JSON API's own report routes -- a
    tenant-bound operator sees their own numbers, not everyone's. ``role_dep`` (D-102) resolves
    the caller's role for the admin-only tenants table -- deliberately threaded in from
    ``server/app.py`` rather than this module calling ``get_settings()`` itself: that would be a
    second, separate ``get_settings`` reference from ``app.py``'s own, the exact "patch every
    module's own import" pitfall this session has hit repeatedly for ``db`` (D-091/095/097),
    just for a different name. All three default to falling back to unscoped/full-access behavior
    for backward compatibility with any caller not yet passing them.
    """
    write_dep = approver_dep or actor_dep
    tenant_dep = tenant_scope_dep or (lambda: None)
    role_lookup = role_dep or (lambda: "admin")

    @app.get("/ui", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        actor: str = Depends(actor_dep),
        tenant_id: str | None = Depends(tenant_dep),
        role: str = Depends(role_lookup),
    ) -> HTMLResponse:
        flash = request.query_params.get("flash", "")

        costs = costs_by_tenant(since_hours=24.0, tenant_id=tenant_id)
        cost_units_24h = sum(float(row["cost_units"]) for row in costs)

        compliance = compliance_report(since_hours=24.0, tenant_id=tenant_id)
        verdicts = cast(dict[str, Any], compliance["policy_verdicts"])
        # a verdict missing from `percentages` means it never occurred, not "no data" -- only
        # `total == 0` (no actions at all in the window) means there's genuinely nothing to show.
        allow_rate = verdicts["percentages"].get("allowed", 0.0) if verdicts["total"] else None

        dq = live_decision_quality(since_hours=24.0, tenant_id=tenant_id)

        return _templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "actor": actor,
                "role": role,
                "m": metrics.snapshot(),
                "approvals": approvals.list_pending(),
                "flash": flash,
                "flash_ok": request.query_params.get("ok") == "1",
                "cost_units_24h": cost_units_24h,
                "allow_rate": allow_rate,
                "decision_accuracy": dq["accuracy"],
                # tenant management stays admin-only, matching D-097's own /tenants* routes --
                # not fetched at all for a non-admin actor.
                "tenants": tenancy.list_tenants() if role == "admin" else None,
            },
        )

    @app.post("/ui/approvals/{approval_id}/approve")
    def ui_approve(approval_id: int, actor: str = Depends(write_dep)) -> RedirectResponse:
        result = approvals.approve(approval_id, actor=actor)
        ok = "1" if result["status"] == "executed" else "0"
        msg = f"#{approval_id}: {result['status']} — {result['outcome']}"
        return RedirectResponse(f"/ui?flash={quote(msg)}&ok={ok}", status_code=303)

    @app.post("/ui/approvals/{approval_id}/reject")
    def ui_reject(approval_id: int, actor: str = Depends(write_dep)) -> RedirectResponse:
        result = approvals.reject(approval_id, actor=actor)
        msg = f"#{approval_id}: {result['status']}"
        return RedirectResponse(f"/ui?flash={quote(msg)}&ok=1", status_code=303)
