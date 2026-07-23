# Document Ingestion Pipeline

Load -> clean -> analyze -> chunk -> generate metadata -> embed -> index.

## Documentation

This README covers what changed and how to run things day to day. For
more:

- [`DOCUMENTATION.md`](DOCUMENTATION.md) — full architecture and
  module-by-module reference.
- [`docs/`](docs/) — deeper-dive docs: [architecture](docs/01-architecture.md),
  [ingestion best practices](docs/02-ingestion-best-practices.md),
  [development guide](docs/03-development-guide.md),
  [contributing](docs/04-contributing.md), [roadmap](docs/05-roadmap.md),
  [release notes](docs/06-release-notes.md),
  [design decisions](docs/07-design-decisions.md).
- [`PATCH_NOTES.md`](PATCH_NOTES.md) — the specific patch that added e2e
  tests, the quality-validation scripts, and the chunk-packing fix.

This pipeline pairs with a separate RAG project (`RAG_Project_1`, a sibling
repo) that reads the FAISS index this pipeline produces — see
`docs/01-architecture.md` for how the two connect.

## What changed from the uploaded version

This is a fixed/hardened version of the pipeline you uploaded. Full
findings are summarized below; see inline comments in the source for
the "why" behind each change.

### Chunking (was broken)
- `RecursiveChunker` previously split text once on the first separator
  found anywhere in the document and returned the pieces as "chunks" --
  it never enforced `chunk_size`, never applied overlap, and wasn't
  actually recursive. It's now a real recursive splitter: it tries
  separators in priority order (paragraph → line → sentence → word →
  character), recurses into any piece still over `chunk_size`, then
  re-joins pieces with a trailing-context overlap.
- The analyzer's per-document `chunk_size` / `chunk_overlap` /
  `strategy` recommendation was computed and logged but never actually
  used -- the chunker read static values from `IngestionConfig`
  instead. It's now threaded through end-to-end
  (`analysis.recommendation` → `HybridChunker` → `ChunkerFactory` →
  concrete chunker).
- `merge_small_chunks` / `split_large_chunks` were flags the analyzer
  produced but no chunker consulted. Both are now implemented:
  small trailing fragments get merged into a neighbor, and paragraphs
  far larger than the chunk window get hard-split even when the
  document-type profile would otherwise preserve them whole.
- `BaseChunker.chunk()`'s abstract signature didn't match any real
  implementation (`documents` vs `documents, analysis`) -- fixed.

### Analyzer / recommendation engine (was static)
- `_recommend_chunking` used to be a pure `document_type` lookup table;
  the `DocumentStatistics` it computed (avg paragraph/sentence length,
  word count) were calculated and never used. Sizing now adjusts from
  the per-type baseline based on actual paragraph length, with a
  `rationale` string logged for observability.
- Added a `confidence` score (0-1) reflecting how much to trust the
  classification (and therefore the recommendation) -- e.g. a 3-word
  document gets a low-confidence "general" classification rather than
  silently being treated the same as a well-classified one. This
  finally populates the `confidence` field `pipeline.py` was already
  trying to log via a dead `hasattr` check.
- Added the missing `invoice` recommendation branch (previously fell
  through to `general` silently).

### Metadata
- Fixed a real naming collision: the metadata generator wrote
  `document_type` = file extension ("pdf"), while the analyzer's
  `DocumentAnalysis.document_type` = semantic classification
  ("research_paper"). Same key, two unrelated meanings. Now
  `file_extension` and `document_type` are distinct, and the semantic
  classification / chunking strategy / confidence are included when
  analysis is available.

### General prod-readiness
- **Imports**: fixed throughout (see "Import path note" below).
- **Error handling**: `ingest()` now validates the file up front
  (exists, supported extension, under `max_document_size_mb`) and
  wraps every stage so failures raise a typed `IngestionError` instead
  of an arbitrary exception with no context. See `exceptions.py`.
- **PDF loading**: handles missing files, encrypted PDFs (tries an
  empty password), per-page extraction failures (logs + continues
  instead of crashing the whole document), and raises a clear error
  for scanned/image-only PDFs that yield no text at all (needs OCR,
  not this pipeline).
- **FAISS indexing**: creates the output directory if missing, refuses
  to silently build an empty index, and adds `load()`/`add()` for
  incremental indexing instead of always rebuilding from scratch.
- **Config**: validates itself (`chunk_overlap < chunk_size`, etc.) and
  is overridable via env vars (`INGESTION_CHUNK_SIZE`,
  `INGESTION_INDEX_PATH`, `INGESTION_EMBEDDING_MODEL`, ...) for
  container deployments.
- **Logging**: centralized, configurable via `LOG_LEVEL`, no more
  inline `print`-style debugging.
- **Dead code removed**: `ingestion_pipeline.py` (100% commented-out
  legacy code) is gone. `embedders/embedder.py` was defined but never
  called -- it's now the actual call path `pipeline.py` uses instead
  of reaching into `retrieval` directly.
- Added `tests/` (pytest) covering the chunker and analyzer fixes, a
  `Dockerfile`, `requirements.txt`, and a CLI entrypoint
  (`python -m src.ingestion.pipeline some.pdf`).

### Import path note
Every file imports from `src.ingestion.*`, `src.retrieval.*`, and
`src.utils.*`. Only the `ingestion` package itself was in your zip --
`src/retrieval/embeddings.py` (`EmbeddingFactory`) and
`src/utils/logger.py` didn't exist anywhere in the upload. I've
bundled minimal, working versions of both under `src/retrieval/` and
`src/utils/` so this package runs standalone and the tests pass. If
your real repo already has fuller versions of those two files
elsewhere, drop `src/ingestion/` in and keep your existing
`retrieval`/`utils`, as long as `EmbeddingFactory.get(model_name,
normalize)` keeps that signature.

## Still marked "V1" / not fixed (by design)
`StructureChunker`, `SemanticChunker`, and `MarkdownChunker` are still
documented fallbacks to `RecursiveChunker` -- their docstrings already
said this was future work (real heading/section-aware splitting,
embedding-similarity boundaries, fenced-code/table-aware markdown
splitting). They now at least benefit from the fixed, recommendation-aware
`RecursiveChunker` underneath, but true structure/semantic/markdown-aware
splitting is still not implemented.

## Running

```bash
pip install -r requirements.txt
python -m src.ingestion.pipeline path/to/file.pdf
```

### As a standalone API

For deployment alongside `RAG_Project_1`'s own API, sharing one FAISS index
via a mounted volume (see the top-level `docker-compose.yml`, one directory
up):

```bash
INGESTION_API_KEY=your-shared-secret uvicorn src.ingestion.api:app --reload --port 8000
curl -H "X-API-Key: your-shared-secret" -F "file=@path/to/file.pdf" http://localhost:8000/ingest
```

`INGESTION_API_KEY` is optional for local dev (omit it and the endpoint runs
unauthenticated with a warning) but required before exposing this beyond
localhost — this service shares a vector store with the RAG API, so an
unauthenticated `/ingest` can poison data the RAG side trusts.

See `docs/01-architecture.md` and `DOCUMENTATION.md` §9 for details.

## Testing

```bash
pip install pytest
pytest tests/ -v
```

## Validating chunk & embedding quality

Two standalone scripts under `scripts/` let you sanity-check a real
document without writing a one-off notebook every time.

### Chunking quality (no embedding model needed, fast/offline)

```bash
python scripts/validate_chunks.py path/to/file.pdf
python scripts/validate_chunks.py path/to/file.pdf --dump-samples 5
```

Reports: chunk-size distribution vs the recommended target, how many
chunks land within 0.5x-1.5x of that target, near-empty/duplicate
chunks, whether `chunk_overlap` is actually showing up between
consecutive chunks, and a "mid-sentence boundary" heuristic rate.
`--dump-samples N` prints N full random chunks so you can eyeball
them directly -- automated metrics catch structural problems, but
"does this chunk actually make sense on its own" still needs a human
read.

This is exactly how a real packing bug was caught during review: an
early version of `RecursiveChunker` split text into fragments <=
chunk_size but never recombined small fragments back up toward the
target -- on a PDF with lots of short extracted lines this produced
38 chunks averaging ~215 chars against a 630-char target (3% within
range). `RecursiveChunker._pack()` now greedily combines consecutive
fragments up to `chunk_size` before overlap is applied; the same
document now produces 8 chunks averaging ~520 chars (75% within
range). Re-run `validate_chunks.py` after any chunker change --
it'll catch a regression like this immediately.

### Embedding & retrieval quality (loads the real embedding model)

```bash
# Structural sanity: NaNs, zero vectors, norm distribution,
# near-duplicate embeddings, pairwise similarity spread.
python scripts/validate_embeddings.py path/to/file.pdf

# Retrieval smoke test: embed a real question, see what comes back.
python scripts/validate_embeddings.py path/to/file.pdf \
    --query "what does section 3 say about X?"

# Labeled hit-rate check over a small eval set you maintain:
python scripts/validate_embeddings.py path/to/file.pdf --eval eval_set.json
```

`eval_set.json` format:

```json
[
  {"query": "what chunking strategies were evaluated?", "expected_keyword": "chunking"},
  {"query": "who are the authors?", "expected_keyword": "author"}
]
```

This checks whether the expected keyword shows up anywhere in the
top-k retrieved chunks -- a lightweight proxy for recall@k that
doesn't require a fully labeled ground-truth dataset. It's meant to
grow over time: every time you find a retrieval failure worth
guarding against, add it as a case here.

Things worth specifically looking for in the output:
- **near-duplicate embeddings** across genuinely different chunks
  usually means chunks are too short/repetitive, or the wrong model
  is loaded.
- **norm mean far from 1.0** when `normalize_embeddings=True` means
  normalization isn't actually happening -- check the embedding
  factory wiring.
- **pairwise similarity mean > 0.9** across the whole document means
  the embedding space has no spread -- retrieval can't discriminate
  between chunks, which usually means something upstream is wrong
  (e.g. a broken tokenizer, or degenerate/near-identical chunks).

## Docker

Batch/CLI (one-shot container per document):

```bash
docker build -t ingestion .
docker run -v $(pwd)/data:/data -v $(pwd)/input_docs:/input ingestion /input/file.pdf
```

(`./input_docs` here is wherever you keep the PDFs you're ingesting — kept
distinct from `./docs/`, which is this repo's own documentation.)

Standalone API (long-running service, uses `Dockerfile.api` instead):

```bash
docker build -f Dockerfile.api -t ingestion-api .
docker run -p 8000:8000 -v $(pwd)/data:/data ingestion-api
```
