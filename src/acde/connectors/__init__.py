"""Connectors: attach ACDE to a company's own orchestrator/warehouse (v2, P2, D-066).

The runtime talks to external systems only through a `Connector` so ACDE points at *their* stack
(their Airflow, their warehouse) rather than requiring ours. `get_connector()` selects the
configured connector; `noop` gives an observe-only deployment (propose + gate + log, never act).
"""

from acde.connectors.registry import get_connector

__all__ = ["get_connector"]
