"""API route for exposing discovered schema metadata."""

from fastapi import APIRouter, HTTPException
from api.services.schema_discovery import schema_discovery

router = APIRouter()


@router.get("/api/schema")
async def get_schema():
    """Return the current discovered schema for visualization.

    Returns { status: 'ok', schema: {...} } if available, or 404 if no schema
    was previously discovered via /api/connect-database.
    """
    schema = schema_discovery.schema
    if not schema:
        raise HTTPException(status_code=404, detail="schema_not_available")
    return {"status": "ok", "schema": schema}
