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

This is one of the most important parts of SMERF because it determines whether the system should spend extra time and compute on multi-model generation or take the cheaper single-model path.

The router follows a hybrid design, but in the current project state it primarily relies on a strong heuristic layer. The code is structured so that an LLM-based router can also be enabled later.

The router examines the query using several signals:

- word count
- complexity keywords like `design`, `architecture`, `distributed`, `compare`, `analyze`
- multi-concept detection
- optional LLM-based classification if enabled later

More concretely, the router computes two internal values:

- `heuristic_score`
- `llm_score`

Then it combines them into a final routing score.

### 5.2.1 Heuristic routing logic

The heuristic layer looks for patterns that usually indicate deeper reasoning requirements.

Examples of high-signal keywords:

- `design`
- `architecture`
- `system`
- `scalable`
- `distributed`
- `compare`
- `analyze`
- `trade-offs`

The heuristic logic also checks:

- whether the prompt is longer than a threshold
- whether the prompt appears to contain multiple concepts
- whether the query starts with analytical prompts such as `how`, `why`, `compare`, `design`, or `analyze`
- whether the query already contains note-like or detailed phrasing

This matters because a short query can still be complex. For example:

- `Compare microservices vs monolith`
- `Explain transformer architecture`

These are not long, but they clearly require structured reasoning.

### 5.2.2 Multiple concept detection

The router does not only count words. It also tries to detect whether the user is asking about more than one idea at once.

Examples:

- `agentic RAG vs standard RAG`
- `design a scalable distributed cache`
- `architecture trade-offs in detail`

The router treats separators and concept markers as evidence of complexity, such as:

- `vs`
- `versus`
- `and`
- commas
- design-related and architecture-related markers appearing together

This is helpful because many engineering prompts are complex due to scope, not just length.

### 5.2.3 Weighted final routing decision

After calculating heuristic evidence, the router combines signals into a final score. Conceptually the decision process is:

1. compute `heuristic_score`
2. compute or estimate `llm_score`
3. combine them with weighted scoring
4. assign:
   - `simple` if the score is low
   - `complex` if the score is high

The project also includes a safety override in the pipeline:

- if a query contains terms like `design` or `architecture`
- and the router somehow labels it `simple`
- the system forcibly upgrades it to `complex`

This was added to reduce obvious misclassification of engineering and systems-design prompts.

### 5.2.4 Router output

The router returns structured output, not just a label.

Typical fields include:

- `label`
- `confidence`
- `debug.heuristic_score`
- `debug.llm_score`
- `debug.matched_keywords`
- `debug.multiple_concepts`
- `debug.word_count`

This makes the routing process inspectable and easier to debug during experiments.

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

The generation stage is designed to be resilient, not just parallel.

Why this helps:

- reduces total waiting time compared to sequential execution
- allows parallel comparison across models
- keeps the pipeline scalable

The system also includes:

- retry attempts
- per-model timeout handling
- failure isolation so one broken model does not crash the whole request

### 5.4.1 What actually happens during generation

For a complex query:

1. the orchestrator reads the list of complex models from configuration
2. it creates one async task per model
3. every task calls `client.generate(query)`
4. each task is wrapped with timeout handling
5. failures are logged and skipped
6. successful responses are collected into a dictionary

Returned shape:

```json
{
  "responses": {
    "mock-simple": "...",
    "mock-critic": "..."
  },
  "latency": 0.001
}
```

So the output of this stage is not yet a final answer. It is a candidate pool for evaluation.

### Stage 5: Response evaluation

The current evaluator is a deterministic heuristic scorer.

This stage is critical because it acts as a lightweight judge. Instead of trusting the first generated answer, SMERF compares all candidate answers and assigns each one a usefulness score.

The evaluator runs over the response dictionary:

```json
{
  "model_a": "response text",
  "model_b": "response text"
}
```

and produces a parallel score dictionary:

```json
{
  "model_a": {
    "score": 5,
    "reason": "..."
  },
  "model_b": {
    "score": 7,
    "reason": "..."
  }
}
```

### 5.5.1 Why evaluation exists

In multi-model systems, generation alone is not enough. If two models disagree or produce answers of very different quality, the system needs a way to rank them.

The evaluator helps SMERF answer questions like:

- Which response is more detailed?
- Which response shows stronger reasoning?
- Which response is better structured?
- Which model should become the primary answer source?

Without evaluation, fusion would be arbitrary. With evaluation, fusion becomes ranked and intentional.

### 5.5.2 Current scoring method

The current implementation does not use an LLM judge. It uses a deterministic heuristic so the project can run without external APIs.

For each response, the evaluator checks:

- length as a proxy for depth
- presence of reasoning-related keywords such as `because`, `therefore`, `trade-off`, `architecture`, `design`
- structural markers such as `:` or `-`
- paragraph richness

### 5.5.3 Exact evaluation idea

The score is built using simple additive logic. The evaluator gives points for signals that generally indicate a more useful technical answer.

Examples of signals:

1. Length
Longer responses often contain more depth, so responses over a threshold gain additional score.

2. Reasoning vocabulary
If a response includes words such as:

- `because`
- `therefore`
- `trade-off`
- `architecture`
- `design`

it is treated as more reasoning-oriented.

3. Structure
If a response uses formatting like:

- `:`
- `-`
- multiple sections
- multiple paragraphs

it is often easier to read and more likely to contain organized thought.

4. Coverage
Longer and more structured responses may receive an additional bonus if they appear to cover the topic more fully.

### 5.5.4 Evaluation output meaning

Each evaluated model gets:

- `score`: a numeric summary of usefulness
- `reason`: a short explanation of why that score was assigned

Example:

```json
{
  "mock-critic": {
    "score": 7,
    "reason": "reasoning terms: trade-off, design, multiple paragraphs, structured formatting"
  }
}
```

This score does not claim absolute truth. It is a ranking signal used inside the orchestration pipeline.

### 5.5.5 Practical impact of evaluation

This stage directly influences:

- `best_model`
- response fusion order
- which answer becomes the main explanation

In other words, evaluation is the bridge between raw generation and final answer construction.

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

This stage uses evaluation results to decide the order of fusion.

Current fusion logic:

- choose top-scoring answer as primary answer
- attach second-best answer as supporting insight
- pass the fused text into refinement

### 5.6.1 Why fusion is useful

Sometimes the top answer is the strongest overall, but the second answer still contributes something valuable:

- a missing insight
- a different phrasing
- a useful technical nuance
- a trade-off or implementation detail

Fusion helps SMERF avoid losing potentially valuable content from the runner-up response.

### 5.6.2 Current fusion mechanism

The current implementation is intentionally simple and deterministic:

1. sort all candidate responses by evaluation score
2. pick the top 2
3. create a fused intermediate answer where:
   - top 1 becomes the primary answer
   - top 2 becomes additional insight

This keeps the logic explainable and easy to inspect.

The pipeline also stores:

- fused answer text
- source models
- fusion method

So it is always clear which models contributed to the final answer.

This is intentionally simple right now, but the architecture allows replacement with a more advanced fusion strategy later.

### Stage 7: Refinement

The `Refiner` attempts to improve the fused answer.

Current behavior:

- if a real non-mock model is connected, it can run a self-critique prompt
- otherwise it falls back to a deterministic refinement process

After refinement, the orchestrator performs a final presentation pass to transform the answer into a cleaner user-facing structure.

### 5.7.1 Why refinement is separate from fusion

Fusion and refinement are not the same thing.

Fusion answers:

- Which candidate responses should be combined?

Refinement answers:

- How should that combined answer be cleaned up before showing it to the user?

Keeping them separate makes the pipeline easier to reason about and upgrade later.

### Stage 8: Final answer formatting

Complex-query answers are formatted into sections such as:

- Explanation
- Key Insights
- Trade-offs / Notes

This helps move the system away from raw debug-style output and toward presentation-ready output.

### 5.8.1 Final formatting logic

The orchestrator performs a final answer-formatting pass after refinement. This layer is presentation-focused, not model-focused.

Its job is to reorganize the refined answer into sections such as:

- `Explanation`
- `Key Insights`
- `Trade-offs / Notes`

The formatter tries to:

- extract the main explanation paragraph
- capture `Key points`-style content
- convert refinement bullets into notes or trade-offs
- fall back to a cleaned plain answer if the response is too unstructured

This makes the final answer easier for users to read in the frontend.

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
2. router analyzes complexity using heuristic and optional LLM signals
3. router returns label, confidence, and debug data
4. pipeline applies sanity overrides for obviously complex engineering prompts
5. simple queries use one model and return quickly
6. complex queries call multiple configured models in parallel
7. generation stage collects candidate responses and per-stage latency
8. evaluator scores every candidate response using deterministic heuristics
9. orchestrator ranks the candidates and identifies the best model
10. top responses are fused into one intermediate answer
11. fused answer is refined
12. refined answer is reformatted into readable user-facing sections
13. API returns structured metadata and output
14. frontend displays the answer, best model, scores, reasoning, and latency

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
