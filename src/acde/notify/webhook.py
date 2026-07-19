"""Outbound operator notifications via a generic JSON webhook (Slack-compatible payload) — P1.

Fired when a proposal is shadowed, an action is pending approval, an escalation happens, or an
execution fails. Delivery is **fire-and-forget on a daemon thread** so a slow or down webhook never
blocks or crashes the control loop (mirrors the gate/executor fail-safe philosophy). Action `params`
are redacted by default — only the summary fields leave the process.

Config (`acde.config`): ``webhook_url`` (empty disables), ``webhook_events`` (CSV filter),
``webhook_timeout_s``. The payload uses Slack's ``{"text": ...}`` shape plus a structured
``attachments``/``acde`` block so it also works with any generic JSON receiver.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import httpx

from acde.config import get_settings
from acde.logging import get_logger

if TYPE_CHECKING:
    from acde.contracts import PolicyDecision, ProposedAction

log = get_logger("notify.webhook")

_EMOJI = {
    "shadow_proposal": ":eyes:",
    "pending_approval": ":hourglass_flowing_sand:",
    "escalation": ":rotating_light:",
    "execution_failure": ":x:",
}


def build_payload(
    event: str,
    action: ProposedAction,
    decision: PolicyDecision,
    experiment_run: str,
    **extra: Any,
) -> dict[str, Any]:
    """Redacted, Slack-compatible payload. Never includes action ``params`` (may hold data refs)."""
    emoji = _EMOJI.get(event, ":robot_face:")
    verdict = "escalate" if decision.escalate else ("allow" if decision.allowed else "deny")
    text = (
        f"{emoji} ACDE {event.replace('_', ' ')}: *{action.agent}* proposes "
        f"`{action.action_type}` on `{action.target}` (verdict: {verdict}) — {action.justification}"
    )
    body = {
        "text": text,
        "acde": {
            "event": event,
            "environment": experiment_run,
            "agent": action.agent,
            "action_type": action.action_type,
            "target": action.target,
            "confidence": action.confidence,
            "policy_verdict": verdict,
            "policy_reason": decision.reason,
            **extra,
        },
    }
    return body


def _post(url: str, payload: dict[str, Any], timeout: float) -> None:  # pragma: no cover - network
    try:
        httpx.post(url, json=payload, timeout=timeout).raise_for_status()
    except Exception as exc:  # never propagate — notifications must not break the loop
        log.warning(
            "webhook_delivery_failed",
            extra={"event": payload.get("acde", {}).get("event"), "error": str(exc)[:120]},
        )


def notify(
    event: str,
    action: ProposedAction,
    decision: PolicyDecision,
    experiment_run: str,
    **extra: Any,
) -> bool:
    """Queue a notification if configured and this event is enabled. Returns whether it was sent."""
    settings = get_settings()
    if not settings.webhook_url or event not in settings.webhook_event_set:
        return False
    payload = build_payload(event, action, decision, experiment_run, **extra)
    threading.Thread(
        target=_post,
        args=(settings.webhook_url, payload, settings.webhook_timeout_s),
        daemon=True,
    ).start()
    log.info("webhook_queued", extra={"event": event, "experiment_run": experiment_run})
    return True
