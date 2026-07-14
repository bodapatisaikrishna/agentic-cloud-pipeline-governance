"""Schema agent: contain schema drift (quarantine/block) or allow compatible changes."""

from __future__ import annotations

from acde.agents.base import BaseAgent


class SchemaAgent(BaseAgent):
    agent = "schema"
