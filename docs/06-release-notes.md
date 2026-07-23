# 06 — Release Notes

No git tags exist yet (see `04-contributing.md`'s Git hygiene section), so this is organized
by commit rather than by version tag. Once `v1.0.0` is tagged, switch this
file to a standard [Keep a Changelog](https://keepachangelog.com/) format
anchored on tags instead.

## Unreleased (working tree, not yet committed)

Added while scoping standalone-service deployment for this pipeline
alongside the separate `RAG_Project_1` API:

- `src/ingestion/api.py` — FastAPI service (`GET /health`, `POST /ingest`)
  wrapping the existing `IngestionPipeline`, for deployment as a
  long-running service rather than a one-shot CLI container.
- `Dockerfile.api` — separate image for the API, alongside the existing
  batch-mode `Dockerfile` (unchanged).
- `DOCUMENTATION.md` — full architecture/module reference.
- `docs/` — this directory.
- `requirements.txt` — added `fastapi`, `uvicorn`, `python-multipart`.

**Prod-readiness pass on the sibling `RAG_Project_1` (2026-07-24)** touched
this repo too, since the two share a vector store:

- `src/utils/auth.py` (new) — `POST /ingest` now requires an `X-API-Key`
  header matching `INGESTION_API_KEY` (no-op if that env var is unset, with
  a startup warning). Added specifically because an unauthenticated
  `/ingest` would let anyone poison the index the RAG API's own new auth
  was meant to protect. See `05-roadmap.md`.
- Used directly, for real, to rebuild `RAG_Project_1`'s production index
  after discovering its existing "newer" index had the exact packing/
  metadata bugs described in `PATCH_NOTES.md` — see `RAG_Project_1/DOCUMENTATION.md`
  §8 for the full story. Good validation that this pipeline's fixes hold up
  against a real 136-page document (produced 314 well-formed chunks,
  85–841 chars, correctly separated `document_type`/`file_extension`
  metadata).

## 2026-07-22 — Pipeline hardening & standalone packaging

- `8483c98` — Stopped tracking accidentally-committed real test PDFs
  (`.gitignore` already covered them; the files themselves needed removing
  too).
- `6baf90d` — Merged two parallel initial-commit lines.
- `e3dbd6d` — **The real payload commit.** Landed the entire working
  ingestion pipeline in one commit: all of `src/ingestion/*` (loaders,
  cleaners, analysers, chunkers, metadata, embedders, indexers), the
  `src/retrieval/embeddings.py` and `src/utils/logger.py` stand-ins (not
  present in the originally uploaded package this repo hardens), a typed
  `IngestionError` hierarchy, tests (unit + e2e), the two quality-validation
  scripts, `Dockerfile`, and `README.md`/`PATCH_NOTES.md` documenting a
  detailed set of fixes relative to an earlier broken version (not itself
  present in this repo's git history — see `PATCH_NOTES.md` for the specific
  bugs: chunker never enforcing `chunk_size`/overlap, analyzer
  recommendations computed but never consumed, a `document_type` metadata
  key collision, and others).
- `e07521c` — Extended `.gitignore` for local test-data PDFs.

## 2026-07-22 — Initial commit

- `064b933` — Repository created with `.gitignore` only.

## Known-but-undocumented change: the chunk-packing fix

Not tied to a specific commit in this history (it's folded into `e3dbd6d`'s
single payload commit), but significant enough to call out on its own:
`RecursiveChunker._pack()` was added after `scripts/validate_chunks.py`
caught fragments landing far below the target chunk size on real PDFs (38
chunks averaging ~215 chars against a 630-char target). After the fix: 8
chunks averaging ~520 chars, 75% within the 0.5x-1.5x target range. See
`PATCH_NOTES.md` for the full before/after.
