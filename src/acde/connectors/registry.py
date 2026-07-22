"""Connector registry: select the runtime connector from config (P2)."""

from __future__ import annotations

from acde.config import get_settings
from acde.connectors.base import Connector


def get_connector(kind: str | None = None, is_production: bool | None = None) -> Connector:
    """Return the configured connector instance (``connector_kind``: airflow | prefect | noop)."""
    settings = get_settings()
    kind = kind or settings.connector_kind
    if is_production is None:
        is_production = settings.connector_is_production
    if kind == "airflow":
        from acde.connectors.airflow import AirflowConnector

        return AirflowConnector(is_production=is_production)
    if kind == "prefect":
        from acde.connectors.prefect import PrefectConnector

        return PrefectConnector(is_production=is_production)
    if kind == "noop":
        from acde.connectors.noop import NoopConnector

        return NoopConnector()
    raise ValueError(f"unknown connector_kind: {kind!r}; choose from airflow, prefect, noop")
