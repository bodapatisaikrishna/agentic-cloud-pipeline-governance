"""LLM layer: routing, budget guard, in-run cache, retry, and the mock/live split (§5.6).

Agents call :meth:`LLMClient.propose` with a snapshot + system prompt and get back an
``action_json`` (validated into a ``ProposedAction`` by the agent). Under ``MOCK_LLM`` this is
served deterministically by :mod:`acde.llm.mock` — no API calls. Live calls go to the configured
provider (``LLM_PROVIDER``: ``anthropic`` default, ``gemini`` D-056, or ``openai_compatible`` D-057
for NVIDIA NIM / Groq / OpenRouter / z.ai), routing monitoring → fast model and everyone else →
reasoning model (temperature=0), retry 429/5xx up to 3x, and degrade to ``no_action`` (logged
``llm_unavailable``) on final failure or budget exhaustion.
"""

from __future__ import annotations

import json
from collections.abc import Callable
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
        self._gemini: Any = None
        self._oai: Any = None

    def model_for(self, agent: AgentName) -> str:
        settings = get_settings()
        fast = agent == "monitoring"
        if settings.llm_provider == "gemini":
            return settings.gemini_model_fast if fast else settings.gemini_model_reasoning
        if settings.llm_provider == "openai_compatible":
            return settings.oai_model_fast if fast else settings.oai_model_reasoning
        return settings.model_fast if fast else settings.model_reasoning

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

    def _live_call(
        self, agent: AgentName, snapshot: TelemetrySnapshot, system_prompt: str, model: str
    ) -> LLMResult:
        """Dispatch to the configured provider, retrying transient errors then degrading."""
        provider = get_settings().llm_provider
        if provider == "anthropic":
            once, retryable = self._anthropic_once(snapshot, system_prompt, model)
        elif provider == "gemini":
            once, retryable = self._gemini_once(snapshot, system_prompt, model)
        elif provider == "openai_compatible":
            once, retryable = self._openai_compatible_once(snapshot, system_prompt, model)
        else:
            raise ValueError(f"unknown llm_provider: {provider!r}")
        return self._run_with_degrade(agent, snapshot, model, once, retryable)

    def _run_with_degrade(
        self,
        agent: AgentName,
        snapshot: TelemetrySnapshot,
        model: str,
        once: Callable[[], LLMResult],
        retryable: Callable[[BaseException], bool],
    ) -> LLMResult:
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

        runner = retry(
            retry=retry_if_exception(retryable),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, max=8),
            reraise=True,
        )(once)
        try:
            return runner()
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

    def _anthropic_once(  # pragma: no cover - requires the Anthropic API
        self, snapshot: TelemetrySnapshot, system_prompt: str, model: str
    ) -> tuple[Callable[[], LLMResult], Callable[[BaseException], bool]]:
        import anthropic

        settings = get_settings()
        if self._anthropic is None:
            self._anthropic = anthropic.Anthropic()

        def _retryable(exc: BaseException) -> bool:
            if isinstance(exc, anthropic.APIConnectionError):
                return True
            return isinstance(exc, anthropic.APIStatusError) and (
                exc.status_code == 429 or exc.status_code >= 500
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

        return _once, _retryable

    def _gemini_once(  # pragma: no cover - requires the Gemini API
        self, snapshot: TelemetrySnapshot, system_prompt: str, model: str
    ) -> tuple[Callable[[], LLMResult], Callable[[BaseException], bool]]:
        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types

        settings = get_settings()
        if self._gemini is None:
            self._gemini = genai.Client(api_key=settings.gemini_api_key or None)

        def _retryable(exc: BaseException) -> bool:
            code = getattr(exc, "code", None)
            return isinstance(exc, genai_errors.APIError) and (
                code == 429 or (isinstance(code, int) and code >= 500)
            )

        def _once() -> LLMResult:
            resp = self._gemini.models.generate_content(
                model=model,
                contents=snapshot.model_dump_json(),
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                    max_output_tokens=settings.llm_max_tokens_per_call,
                ),
            )
            usage = resp.usage_metadata
            return LLMResult(
                _extract_json(resp.text or ""),
                usage.prompt_token_count or 0,
                usage.candidates_token_count or 0,
                model,
            )

        return _once, _retryable

    def _openai_compatible_once(  # pragma: no cover - requires the API
        self, snapshot: TelemetrySnapshot, system_prompt: str, model: str
    ) -> tuple[Callable[[], LLMResult], Callable[[BaseException], bool]]:
        import openai

        settings = get_settings()
        if self._oai is None:
            self._oai = openai.OpenAI(
                base_url=settings.oai_base_url, api_key=settings.oai_api_key or "missing"
            )

        def _retryable(exc: BaseException) -> bool:
            if isinstance(exc, openai.APIConnectionError):
                return True
            return isinstance(exc, openai.APIStatusError) and (
                exc.status_code == 429 or exc.status_code >= 500
            )

        def _once() -> LLMResult:
            # Larger cap than the other providers: "thinking" models (e.g. GLM-5.2) spend tokens
            # reasoning before the JSON; _extract_json pulls the object out of the surrounding text.
            resp = self._oai.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=settings.oai_max_tokens_per_call,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": snapshot.model_dump_json()},
                ],
            )
            usage = resp.usage
            return LLMResult(
                _extract_json(resp.choices[0].message.content or ""),
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
                model,
            )

        return _once, _retryable
