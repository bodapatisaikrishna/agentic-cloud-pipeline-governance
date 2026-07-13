"""Unit tests for the seeded streaming producer generator."""

import datetime as dt

from acde.dataplane.streaming import producer

START = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class TestGenerateEvents:
    def test_deterministic_for_seed(self):
        a = producer.generate_events(seed=11, n=200, start=START)
        b = producer.generate_events(seed=11, n=200, start=START)
        assert a == b

    def test_different_seed_differs(self):
        a = producer.generate_events(seed=1, n=200, start=START)
        b = producer.generate_events(seed=2, n=200, start=START)
        assert a != b

    def test_record_shape_and_count(self):
        recs = producer.generate_events(seed=3, n=50, start=START)
        assert len(recs) == 50
        assert set(recs[0]) == {"event_ts", "key", "value"}
        assert all(r["key"] in producer._KEYS for r in recs)

    def test_timestamps_monotonic_nondecreasing(self):
        recs = producer.generate_events(seed=4, n=100, start=START)
        times = [dt.datetime.fromisoformat(r["event_ts"]) for r in recs]
        assert times == sorted(times)
        assert times[0] >= START

    def test_rebase_to_end_makes_events_non_future(self):
        end = dt.datetime(2026, 6, 1, 12, 0, tzinfo=dt.UTC)
        recs = producer.generate_events(seed=7, n=200, start=START)
        rebased = producer.rebase_to_end(recs, end)
        times = [dt.datetime.fromisoformat(r["event_ts"]) for r in rebased]
        assert max(times) == end  # latest event lands exactly at the anchor
        assert all(t <= end for t in times)  # nothing in the future
        # relative spacing is preserved (only shifted)
        assert rebased[0]["key"] == recs[0]["key"]

    def test_rebase_empty_is_noop(self):
        assert producer.rebase_to_end([], dt.datetime.now(dt.UTC)) == []

    def test_bursts_compress_gaps(self):
        # With bursts enabled, span is shorter than a purely base-rate stream of equal size.
        bursty = producer.generate_events(seed=5, n=500, start=START, burst_frac=0.5)
        calm = producer.generate_events(seed=5, n=500, start=START, burst_frac=0.0)
        span_bursty = dt.datetime.fromisoformat(bursty[-1]["event_ts"]) - START
        span_calm = dt.datetime.fromisoformat(calm[-1]["event_ts"]) - START
        assert span_bursty < span_calm
