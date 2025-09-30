"""Pydantic schemas describing query request and response payloads."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """Represents a user-issued natural language query."""

    query: str


class QueryResponse(BaseModel):
    """Encapsulates unified response data across structured and unstructured sources."""

    query_type: str
    results: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]
    sources: List[Dict[str, Optional[str]]]
