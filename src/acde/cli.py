"""`acde` command-line interface for operators (v2, P3).

Subcommands: ``run`` (control loop), ``serve`` (operator API), ``status``, ``doctor``,
``approvals list|approve|reject``, ``pause``/``resume``. The ``run`` entrypoint is **shadow-safe by
default**: if ``ACDE_MODE`` is not set in the environment it forces shadow mode and warns, so a
company can never accidentally start ACDE acting on their pipelines.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from acde.logging import get_logger

log = get_logger("cli")


def _print_checks(result: dict[str, Any]) -> int:
    for c in result["checks"]:
        mark = "OK  " if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']:20} {c['detail']}")
    print(f"all_ok: {result['all_ok']}")
    return 0 if result["all_ok"] else 1


def cmd_doctor(_: argparse.Namespace) -> int:
    from acde.ops.health import doctor

    return _print_checks(doctor())


def cmd_status(_: argparse.Namespace) -> int:
    from acde import db
    from acde.config import get_settings
    from acde.orchestrator import control

    s = get_settings()
    pending = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.action_approvals WHERE status='pending'"
    )
    total = db.fetch_one("SELECT count(*) AS n FROM telemetry.agent_actions")
    print(f"mode:            {s.acde_mode}")
    print(f"paused:          {control.is_paused()}")
    print(f"connector:       {s.connector_kind}")
    print(f"pending approvals: {pending['n'] if pending else 0}")
    print(f"actions logged:  {total['n'] if total else 0}")
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    from acde.orchestrator import control

    control.set_paused(True, actor=args.actor)
    print("ACDE paused — the loop will take no actions until resumed.")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    from acde.orchestrator import control

    control.set_paused(False, actor=args.actor)
    print("ACDE resumed.")
    return 0


def cmd_approvals(args: argparse.Namespace) -> int:
    from acde.human import approvals

    if args.action == "list":
        for a in approvals.list_pending():
            print(
                f"  #{a['approval_id']}  {a['agent']}/{a['action_type']} on {a['target']}  "
                f"— {a['justification']}"
            )
        return 0
    if args.action == "approve":
        print(approvals.approve(args.id, actor=args.actor))
        return 0
    if args.action == "reject":
        print(approvals.reject(args.id, actor=args.actor, note=args.note))
        return 0
    return 2


def cmd_report(args: argparse.Namespace) -> int:
    import json

    from acde.ops.roi import roi_report

    print(json.dumps(roi_report(since_hours=args.since_hours), indent=2))
    return 0


def cmd_gameday(args: argparse.Namespace) -> int:
    import json

    from acde.ops.gameday import run_gameday

    try:
        report = run_gameday(args.scenario, env=args.env, force=args.force)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_run(args: argparse.Namespace) -> int:  # pragma: no cover - long-running loop
    import asyncio

    from acde.orchestrator.loop import ControlLoop

    if not os.environ.get("ACDE_MODE"):
        os.environ["ACDE_MODE"] = "shadow"
        from acde.config import get_settings

        get_settings.cache_clear()
        log.warning("acde_mode_defaulted_to_shadow")
        print("WARNING: ACDE_MODE not set — defaulting to SHADOW (no pipeline side effects).")
    asyncio.run(ControlLoop(experiment_run=args.env, config=args.config).run(args.duration))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:  # pragma: no cover - server
    import uvicorn

    from acde.config import get_settings
    from acde.server import create_app

    s = get_settings()
    uvicorn.run(create_app(), host=args.host or s.api_host, port=args.port or s.api_port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="acde", description="ACDE — agentic pipeline governance")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="validate the deployment").set_defaults(func=cmd_doctor)
    sub.add_parser("status", help="current mode / pause / counts").set_defaults(func=cmd_status)

    run = sub.add_parser("run", help="run the control loop (shadow-safe by default)")
    run.add_argument("--env", default="prod", help="environment tag for telemetry")
    run.add_argument("--config", default="full")
    run.add_argument("--duration", type=float, default=86400.0)
    run.set_defaults(func=cmd_run)

    serve = sub.add_parser("serve", help="run the operator API")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    for name in ("pause", "resume"):
        sp = sub.add_parser(name, help=f"{name} the loop (kill switch)")
        sp.add_argument("--actor", default="operator")
        sp.set_defaults(func=cmd_pause if name == "pause" else cmd_resume)

    rp = sub.add_parser("report", help="ROI report from the audit trail")
    rp.add_argument("--since-hours", type=float, default=720.0)
    rp.set_defaults(func=cmd_report)

    gd = sub.add_parser("gameday", help="rehearse an incident in staging (research extra)")
    gd.add_argument("--scenario", required=True)
    gd.add_argument("--env", default="staging")
    gd.add_argument("--force", action="store_true", help="allow against a production connector")
    gd.set_defaults(func=cmd_gameday)

    ap = sub.add_parser("approvals", help="human approval queue")
    ap.add_argument("action", choices=["list", "approve", "reject"])
    ap.add_argument("id", nargs="?", type=int, default=0)
    ap.add_argument("--actor", default="operator")
    ap.add_argument("--note", default="")
    ap.set_defaults(func=cmd_approvals)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
