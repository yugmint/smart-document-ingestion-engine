# src/utils/auth.py

import os

from fastapi import Header, HTTPException

from src.utils.logger import logger

_API_KEY = os.getenv("INGESTION_API_KEY")

if not _API_KEY:
    logger.warning(
        "INGESTION_API_KEY is not set -- /ingest is running "
        "UNAUTHENTICATED. Fine for local dev; set INGESTION_API_KEY "
        "before exposing this service beyond localhost."
    )


def require_api_key(x_api_key: str | None = Header(default=None)):
    """
    FastAPI dependency enforcing a shared-secret API key via the
    X-API-Key header. A no-op (allows everything) if INGESTION_API_KEY
    isn't configured -- see the module-level warning above.

    Intentionally minimal: one shared key, no per-client identity, no
    rotation, no rate limiting. Matters here specifically because this
    service and the sibling RAG_Project_1 API share one vector store --
    an unauthenticated /ingest can poison the index the RAG side trusts,
    making auth on that side alone pointless. See docs/05-roadmap.md.
    """

    if _API_KEY is None:
        return

    if x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
