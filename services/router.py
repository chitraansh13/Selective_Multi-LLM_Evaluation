from __future__ import annotations

import json
from typing import Any

from config import Settings
from services.llm_clients import LLMClient, LLMClientError
from utils.logger import get_logger

logger = get_logger(__name__)


class QueryRouter:
    """Hybrid query router that combines heuristic and LLM signals."""

    HIGH_SIGNAL_KEYWORDS = {"design", "architecture", "distributed", "scalable", "system", "compare", "analyze"}

    def __init__(
        self,
        config: Settings,
        classifier_client: LLMClient | None = None,
    ) -> None:
        self.config = config
        self.classifier_client = classifier_client

    async def classify(self, query: str) -> dict[str, Any]:
        heuristic = self._heuristic_score(query)
        llm_result = await self._llm_classification(query)
        llm_score = self._resolve_llm_score(llm_result, heuristic["score"])
        final_score = (
            self.config.router_complexity_weight * heuristic["score"]
            + self.config.llm_complexity_weight * llm_score
        )
        label = "complex" if final_score > 0.5 else "simple"

        result = {
            "label": label,
            "confidence": round(final_score, 3),
            "debug": {
                "heuristic_score": round(heuristic["score"], 3),
                "llm_score": round(llm_score, 3),
                "matched_keywords": heuristic["matched_keywords"],
                "multiple_concepts": heuristic["multiple_concepts"],
                "word_count": heuristic["word_count"],
                "llm_enabled": self.config.enable_llm_router,
                "llm_raw": llm_result,
            },
        }

        logger.info(
            "Router decision label=%s final_score=%.3f heuristic=%.3f llm=%.3f query=%r",
            result["label"],
            final_score,
            heuristic["score"],
            llm_score,
            query,
        )
        if self.config.debug:
            logger.debug("Router debug payload: %s", result["debug"])

        return result

    def _heuristic_score(self, query: str) -> dict[str, Any]:
        lowered = query.lower().strip()
        words = query.split()
        matched_keywords = [
            keyword for keyword in self.config.router_keywords if keyword in lowered
        ]

        score = 0.0
        if len(words) > self.config.router_length_threshold:
            score += 0.2

        if matched_keywords:
            score += min(0.5, 0.18 + 0.14 * len(matched_keywords))

        if len(words) >= 5 and any(keyword in self.HIGH_SIGNAL_KEYWORDS for keyword in matched_keywords):
            score += 0.2

        multiple_concepts = self._has_multiple_concepts(lowered, matched_keywords)
        if multiple_concepts:
            score += 0.3

        if lowered.startswith(("how to", "how does", "why does", "explain", "analyze", "compare", "design")):
            score += 0.12

        if " in detail" in lowered or "step by step" in lowered:
            score += 0.15

        score = min(score, 1.0)
        return {
            "score": score,
            "matched_keywords": matched_keywords,
            "multiple_concepts": multiple_concepts,
            "word_count": len(words),
        }

    def _has_multiple_concepts(
        self,
        lowered_query: str,
        matched_keywords: list[str],
    ) -> bool:
        disambiguation_markers = [" vs ", " versus ", " and ", ","]
        if any(marker in lowered_query for marker in disambiguation_markers):
            return True

        concept_markers = [
            " trade-offs",
            " system",
            " architecture",
            " design",
            " cache",
            " complexity",
        ]
        marker_hits = sum(1 for marker in concept_markers if marker in lowered_query)
        return len(matched_keywords) >= 2 or marker_hits >= 2

    async def _llm_classification(self, query: str) -> dict[str, Any] | None:
        if not self.config.enable_llm_router or self.classifier_client is None:
            return None

        prompt = (
            "Classify the following query as SIMPLE or COMPLEX.\n"
            "Return only JSON with fields: label, confidence.\n"
            f"Query: {query}"
        )

        try:
            response = await self.classifier_client.generate(prompt)
            parsed = self._parse_llm_payload(response)
            logger.info("LLM router classification succeeded for query=%r", query)
            return parsed
        except (LLMClientError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("LLM router classification failed for query=%r: %s", query, exc)
            return None

    def _resolve_llm_score(
        self,
        llm_result: dict[str, Any] | None,
        heuristic_score: float,
    ) -> float:
        if llm_result is None:
            return heuristic_score
        return 1.0 if llm_result["label"] == "complex" else 0.0

    @staticmethod
    def _parse_llm_payload(payload: str) -> dict[str, Any]:
        start = payload.find("{")
        end = payload.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Classifier did not return JSON.")

        parsed = json.loads(payload[start : end + 1])
        label = str(parsed["label"]).strip().lower()
        if label not in {"simple", "complex"}:
            raise ValueError("Classifier returned invalid label.")

        confidence = max(0.0, min(float(parsed["confidence"]), 1.0))
        return {
            "label": label,
            "confidence": confidence,
        }
