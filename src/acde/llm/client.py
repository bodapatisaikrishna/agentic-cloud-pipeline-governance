"""LLM layer: routing, budget guard, in-run cache, retry, and the mock/live split (§5.6).

Agents call :meth:`LLMClient.propose` with a snapshot + system prompt and get back an
``action_json`` (validated into a ``ProposedAction`` by the agent). Under ``MOCK_LLM`` this is
served deterministically by :mod:`acde.llm.mock` — no API calls. Live calls route monitoring →
``MODEL_FAST`` and everyone else → ``MODEL_REASONING`` (temperature=0), retry 429/5xx up to 3x,
and degrade to ``no_action`` (logged ``llm_unavailable``) on final failure or budget exhaustion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from acde.config import get_settings
from acde.contracts import AgentName, TelemetrySnapshot
from acde.logging import get_logger

log = get_logger("llm.client")


@dataclass
class LLMResult:
    """One agent proposal from the LLM (or mock)."""

    action_json: dict[str, Any]
    tokens_in: int
    tokens_out: int
    model: str


@dataclass
class BudgetTracker:
    """Per-experiment-run cap on LLM calls and tokens (§5.6)."""

    max_calls: int
    max_tokens: int
    calls: int = 0
    tokens: int = 0

    def exceeded(self) -> bool:
        return self.calls >= self.max_calls or self.tokens >= self.max_tokens

    def add(self, tokens_in: int, tokens_out: int) -> None:
        self.calls += 1
        self.tokens += tokens_in + tokens_out


def _no_action(agent: AgentName, reason: str) -> dict[str, Any]:
    return {
        "agent": agent,
        "action_type": "no_action",
        "target": "none",
        "params": {},
        "justification": reason,
        "confidence": 0.0,
    }


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model response (tolerates prose/markdown fences)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


class LLMClient:
    """Routes proposals to the mock or the live Anthropic API, with budget + cache guards."""

    def __init__(self, budget: BudgetTracker | None = None) -> None:
        settings = get_settings()
        self.budget = budget or BudgetTracker(
            settings.llm_max_calls_per_run, settings.llm_max_tokens_per_run
        )
        self._cache: dict[tuple[str, str], LLMResult] = {}
        self._anthropic: Any = None

    def model_for(self, agent: AgentName) -> str:
        settings = get_settings()
        return settings.model_fast if agent == "monitoring" else settings.model_reasoning

    def propose(
        self, agent: AgentName, snapshot: TelemetrySnapshot, system_prompt: str
    ) -> LLMResult:
        """Return a proposal for ``agent`` given ``snapshot`` (cached, budgeted, degradable)."""
        key = (agent, snapshot.cache_key_material())
        if key in self._cache:
            return self._cache[key]

        model = self.model_for(agent)
        if self.budget.exceeded():
            log.warning(
                "llm_budget_exceeded",
                extra={
                    "agent": agent,
                    "calls": self.budget.calls,
                    "tokens": self.budget.tokens,
                    "experiment_run": snapshot.experiment_run,
                },
            )
            return LLMResult(
                _no_action(agent, "budget exhausted; degraded to no_action"), 0, 0, model
            )

        settings = get_settings()
        if settings.mock_llm:
            from acde.llm import mock

            result = mock.mock_propose(agent, snapshot)
        else:
            result = self._live_call(agent, snapshot, system_prompt, model)

        self.budget.add(result.tokens_in, result.tokens_out)
        self._cache[key] = result
        return result

    def _live_call(  # pragma: no cover - requires the Anthropic API
        self, agent: AgentName, snapshot: TelemetrySnapshot, system_prompt: str, model: str
    ) -> LLMResult:
        import anthropic
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

        settings = get_settings()
        if self._anthropic is None:
            self._anthropic = anthropic.Anthropic()

        def _retryable(exc: BaseException) -> bool:
            if isinstance(exc, anthropic.APIConnectionError):
                return True
            return isinstance(exc, anthropic.APIStatusError) and (
                exc.status_code == 429 or exc.status_code >= 500
            )

        @retry(
            retry=retry_if_exception(_retryable),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, max=8),
            reraise=True,
        )
        def _once() -> LLMResult:
            resp = self._anthropic.messages.create(
                model=model,
                max_tokens=settings.llm_max_tokens_per_call,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": snapshot.model_dump_json()}],
            )
            text = "".join(block.text for block in resp.content if block.type == "text")
            return LLMResult(
                _extract_json(text), resp.usage.input_tokens, resp.usage.output_tokens, resp.model
            )

        try:
            return _once()
        except Exception as exc:  # final failure → degrade
            log.warning(
                "llm_unavailable",
                extra={
                    "agent": agent,
                    "error": str(exc),
                    "model": model,
                    "experiment_run": snapshot.experiment_run,
                },
            )
            return LLMResult(
                _no_action(agent, "LLM unavailable; degraded to no_action"), 0, 0, model
            )
