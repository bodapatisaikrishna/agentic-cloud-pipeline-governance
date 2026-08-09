"""Hermetic-by-construction defaults for the unit suite.

Unit tests must never touch the network or a developer's real credentials (CLAUDE.md: "MOCK_LLM=1 is
the default. All tests and CI pass with zero API calls."). Nothing enforced that, and ``Settings``
resolves config from two ambient sources that tests were exposed to:

* **The ``.env`` file** — any test constructing ``LLMClient()`` without patching ``get_settings``
  inherited whatever the developer had configured. With ``MOCK_LLM=0`` and a live provider key in
  ``.env``, those tests made real, billed API calls — invisible in CI, which has no ``.env``.
* **Exported environment variables** — ``Settings(_env_file=None)`` suppresses the *file* but not
  the environment, so a developer with e.g. ``POSTGRES_HOST`` exported in their shell saw tests that
  assert on default values fail for reasons unrelated to their change.

Clearing every ``Settings``-derived variable here removes both, so the suite sees pristine defaults
regardless of local machine state. This runs at import time — before collection, and before anything
can populate the process-wide ``get_settings`` cache.

Tests that deliberately exercise non-default config still pass explicit constructor kwargs (e.g.
``Settings(_env_file=None, mock_llm=False, ...)``) or set vars via ``monkeypatch``; both outrank
this baseline, so they keep working — they patch the provider seam rather than making real calls.
"""

from __future__ import annotations

import os

from acde.config import Settings, get_settings

# Field name -> env var is a straight uppercase (Settings declares no env_prefix).
for _field in Settings.model_fields:
    os.environ.pop(_field.upper(), None)

# Pin the safety-critical values rather than trusting the declared defaults to stay put: unit tests
# must never reach a live provider even if someone later flips the default.
os.environ["MOCK_LLM"] = "1"
# Belt-and-braces: even if a test bypasses the mock path, there is no credential to spend.
for _var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OAI_API_KEY", "OAI_BASE_URL"):
    os.environ[_var] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Keep the process-wide ``get_settings`` cache from leaking config between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
