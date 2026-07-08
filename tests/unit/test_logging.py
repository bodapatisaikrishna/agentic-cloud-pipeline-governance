"""Unit tests for structured JSON logging."""

import json
import logging

from acde.logging import JSONFormatter, get_logger, setup_logging


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JSONFormatter().format(record))


def _record(msg: str = "test_event", **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="unit.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJSONFormatter:
    def test_line_is_valid_json_with_required_keys(self):
        payload = _format(_record())
        assert payload["level"] == "INFO"
        assert payload["component"] == "unit.test"
        assert payload["event"] == "test_event"
        assert "ts" in payload

    def test_extras_pass_through(self):
        payload = _format(_record(experiment_run="run-7", fault_type="schema_drift"))
        assert payload["experiment_run"] == "run-7"
        assert payload["fault_type"] == "schema_drift"

    def test_non_serializable_extras_stringified(self):
        payload = _format(_record(weird=object()))
        assert isinstance(payload["weird"], str)

    def test_exception_included(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _record()
            record.exc_info = sys.exc_info()
        payload = _format(record)
        assert "ValueError: boom" in payload["exception"]


class TestSetup:
    def test_setup_idempotent(self):
        setup_logging()
        root = logging.getLogger()
        count = sum(isinstance(h.formatter, JSONFormatter) for h in root.handlers)
        setup_logging()
        assert sum(isinstance(h.formatter, JSONFormatter) for h in root.handlers) == count

    def test_get_logger_named_after_component(self):
        assert get_logger("agents.recovery").name == "agents.recovery"
