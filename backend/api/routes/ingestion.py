"""API routes for data ingestion workflows."""

from typing import List
import logging
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import tempfile

from api.services.schema_discovery import schema_discovery
from api.services.document_processor import DocumentProcessor

logger = logging.getLogger("ingestion")
router = APIRouter()
# Module-level processor to persist job state across requests
processor = DocumentProcessor()


class ConnectRequest(BaseModel):
    connection_string: str


def _mask_connection_string(raw: str) -> str:
    """Return a safe-to-log version of the DB URL with password masked.

    Best-effort; if parsing fails, avoid echoing full secret.
    """
    try:
        from sqlalchemy.engine.url import make_url

        url = make_url(raw)
        # SQLAlchemy URL objects are immutable; use .set() to create a masked copy
        masked = url.set(password="***")
        return str(masked)
    except Exception:
        # Fallback: only show driver and host portion if possible
        try:
            # crude host extraction without exposing credentials
            at = raw.rfind("@")
            tail = raw[at + 1 :] if at != -1 else raw
            # Trim any query params
            q = tail.find("?")
            if q != -1:
                tail = tail[:q]
            return f"<masked>://{tail}"
        except Exception:
            return "<masked>"


@router.post("/api/connect-database")
async def connect_database(payload: ConnectRequest):
    """
    Connect to database and auto-discover schema.
    Supports only SQLite and PostgreSQL. Returns:
    { status: 'ok', schema: {...} } on success, or raises HTTPException on error.
    """
    connection_string = payload.connection_string
    if not connection_string or not isinstance(connection_string, str):
        raise HTTPException(status_code=400, detail="connection_string is required")

    safe_cs = _mask_connection_string(connection_string)
    discovery = schema_discovery
    try:
        logger.info("Connecting to database: %s", safe_cs)
        schema = discovery.analyze_database(connection_string)
    except ValueError as ve:
        logger.warning("Invalid connection string: %s | error=%s", safe_cs, ve)
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except ConnectionError as ce:
        logger.exception("Database connection failed for %s: %s", safe_cs, ce)
        detail = str(ce)
        raise HTTPException(status_code=502, detail=detail) from ce
    except Exception as exc:
        logger.exception("Unexpected error during connect for %s", safe_cs)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    return {"status": "ok", "schema": schema}


@router.post("/api/upload-documents")
async def upload_documents(files: List[UploadFile]):
    """
    Accept multiple document uploads and start ingestion job.
    Returns: { status: 'ok', job_id }
    """
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")

    # Persist to temp dir for the worker to read
    tmpdir = Path(tempfile.mkdtemp(prefix="ingest_"))
    saved_paths: List[Path] = []
    for f in files:
        # We only trust filename for demo; in production sanitize/validate more
        dest = tmpdir / f.filename
        content = await f.read()
        dest.write_bytes(content)
        saved_paths.append(dest)

    job_id = processor.start_job(saved_paths)
    logger.info(
        "Started ingestion job %s with %d files in %s", job_id, len(saved_paths), tmpdir
    )
    return {"status": "ok", "job_id": job_id}


@router.get("/api/ingestion-status/{job_id}")
async def get_status(job_id: str):
    """
    Return progress of document processing
    """
    status = processor.get_status(job_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="job_not_found")
    return status


@router.get("/api/download-document/{doc_id}")
async def download_document(doc_id: str):
    """Download the original document by its ID (filename)."""
    path = processor.get_file_path(doc_id)
    if not path:
        raise HTTPException(status_code=404, detail="document_not_found")
    return FileResponse(path, filename=doc_id)
