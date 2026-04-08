from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ModelConfig:
    name: str
    provider: str
    model_name: str
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float = 60.0
    temperature: float = 0.2
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Settings:
    app_name: str = "SMERF"
    app_version: str = "0.1.0"
    debug: bool = True
    default_simple_model: str = "mock-simple"
    default_complex_models: list[str] = field(
        default_factory=lambda: ["mock-simple", "mock-critic"]
    )
    enable_llm_router: bool = False
    router_keywords: list[str] = field(
        default_factory=lambda: [
            "analyze",
            "compare",
            "design",
            "architecture",
            "system",
            "scalable",
            "distributed",
            "trade-offs",
            "optimize",
            "explain in detail",
            "how does",
            "why does",
            "multi-step",
        ]
    )
    router_length_threshold: int = 20
    router_complexity_weight: float = 0.6
    llm_complexity_weight: float = 0.4
    generation_retries: int = 1
    model_configs: list[ModelConfig] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_models = os.getenv("SMERF_MODELS_JSON")
        model_configs: list[ModelConfig] = []

        if raw_models:
            parsed_models = json.loads(raw_models)
            model_configs = [ModelConfig(**item) for item in parsed_models]
        else:
            model_configs = [
                ModelConfig(
                    name="mock-simple",
                    provider="mock",
                    model_name="mock-simple",
                    metadata={"persona": "concise"},
                ),
                ModelConfig(
                    name="mock-critic",
                    provider="mock",
                    model_name="mock-critic",
                    metadata={"persona": "analytical"},
                ),
            ]

        complex_models = os.getenv("SMERF_COMPLEX_MODELS")
        return cls(
            debug=os.getenv("SMERF_DEBUG", "true").lower() == "true",
            default_simple_model=os.getenv("SMERF_SIMPLE_MODEL", "mock-simple"),
            default_complex_models=(
                [item.strip() for item in complex_models.split(",") if item.strip()]
                if complex_models
                else ["mock-simple", "mock-critic"]
            ),
            enable_llm_router=os.getenv("SMERF_ENABLE_LLM_ROUTER", "false").lower()
            == "true",
            router_length_threshold=int(os.getenv("SMERF_ROUTER_LENGTH_THRESHOLD", "8")),
            router_complexity_weight=float(
                os.getenv("SMERF_ROUTER_HEURISTIC_WEIGHT", "0.6")
            ),
            llm_complexity_weight=float(os.getenv("SMERF_ROUTER_LLM_WEIGHT", "0.4")),
            generation_retries=int(os.getenv("SMERF_GENERATION_RETRIES", "1")),
            model_configs=model_configs,
        )


settings = Settings.from_env()
