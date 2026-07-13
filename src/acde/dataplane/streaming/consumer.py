"""Streaming consumer: windowed aggregation over a live-resizable worker pool.

Orchestration only (integration-verified; excluded from unit coverage). The pure pieces it
composes — :class:`WindowAggregator` and :class:`WorkerPool` — are unit-tested. A background
controller polls ``control.desired_state['streaming.workers']`` and resizes the pool within
[1, 8] live, satisfying the §5.2 ``scale_workers`` action mapping.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys

from acde import db
from acde.config import get_settings
from acde.dataplane.streaming.windows import WindowAggregator, WindowState
from acde.dataplane.streaming.workers import WorkerPool, read_desired_workers
from acde.logging import get_logger

log = get_logger("dataplane.streaming.consumer")


class StreamSession:  # pragma: no cover - integration-verified
    """Runs one bounded streaming-aggregation session."""

    def __init__(self, pipeline_id: str = "stream", experiment_run: str | None = None) -> None:
        settings = get_settings()
        self.pipeline_id = pipeline_id
        self.experiment_run = experiment_run
        self.width_s = settings.stream_window_s
        self.lo = settings.stream_min_workers
        self.hi = settings.stream_max_workers
        self.initial = settings.stream_default_workers
        self.agg = WindowAggregator(width_s=self.width_s)
        self.lock = asyncio.Lock()
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10_000)
        self.max_event_ts: dt.datetime | None = None
        self._stop = asyncio.Event()

    async def _worker(self, index: int, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                rec = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            event_ts = dt.datetime.fromisoformat(rec["event_ts"])
            async with self.lock:
                self.agg.add(rec["key"], event_ts, float(rec["value"]))
                if self.max_event_ts is None or event_ts > self.max_event_ts:
                    self.max_event_ts = event_ts
            self.queue.task_done()

    def _blocking_consume(self, loop: asyncio.AbstractEventLoop) -> None:
        """Own the Kafka consumer entirely within one thread: create, poll, close.

        librdkafka is not happy being poll()ed and close()d from different threads, so the
        whole lifecycle stays here; records cross back to the event loop thread-safely.
        """
        from acde.dataplane.streaming.kafka_io import JsonConsumer

        consumer = JsonConsumer(group_id=f"acde-{self.pipeline_id}")
        try:
            while not self._stop.is_set():
                rec = consumer.poll(1.0)
                if rec is not None:
                    asyncio.run_coroutine_threadsafe(self.queue.put(rec), loop)
        finally:
            consumer.close()

    async def _poll_broker(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._blocking_consume, loop)

    def _write(self, cells: list[WindowState]) -> None:
        for cell in cells:
            db.execute(
                "INSERT INTO warehouse.stream_aggregates "
                "(pipeline_id, agg_key, window_start, window_end, event_count, sum_value, "
                " event_ts, materialized_ts, experiment_run) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s) "
                "ON CONFLICT (pipeline_id, agg_key, window_start, experiment_run) "
                "DO UPDATE SET event_count = EXCLUDED.event_count, sum_value = EXCLUDED.sum_value, "
                "  event_ts = EXCLUDED.event_ts, materialized_ts = now()",
                (
                    self.pipeline_id,
                    cell.key,
                    cell.window_start,
                    cell.window_end,
                    cell.count,
                    round(cell.sum_value, 4),
                    cell.event_ts,
                    self.experiment_run,
                ),
            )

    async def _flusher(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(2.0)
            async with self.lock:
                watermark = self.max_event_ts
                done = self.agg.flush(watermark) if watermark else []
            if done:
                self._write(done)
                log.info(
                    "windows_flushed",
                    extra={"count": len(done), "experiment_run": self.experiment_run},
                )

    async def _controller(self, pool: WorkerPool) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(2.0)
            await pool.resize(read_desired_workers(self.initial))

    async def run(self, duration_s: float) -> None:
        pool = WorkerPool(self._worker, lo=self.lo, hi=self.hi)
        await pool.resize(self.initial)
        broker = asyncio.ensure_future(self._poll_broker())
        flusher = asyncio.ensure_future(self._flusher())
        controller = asyncio.ensure_future(self._controller(pool))
        log.info(
            "stream_session_started",
            extra={"duration_s": duration_s, "experiment_run": self.experiment_run},
        )
        try:
            await asyncio.sleep(duration_s)
        finally:
            self._stop.set()
            await pool.shutdown()
            # Let the broker thread finish its current poll and close the consumer cleanly
            # (no in-flight poll during close), then stop the periodic tasks.
            try:
                await asyncio.wait_for(broker, timeout=6)
            except (TimeoutError, asyncio.CancelledError):  # pragma: no cover - defensive
                broker.cancel()
            flusher.cancel()
            controller.cancel()
            async with self.lock:
                remaining = self.agg.flush_all()
            if remaining:
                self._write(remaining)
            log.info("stream_session_stopped", extra={"experiment_run": self.experiment_run})


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE streaming consumer")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--pipeline-id", default="stream")
    parser.add_argument("--experiment-run", default=None)
    args = parser.parse_args()
    session = StreamSession(pipeline_id=args.pipeline_id, experiment_run=args.experiment_run)
    asyncio.run(session.run(args.duration))
    # librdkafka's background threads can segfault during interpreter teardown even after a
    # clean close(); the session's work (flushes, DB writes) is already durable here, so exit
    # immediately to skip the problematic GC/atexit path.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
