from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from services.llm_clients import build_client_map
from services.router import QueryRouter
from utils.logger import configure_logging

QUERIES = [
    "What is 2+2?",
    "Define AI",
    "Capital of France",
    "Explain how binary search works",
    "What is REST API",
    "Design a scalable system like Instagram",
    "Compare microservices vs monolith",
    "Explain transformers architecture in deep learning",
    "How to build distributed cache system",
    "Analyze time complexity of merge sort in detail",
]


async def main() -> None:
    configure_logging(settings.debug)
    clients = build_client_map(settings.model_configs)
    router = QueryRouter(settings, classifier_client=clients.get(settings.default_simple_model))

    for query in QUERIES:
        result = await router.classify(query)
        print("-" * 80)
        print(query)
        print(json.dumps(result, indent=2))

        lowered = query.lower()
        if "design" in lowered or "architecture" in lowered:
            assert result["label"] == "complex", f"Expected complex for: {query}"


if __name__ == "__main__":
    asyncio.run(main())
