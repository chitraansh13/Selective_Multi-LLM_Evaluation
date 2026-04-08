from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from pipeline.orchestrator import build_default_pipeline
from utils.logger import configure_logging


async def main() -> None:
    configure_logging(settings.debug)
    pipeline = build_default_pipeline()

    simple_query = "What is 2+2?"
    complex_query = "Design a scalable system like Instagram"

    simple_result = await pipeline.run(simple_query)
    complex_result = await pipeline.run(complex_query)

    print("SIMPLE RESULT")
    print(json.dumps(simple_result, indent=2))
    print(f"latency={simple_result['latency']} models_used={len(simple_result['responses'])}")

    print("COMPLEX RESULT")
    print(json.dumps(complex_result, indent=2))
    print(f"latency={complex_result['latency']} models_used={len(complex_result['responses'])}")

    assert len(simple_result["responses"]) == 1, "Simple query should use one model."
    assert len(complex_result["responses"]) > 1, "Complex query should use multiple models."
    assert complex_result["scores"], "Complex query should include evaluator scores."
    assert all("score" in item for item in complex_result["scores"].values()), "Each score entry should expose a numeric score."
    assert complex_result.get("fusion", {}).get("answer"), "Fusion output should exist."
    assert complex_result.get("best_model"), "Best model should be identified."
    assert complex_result.get("final_answer"), "Refined answer should exist."
    assert complex_result["stage"] == "refined", "Complex path should finish in refined stage."


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
