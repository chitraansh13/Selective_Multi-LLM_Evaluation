from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User query to process.")


class QueryResponse(BaseModel):
    query: str
    complexity: dict = Field(default_factory=dict)
    final_answer: str | None = None
    responses: dict = Field(default_factory=dict)
    scores: dict = Field(default_factory=dict)
    best_model: str | None = None
    fusion: dict = Field(default_factory=dict)
    stage: str
    latency: dict = Field(default_factory=dict)


class APIResponse(BaseModel):
    success: bool
    data: QueryResponse | None = None
    error: str | None = None
