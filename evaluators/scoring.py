from __future__ import annotations

from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


class ResponseEvaluator:
    """Deterministic response evaluator for SMERF."""

    REASONING_WORDS = ["because", "therefore", "trade-off", "architecture", "design"]

    def __init__(self, judge_client: Any | None = None) -> None:
        self.judge_client = judge_client

    async def evaluate(self, query: str, responses: dict[str, str]) -> dict[str, dict[str, Any]]:
        evaluations: dict[str, dict[str, Any]] = {}

        for model_name, response in responses.items():
            score = 0
            reasons: list[str] = []
            lowered = response.lower()

            if len(response) > 150:
                score += 2
                reasons.append("good depth")

            matched_reasoning = [word for word in self.REASONING_WORDS if word in lowered]
            if matched_reasoning:
                score += 3
                reasons.append(f"reasoning terms: {', '.join(matched_reasoning)}")

            paragraph_count = len([chunk for chunk in response.splitlines() if chunk.strip()])
            if paragraph_count >= 2:
                score += 2
                reasons.append("multiple paragraphs")

            if ":" in response or "-" in response:
                score += 2
                reasons.append("structured formatting")

            if len(response.split()) > 25:
                score += 1
                reasons.append("substantial coverage")

            final_score = min(score, 10)
            evaluations[model_name] = {
                "score": final_score,
                "reason": ", ".join(reasons) if reasons else "brief response with limited reasoning",
            }
            logger.info(
                "Evaluation completed for model=%s score=%s reason=%s",
                model_name,
                final_score,
                evaluations[model_name]["reason"],
            )

        return evaluations
