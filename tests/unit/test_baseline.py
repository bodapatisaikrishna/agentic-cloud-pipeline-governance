"""Unit tests for the baseline human-resolution responder (mocked db + HumanSimulator)."""

import datetime as dt
from unittest.mock import MagicMock

from acde.experiments import baseline

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def test_resolve_via_human_stamps_and_resolves(monkeypatch):
    fake_db = MagicMock()
    # open faults (2), then completed interventions (2) for back-fill
    fake_db.fetch_all.side_effect = [
        [{"event_id": "e1", "detected_ts": NOW}, {"event_id": "e2", "detected_ts": NOW}],
        [
            {"completed_ts": NOW + dt.timedelta(seconds=360)},
            {"completed_ts": NOW + dt.timedelta(seconds=400)},
        ],
    ]
    monkeypatch.setattr(baseline, "db", fake_db)

    fake_sim = MagicMock()
    monkeypatch.setattr(baseline, "HumanSimulator", lambda **k: fake_sim)

    resolved = baseline.resolve_via_human("run-1", seed=42)
    assert resolved == 2
    sqls = [c.args[0] for c in fake_db.execute.call_args_list]
    assert any(
        "detected_ts = COALESCE(detected_ts, injected_ts)" in s for s in sqls
    )  # fixed monitor
    assert any("manual_interventions" in s for s in sqls)  # escalations created
    assert any("resolved_ts = %s" in s for s in sqls)  # back-filled
    fake_sim.assign_latencies.assert_called_once()
    fake_sim.resolve_due.assert_called_once()


def test_resolve_via_human_no_open_faults(monkeypatch):
    fake_db = MagicMock()
    fake_db.fetch_all.return_value = []  # nothing open
    monkeypatch.setattr(baseline, "db", fake_db)
    assert baseline.resolve_via_human("run-1", seed=1) == 0
