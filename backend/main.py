"""FastAPI application entry point for the NLP query engine backend."""

import logging
from logging import StreamHandler, Formatter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import ingestion, query, schema


def create_app() -> FastAPI:
    """Instantiate the FastAPI application and register API routes."""
    # Configure logging (root + uvicorn family) for concise INFO-level output
    root = logging.getLogger()
    if not root.handlers:
        handler = StreamHandler()
        handler.setFormatter(Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.INFO)
    application = FastAPI(title="NLP Query Engine API")

    # CORS for local frontend dev and simple deployments
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    application.include_router(ingestion.router)
    application.include_router(query.router)
    application.include_router(schema.router)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)