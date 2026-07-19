"""Connector registry: select the runtime connector from config (P2)."""

from __future__ import annotations

from acde.config import get_settings
from acde.connectors.base import Connector


def get_connector(kind: str | None = None, is_production: bool = True) -> Connector:
    """Return the configured connector instance (``connector_kind``: airflow | noop)."""
    kind = kind or get_settings().connector_kind
    if kind == "airflow":
        from acde.connectors.airflow import AirflowConnector

        return AirflowConnector(is_production=is_production)
    if kind == "noop":
        from acde.connectors.noop import NoopConnector

        return NoopConnector()
    raise ValueError(f"unknown connector_kind: {kind!r}; choose from airflow, noop")
