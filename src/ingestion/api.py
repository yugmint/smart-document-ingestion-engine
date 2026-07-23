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

import shutil
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile

from src.ingestion.exceptions import IngestionError
from src.ingestion.pipeline import IngestionPipeline
from src.utils.auth import require_api_key
from src.utils.logger import logger

app = FastAPI(title="Document Ingestion API", version="0.2.0")

# Built once at startup and reused across requests -- avoids reloading
# the embedding model on every call (mirrors IngestionPipeline's own
# reuse of its cleaner/chunker/embedder/indexer across ingest() calls).
pipeline = IngestionPipeline()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest", dependencies=[Depends(require_api_key)])
def ingest(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file must have a filename")

    suffix = Path(file.filename).suffix.lower()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        chunks, analysis = pipeline.ingest(str(tmp_path))
    except IngestionError as exc:
        logger.error(f"Ingestion failed for '{file.filename}': {exc}")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "source": file.filename,
        "document_type": analysis.document_type,
        "confidence": analysis.confidence,
        "chunking_strategy": analysis.recommendation.strategy,
        "chunk_count": len(chunks),
        "report": analysis.metadata.get("ingestion_report"),
    }
