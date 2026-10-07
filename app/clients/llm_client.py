"""LLM client — native Structured Outputs (Pydantic) for OpenAI / Azure AI Foundry, async, with mock fallback."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def _is_reasoning_model(model: str) -> bool:
    m = model.lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


class LLMClient:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.model = settings.llm_model_name
        self._client = None
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return settings.llm_enabled

    def _get_client(self):
        if self._client is None:
            from openai import AsyncAzureOpenAI, AsyncOpenAI

            if self.provider == "azure_foundry":
                self._client = AsyncAzureOpenAI(
                    azure_endpoint=settings.AZURE_FOUNDRY_ENDPOINT,
                    api_key=settings.AZURE_FOUNDRY_API_KEY,
                    api_version=settings.AZURE_FOUNDRY_API_VERSION,
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                    max_retries=2,
                )
            else:
                self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=2)
        return self._client

    def _params(self, reasoning_effort: Optional[str]) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if _is_reasoning_model(self.model):
            effort = reasoning_effort or settings.OPENAI_REASONING_EFFORT
            if effort:
                params["reasoning_effort"] = effort
        elif settings.OPENAI_TEMPERATURE is not None:
            params["temperature"] = settings.OPENAI_TEMPERATURE
        return params

    async def structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        reasoning_effort: Optional[str] = None,
        label: str = "",
    ) -> T:
        """Single-shot structured completion. Raises RuntimeError when the LLM is not configured."""
        if not self.enabled:
            raise RuntimeError("LLM is not configured (set OPENAI_API_KEY or Azure Foundry settings).")
        client = self._get_client()
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.calls += 1
        logger.info("LLM call [%s] model=%s prompt≈%d chars", label or response_model.__name__, self.model,
                    len(system_prompt) + len(user_prompt))
        response = await client.chat.completions.parse(
            model=self.model, messages=messages, response_format=response_model, **self._params(reasoning_effort)
        )
        choice = response.choices[0]
        if choice.message.refusal:
            raise RuntimeError(f"LLM refused: {choice.message.refusal}")
        if choice.message.parsed is None:
            raise RuntimeError(f"LLM returned no parseable structured output (finish_reason={choice.finish_reason}).")
        usage = getattr(response, "usage", None)
        if usage:
            logger.info("LLM usage [%s]: prompt=%s completion=%s", label, usage.prompt_tokens, usage.completion_tokens)
        return choice.message.parsed
