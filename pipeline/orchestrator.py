from __future__ import annotations

import asyncio
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

        final_answer = (
            f"Best Answer:\n{top_two[0][1].strip()}\n\n"
            f"Additional Insight:\n{top_two[1][1].strip()}"
        )
        logger.info("Fused top responses from models=%s", selected_models)
        return {
            "answer": final_answer,
            "sources": selected_models,
            "method": "score_ranked_fusion",
        }

    def _format_final_answer(self, answer: str) -> str:
        if not answer.strip():
            return answer

        lines = [line.strip() for line in answer.splitlines()]
        explanation_parts: list[str] = []
        key_insights: list[str] = []
        tradeoffs: list[str] = []
        current_section = "explanation"

        for line in lines:
            if not line:
                continue
            lowered = line.lower()

            if lowered.startswith("best answer"):
                current_section = "explanation"
                continue
            if lowered.startswith("additional insight") or lowered.startswith("key points"):
                current_section = "insights"
                payload = line.split(":", 1)
                if len(payload) > 1 and payload[1].strip():
                    key_insights.extend(
                        item.strip(" .")
                        for item in payload[1].split(",")
                        if item.strip()
                    )
                continue
            if lowered.startswith("refinement notes") or "trade-off" in lowered or "note" in lowered:
                current_section = "tradeoffs"
                continue

            if line.startswith(("- ", "* ")):
                item = line[2:].strip()
                if current_section == "tradeoffs":
                    tradeoffs.append(item)
                elif current_section == "insights":
                    key_insights.append(item)
                else:
                    key_insights.append(item)
                continue

            if current_section == "explanation":
                explanation_parts.append(line)
            elif current_section == "insights":
                key_insights.append(line)
            else:
                tradeoffs.append(line)

        explanation = " ".join(explanation_parts).strip()
        if not explanation:
            cleaned = answer.replace("Best Answer:", "").replace("Additional Insight:", "").replace("Refinement notes:", "").strip()
            return cleaned

        if not key_insights:
            sentences = [segment.strip() for segment in explanation.split(".") if segment.strip()]
            key_insights = sentences[1:4] if len(sentences) > 1 else []

        if not tradeoffs:
            extracted_notes = [item for item in key_insights if "trade-off" in item.lower() or "reason" in item.lower() or "assumption" in item.lower()]
            tradeoffs = extracted_notes[:2]

        if not key_insights and not tradeoffs:
            return explanation

        sections = [
            "### 🧠 Explanation",
            "",
            explanation,
        ]

        if key_insights:
            sections.extend([
                "",
                "---",
                "",
                "### 🔍 Key Insights",
                "",
            ])
            sections.extend([f"* {item}" for item in key_insights[:3]])

        if tradeoffs:
            sections.extend([
                "",
                "---",
                "",
                "### ⚖️ Trade-offs / Notes",
                "",
            ])
            sections.extend([f"* {item}" for item in tradeoffs[:2]])

        return "\n".join(sections).strip()

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
