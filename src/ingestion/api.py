# src/ingestion/api.py

"""
FastAPI service exposing the ingestion pipeline over HTTP.

Additive deployment mode: the existing CLI entrypoint
(`python -m src.ingestion.pipeline file.pdf`) still works unchanged.
This is meant to run as a standalone service, paired with the separate
RAG_Project_1 project's own API, sharing one FAISS index directory
(e.g. a mounted volume set via INGESTION_INDEX_PATH on this side and
FAISS_INDEX_PATH on that side). See DOCUMENTATION.md for the full
deployment pattern.

Note: `/ingest` handlers are plain `def`, not `async def`, on purpose --
ingestion is CPU-bound (PDF parsing, chunking, embedding) and a blocking
call inside an `async def` would stall the event loop for every other
request. FastAPI runs sync path operations in a threadpool automatically.
"""

import os
import shutil
import tempfile
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.ingestion.exceptions import IngestionError
from src.ingestion.pipeline import IngestionPipeline
from src.utils.auth import require_api_key
from src.utils.logger import logger

app = FastAPI(title="Document Ingestion API", version="0.2.0")

# Without this, browsers silently block every request from any frontend
# not served from this exact origin -- including a `file://`-opened
# local HTML page (see ../frontend), which is the primary local-testing
# client this API needs to support. Defaults wide open, matching that
# use case; API-key auth (above/below) is the actual access-control
# layer once APP_ENV is set to anything other than "development" -- CORS
# alone was never meant to be that. Override via CORS_ALLOW_ORIGINS
# (comma-separated) for a real deployment that wants to restrict this.
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_origins == "*" else _cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-notifies the sibling RAG API's /reload after a successful /ingest,
# closing the gap the shared docker-compose.yml explicitly called out as
# not built yet ("call /reload yourself"). Opt-in via RAG_RELOAD_URL so
# standalone/CLI-only use of this service (no RAG API colocated) is
# unaffected -- unset means today's manual-reload behavior, unchanged.
# A failed notification does NOT fail the /ingest call: the FAISS write
# already succeeded by the time this runs, so the ingestion itself was
# real regardless of whether the sibling service happened to be
# reachable at that instant. See docs/05-roadmap.md.
_RAG_RELOAD_URL = os.getenv("RAG_RELOAD_URL")
_RAG_API_KEY = os.getenv("RAG_API_KEY")
_RAG_RELOAD_TIMEOUT_SECONDS = 10

# Per-client (by IP) rate limiting -- stricter than the RAG API's /query
# limit since each call here is a genuinely heavy CPU-bound operation
# (~3s of embedding work per document, see
# docs/reports/2026-07-26-performance-and-deployment-readiness.md),
# not just an LLM call. In-memory storage (the default, no `storage_uri`
# set) is fine for a single-process deployment. See docs/05-roadmap.md.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Built once at startup and reused across requests -- avoids reloading
# the embedding model on every call (mirrors IngestionPipeline's own
# reuse of its cleaner/chunker/embedder/indexer across ingest() calls).
pipeline = IngestionPipeline()


@app.get("/health")
def health():
    return {"status": "ok"}


def _notify_rag_reload() -> str:
    """
    Best-effort POST to the sibling RAG API's /reload. Returns a short
    status string for the /ingest response ("skipped", "ok", or
    "failed: <reason>") rather than raising -- see the module-level
    comment above for why a failure here doesn't fail the ingest itself.
    """

    if not _RAG_RELOAD_URL:
        return "skipped (RAG_RELOAD_URL not set)"

    headers = {"X-API-Key": _RAG_API_KEY} if _RAG_API_KEY else {}

    try:
        response = requests.post(
            _RAG_RELOAD_URL, headers=headers, timeout=_RAG_RELOAD_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(
            f"Ingestion succeeded but notifying the RAG API's /reload "
            f"failed ({exc}) -- the new index is on disk, but the RAG "
            f"service won't pick it up until reload is called manually "
            f"or it restarts."
        )
        return f"failed: {exc}"

    logger.info("RAG API notified of the new index (reload succeeded).")
    return "ok"


@app.post("/ingest", dependencies=[Depends(require_api_key)])
@limiter.limit("5/minute")
def ingest(
    request: Request,
    file: UploadFile = File(...),
    replace: bool = Form(
        default=False,
        description=(
            "Replace the existing index instead of adding to it "
            "(default: additive/incremental -- new documents accumulate "
            "into the existing index rather than overwriting it)."
        ),
    ),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file must have a filename")

    suffix = Path(file.filename).suffix.lower()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        chunks, analysis = pipeline.ingest(str(tmp_path), replace=replace)
    except IngestionError as exc:
        logger.error(f"Ingestion failed for '{file.filename}': {exc}")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    reload_status = _notify_rag_reload()

    return {
        "source": file.filename,
        "document_type": analysis.document_type,
        "confidence": analysis.confidence,
        "chunking_strategy": analysis.recommendation.strategy,
        "chunk_count": len(chunks),
        "report": analysis.metadata.get("ingestion_report"),
        "rag_reload": reload_status,
    }
