from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from config import ModelConfig

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - depends on environment
    AsyncOpenAI = None

try:
    import httpx
except ImportError:  # pragma: no cover - depends on environment
    httpx = None


class LLMClientError(RuntimeError):
    """Raised when a model invocation fails."""


class LLMClient(ABC):
    """Unified async interface for any text generation backend."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text for a prompt."""


class OpenAIClient(LLMClient):
    """Adapter for OpenAI-compatible chat models."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        if AsyncOpenAI is None:
            raise ImportError(
                "The `openai` package is required to use OpenAIClient."
            )

        api_key = None
        if config.api_key_env:
            import os

            api_key = os.getenv(config.api_key_env)

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        self._client = AsyncOpenAI(**client_kwargs)

    async def generate(self, prompt: str) -> str:
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.config.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                ),
                timeout=self.config.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - network dependency
            raise LLMClientError(
                f"OpenAI request failed for model `{self.config.model_name}`."
            ) from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMClientError(
                f"OpenAI model `{self.config.model_name}` returned empty content."
            )
        return content


class MockClient(LLMClient):
    """Deterministic async client for local development and tests."""

    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(0)
        persona = self.config.metadata.get("persona", "general")

        if persona == "analytical":
            return (
                f"[{self.name}] Analytical mock answer for: {prompt}\n"
                "Key points: assumptions, trade-offs, and next steps are included."
            )

        return f"[{self.name}] Concise mock answer for: {prompt}"


class LocalHTTPClient(LLMClient):
    """Adapter for OpenAI-like local inference servers or custom HTTP backends."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        if httpx is None:
            raise ImportError("The `httpx` package is required to use LocalHTTPClient.")
        if not config.base_url:
            raise ValueError("LocalHTTPClient requires `base_url` in ModelConfig.")

    async def generate(self, prompt: str) -> str:
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        timeout = httpx.Timeout(self.config.timeout_seconds)

        try:
            async with httpx.AsyncClient(base_url=self.config.base_url, timeout=timeout) as client:
                response = await client.post("/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # pragma: no cover - network dependency
            raise LLMClientError(
                f"Local model request failed for `{self.config.model_name}`."
            ) from exc

        text = data.get("text") or data.get("response")
        if not text:
            raise LLMClientError(
                f"Local model `{self.config.model_name}` returned no text field."
            )
        return text


CLIENT_REGISTRY: dict[str, type[LLMClient]] = {
    "openai": OpenAIClient,
    "mock": MockClient,
    "local_http": LocalHTTPClient,
}


def register_client(provider: str, client_cls: type[LLMClient]) -> None:
    """Register a new provider without touching orchestration code."""
    CLIENT_REGISTRY[provider] = client_cls


def build_client(config: ModelConfig) -> LLMClient:
    client_cls = CLIENT_REGISTRY.get(config.provider)
    if client_cls is None:
        available = ", ".join(sorted(CLIENT_REGISTRY))
        raise ValueError(
            f"Unknown provider `{config.provider}` for model `{config.name}`. "
            f"Available providers: {available}"
        )
    return client_cls(config)


def build_client_map(configs: list[ModelConfig]) -> dict[str, LLMClient]:
    return {config.name: build_client(config) for config in configs}
