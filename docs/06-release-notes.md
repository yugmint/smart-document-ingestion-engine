# 06 — Release Notes

[Keep a Changelog](https://keepachangelog.com/)-style, anchored on tags.
`v0.1.0` is the first tag this repo has — everything before it is
reconstructed from `git log`, without version numbers of its own (it was
never tagged at the time).

**Note:** this was briefly tagged `v1.0.0` on 2026-07-24, then retagged
`v0.1.0` the same day — reconsidered that a 1.0 claim was premature (one
document's worth of real-world validation, several roadmap items still
open). See `05-roadmap.md`.

## [0.1.2] — 2026-07-24

**Fixed:**
- `PDFAnalyzer._classify_document`'s `"chapter"` → `book` rule fired on
  the keyword alone, with no corroboration — a dense technical/reference
  document (equations, tables, citations) that happens to open with
  "Chapter N" got the narrative-prose `book` chunking profile
  (`chunk_size=800`, `split_large_chunks=False`) instead of something
  closer-fitting. Now requires the document to *not* also look technical
  (`layout.has_equations`/`has_tables` both false) before committing to
  `book`; otherwise falls through toward `general`. Verified against the
  real `Factor_Analysis.pdf` that surfaced this — now classifies
  `general`, previously `book`. Classification-correctness fix only; a
  same-day controlled experiment (2026-07-24 academic-document report,
  §5) already ruled this out as the cause of that report's retrieval
  failures, which reranking (in the sibling `RAG_Project_1`) fixed
  instead.

## [0.1.1] — 2026-07-24

Patch fix, first version bumped under standard semver rather than the
project's earlier flat sequence.

**Fixed:**
- `scripts/validate_chunks.py --dump-samples` crashed on Windows
  (`UnicodeEncodeError`) the moment a sampled chunk contained a character
  outside cp1252 (found via a real "χ" from a chi-square formula) —
  `print()` inherited the console's default encoding. Fixed by
  reconfiguring `sys.stdout` to UTF-8 with `errors="replace"` at the top
  of `main()`; no longer depends on `PYTHONIOENCODING` being set manually.

## [0.1.0] — 2026-07-24

First tagged version. Core pipeline logic (`e3dbd6d`, 2026-07-22) had
already been solid for two days; this tag reflects standalone-service
deployment, git hygiene fixes, and full documentation landing on top of
it.

**Added:**
- Standalone FastAPI service (`src/ingestion/api.py`): `GET /health`,
  `POST /ingest` (multipart upload, runs the existing `IngestionPipeline`)
  — behind `X-API-Key` auth (`INGESTION_API_KEY`). Deployable alongside
  `RAG_Project_1`'s own API over a shared FAISS volume
  (`docker-compose.yml`). (`1ca2667`)
- `src/utils/auth.py` — added specifically because an unauthenticated
  `/ingest` would let anyone poison the index the sibling RAG API's own
  auth was meant to protect. (`1ca2667`)
- `Dockerfile.api` — separate image for the API, alongside the existing
  batch-mode `Dockerfile` (unchanged). (`1ca2667`)
- Full documentation set: `DOCUMENTATION.md` + numbered `docs/`.
  (`6706b3a`)

**Fixed:**
- 39 `.pyc` files that were wrongly git-tracked despite `.gitignore`
  covering `__pycache__/` since the first commit. (`d4eb46a`)
- `tests/fixtures/sample_research_paper.pdf` — the e2e test's fixture was
  never actually committed (a fresh clone would fail
  `test_load_through_metadata_on_real_pdf` with a missing-file error);
  now tracked, along with two related path-string test fixes.
  (`a01b0bc`)

**Validated:**
- Used directly, for real, to rebuild the sibling `RAG_Project_1`'s
  production index after discovering its existing "newer" index had the
  exact packing/metadata bugs this pipeline was built to fix — see
  `RAG_Project_1/DOCUMENTATION.md` §8. Produced 314 well-formed chunks
  from a real 136-page document, 85–841 chars each, correctly separated
  `document_type`/`file_extension` metadata. Good real-world confirmation
  that the fixes documented in `PATCH_NOTES.md` hold up outside the test
  suite.

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
