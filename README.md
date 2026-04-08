# SMERF

Selective Multi-LLM Evaluation and Refinement System (SMERF) is a modular AI orchestration project built with Python, FastAPI, asyncio, and a lightweight frontend. It routes incoming queries based on complexity, runs one or more LLMs, evaluates their responses, fuses the strongest outputs, refines the final answer, and returns structured metadata for debugging and demos.

## What this project includes

- Async Python backend
- FastAPI API layer
- Query complexity router
- Parallel multi-model response generation
- Response evaluator
- Fusion and refinement pipeline
- Frontend built with plain HTML, CSS, and JavaScript
- Logging and simple test scripts

## Project structure

```text
SMERF/
|-- main.py
|-- config.py
|-- services/
|   |-- llm_clients.py
|   `-- router.py
|-- pipeline/
|   `-- orchestrator.py
|-- evaluators/
|   `-- scoring.py
|-- refinement/
|   `-- refiner.py
|-- routers/
|   `-- query.py
|-- models/
|   `-- schemas.py
|-- utils/
|   |-- async_utils.py
|   `-- logger.py
|-- frontend/
|   |-- index.html
|   |-- style.css
|   `-- script.js
`-- tests/
    |-- test_queries.py
    `-- test_pipeline.py
```

## Requirements

Recommended Python version:

- Python 3.11 or newer

Install dependencies:

```powershell
pip install fastapi uvicorn pydantic
```

Optional dependencies:

```powershell
pip install openai httpx
```

Install these if you want to use real OpenAI-compatible models or local HTTP model servers instead of mock clients.

## Setup

### 1. Open the project folder

```powershell
cd "G:\Users\chitr\Desktop\Folders\Sem 6\GenAI\MiniProject"
```

### 2. Install dependencies

```powershell
pip install fastapi uvicorn pydantic
```

Optional:

```powershell
pip install openai httpx
```

### 3. Configure environment variables if needed

SMERF runs with mock models by default, so configuration is optional for local testing. If you want to customize behavior, you can use environment variables such as:

- `SMERF_DEBUG=true`
- `SMERF_SIMPLE_MODEL=mock-simple`
- `SMERF_COMPLEX_MODELS=mock-simple,mock-critic`
- `SMERF_ENABLE_LLM_ROUTER=false`
- `SMERF_GENERATION_RETRIES=1`
- `SMERF_MODELS_JSON=<json config>`

Example PowerShell session:

```powershell
$env:SMERF_DEBUG="true"
$env:SMERF_ENABLE_LLM_ROUTER="false"
```

### 4. Run the backend API

```powershell
uvicorn main:app --reload
```

Backend API will be available at:

- `http://127.0.0.1:8000`

Useful endpoints:

- `GET /health`
- `POST /query`

### 5. Run the built-in demo without the API server

```powershell
python main.py
```

This runs a small local demo and prints sample pipeline outputs to the terminal.

### 6. Open the frontend

Open this file in your browser:

- `frontend/index.html`

The frontend sends requests to:

- `http://127.0.0.1:8000/query`

Make sure the FastAPI server is running before testing the UI.

## How to test

Run router tests:

```powershell
python tests\test_queries.py
```

Run pipeline tests:

```powershell
python tests\test_pipeline.py
```

## API request example

```json
{
  "query": "Design a scalable system like Instagram"
}
```

## API response format

Successful response:

```json
{
  "success": true,
  "data": {
    "query": "Design a scalable system like Instagram",
    "complexity": {
      "label": "complex",
      "confidence": 1.0,
      "debug": {}
    },
    "final_answer": "...",
    "responses": {
      "mock-simple": "...",
      "mock-critic": "..."
    },
    "scores": {
      "mock-simple": {
        "score": 5,
        "reason": "..."
      },
      "mock-critic": {
        "score": 7,
        "reason": "..."
      }
    },
    "best_model": "mock-critic",
    "fusion": {
      "answer": "...",
      "sources": ["mock-critic", "mock-simple"],
      "method": "score_ranked_fusion"
    },
    "stage": "refined",
    "latency": {
      "generation": 0.001,
      "evaluation": 0.001,
      "fusion": 0.001,
      "refinement": 0.001,
      "total": 0.004
    }
  },
  "error": null
}
```

Error response:

```json
{
  "success": false,
  "data": null,
  "error": "error message"
}
```

## Current behavior

By default, the project uses mock clients:

- `mock-simple`
- `mock-critic`

This makes the project easy to run without API keys.

## Where to read more

See [README_DETAILED.md](./README_DETAILED.md) for a full explanation of the system architecture, component responsibilities, pipeline stages, and how SMERF can be used in practice.
