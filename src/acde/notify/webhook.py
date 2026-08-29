"""Outbound operator notifications via a generic JSON webhook (Slack-compatible payload) — P1.
D-101 adds Slack Block Kit rich formatting and a PagerDuty dispatch alongside it.

Fired when a proposal is shadowed, an action is pending approval, an escalation happens, or an
execution fails. Delivery is **fire-and-forget on a daemon thread** so a slow or down webhook never
blocks or crashes the control loop (mirrors the gate/executor fail-safe philosophy). Action `params`
are redacted by default — only the summary fields leave the process.

Config (`acde.config`): ``webhook_url`` (empty disables), ``webhook_events`` (CSV filter, shared
with the PagerDuty dispatch below so an operator configures event routing once for both
destinations), ``webhook_timeout_s``. The payload uses Slack's ``{"text": ...}`` shape plus a
structured ``attachments``/``acde`` block so it also works with any generic JSON receiver — the
D-101 ``attachments`` addition is purely additive, so an existing generic receiver reading only
``text``/``acde`` is unaffected.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import httpx

from acde.config import get_settings
from acde.logging import get_logger
from acde.notify import pagerduty

if TYPE_CHECKING:
    from acde.contracts import PolicyDecision, ProposedAction

log = get_logger("notify.webhook")

_EMOJI = {
    "shadow_proposal": ":eyes:",
    "pending_approval": ":hourglass_flowing_sand:",
    "escalation": ":rotating_light:",
    "execution_failure": ":x:",
}

# D-101: Slack attachment sidebar color by event severity -- grey for informational (shadow mode
# took no real action), amber for "needs a human," red for "needs a human now."
_COLOR = {
    "shadow_proposal": "#868686",
    "pending_approval": "#ECB22E",
    "escalation": "#E01E5A",
    "execution_failure": "#E01E5A",
}


def build_payload(
    event: str,
    action: ProposedAction,
    decision: PolicyDecision,
    experiment_run: str,
    **extra: Any,
) -> dict[str, Any]:
    """Redacted, Slack-compatible payload. Never includes action ``params`` (may hold data refs).

    D-101: also carries a Slack ``attachments`` block (colored sidebar + Block Kit fields) --
    additive alongside the original ``text``/``acde`` fields, so a generic JSON receiver reading
    only those is unaffected; Slack itself renders the richer ``attachments`` block instead of
    the plain ``text``.
    """
    emoji = _EMOJI.get(event, ":robot_face:")
    verdict = "escalate" if decision.escalate else ("allow" if decision.allowed else "deny")
    text = (
        f"{emoji} ACDE {event.replace('_', ' ')}: *{action.agent}* proposes "
        f"`{action.action_type}` on `{action.target}` (verdict: {verdict}) — {action.justification}"
    )
    body = {
        "text": text,
        "attachments": [
            {
                "color": _COLOR.get(event, "#868686"),
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": text}},
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Agent:*\n{action.agent}"},
                            {"type": "mrkdwn", "text": f"*Action:*\n{action.action_type}"},
                            {"type": "mrkdwn", "text": f"*Target:*\n{action.target}"},
                            {"type": "mrkdwn", "text": f"*Verdict:*\n{verdict}"},
                            {"type": "mrkdwn", "text": f"*Confidence:*\n{action.confidence:.2f}"},
                            {"type": "mrkdwn", "text": f"*Run:*\n{experiment_run}"},
                        ],
                    },
                ],
            }
        ],
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
    """Queue a notification on every configured channel for this event. Returns whether at least
    one channel sent it. D-101: dispatches to the generic/Slack webhook and PagerDuty
    independently -- either, both, or neither may be configured, and each fires on its own
    daemon thread so a slow one never delays the other.
    """
    settings = get_settings()
    if event not in settings.webhook_event_set:
        return False
    sent = False
    if settings.webhook_url:
        payload = build_payload(event, action, decision, experiment_run, **extra)
        threading.Thread(
            target=_post,
            args=(settings.webhook_url, payload, settings.webhook_timeout_s),
            daemon=True,
        ).start()
        log.info("webhook_queued", extra={"event": event, "experiment_run": experiment_run})
        sent = True
    if pagerduty.send(event, action, decision, experiment_run):
        sent = True
    return sent
