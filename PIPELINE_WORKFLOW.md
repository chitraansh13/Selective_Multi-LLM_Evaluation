
# SMERF Pipeline Workflow Guide

## Purpose

This document explains how the SMERF backend pipeline works from the moment a user sends a query to the moment the system returns the final answer. It is meant to be presentation-friendly, so it focuses on the actual flow of the code and shows a practical example.

## What SMERF does

SMERF stands for Selective Multi-LLM Evaluation and Refinement System.

The core idea is:

1. classify the query
2. decide whether the query is simple or complex
3. if simple, use one low-cost model
4. if complex, use multiple LLMs in parallel
5. evaluate all candidate answers
6. fuse the strongest responses
7. refine and format the final answer

This gives better answers than blindly trusting one model for every request.

## Backend modules involved

### [main.py]

Starts FastAPI, enables CORS, creates the shared pipeline instance, and exposes the `/query` API route.

### [routers/query.py]

Receives the request payload and forwards the query to the SMERF pipeline.

### [pipeline/orchestrator.py]

Acts as the central brain of the system. It coordinates routing, generation, evaluation, fusion, refinement, and final formatting.

### [services/router.py]

Classifies the query as `simple` or `complex`.

### [services/llm_clients.py]

Provides the pluggable LLM client architecture. The same pipeline can use mock models, OpenAI-compatible models, OpenRouter models, or Gemini in OpenAI-compatible mode.

### [evaluators/scoring.py]

Scores each generated answer.

### [refinement/refiner.py]

Improves the fused answer before it is returned.

## End-to-end flow

### Step 1: User sends a query

Example input:

```json
{
  "query": "Design a scalable clone of Netflix with authentication, streaming, and recommendations."
}
```

The frontend sends this to:

```http
POST /query
```

### Step 2: API router receives the request

In [routers/query.py], the backend validates the JSON payload and sends the query into the shared pipeline:

```python
result = await request.app.state.pipeline.run(payload.query)
```

### Step 3: Query routing

In [services/router.py], `QueryRouter.classify()` analyzes the query.

The router checks:

- query length
- engineering keywords such as `design`, `architecture`, `system`, `distributed`
- build intent such as `build`, `make`, `create`, `develop`
- clone/product intent such as `clone of Netflix`
- multiple concepts in the same prompt
- optional LLM classification if enabled

The router returns a structure like this:

```json
{
  "label": "complex",
  "confidence": 0.92,
  "debug": {
    "heuristic_score": 1.0,
    "llm_score": 0.8,
    "matched_keywords": ["design", "scalable", "authentication"],
    "detected_intents": ["build", "clone", "domain_scope"]
  }
}
```

### Step 4: Pipeline decides the path

In [pipeline/orchestrator.py], `SMERFPipeline.run()` checks the router result.

If the label is `simple`:

- only one model is called
- the answer is returned directly

If the label is `complex`:

- the system enters the full multi-LLM workflow

### Step 5: Parallel generation

For complex queries, `generate_responses()` runs multiple models in parallel with `asyncio.gather()`.

Pseudo-flow:

```python
pairs = await asyncio.gather(
    *[_invoke_model(model_name) for model_name in model_names]
)
```

Each model call:

- uses the shared `LLMClient` interface
- respects timeout settings
- supports retry logic
- logs latency
- does not crash the whole request if one model fails

Example generated responses:

```json
{
  "gemini-flash": "Use a CDN, chunked video delivery, and a microservices backend...",
  "gpt-oss-20b-free": "Split the system into auth, catalog, streaming, and recommendation services...",
  "glm-4.5-air-free": "Focus on user auth, watch history, and cache-heavy content metadata..."
}
```

### Step 6: Response evaluation

In [evaluators/scoring.py], `ResponseEvaluator.evaluate()` scores each answer.

Current scoring signals include:

- response length
- reasoning words like `because`, `therefore`, `trade-off`, `architecture`, `design`
- structured output
- multi-paragraph content

Example evaluation output:

```json
{
  "gemini-flash": {
    "score": 8,
    "reason": "Strong structure, good depth, and clear reasoning signals."
  },
  "gpt-oss-20b-free": {
    "score": 7,
    "reason": "Good detail and coverage, but less structured."
  },
  "glm-4.5-air-free": {
    "score": 6,
    "reason": "Useful content, but shorter and less complete."
  }
}
```

### Step 7: Best model selection

The orchestrator sorts models by score and marks the strongest one as `best_model`.

Example:

```json
{
  "best_model": "gemini-flash"
}
```

This is useful in demos because it shows that the pipeline is not choosing arbitrarily.

### Step 8: Fusion

`fuse_responses()` takes the top two responses and combines them into a single intermediate answer.

The current logic:

1. sort responses by evaluator score
2. take the top 2
3. keep the strongest response as primary
4. keep the second response as supporting insight

This gives the system a simple but explainable ensemble behavior.

### Step 9: Refinement

In [refinement/refiner.py], `refine()` improves the fused answer.

If a real LLM is available for refinement:

- it performs self-critique and improvement

If not:

- SMERF uses a fallback refinement strategy to improve structure and clarity

### Step 10: Final formatting

The orchestrator then reshapes the refined text into a cleaner user-facing answer. The current formatting stage tries to produce:

- `### Explanation`
- `### Key Insights`
- `### Trade-offs / Notes`

This is important because raw model outputs can be messy, table-like, or too dense for presentation.

### Step 11: API response returned

The final API response is wrapped in the standard backend contract:

```json
{
  "success": true,
  "data": {
    "query": "Design a scalable clone of Netflix with authentication, streaming, and recommendations.",
    "complexity": {
      "label": "complex",
      "confidence": 0.92
    },
    "final_answer": "### Explanation\n...\n### Key Insights\n- ...",
    "responses": {
      "gemini-flash": "...",
      "gpt-oss-20b-free": "...",
      "glm-4.5-air-free": "..."
    },
    "scores": {
      "gemini-flash": {
        "score": 8,
        "reason": "Strong structure, good depth, and clear reasoning signals."
      }
    },
    "best_model": "gemini-flash",
    "stage": "refined",
    "latency": {
      "generation": 2.1,
      "evaluation": 0.01,
      "fusion": 0.0,
      "refinement": 0.12,
      "total": 2.24
    }
  },
  "error": null
}
```

## Code workflow example

This is the real high-level workflow in code form:

```python
async def run(self, query: str) -> dict[str, Any]:
    complexity = await self.router.classify(query)

    if complexity["label"] == "simple":
        response = await simple_client.generate(query)
        return {
            "query": query,
            "complexity": complexity,
            "final_answer": response,
            "responses": {simple_model_name: response},
            "stage": "single_generation",
        }

    generation_result = await self.generate_responses(query)
    responses = generation_result["responses"]

    scores = await self.evaluator.evaluate(query, responses)
    fused = await self.fuse_responses(query, responses, scores)
    refined = await self.refiner.refine(query, fused["answer"])
    final_answer = self._format_final_answer(refined)

    return {
        "query": query,
        "complexity": complexity,
        "final_answer": final_answer,
        "responses": responses,
        "scores": scores,
        "best_model": best_model,
        "stage": "refined",
    }
```

## Why this architecture is useful

This design helps because:

- simple questions stay fast and cheap
- complex questions get stronger multi-model treatment
- evaluation makes the system more transparent
- fusion allows the system to preserve useful ideas from more than one model
- refinement improves readability for the final user
- the modular structure makes the project easier to explain, test, and extend

## Gemini support in this architecture

Gemini works cleanly in SMERF because the pipeline depends only on the `LLMClient` interface, not on any provider-specific code.

That means Gemini can be added just by registering a Gemini-compatible client and providing config like:

```json
{
  "name": "gemini-flash",
  "provider": "gemini",
  "model_name": "google/gemini-2.0-flash",
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
  "api_key_env": "GEMINI_API_KEY"
}
```

The rest of the pipeline stays unchanged:

- router still classifies
- generation still runs in parallel
- evaluator still scores
- fusion still combines top answers
- refiner still improves the answer

That is exactly why the `LLMClient` abstraction exists.
