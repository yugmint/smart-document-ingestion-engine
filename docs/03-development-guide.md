# 03 — Development Guide

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Requires Python `>=3.10` (`pyproject.toml`); the repo has been run under
3.11 (see `tests/__pycache__/*.cpython-311*`).

## Running the pipeline

```bash
# CLI, one document at a time
python -m src.ingestion.pipeline path/to/file.pdf
python -m src.ingestion.pipeline path/to/file.pdf --no-save-index   # dry run, no FAISS write

# HTTP service (added for standalone deployment -- see DOCUMENTATION.md §9)
uvicorn src.ingestion.api:app --reload --port 8000
curl -F "file=@path/to/file.pdf" http://localhost:8000/ingest
```

## Configuration

Every `IngestionConfig` field is overridable by env var — see
`src/ingestion/config.py` or `DOCUMENTATION.md` §3 for the full table. Most
useful during local dev:

```bash
INGESTION_CHUNK_SIZE=800 INGESTION_INDEX_PATH=./tmp_index \
    python -m src.ingestion.pipeline path/to/file.pdf
```

Remember: these are *fallback* defaults. For any document that goes through
`PDFAnalyzer`, the per-document `ChunkingRecommendation` overrides
`chunk_size`/`chunk_overlap`/`chunk_strategy` — env vars mainly matter for
unit tests and the rare document that fails classification.

## Tests

```bash
pytest tests/ -v              # fast suite -- no model download, runs in CI
pytest tests/ -v -m e2e       # + real-embeddings pipeline test (downloads a model)
```

`pyproject.toml` excludes the `e2e` marker by default (`addopts = "-m 'not e2e'"`).
Run the `e2e` suite before anything you'd call a release — it's the only
test that exercises the real embedding model + FAISS path end to end.

## Quality-checking a real document

Before trusting output on a new document type or after touching a chunker,
run the two validation scripts (see `DOCUMENTATION.md` §5 for full output
interpretation):

```bash
python scripts/validate_chunks.py path/to/file.pdf --dump-samples 5
python scripts/validate_embeddings.py path/to/file.pdf --query "a real question about the doc"
```

These caught the chunk-packing bug described in `PATCH_NOTES.md` — treat a
regression in `validate_chunks.py`'s "% within 0.5x-1.5x target" number as a
real test failure, not just informational output.

## Adding a new loader / analyzer / chunker / cleaner

Every stage follows the same shape:

1. Subclass the stage's `base.py` ABC (e.g. `BaseChunker`).
2. Implement the abstract method.
3. Register it in the stage's `factory.py` dispatch dict (or in
   `AnalyzerFactory`/`LoaderFactory` for extension-based dispatch).
4. Add a unit test alongside the existing ones in `tests/`.

You should not need to touch `pipeline.py` to add a new implementation of an
existing stage — if you find yourself editing it for that, something's off
with the factory registration instead.

## Docker

Two separate images for two separate use cases — don't merge them:

```bash
# Batch/CLI (one-shot container per document)
docker build -t ingestion .
docker run -v $(pwd)/data:/data -v $(pwd)/docs:/docs ingestion /docs/file.pdf

# Standalone API service (long-running)
docker build -f Dockerfile.api -t ingestion-api .
docker run -p 8000:8000 -v $(pwd)/data:/data ingestion-api
```

See the top-level `docker-compose.yml` (one directory up) to run the API
together with `RAG_Project_1`'s API against a shared index volume.

## Known rough edges while developing

- `.pyc` files are currently tracked in git (see `04-contributing.md`'s Git hygiene section)
  — don't be surprised by spurious diffs after running tests; it's not
  something your changes caused.
- Only `.pdf` is supported end to end — `LoaderFactory`/`AnalyzerFactory`
  will raise `UnsupportedDocumentError` for anything else.
