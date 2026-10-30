"""Unit tests for the baseline human-resolution responder (mocked db)."""

import datetime as dt
from unittest.mock import MagicMock

from acde.config import get_settings
from acde.experiments import baseline
from acde.human.simulator import sample_latency

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def _fault(event_id, offset_s=0.0, resolved=None):
    ts = NOW + dt.timedelta(seconds=offset_s)
    return {"event_id": event_id, "injected_ts": ts, "detected_ts": ts, "resolved_ts": resolved}


def _latency(seed, ordinal):
    s = get_settings()
    return sample_latency(seed, ordinal, s.human_latency_median_s, s.human_latency_sigma)


def test_unpaged_faults_are_paged_at_detection_and_resolved(monkeypatch):
    fake_db = MagicMock()
    fake_db.fetch_all.return_value = [_fault("e1"), _fault("e2", 10)]
    # per fault: no escalation filed yet -> the INSERT ... RETURNING page
    fake_db.fetch_one.side_effect = [
        None,
        {"id": 1, "requested_ts": NOW},
        None,
        {"id": 2, "requested_ts": NOW + dt.timedelta(seconds=10)},
    ]
    monkeypatch.setattr(baseline, "db", fake_db)

    assert baseline.resolve_via_human("run-1", seed=42) == 2
    sqls = [c.args[0] for c in fake_db.execute.call_args_list]
    assert any("detected_ts = COALESCE(detected_ts, injected_ts)" in s for s in sqls)
    inserts = [c.args[0] for c in fake_db.fetch_one.call_args_list if "INSERT" in c.args[0]]
    assert len(inserts) == 2  # one page per fault
    resolved = [
        c.args[1] for c in fake_db.execute.call_args_list if "resolution = 'human'" in c.args[0]
    ]
    assert resolved[0] == (NOW + dt.timedelta(seconds=_latency(42, 0)), "e1")


def test_repeated_escalations_get_one_human_draw(monkeypatch):
    # An agent escalated six times; v1 drew six delays and kept the fastest (D-106).
    fake_db = MagicMock()
    fake_db.fetch_all.return_value = [_fault("e1")]
    page = NOW + dt.timedelta(seconds=4)
    fake_db.fetch_one.side_effect = [{"id": 7, "requested_ts": page}]
    monkeypatch.setattr(baseline, "db", fake_db)

    baseline.resolve_via_human("run-1", seed=5)
    completed = page + dt.timedelta(seconds=_latency(5, 0))
    calls = {c.args[0]: c.args[1] for c in fake_db.execute.call_args_list}
    first = next(v for k, v in calls.items() if k.endswith("WHERE id = %s"))
    assert first == (_latency(5, 0), completed, 7)
    repages = next(v for k, v in calls.items() if "requested_ts <= %s" in k)
    assert repages[0] == completed  # duplicates closed by the same human action
    assert not any("INSERT" in c.args[0] for c in fake_db.fetch_one.call_args_list)


def test_ordinal_counts_faults_an_agent_already_resolved(monkeypatch):
    # The second fault keeps ordinal 1 even though the first is already resolved, so a paired run
    # in which no agent acted draws the same delay for it.
    fake_db = MagicMock()
    fake_db.fetch_all.return_value = [_fault("e1", resolved=NOW), _fault("e2", 10)]
    page = NOW + dt.timedelta(seconds=10)
    fake_db.fetch_one.side_effect = [{"id": 3, "requested_ts": page}]
    monkeypatch.setattr(baseline, "db", fake_db)

    assert baseline.resolve_via_human("run-1", seed=9) == 1
    resolved = [
        c.args[1] for c in fake_db.execute.call_args_list if "resolution = 'human'" in c.args[0]
    ]
    assert resolved == [(page + dt.timedelta(seconds=_latency(9, 1)), "e2")]


def test_paired_seed_gives_the_same_draw():
    assert _latency(123, 0) == _latency(123, 0)
    assert _latency(123, 0) != _latency(124, 0)


def test_resolve_via_human_no_open_faults(monkeypatch):
    fake_db = MagicMock()
    fake_db.fetch_all.return_value = []  # nothing open
    monkeypatch.setattr(baseline, "db", fake_db)
    assert baseline.resolve_via_human("run-1", seed=1) == 0
