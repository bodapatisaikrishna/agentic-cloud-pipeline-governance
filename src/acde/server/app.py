"""FastAPI operator API (P3): health, metrics, proposals, audit, approvals.

Multi-actor auth (T2.1): each request is authenticated via ``X-API-Key`` (JSON/CLI clients) or HTTP
Basic (browser dashboard — username=actor, password=key) against ``Settings.api_key_map``, and the
resolved *actor name* — not a client-supplied field — is what lands in the audit trail. The app
**refuses to build** with no key configured at all, so it can never be exposed unauthenticated by
accident. TLS is expected to be terminated by a reverse proxy (documented in docs/OPERATIONS.md).

RBAC (D-093): three roles, ``viewer < approver < admin``, from ``Settings.role_map`` (an optional
third ``actor:key:role`` field). An actor missing a role — including every deployment that only
has ``api_key``/``api_keys`` with no role syntax at all today — defaults to ``admin``, so upgrading
never silently downgrades anyone's existing access.

Multi-tenant SaaS layer (D-097): an optional fourth ``actor:key:role:tenant_id`` field
(``Settings.tenant_map``) binds an actor to one tenant. Missing means **unscoped** (sees every
tenant, today's behavior, zero regression) — only an admin-provisioned actor with an explicit
tenant binding is isolated to it. A bound actor whose tenant is suspended (``control.tenants``,
via ``acde.tenancy``) gets 403 at authentication time, before any route runs. Scope: this isolates
the *read* side of the operator API (``/proposals``, ``/audit``, ``/audit/export``, ``/costs``,
``/compliance-report``) — the control loop and the human-approval queue remain one
process/one-tenant-per-deployment, unchanged (see DEVIATIONS D-097 for why).

Rate limiting (D-098): an in-process, per-app fixed-window limiter (``server/ratelimit.py``),
``Settings.api_rate_limit_per_minute`` (``0`` = unlimited, the default). Runs as middleware —
*before* ``_authenticate`` — so it also throttles pre-auth key-guessing floods, keyed by the
resolved actor when credentials match, else the raw client address. Does not trust
``X-Forwarded-For`` (client-supplied, spoofable). ``/health`` is exempt.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from collections.abc import Awaitable, Callable, Iterator
from secrets import compare_digest
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from acde import db, tenancy
from acde.config import get_settings
from acde.human import approvals
from acde.logging import get_logger
from acde.ops.compliance import compliance_report
from acde.ops.health import doctor
from acde.server import dashboard, metrics, ratelimit
from acde.telemetry import cost

log = get_logger("server.app")

_basic = HTTPBasic(auto_error=False)


def _authenticate(
    x_api_key: Annotated[str, Header()] = "",
    basic: Annotated[HTTPBasicCredentials | None, Depends(_basic)] = None,
) -> str:
    """Resolve the caller to an actor name via X-API-Key or HTTP Basic; 401 on any mismatch.

    Key comparison goes through ``compare_digest`` so a wrong key takes the same time to reject
    regardless of how many leading characters were right — a plain ``==`` leaks that prefix length
    through timing and lets an attacker recover a key byte by byte. Operands are encoded to bytes
    because ``compare_digest`` raises TypeError on non-ASCII *str*; both callers are already
    ASCII-constrained upstream (HTTP header values, and FastAPI's ASCII decode of the Basic header),
    so this is defence in depth rather than a reachable bug.
    """
    key_map = get_settings().api_key_map
    if x_api_key:
        for actor, key in key_map.items():
            if compare_digest(x_api_key.encode(), key.encode()):
                _check_tenant_active(actor)
                return actor
    elif basic is not None:
        expected = key_map.get(basic.username)
        if expected is not None and compare_digest(basic.password.encode(), expected.encode()):
            _check_tenant_active(basic.username)
            return basic.username
    raise HTTPException(
        status_code=401,
        detail="invalid or missing credentials (X-API-Key header or HTTP Basic)",
        headers={"WWW-Authenticate": "Basic"},
    )


def _rate_limit_key(request: Request) -> str:
    """Resolve the rate-limit bucket key for an incoming request (D-098): the actor if valid
    credentials are already present (so one actor's floods never burn another actor's budget),
    else the raw client address (so pre-auth floods -- including wrong-key guessing -- still get
    bucketed by source). Deliberately duplicates ``_authenticate``'s lookup rather than depending
    on it: middleware runs before FastAPI's dependency injection resolves anything, so there is no
    already-authenticated identity to reuse here.
    """
    key_map = get_settings().api_key_map
    x_api_key = request.headers.get("x-api-key", "")
    if x_api_key:
        for actor, key in key_map.items():
            if compare_digest(x_api_key.encode(), key.encode()):
                return actor
    else:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Basic "):
            try:
                username, _, password = (
                    base64.b64decode(auth_header[6:]).decode("ascii").partition(":")
                )
            except (ValueError, UnicodeDecodeError):
                username, password = "", ""
            expected = key_map.get(username)
            if expected is not None and compare_digest(password.encode(), expected.encode()):
                return username
    return request.client.host if request.client else "unknown"


def _check_tenant_active(actor: str) -> None:
    """D-097: if ``actor`` is bound to a tenant, that tenant must exist and be ``active`` — a
    suspended tenant's credentials are valid but not authorized (403, not 401, same reasoning as
    ``require_role``). An unbound actor (``tenant_map.get`` misses — every actor configured before
    this feature existed, and every actor an admin never explicitly bound) skips the DB read
    entirely: zero added latency and zero behavior change for today's single-tenant deployments.
    """
    tenant_id = get_settings().tenant_map.get(actor)
    if tenant_id is None:
        return
    tenant = tenancy.get_tenant(tenant_id)
    if tenant is None or tenant["status"] != "active":
        raise HTTPException(status_code=403, detail=f"tenant '{tenant_id}' is not active")


_EXPORT_COLUMNS = (
    "action_id",
    "agent",
    "action_type",
    "target",
    "policy_decision",
    "policy_reason",
    "executed",
    "outcome",
    "status",
    "llm_model",
    "tenant_id",
    "environment",
    "ts",
)
_EXPORT_BATCH_SIZE = 1000


def _audit_rows_paginated(
    since: str | None,
    until: str | None,
    tenant_id: str | None = None,
    batch_size: int = _EXPORT_BATCH_SIZE,
) -> Iterator[dict[str, Any]]:
    """Every matching audit row, oldest first, fetched in bounded batches (D-094) — unlike
    ``/audit``'s ``LIMIT``, this is a genuine full export: a keyset cursor on ``(ts, action_id)``
    (a plain ``OFFSET`` degrades on a large table, and ``ts`` alone isn't a unique tiebreaker)
    means memory stays bounded to one batch at a time regardless of how large the result is.
    ``tenant_id`` (D-097) restricts the export to one tenant when the caller is bound to one.
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if since:
        conditions.append("ts >= %s")
        params.append(since)
    if until:
        conditions.append("ts <= %s")
        params.append(until)
    if tenant_id is not None:
        conditions.append("tenant_id = %s")
        params.append(tenant_id)
    cursor: tuple[Any, str] | None = None
    while True:
        cursor_conditions = list(conditions)
        cursor_params = list(params)
        if cursor is not None:
            cursor_conditions.append("(ts, action_id) > (%s, %s)")
            cursor_params.extend(cursor)
        cursor_params.append(batch_size)
        rows = db.fetch_all(
            "SELECT action_id, agent, action_type, target, policy_decision, policy_reason, "
            "executed, outcome, status, llm_model, tenant_id, environment, ts "
            "FROM telemetry.agent_actions "
            f"WHERE {' AND '.join(cursor_conditions)} ORDER BY ts ASC, action_id ASC LIMIT %s",
            tuple(cursor_params),
        )
        if not rows:
            return
        yield from rows
        if len(rows) < batch_size:
            return
        last = rows[-1]
        cursor = (last["ts"], str(last["action_id"]))


_ROLE_RANK = {"viewer": 0, "approver": 1, "admin": 2}


def require_role(min_role: str) -> Any:
    """Dependency factory: authenticate (nested ``Depends(_authenticate)``), then require the
    resolved actor's role to be at least ``min_role`` (403, not 401 — the caller is a real,
    authenticated actor, just not authorized for this action). Returns the actor string, so this
    drops into any route or ``dashboard.add_routes`` slot that already expects
    ``Depends(actor_dep)``.
    """

    def _check(actor: str = Depends(_authenticate)) -> str:
        role = get_settings().role_map.get(actor, "admin")
        if _ROLE_RANK.get(role, -1) < _ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=403,
                detail=f"actor '{actor}' has role '{role}', this action needs '{min_role}'+",
            )
        return actor

    return _check


def tenant_scope(actor: str = Depends(_authenticate)) -> str | None:
    """The authenticated caller's bound tenant, or ``None`` if unscoped (D-097). Used by the
    read routes to add an optional ``tenant_id`` filter — a plain lookup against config already
    resolved during ``_authenticate``, no extra DB round trip."""
    return get_settings().tenant_map.get(actor)


def create_app(require_key: bool = True) -> FastAPI:
    """Build the operator API. Raises if no API key at all is configured (fail-closed)."""
    if require_key and not get_settings().api_key_map:
        raise RuntimeError(
            "ACDE has no api_key/api_keys configured — refusing to start unauthenticated"
        )

    # D-092: FastAPI's own docs_url/redoc_url/openapi_url routes are unauthenticated by
    # construction (framework-level routes, not subject to per-route `dependencies=`) — anyone
    # could read the full API schema with zero credentials. Disabled here, re-added below as
    # regular routes behind the same `auth` every other endpoint uses.
    app = FastAPI(
        title="ACDE Operator API", version="2.2", docs_url=None, redoc_url=None, openapi_url=None
    )

    # D-098: one limiter instance per app (not a module global) -- so tests creating multiple
    # `create_app()`s, and any future multi-app scenario, never share window state.
    app.state.rate_limiter = ratelimit.RateLimiter(get_settings().api_rate_limit_per_minute)

    @app.middleware("http")
    async def rate_limit_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == "/health":  # load-balancer target -- must never 429
            return await call_next(request)
        limiter: ratelimit.RateLimiter = app.state.rate_limiter
        allowed, retry_after = limiter.check(_rate_limit_key(request))
        if not allowed:
            return Response(
                content=json.dumps({"detail": "rate limit exceeded, try again later"}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    auth = [Depends(_authenticate)] if require_key else []
    # In no-auth test mode there's no identity to resolve; fall back to a fixed actor name, full
    # access (no role concept to enforce when auth itself is off).
    actor_dep = _authenticate if require_key else (lambda: "api")
    approver_dep = require_role("approver") if require_key else (lambda: "api")
    admin_dep = require_role("admin") if require_key else (lambda: "api")
    # In no-auth test mode there's no bound tenant to resolve either -- every request is unscoped.
    tenant_scope_dep = tenant_scope if require_key else (lambda: None)

    @app.get("/openapi.json", dependencies=auth, include_in_schema=False)
    def openapi_schema() -> dict[str, Any]:
        return get_openapi(title=app.title, version=app.version, routes=app.routes)

    @app.get("/docs", dependencies=auth, include_in_schema=False)
    def docs() -> Response:
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} — Swagger UI")

    @app.get("/redoc", dependencies=auth, include_in_schema=False)
    def redoc() -> Response:
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} — ReDoc")

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Unauthenticated shallow liveness only (D-087) -- a load balancer's health check must
        work with no credentials, but the full ``doctor()`` report discloses LLM provider,
        connector identity, execution mode, and raw exception fragments that can carry hostnames
        or DSN pieces. That detail moves to the authenticated ``/health/ready``."""
        return {"status": "ok"}

    @app.get("/health/ready", dependencies=auth)
    def health_ready() -> dict[str, Any]:
        """Full deployment readiness report (was ``/health``'s body) -- now behind auth."""
        return doctor()

    @app.get("/metrics", dependencies=auth)
    def metrics_endpoint() -> Response:
        return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")

    @app.get("/proposals", dependencies=auth)
    def proposals(
        limit: int = 50, tenant_id: str | None = Depends(tenant_scope_dep)
    ) -> list[dict[str, Any]]:
        conditions = ["1=1"]
        params: list[Any] = []
        if tenant_id is not None:
            conditions.append("tenant_id = %s")
            params.append(tenant_id)
        params.append(min(limit, 500))
        return db.fetch_all(
            "SELECT agent, action_type, target, policy_decision, executed, outcome, status, ts "
            f"FROM telemetry.agent_actions WHERE {' AND '.join(conditions)} "
            "ORDER BY ts DESC LIMIT %s",
            tuple(params),
        )

    @app.get("/audit", dependencies=auth)
    def audit(
        limit: int = 100,
        since: str | None = None,
        until: str | None = None,
        tenant_id: str | None = Depends(tenant_scope_dep),
    ) -> list[dict[str, Any]]:
        """Audit trail, most recent first. ``since``/``until`` are ISO-8601 timestamps — the actual
        compliance question ("what happened on date X") a `LIMIT`-only query cannot answer."""
        conditions = ["1=1"]
        params: list[Any] = []
        if since:
            conditions.append("ts >= %s")
            params.append(since)
        if until:
            conditions.append("ts <= %s")
            params.append(until)
        if tenant_id is not None:
            conditions.append("tenant_id = %s")
            params.append(tenant_id)
        params.append(min(limit, 1000))
        return db.fetch_all(
            "SELECT agent, action_type, target, policy_decision, policy_reason, executed, "
            "outcome, status, llm_model, ts FROM telemetry.agent_actions "
            f"WHERE {' AND '.join(conditions)} ORDER BY ts DESC LIMIT %s",
            tuple(params),
        )

    @app.get("/audit/export", dependencies=auth)
    def audit_export(
        since: str | None = None,
        until: str | None = None,
        export_format: str = Query("csv", alias="format", pattern="^(csv|json)$"),
        tenant_id: str | None = Depends(tenant_scope_dep),
    ) -> Response:
        """The full audit trail matching the same ``since``/``until`` filters as ``/audit`` — no
        row cap, unlike that endpoint. CSV (default) streams in bounded batches; JSON collects the
        same paginated query into one response (still uncapped, just not memory-bounded)."""
        rows = _audit_rows_paginated(since, until, tenant_id)
        if export_format == "json":
            return Response(
                content=json.dumps(list(rows), default=str),
                media_type="application/json",
            )

        def _csv_chunks() -> Iterator[str]:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS)
            writer.writeheader()
            yield buf.getvalue()
            for row in rows:
                buf.seek(0)
                buf.truncate(0)
                writer.writerow(row)
                yield buf.getvalue()

        return StreamingResponse(
            _csv_chunks(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=acde_audit_export.csv"},
        )

    @app.get("/costs", dependencies=auth)
    def costs(
        since_hours: float = 24.0, tenant_id: str | None = Depends(tenant_scope_dep)
    ) -> list[dict[str, float | str]]:
        """Per-tenant cost + LLM token breakdown over the trailing window (D-095). Restricted to
        the caller's own tenant when they're bound to one (D-097)."""
        return cost.costs_by_tenant(since_hours=since_hours, tenant_id=tenant_id)

    @app.get("/compliance-report", dependencies=auth)
    def compliance_report_endpoint(
        since_hours: float = 720.0, tenant_id: str | None = Depends(tenant_scope_dep)
    ) -> dict[str, Any]:
        """Compliance/audit evidence report (D-096): policy verdict distribution, incident
        count + MTTR, and a point-in-time availability check. Restricted to the caller's own
        tenant when they're bound to one (D-097); availability stays global (see that report's
        own docstring)."""
        return compliance_report(since_hours=since_hours, tenant_id=tenant_id)

    @app.post("/tenants")
    def create_tenant_route(
        tenant_id: str, display_name: str, actor: str = Depends(admin_dep)
    ) -> dict[str, Any]:
        """Admin-provisioned tenant creation (D-097) -- no public signup."""
        try:
            tenant = tenancy.create_tenant(tenant_id, display_name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        log.info("tenant_created", extra={"tenant_id": tenant_id, "actor": actor})
        return tenant

    @app.get("/tenants")
    def list_tenants_route(_actor: str = Depends(admin_dep)) -> list[dict[str, Any]]:
        return tenancy.list_tenants()

    @app.post("/tenants/{tenant_id}/suspend")
    def suspend_tenant_route(tenant_id: str, actor: str = Depends(admin_dep)) -> dict[str, Any]:
        try:
            tenant = tenancy.set_tenant_status(tenant_id, "suspended")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        log.info("tenant_suspended", extra={"tenant_id": tenant_id, "actor": actor})
        return tenant

    @app.post("/tenants/{tenant_id}/activate")
    def activate_tenant_route(tenant_id: str, actor: str = Depends(admin_dep)) -> dict[str, Any]:
        try:
            tenant = tenancy.set_tenant_status(tenant_id, "active")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        log.info("tenant_activated", extra={"tenant_id": tenant_id, "actor": actor})
        return tenant

    @app.get("/approvals", dependencies=auth)
    def list_approvals() -> list[dict[str, Any]]:
        return approvals.list_pending()

    @app.post("/approvals/{approval_id}/approve")
    def approve(approval_id: int, actor: str = Depends(approver_dep)) -> dict[str, Any]:
        return approvals.approve(approval_id, actor=actor)

    @app.post("/approvals/{approval_id}/reject")
    def reject(
        approval_id: int, note: str = "", actor: str = Depends(approver_dep)
    ) -> dict[str, Any]:
        return approvals.reject(approval_id, actor=actor, note=note)

    dashboard.add_routes(app, actor_dep, approver_dep)
    return app


def main() -> None:  # pragma: no cover - server entrypoint
    import uvicorn

    s = get_settings()
    uvicorn.run(create_app(), host=s.api_host, port=s.api_port)


if __name__ == "__main__":  # pragma: no cover
    main()
