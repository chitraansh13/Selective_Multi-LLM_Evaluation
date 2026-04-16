from __future__ import annotations

import asyncio
import re
from time import perf_counter
from typing import Any

from config import settings
from evaluators.scoring import ResponseEvaluator
from refinement.refiner import Refiner
from services.llm_clients import LLMClient, build_client_map
from services.router import QueryRouter
from utils.logger import get_logger

logger = get_logger(__name__)


class SMERFPipeline:
    """Main orchestration entry point for SMERF."""

    def __init__(
        self,
        config: Any,
        router: QueryRouter,
        evaluator: ResponseEvaluator,
        refiner: Refiner,
        clients: dict[str, LLMClient],
        fusion_client: LLMClient | None = None,
    ) -> None:
        self.config = config
        self.router = router
        self.evaluator = evaluator
        self.refiner = refiner
        self.clients = clients
        self.fusion_client = fusion_client

    async def generate_responses(self, query: str) -> dict[str, Any]:
        model_names = self.config.default_complex_models
        started_at = perf_counter()

        async def _invoke_model(model_name: str) -> tuple[str, str | None]:
            client = self.clients.get(model_name)
            if client is None:
                logger.error("Configured model `%s` is not available.", model_name)
                return model_name, None

            for attempt in range(self.config.generation_retries + 1):
                try:
                    model_started = perf_counter()
                    logger.info("Calling model `%s` for query=%r", model_name, query)
                    response = await asyncio.wait_for(
                        client.generate(query),
                        timeout=client.config.timeout_seconds,
                    )
                    elapsed = perf_counter() - model_started
                    logger.info(
                        "Model `%s` completed in %.3fs on attempt %s.",
                        model_name,
                        elapsed,
                        attempt + 1,
                    )
                    return model_name, response
                except Exception as exc:
                    logger.warning(
                        "Model `%s` failed on attempt %s: %s",
                        model_name,
                        attempt + 1,
                        exc,
                    )
            return model_name, None

        pairs = await asyncio.gather(*[_invoke_model(model_name) for model_name in model_names])
        responses = {model_name: response for model_name, response in pairs if response is not None}
        latency = round(perf_counter() - started_at, 4)
        logger.info(
            "Parallel generation finished in %.4fs with %s/%s successful models.",
            latency,
            len(responses),
            len(model_names),
        )
        return {"responses": responses, "latency": latency}

    async def fuse_responses(
        self,
        query: str,
        responses: dict[str, str],
        scores: dict[str, Any],
    ) -> dict[str, Any]:
        ranked = sorted(
            responses.items(),
            key=lambda item: scores.get(item[0], {}).get("score", 0),
            reverse=True,
        )
        top_two = ranked[:2]
        selected_models = [model_name for model_name, _ in top_two]

        if not top_two:
            return {"answer": "", "sources": [], "method": "no_responses"}

        if len(top_two) == 1:
            return {
                "answer": top_two[0][1],
                "sources": selected_models,
                "method": "single_best",
            }

        primary = self._sanitize_fusion_source(top_two[0][1])
        secondary = self._sanitize_fusion_source(top_two[1][1])
        final_answer = (
            "Primary answer:\n"
            f"{primary}\n\n"
            "Supporting insights:\n"
            f"{secondary}"
        )
        logger.info("Fused top responses from models=%s", selected_models)
        return {
            "answer": final_answer,
            "sources": selected_models,
            "method": "score_ranked_fusion",
        }

    def _sanitize_fusion_source(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.replace("\r", "\n")).strip()
        if cleaned.count("|") >= 4:
            fragments = [
                fragment.strip(" -")
                for fragment in cleaned.split("|")
                if fragment.strip(" -")
            ]
            bullets = [fragment for fragment in fragments[:6] if len(fragment.split()) > 1]
            if bullets:
                return "\n".join(f"- {item}" for item in bullets)
        return text.strip()

    def _normalize_answer_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _extract_bullets(self, text: str) -> list[str]:
        bullets: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ")):
                bullets.append(stripped[2:].strip())
                continue
            if "|" in stripped and stripped.count("|") >= 2:
                parts = [part.strip(" -") for part in stripped.split("|") if part.strip(" -")]
                bullets.extend(part for part in parts if len(part.split()) > 1)
        return bullets

    def _extract_sentences(self, text: str) -> list[str]:
        flattened = self._normalize_answer_text(text).replace("\n", " ")
        flattened = re.sub(r"\s+", " ", flattened)
        return [
            sentence.strip(" -")
            for sentence in re.split(r"(?<=[.!?])\s+", flattened)
            if sentence.strip()
        ]

    def _dedupe_preserve_order(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            key = item.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item.strip())
        return deduped

    def _build_structured_answer(self, answer: str) -> str:
        normalized = self._normalize_answer_text(answer)
        if not normalized:
            return ""

        explanation_lines: list[str] = []
        key_insights: list[str] = []
        notes: list[str] = []
        current_section = "explanation"

        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            lowered = line.lower().rstrip(":")
            if lowered in {"best answer", "primary answer"}:
                current_section = "explanation"
                continue
            if lowered in {"additional insight", "supporting insights", "key points"}:
                current_section = "insights"
                continue
            if lowered == "refinement notes":
                current_section = "notes"
                continue

            if line.startswith(("- ", "* ")):
                payload = line[2:].strip()
                if current_section == "notes":
                    notes.append(payload)
                else:
                    key_insights.append(payload)
                continue

            if line.lower().startswith("key points:"):
                payload = line.split(":", 1)[1].strip()
                key_insights.extend(
                    item.strip(" .")
                    for item in payload.split(",")
                    if item.strip()
                )
                current_section = "insights"
                continue

            if current_section == "notes":
                notes.append(line)
            elif current_section == "insights":
                if "|" in line and line.count("|") >= 2:
                    key_insights.extend(
                        part.strip(" -")
                        for part in line.split("|")
                        if part.strip(" -")
                    )
                else:
                    key_insights.append(line)
            else:
                explanation_lines.append(line)

        explanation = " ".join(explanation_lines).strip()
        bullet_candidates = self._extract_bullets(normalized)
        sentences = self._extract_sentences(explanation or normalized)

        if not explanation and sentences:
            explanation = " ".join(sentences[:2]).strip()
        if not explanation:
            explanation = normalized

        key_insights = self._dedupe_preserve_order(key_insights)[:4]
        if not key_insights:
            key_insights = self._dedupe_preserve_order(bullet_candidates or sentences[1:5])[:4]

        notes.extend(
            item
            for item in bullet_candidates + sentences
            if any(
                token in item.lower()
                for token in (
                    "trade-off",
                    "tradeoff",
                    "limitation",
                    "consideration",
                    "note",
                    "assumption",
                    "cost",
                    "latency",
                    "complexity",
                )
            )
        )
        notes = self._dedupe_preserve_order(notes)[:3]

        if normalized.count("|") >= 4 and not key_insights:
            table_parts = [
                part.strip(" -")
                for part in normalized.split("|")
                if part.strip(" -")
            ]
            key_insights = self._dedupe_preserve_order(table_parts)[:4]

        if not key_insights and not notes:
            return explanation

        sections = [
            "### Explanation",
            "",
            explanation,
        ]

        if key_insights:
            sections.extend(
                [
                    "",
                    "### Key Insights",
                    "",
                    *[f"- {item}" for item in key_insights],
                ]
            )

        if notes:
            sections.extend(
                [
                    "",
                    "### Trade-offs / Notes",
                    "",
                    *[f"- {item}" for item in notes],
                ]
            )

        return "\n".join(sections).strip()

    def _format_final_answer(self, answer: str) -> str:
        if not answer.strip():
            return answer

        structured = self._build_structured_answer(answer)
        if structured:
            return structured

        return self._normalize_answer_text(answer)

    def _apply_sanity_checks(self, query: str, complexity: dict[str, Any]) -> dict[str, Any]:
        lowered = query.lower()
        if any(token in lowered for token in ("design", "architecture")) and complexity["label"] == "simple":
            logger.warning("Sanity override forcing complex classification for query=%r", query)
            complexity["label"] = "complex"
            complexity["confidence"] = max(float(complexity["confidence"]), 0.51)
            debug = complexity.setdefault("debug", {})
            debug["sanity_override"] = True
        return complexity

    async def run(self, query: str) -> dict[str, Any]:
        started_at = perf_counter()
        complexity = await self.router.classify(query)
        complexity = self._apply_sanity_checks(query, complexity)

        if complexity["label"] == "simple":
            model_name = self.config.default_simple_model
            client = self.clients.get(model_name)
            if client is None:
                raise ValueError(f"Configured simple model `{model_name}` is unavailable.")

            response_started = perf_counter()
            logger.info("Running single-model path with `%s` for query=%r", model_name, query)
            response = await asyncio.wait_for(client.generate(query), timeout=client.config.timeout_seconds)
            result = {
                "query": query,
                "complexity": complexity,
                "final_answer": response,
                "responses": {model_name: response},
                "scores": {},
                "best_model": model_name,
                "stage": "single_generation",
                "latency": {
                    "generation": round(perf_counter() - response_started, 4),
                    "total": round(perf_counter() - started_at, 4),
                },
            }
        else:
            generation_result = await self.generate_responses(query)
            responses = generation_result["responses"]
            evaluation_started = perf_counter()
            scores = await self.evaluator.evaluate(query, responses)
            evaluation_latency = round(perf_counter() - evaluation_started, 4)

            ranked_models = sorted(
                scores,
                key=lambda name: scores[name].get("score", 0),
                reverse=True,
            )
            best_model = ranked_models[0] if ranked_models else None

            fusion_started = perf_counter()
            fused = await self.fuse_responses(query, responses, scores)
            fusion_latency = round(perf_counter() - fusion_started, 4)

            refinement_started = perf_counter()
            refined_answer = await self.refiner.refine(query, fused["answer"])
            refinement_latency = round(perf_counter() - refinement_started, 4)
            formatted_answer = self._format_final_answer(refined_answer)

            result = {
                "query": query,
                "complexity": complexity,
                "final_answer": formatted_answer,
                "responses": responses,
                "scores": scores,
                "best_model": best_model,
                "fusion": fused,
                "stage": "refined",
                "latency": {
                    "generation": generation_result["latency"],
                    "evaluation": evaluation_latency,
                    "fusion": fusion_latency,
                    "refinement": refinement_latency,
                    "total": round(perf_counter() - started_at, 4),
                },
            }

        if self.config.debug:
            logger.debug("Pipeline result: %s", result)
        return result


def build_default_pipeline() -> SMERFPipeline:
    clients = build_client_map(settings.model_configs)
    classifier_client = clients.get(settings.default_simple_model)
    refinement_client = clients.get(settings.default_complex_models[-1]) if settings.default_complex_models else None
    return SMERFPipeline(
        config=settings,
        router=QueryRouter(settings, classifier_client=classifier_client),
        evaluator=ResponseEvaluator(),
        refiner=Refiner(client=refinement_client),
        clients=clients,
        fusion_client=None,
    )
