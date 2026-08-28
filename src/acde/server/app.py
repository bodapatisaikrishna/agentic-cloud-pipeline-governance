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
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from secrets import compare_digest
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from acde import db
from acde.config import get_settings
from acde.human import approvals
from acde.logging import get_logger
from acde.ops.health import doctor
from acde.server import dashboard, metrics
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
                return actor
    elif basic is not None:
        expected = key_map.get(basic.username)
        if expected is not None and compare_digest(basic.password.encode(), expected.encode()):
            return basic.username
    raise HTTPException(
        status_code=401,
        detail="invalid or missing credentials (X-API-Key header or HTTP Basic)",
        headers={"WWW-Authenticate": "Basic"},
    )


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
    since: str | None, until: str | None, batch_size: int = _EXPORT_BATCH_SIZE
) -> Iterator[dict[str, Any]]:
    """Every matching audit row, oldest first, fetched in bounded batches (D-094) — unlike
    ``/audit``'s ``LIMIT``, this is a genuine full export: a keyset cursor on ``(ts, action_id)``
    (a plain ``OFFSET`` degrades on a large table, and ``ts`` alone isn't a unique tiebreaker)
    means memory stays bounded to one batch at a time regardless of how large the result is.
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if since:
        conditions.append("ts >= %s")
        params.append(since)
    if until:
        conditions.append("ts <= %s")
        params.append(until)
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
    auth = [Depends(_authenticate)] if require_key else []
    # In no-auth test mode there's no identity to resolve; fall back to a fixed actor name, full
    # access (no role concept to enforce when auth itself is off).
    actor_dep = _authenticate if require_key else (lambda: "api")
    approver_dep = require_role("approver") if require_key else (lambda: "api")

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
    def proposals(limit: int = 50) -> list[dict[str, Any]]:
        return db.fetch_all(
            "SELECT agent, action_type, target, policy_decision, executed, outcome, status, ts "
            "FROM telemetry.agent_actions ORDER BY ts DESC LIMIT %s",
            (min(limit, 500),),
        )

    @app.get("/audit", dependencies=auth)
    def audit(
        limit: int = 100, since: str | None = None, until: str | None = None
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
    ) -> Response:
        """The full audit trail matching the same ``since``/``until`` filters as ``/audit`` — no
        row cap, unlike that endpoint. CSV (default) streams in bounded batches; JSON collects the
        same paginated query into one response (still uncapped, just not memory-bounded)."""
        rows = _audit_rows_paginated(since, until)
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
    def costs(since_hours: float = 24.0) -> list[dict[str, float | str]]:
        """Per-tenant cost + LLM token breakdown over the trailing window (D-095)."""
        return cost.costs_by_tenant(since_hours=since_hours)

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
