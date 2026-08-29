"""PagerDuty Events API v2 dispatch (D-101) -- fires alongside (or instead of) the generic/Slack
webhook in ``notify/webhook.py``. Same fire-and-forget-on-a-daemon-thread philosophy: a slow or
down PagerDuty endpoint must never block or crash the control loop.

``shadow_proposal`` is never sent here regardless of ``Settings.webhook_event_set`` -- a
shadow-mode "here's what I would have done" log entry is informational, not something a human
should be paged for. Trigger-only in this pass: no matching "resolve" call site exists yet to
close a PagerDuty incident automatically when the underlying issue clears, so incidents raised
here need manual acknowledgement/resolution in PagerDuty -- a stated limitation, not a silent gap.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import httpx

from acde.config import get_settings
from acde.logging import get_logger

if TYPE_CHECKING:
    from acde.contracts import PolicyDecision, ProposedAction

log = get_logger("notify.pagerduty")

_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

# PagerDuty's own severity vocabulary (critical/error/warning/info) -- escalation/execution
# failures need eyes now; a pending approval is real but lower urgency.
_SEVERITY = {
    "pending_approval": "warning",
    "escalation": "critical",
    "execution_failure": "error",
}

_NEVER_PAGE = frozenset({"shadow_proposal"})


def build_event(
    routing_key: str,
    event: str,
    action: ProposedAction,
    decision: PolicyDecision,
    experiment_run: str,
) -> dict[str, Any]:
    """PagerDuty Events API v2 trigger payload. Never includes action ``params`` (may hold data
    refs) -- same redaction rule ``webhook.build_payload`` already follows."""
    verdict = "escalate" if decision.escalate else ("allow" if decision.allowed else "deny")
    summary = (
        f"ACDE {event.replace('_', ' ')}: {action.agent} proposes {action.action_type} on "
        f"{action.target} (verdict: {verdict})"
    )
    return {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": str(action.action_id),
        "payload": {
            "summary": summary[:1024],  # PagerDuty's own summary length cap
            "severity": _SEVERITY.get(event, "warning"),
            "source": experiment_run,
            "custom_details": {
                "agent": action.agent,
                "action_type": action.action_type,
                "target": action.target,
                "confidence": action.confidence,
                "policy_verdict": verdict,
                "policy_reason": decision.reason,
                "justification": action.justification,
            },
        },
    }


def _post(payload: dict[str, Any], timeout: float) -> None:  # pragma: no cover - network
    try:
        httpx.post(_EVENTS_URL, json=payload, timeout=timeout).raise_for_status()
    except Exception as exc:  # never propagate — notifications must not break the loop
        log.warning("pagerduty_delivery_failed", extra={"error": str(exc)[:120]})


def send(event: str, action: ProposedAction, decision: PolicyDecision, experiment_run: str) -> bool:
    """Queue a PagerDuty trigger if configured and this event pages. Returns whether it was sent."""
    settings = get_settings()
    routing_key = settings.pagerduty_routing_key.get_secret_value()
    if not routing_key or event in _NEVER_PAGE:
        return False
    payload = build_event(routing_key, event, action, decision, experiment_run)
    threading.Thread(
        target=_post,
        args=(payload, settings.webhook_timeout_s),
        daemon=True,
    ).start()
    log.info("pagerduty_queued", extra={"event": event, "experiment_run": experiment_run})
    return True
