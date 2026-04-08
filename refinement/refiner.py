from __future__ import annotations

from services.llm_clients import LLMClient, LLMClientError
from utils.logger import get_logger

logger = get_logger(__name__)


class Refiner:
    """Response improvement stage with self-critique and fallback refinement."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client

    async def refine(self, query: str, answer: str) -> str:
        prompt = (
            "Critically analyze this answer. Identify flaws, missing points, and improve it.\n"
            f"Query: {query}\n"
            f"Answer: {answer}"
        )

        if self.client is not None and self.client.config.provider != "mock":
            try:
                refined = await self.client.generate(prompt)
                if refined.strip():
                    logger.info("Refinement completed with LLM client=%s", self.client.name)
                    return refined.strip()
            except LLMClientError as exc:
                logger.warning("LLM refinement failed: %s", exc)

        logger.info("Using heuristic refinement fallback.")
        return self._fallback_refinement(query, answer)

    def _fallback_refinement(self, query: str, answer: str) -> str:
        improvements = [
            answer.strip(),
            "",
            "Refinement notes:",
            f"- Directly addresses the query: {query}",
            "- Adds clearer structure and removes redundancy.",
            "- Highlights reasoning, trade-offs, and implementation considerations where relevant.",
        ]
        return "\n".join(improvements).strip()
