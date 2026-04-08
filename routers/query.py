from __future__ import annotations

from fastapi import APIRouter, Request

from models.schemas import APIResponse, QueryRequest, QueryResponse
from utils.logger import get_logger

router = APIRouter(tags=["query"])
logger = get_logger(__name__)


@router.post("/query", response_model=APIResponse)
async def query_endpoint(payload: QueryRequest, request: Request) -> APIResponse:
    logger.info("Incoming query received: %r", payload.query)
    result = await request.app.state.pipeline.run(payload.query)
    logger.info(
        "Query completed stage=%s models_used=%s latency=%s",
        result.get("stage"),
        len(result.get("responses", {})),
        result.get("latency", {}),
    )
    return APIResponse(success=True, data=QueryResponse(**result), error=None)
