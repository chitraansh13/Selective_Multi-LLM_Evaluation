# SMERF Detailed Guide

## 1. Overview

SMERF stands for Selective Multi-LLM Evaluation and Refinement System. It is an orchestration framework designed to improve answer quality by combining multiple ideas that are common in modern AI systems engineering:

- routing queries based on complexity
- using different models for different workloads
- evaluating candidate outputs instead of trusting the first answer
- fusing strong responses into a more useful final response
- refining the final answer before returning it to the user

In short, SMERF behaves like a lightweight ensemble system for language models.

## 2. Problem SMERF solves

Single-model systems are simple, but they have limits:

- one model may be fast but shallow
- another may be slower but more analytical
- one response may be concise but incomplete
- another may be detailed but messy
- some prompts do not need expensive multi-model processing at all

SMERF addresses this by making a decision first:

- if the query is simple, use one cheap model
- if the query is complex, generate multiple responses, score them, combine the strongest parts, and refine the final output

This helps improve quality while controlling cost and latency.

## 3. Core goals of the project

The system was built to support the following goals:

1. Modularity
Each stage is implemented in a separate module so it can be changed without rewriting the entire system.

2. Extensibility
New model providers, evaluation strategies, or fusion approaches can be plugged in later.

3. Transparency
The API returns debug and scoring information so the system is easier to inspect.

4. Practicality
The project runs with mock clients by default, which makes development and testing possible without paid APIs.

5. Demonstrability
A simple frontend is included so the pipeline can be shown in a browser during demos.

## 4. High-level architecture

SMERF is divided into a few major layers.

### 4.1 API layer

Files:

- `main.py`
- `routers/query.py`
- `models/schemas.py`

Responsibilities:

- starts the FastAPI app
- enables CORS
- exposes `/query`
- handles global errors
- returns structured success/error responses

### 4.2 Configuration layer

File:

- `config.py`

Responsibilities:

- stores app settings
- reads environment variables
- defines model configuration objects
- provides default mock model setup

### 4.3 Service layer

Files:

- `services/llm_clients.py`
- `services/router.py`

Responsibilities:

- standardizes model access through `LLMClient`
- supports multiple providers such as mock, OpenAI-style, and local HTTP models
- classifies query complexity before orchestration begins

### 4.4 Pipeline layer

File:

- `pipeline/orchestrator.py`

Responsibilities:

- coordinates the full end-to-end workflow
- calls models in parallel for complex queries
- invokes evaluation
- fuses responses
- refines final answer
- returns structured metadata such as scores and latency

### 4.5 Evaluation and refinement layer

Files:

- `evaluators/scoring.py`
- `refinement/refiner.py`

Responsibilities:

- scores candidate outputs
- selects the strongest model response indirectly through ranking
- improves answer presentation and completeness before returning final output

### 4.6 Utility and frontend layer

Files:

- `utils/logger.py`
- `utils/async_utils.py`
- `frontend/index.html`
- `frontend/style.css`
- `frontend/script.js`

Responsibilities:

- centralized logging
- async helpers
- browser-based query interface
- rendering of final answer, scores, best model, and reasoning

## 5. How SMERF works step by step

### Stage 1: Query enters the system

A user submits a prompt through either:

- the FastAPI `/query` endpoint
- the frontend page
- the local demo in `main.py`

Example:

- `What is 2+2?`
- `Design a scalable system like Instagram`

### Stage 2: Query routing

The `QueryRouter` decides whether the prompt is simple or complex.

The router uses heuristics such as:

- word count
- complexity keywords like `design`, `architecture`, `distributed`, `compare`, `analyze`
- multi-concept detection
- optional LLM-based classification if enabled later

Output example:

```json
{
  "label": "complex",
  "confidence": 1.0,
  "debug": {
    "heuristic_score": 1.0,
    "llm_score": 1.0,
    "matched_keywords": ["design", "system", "scalable"]
  }
}
```

### Stage 3: Query path decision

If query is simple:

- one simple model is called
- result is returned directly

If query is complex:

- multiple configured models are called in parallel
- response candidates are collected
- scoring begins

### Stage 4: Parallel generation

`SMERFPipeline.generate_responses()` uses `asyncio.gather()` to call multiple model clients concurrently.

Why this helps:

- reduces total waiting time compared to sequential execution
- allows parallel comparison across models
- keeps the pipeline scalable

The system also includes:

- retry attempts
- per-model timeout handling
- failure isolation so one broken model does not crash the whole request

### Stage 5: Response evaluation

The current evaluator is a deterministic heuristic scorer.

For each response, it scores based on:

- length as a proxy for depth
- presence of reasoning-related keywords such as `because`, `therefore`, `trade-off`, `architecture`, `design`
- structural markers such as `:` or `-`
- paragraph richness

Returned format:

```json
{
  "mock-critic": {
    "score": 7,
    "reason": "reasoning terms: trade-off, design, multiple paragraphs, structured formatting"
  }
}
```

Why this matters:

- not all responses are equally useful
- scoring gives the pipeline a simple way to rank outputs
- scoring metadata helps debugging and demos

### Stage 6: Fusion

The orchestrator sorts responses by score, selects the top two, and fuses them.

Current fusion logic:

- choose top-scoring answer as primary answer
- attach second-best answer as supporting insight
- pass the fused text into refinement

This is intentionally simple right now, but the architecture allows replacement with a more advanced fusion strategy later.

### Stage 7: Refinement

The `Refiner` attempts to improve the fused answer.

Current behavior:

- if a real non-mock model is connected, it can run a self-critique prompt
- otherwise it falls back to a deterministic refinement process

After refinement, the orchestrator performs a final presentation pass to transform the answer into a cleaner user-facing structure.

### Stage 8: Final answer formatting

Complex-query answers are formatted into sections such as:

- Explanation
- Key Insights
- Trade-offs / Notes

This helps move the system away from raw debug-style output and toward presentation-ready output.

## 6. Current backend response contract

Every API response is wrapped consistently.

Successful response:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

Failure response:

```json
{
  "success": false,
  "data": null,
  "error": "message"
}
```

This is important for frontend reliability because the client can always check the same shape.

## 7. Frontend behavior

The frontend is intentionally simple and framework-free.

Features included:

- textarea for user query
- submit button with loading state
- clean result card
- complexity badge
- best model display
- model count display
- latency display
- per-model score cards
- reasoning display under "Why This Answer?"
- improved final answer formatting

Why plain HTML/CSS/JS was used:

- easier to understand in a student or research demo setting
- no build system required
- low friction for quick testing

## 8. Why this project can help

SMERF can help in several ways depending on the use case.

### 8.1 Higher answer quality

Instead of trusting one model blindly, the system compares multiple outputs.

### 8.2 Better use of resources

Simple queries do not need multi-model orchestration. Routing allows the system to save cost and time.

### 8.3 Better debugging

You can inspect:

- router decisions
- scores
- chosen best model
- fusion source models
- latency by stage

### 8.4 Research and experimentation

The modular structure makes the project useful for experimentation with:

- model routing strategies
- judge-based evaluation
- heuristic evaluation
- response fusion techniques
- refinement methods
- local versus remote model backends

### 8.5 Educational value

This project is also a strong learning example for:

- async Python systems
- API design
- AI orchestration architecture
- model ensembles
- explainable AI pipeline design

## 9. Current strengths

The project already has several strong qualities:

- modular architecture
- async orchestration
- pluggable model clients
- robust response shape
- CORS-enabled backend design
- frontend for interactive demos
- scoring and best-model selection
- clean logging and test scripts

## 10. Current limitations

The project is functional, but there are still limits.

1. Mock clients are still the default
This is great for development, but final answer quality is limited compared to real LLMs.

2. Evaluator is heuristic
The current scorer is intentionally simple and deterministic. A real judge model would be stronger.

3. Fusion is basic
Top-two concatenation is useful, but more advanced synthesis would improve final answer quality.

4. Refinement is partly heuristic
The structure is ready for richer LLM-based refinement, but default behavior is still lightweight.

5. No persistent caching or database layer yet
All work happens in memory for each request.

## 11. How it can be improved in the future

Good next steps include:

- add a `requirements.txt` or `pyproject.toml`
- support more provider backends
- implement full LLM-as-judge evaluation
- improve fusion with semantic deduplication
- add caching for repeated queries
- log cost estimates and token usage
- add formal unit tests with pytest
- serve the frontend directly from FastAPI
- support conversation memory
- add authentication for production deployment

## 12. End-to-end flow summary

A short summary of the full flow:

1. user submits a query
2. router labels it simple or complex
3. simple queries use one model
4. complex queries call multiple models in parallel
5. evaluator scores each model output
6. orchestrator ranks responses and identifies best model
7. top responses are fused
8. fused answer is refined
9. final answer is formatted for readability
10. API returns structured metadata and output
11. frontend displays the answer, scores, and reasoning

## 13. Running the system

### Start backend

```powershell
pip install fastapi uvicorn pydantic
uvicorn main:app --reload
```

### Run demo without API server

```powershell
python main.py
```

### Run tests

```powershell
python tests\test_queries.py
python tests\test_pipeline.py
```

### Open frontend

Open:

- `frontend/index.html`

and make sure the backend is already running at:

- `http://127.0.0.1:8000`

## 14. Final takeaway

SMERF is more than a single-model chatbot wrapper. It is a small but meaningful orchestration system that demonstrates how to combine routing, parallel model execution, evaluation, fusion, refinement, and frontend visibility in one coherent project.

It is useful as:

- a mini research prototype
- a systems engineering learning project
- a demo of multi-LLM orchestration
- a base for future production-oriented experimentation
