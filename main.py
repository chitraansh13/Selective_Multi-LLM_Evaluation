import asyncio
import json

from config import settings
from pipeline.orchestrator import build_default_pipeline
from utils.logger import configure_logging, get_logger

configure_logging(settings.debug)
logger = get_logger(__name__)

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.requests import Request
    from fastapi.responses import JSONResponse
    from routers.query import router as query_router
except ImportError:
    FastAPI = None
    CORSMiddleware = None
    Request = None
    JSONResponse = None
    query_router = None
    logger.warning("FastAPI is not installed; API app initialization is skipped.")

app = None
if FastAPI is not None and query_router is not None:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.pipeline = build_default_pipeline()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error for path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": str(exc),
            },
        )

    app.include_router(query_router)


if app is not None:
    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}


async def _demo() -> None:
    pipeline = build_default_pipeline()
    examples = [
        "What is retrieval augmented generation?",
        "Compare agentic RAG vs standard RAG and explain the architecture trade-offs in detail.",
    ]

    for query in examples:
        result = await pipeline.run(query)
        print("=" * 80)
        print(f"QUERY: {query}")
        print(json.dumps({"success": True, "data": result, "error": None}, indent=2))


if __name__ == "__main__":
    asyncio.run(_demo())
