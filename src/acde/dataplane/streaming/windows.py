"""Tumbling-window aggregation (pure logic, no I/O).

Assigns events to fixed-width tumbling windows by event time, accumulates count/sum, and
flushes windows once a watermark passes their end. ``event_ts`` is the max event time seen
in a window; ``materialized_ts`` is stamped by the caller at flush time. Freshness (§5.4)
is then ``materialized_ts - event_ts``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


def window_start(event_ts: dt.datetime, width_s: float) -> dt.datetime:
    """Floor ``event_ts`` to the start of its tumbling window."""
    epoch = event_ts.timestamp()
    floored = (int(epoch) // int(width_s)) * int(width_s)
    return dt.datetime.fromtimestamp(floored, tz=dt.UTC)


@dataclass
class WindowState:
    """Accumulator for one (key, window) cell."""

    key: str
    window_start: dt.datetime
    window_end: dt.datetime
    count: int = 0
    sum_value: float = 0.0
    event_ts: dt.datetime | None = None  # max event time observed

    def add(self, event_ts: dt.datetime, value: float) -> None:
        self.count += 1
        self.sum_value += value
        if self.event_ts is None or event_ts > self.event_ts:
            self.event_ts = event_ts


@dataclass
class WindowAggregator:
    """Accumulates events into tumbling windows and flushes completed ones."""

    width_s: float = 60.0
    _cells: dict[tuple[str, dt.datetime], WindowState] = field(default_factory=dict)

    def add(self, key: str, event_ts: dt.datetime, value: float) -> None:
        start = window_start(event_ts, self.width_s)
        cell_key = (key, start)
        cell = self._cells.get(cell_key)
        if cell is None:
            cell = WindowState(
                key=key,
                window_start=start,
                window_end=start + dt.timedelta(seconds=self.width_s),
            )
            self._cells[cell_key] = cell
        cell.add(event_ts, value)

    def flush(self, watermark: dt.datetime) -> list[WindowState]:
        """Remove and return windows whose end is at or before ``watermark`` (sorted)."""
        done = [cell for cell in self._cells.values() if cell.window_end <= watermark]
        for cell in done:
            del self._cells[(cell.key, cell.window_start)]
        return sorted(done, key=lambda c: (c.window_start, c.key))

    def flush_all(self) -> list[WindowState]:
        """Remove and return every open window (end-of-session drain)."""
        done = sorted(self._cells.values(), key=lambda c: (c.window_start, c.key))
        self._cells.clear()
        return done

    def open_windows(self) -> int:
        return len(self._cells)
