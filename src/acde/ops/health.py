"""`acde doctor`: validate the whole deployment before it runs (P2).

Checks each dependency an operator must get right — database, policy engine, orchestrator connector,
LLM provider config, notifications, and the execution mode — and returns actionable results. This is
the "attach in 30 minutes" experience: run it, fix what's red, start the loop.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("ops.health")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _check_db() -> Check:
    try:
        from acde import db

        db.fetch_one("SELECT 1 AS ok")
        return Check("database", True, "reachable")
    except Exception as exc:
        return Check("database", False, str(exc)[:120])


def _check_opa() -> Check:
    s = get_settings()
    try:
        with urllib.request.urlopen(f"{s.opa_url}/health", timeout=5) as r:
            return Check("opa", r.status == 200, f"HTTP {r.status}")
    except Exception as exc:
        return Check("opa", False, str(exc)[:120])


def _check_connector() -> Check:
    try:
        from acde.connectors import get_connector

        h = get_connector().health()
        detail = h.detail + ("" if h.can_act else " (observe-only)")
        return Check(f"connector:{h.name}", h.ok, detail)
    except Exception as exc:
        return Check("connector", False, str(exc)[:120])


def _check_llm() -> Check:
    s = get_settings()
    if s.mock_llm:
        return Check("llm", True, "MOCK_LLM (no provider needed)")
    keys = {
        "anthropic": s.anthropic_api_key,
        "gemini": s.gemini_api_key,
        "openai_compatible": s.oai_api_key,
    }
    key = keys.get(s.llm_provider, "")
    return Check("llm", bool(key), f"provider={s.llm_provider}, key {'set' if key else 'MISSING'}")


def _check_mode() -> Check:
    s = get_settings()
    # autonomous on prod is legal but worth flagging; shadow/approval are always fine.
    warn = s.acde_mode == "autonomous"
    return Check(
        "mode", True, f"{s.acde_mode}" + (" (executes actions — verify policies!)" if warn else "")
    )


def _check_webhook() -> Check:
    s = get_settings()
    return Check(
        "notifications",
        True,
        f"webhook {'configured' if s.webhook_url else 'disabled'}; events={s.webhook_events}",
    )


def doctor() -> dict[str, object]:
    """Run all checks; return {checks, all_ok}."""
    checks = [
        _check_db(),
        _check_opa(),
        _check_connector(),
        _check_llm(),
        _check_mode(),
        _check_webhook(),
    ]
    all_ok = all(c.ok for c in checks)
    for c in checks:
        log.info("doctor_check", extra={"check": c.name, "ok": c.ok, "detail": c.detail})
    return {"checks": [c.__dict__ for c in checks], "all_ok": all_ok}
