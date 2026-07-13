"""Unit tests for tumbling-window aggregation."""

import datetime as dt

from acde.dataplane.streaming.windows import WindowAggregator, window_start

UTC = dt.UTC


def ts(minute: int, second: int = 0) -> dt.datetime:
    return dt.datetime(2026, 1, 1, 12, minute, second, tzinfo=UTC)


class TestWindowStart:
    def test_floors_to_window(self):
        assert window_start(ts(3, 45), 60.0) == ts(3, 0)
        assert window_start(ts(3, 0), 60.0) == ts(3, 0)

    def test_wider_window(self):
        assert window_start(ts(7, 30), 300.0) == ts(5, 0)


class TestAggregator:
    def test_events_accumulate_into_windows(self):
        agg = WindowAggregator(width_s=60.0)
        agg.add("k", ts(0, 5), 10.0)
        agg.add("k", ts(0, 50), 5.0)
        agg.add("k", ts(1, 5), 2.0)
        assert agg.open_windows() == 2

    def test_flush_returns_completed_windows_only(self):
        agg = WindowAggregator(width_s=60.0)
        agg.add("k", ts(0, 10), 10.0)
        agg.add("k", ts(1, 10), 3.0)
        done = agg.flush(watermark=ts(1, 0))  # first window (ends 12:01) is complete
        assert len(done) == 1
        cell = done[0]
        assert cell.window_start == ts(0, 0)
        assert cell.count == 1
        assert cell.sum_value == 10.0
        assert cell.event_ts == ts(0, 10)
        assert agg.open_windows() == 1  # second window still open

    def test_event_ts_is_max_in_window(self):
        agg = WindowAggregator(width_s=60.0)
        agg.add("k", ts(0, 10), 1.0)
        agg.add("k", ts(0, 40), 1.0)
        agg.add("k", ts(0, 25), 1.0)
        [cell] = agg.flush_all()
        assert cell.event_ts == ts(0, 40)
        assert cell.count == 3
        assert cell.sum_value == 3.0

    def test_separate_keys_separate_windows(self):
        agg = WindowAggregator(width_s=60.0)
        agg.add("a", ts(0, 10), 1.0)
        agg.add("b", ts(0, 20), 2.0)
        assert agg.open_windows() == 2
        cells = agg.flush_all()
        assert {c.key for c in cells} == {"a", "b"}

    def test_flush_all_drains_everything(self):
        agg = WindowAggregator(width_s=60.0)
        agg.add("k", ts(0, 10), 1.0)
        agg.add("k", ts(5, 10), 1.0)
        assert len(agg.flush_all()) == 2
        assert agg.open_windows() == 0
