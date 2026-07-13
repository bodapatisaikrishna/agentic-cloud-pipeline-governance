"""Thin confluent-kafka wrappers (lazy import so pure logic tests need no librdkafka).

Records are JSON objects: ``{"event_ts": <iso8601>, "key": <str>, "value": <float>}``.
"""

from __future__ import annotations

import json
from typing import Any

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("dataplane.streaming.kafka")


class JsonProducer:  # pragma: no cover - requires a broker
    """Produces JSON records to a topic."""

    def __init__(self, bootstrap: str | None = None) -> None:
        from confluent_kafka import Producer

        settings = get_settings()
        self._topic = settings.stream_topic
        self._producer = Producer({"bootstrap.servers": bootstrap or settings.broker_bootstrap})

    def send(self, record: dict[str, Any], key: str | None = None) -> None:
        self._producer.produce(self._topic, key=key, value=json.dumps(record).encode())
        self._producer.poll(0)

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)


class JsonConsumer:  # pragma: no cover - requires a broker
    """Consumes JSON records from a topic."""

    def __init__(self, group_id: str, bootstrap: str | None = None) -> None:
        from confluent_kafka import Consumer

        settings = get_settings()
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap or settings.broker_bootstrap,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
        )
        self._consumer.subscribe([settings.stream_topic])

    def poll(self, timeout: float = 1.0) -> dict[str, Any] | None:
        msg = self._consumer.poll(timeout)
        if msg is None or msg.error():
            return None
        raw = msg.value()
        if raw is None:
            return None
        return json.loads(raw.decode())

    def close(self) -> None:
        self._consumer.close()


def ensure_topic(bootstrap: str | None = None) -> None:  # pragma: no cover - requires a broker
    """Create the stream topic if it does not yet exist (idempotent)."""
    from confluent_kafka.admin import AdminClient, NewTopic

    settings = get_settings()
    admin = AdminClient({"bootstrap.servers": bootstrap or settings.broker_bootstrap})
    existing = admin.list_topics(timeout=10).topics
    if settings.stream_topic not in existing:
        admin.create_topics(
            [NewTopic(settings.stream_topic, num_partitions=1, replication_factor=1)]
        )
        log.info("topic_created", extra={"topic": settings.stream_topic})
