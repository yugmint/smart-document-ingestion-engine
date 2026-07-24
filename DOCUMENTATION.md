# Ingestion Pipeline — Technical Documentation

> Companion reference to [`README.md`](README.md) (what changed / how to run) and
> [`PATCH_NOTES.md`](PATCH_NOTES.md) (the specific patch that added e2e tests,
> quality-validation scripts, and the chunk-packing fix). This document covers
> **architecture, module reference, data flow, and how the pieces fit together**,
> for anyone picking up the codebase cold.

Repo: `smart-document-ingestion-engine` (`github.com/yugmint/smart-document-ingestion-engine`)
Package: `document-ingestion`, version `0.1.1` (`v0.1.0` tagged 2026-07-24 —
briefly tagged `v1.0.0` the same day, then deliberately walked back; see §8
and `docs/05-roadmap.md`; `0.1.1` is an untagged patch fix on top), Python
`>=3.10`.

---

## 1. What this project is

A standalone, document-type-aware ingestion pipeline for RAG systems:

```
load → clean → analyze → chunk → generate metadata → embed → index
```

The distinguishing design choice is **adaptive chunking**: instead of one fixed
`chunk_size`/`chunk_overlap` for every document, a `PDFAnalyzer` inspects each
document's statistics and layout, classifies its type (research paper, book,
legal, invoice, general), and emits a `ChunkingRecommendation` that is threaded
through the rest of the pipeline and into the final chunk metadata.

This repo began life as a rewrite/hardening of an earlier, broken version of
the same pipeline — see [PATCH_NOTES.md](PATCH_NOTES.md) and README's
"What changed from the uploaded version" for the specific bugs that were fixed
(chunker never enforcing `chunk_size`/overlap, analyzer recommendations
computed but never consumed, a `document_type` metadata key collision, etc.).
Git history itself starts with the fixed code already in place (see §8) — the
"broken" version is documented but not present as a commit.

It is also the **successor to the ingestion code that used to live inside
`RAG_Project_1`** (`src/ingestion/` there). That project's in-tree ingestion
pipeline has since been removed from its working tree in favor of this
standalone, independently packaged and deployable project. See
`RAG_Project_1/DOCUMENTATION.md` §8 for the full history of that migration.

---

## 2. Architecture

### 2.1 Orchestrator — `src/ingestion/pipeline.py`

`IngestionPipeline` wires together one instance each of:

| Stage | Class | Source |
|---|---|---|
| Clean | `TextCleaner` | `CleanerFactory.build()` |
| Chunk | `HybridChunker(config)` | `src/ingestion/chunkers/hybrid_chunker.py` |
| Metadata | `MetadataGenerator()` | `src/ingestion/metadata/generator.py` |
| Embed | `Embedder.get(config)` | `src/ingestion/embedders/embedder.py` |
| Index | `FAISSIndexer()` | `src/ingestion/indexers/faiss_indexer.py` |

`ingest(file_path, save_index=True) -> tuple[list[Document], DocumentAnalysis]`:

1. **`_validate_file()`** — file exists, extension is supported (`.pdf` only),
   size ≤ `config.max_document_size_mb`.
2. **Load** — `LoaderFactory.build(file_path)` → `loader.load(file_path)`.
3. **Clean** — `self.cleaner.clean(documents)`.
4. **Analyze** — `AnalyzerFactory.build(file_path)` → `analyzer.analyze(documents, file_path)` → `DocumentAnalysis`.
5. **Chunk** — `self.chunker.chunk(documents, analysis)` (`HybridChunker`, dispatches by `analysis.recommendation.strategy`).
6. **Metadata** — `self.metadata.generate(chunks, file_path, analysis)`.
7. **Embed + Index** — `self.indexer.build(chunks, self.embeddings)`, then optionally `self.indexer.save(vectorstore, self.config.index_path)`.
8. Assembles an `IngestionReport` (source, page/chunk counts, avg chunk size,
   embedding model, vector store, elapsed time, doc type, strategy,
   confidence) and stores it at `analysis.metadata["ingestion_report"]`.

Any `IngestionError` subclass propagates as-is; any other exception is caught
and re-raised as `IngestionError` with context, so callers only ever need to
catch one exception family.

CLI entrypoint: `python -m src.ingestion.pipeline path/to/file.pdf [--no-save-index]`.

### 2.2 End-to-end data flow

```
file.pdf
  │  PDFLoader.load()
  ▼
[Document per page]  (metadata: page_number, source)
  │  TextCleaner.clean()
  ▼
[Document, whitespace-normalized]
  │  PDFAnalyzer.analyze()
  ▼
DocumentAnalysis { document_type, confidence, statistics, layout, recommendation }
  │  HybridChunker.chunk(documents, analysis)
  │  → ChunkerFactory picks a concrete chunker by recommendation.strategy
  │  → RecursiveChunker: split → pack → overlap → (merge small chunks)
  ▼
[Document chunks]
  │  MetadataGenerator.generate()
  ▼
[Document chunks + metadata: chunk_id, source, file_extension,
 character_count, word_count, token_estimate, document_type,
 language, chunking_strategy, analysis_confidence]
  │  Embedder.get(config) → EmbeddingFactory (HuggingFace sentence-transformers)
  ▼
embeddings
  │  FAISSIndexer.build() → FAISS.from_documents()
  │  FAISSIndexer.save() → vectorstore.save_local(config.index_path)
  ▼
persisted FAISS index + IngestionReport
```

### 2.3 Stage-by-stage module reference

Every stage subpackage follows the same **ABC + Factory** pattern: a `base.py`
defines the abstract interface, `factory.py` (where present) dispatches to a
concrete implementation, and one or more concrete modules do the real work.

**`analysers/`** *(intentional British spelling)*
- `base.py` — `BaseAnalyzer.analyze(documents, file_path) -> DocumentAnalysis`.
- `factory.py` — `AnalyzerFactory.build(file_path)`: `.pdf` → `PDFAnalyzer`; else `UnsupportedDocumentError`.
- `models.py` — `DocumentStatistics`, `LayoutAnalysis`, `ChunkingRecommendation`, `DocumentAnalysis`.
- `pdf_analyzer.py` — the only analyzer. Pipeline:
  1. `_extract_statistics` — page/char/word counts, estimated tokens, avg page/paragraph/sentence/line length.
  2. `_analyze_layout` — regex heuristics for headings, tables, lists, images, equations, code blocks, footnotes, references.
  3. `_classify_document` — keyword rules over the first 5 pages, checked in a **fixed priority order**: `research_paper` requires the literal word `"abstract"` *and* a detected references section; failing that, `invoice` requires `"invoice"`; failing that, `book` fires the instant `"chapter"` or `"table of contents"` appears anywhere in those 5 pages; failing that, `legal` requires `"agreement"`; otherwise `general`. **Real, confirmed misclassification found 2026-07-24:** a dense technical/statistics manual chapter (citations, equations, tables, no literal "Abstract" heading) was classified `book` purely because it opens with "Chapter 420" — the `book` check never gets to consider that it's structurally much closer to a research paper. Full mechanism and downstream impact on chunk sizing: `docs/reports/2026-07-24-academic-document-e2e-test.md` §1 in the sibling `RAG_Project_1` repo; tracked fix (corroborate against `layout.has_equations`/`has_tables` before committing to `book`) in `docs/05-roadmap.md` `v0.2.0`.
  4. `_recommend_chunking` — looks up a `_BASE_PROFILES` baseline per `document_type`, adjusts `chunk_size` based on `average_paragraph_length`, derives `chunk_overlap` (~20% of chunk_size, bounded), force-enables `split_large_chunks` if paragraphs are still >3x chunk_size. Produces a logged `rationale` string. **Caveat found the same day:** `average_paragraph_length` (computed by splitting on `"\n\n"` across the whole document) can be wildly unreliable for dense multi-column academic PDF layouts that don't reproduce blank-line paragraph breaks through `pypdf` extraction — one real 11-page paper measured 43,767 chars for this statistic. Harmless in that instance (the "paragraph too large" branch still made a reasonable call), but the input signal itself was close to meaningless. See `docs/05-roadmap.md` `v0.2.0`.
  5. `_score_confidence` — 0.05–0.99 heuristic score from classification specificity + corroborating layout signals + document length.

**`chunkers/`**
- `base.py` — `BaseChunker.chunk(documents, analysis=None) -> list[Document]`.
- `factory.py` — `ChunkerFactory.build(recommendation, config)`; `_CHUNKERS = {"recursive": RecursiveChunker, "structure": StructureChunker, "semantic": SemanticChunker, "markdown": MarkdownChunker}`; unknown strategy falls back to `RecursiveChunker` with a warning.
- `hybrid_chunker.py` — `HybridChunker`, the one `pipeline.py` actually instantiates. `chunk()` just calls `ChunkerFactory.build(...)` and delegates.
- `recursive_chunker.py` — `RecursiveChunker`, the **only fully implemented** chunking algorithm:
  - `_resolve_params()` — analysis recommendation overrides config defaults.
  - `_split()` — recursively tries separators `\n\n → \n → ". " → " " → ""` (hard character slice as last resort).
  - `_pack()` — greedily recombines undersized fragments up to `chunk_size` (the fix documented in `PATCH_NOTES.md` — without this, real PDFs with many short extracted lines produced tiny, useless chunks).
  - `_apply_overlap()` — prefixes each chunk with the trailing `chunk_overlap` characters of the previous *output* chunk, capped so overlap never pushes a chunk past `1.5 × chunk_size`.
  - `_merge_small_chunks()` (optional) — merges fragments below `min_chunk_size` into a neighbor, capped at `chunk_size × 1.2`.
- `structure_chunker.py`, `semantic_chunker.py`, `markdown_chunker.py` — **documented "V1" stubs**. Each currently just delegates to `RecursiveChunker`, passing `analysis` through. Real heading/section-aware, embedding-similarity, and fenced-code/table-aware splitting are noted as future work in their own docstrings — not implemented yet.

**`cleaners/`**
- `base.py` — `BaseCleaner.clean(documents) -> list[Document]`.
- `factory.py` — `CleanerFactory.build()` — always returns `TextCleaner()` (single implementation, no strategy dispatch).
- `text_cleaner.py` — `TextCleaner`: normalizes line endings, collapses 3+ blank lines to 2, collapses repeated spaces/tabs, strips lines. Future work noted in its docstring: header/footer removal, OCR cleanup, unicode normalization, hyphenation repair, table cleanup.

**`embedders/`**
- `embedder.py` — `Embedder.get(config)` → `EmbeddingFactory.get(model_name=config.embedding_model, normalize=config.normalize_embeddings)`. A thin indirection so `ingestion` doesn't need to know how `src.retrieval.embeddings` builds/caches models. Per `PATCH_NOTES.md`, this module existed before the fix but was never actually called by `pipeline.py`; the pipeline now goes through it instead of reaching into `retrieval` directly.

**`indexers/`**
- `faiss_indexer.py` — `FAISSIndexer` (only implementation; no factory here since FAISS is the sole vector store today):
  - `build(chunks, embeddings)` — raises `IngestionError` on empty `chunks` (refuses to build an empty index); otherwise `FAISS.from_documents(...)`.
  - `save(vectorstore, path)` — creates the output directory if missing, then `vectorstore.save_local()`.
  - `load(path, embeddings)` — loads a previously saved index (`allow_dangerous_deserialization=True` — only load indexes you trust).
  - `add(vectorstore, chunks)` — appends to an existing vectorstore for incremental ingestion.

**`loaders/`**
- `base.py` — `BaseLoader.load(file_path) -> list[Document]`.
- `factory.py` — `LoaderFactory.build(file_path)`: `.pdf` → `PDFLoader`; else `UnsupportedDocumentError`.
- `pdf_loader.py` — `PDFLoader`, using `pypdf.PdfReader`:
  - Raises `DocumentLoadError` if the file is missing or unparsable.
  - Handles encrypted PDFs by attempting an empty password; raises `DocumentLoadError` if that fails.
  - Per-page `extract_text()` failures are caught individually, logged as warnings, and the page is kept with empty text rather than crashing the whole document (`failed_pages` counter logged).
  - If total extracted text across all pages is **0 characters**, raises `EmptyDocumentError` — a signal the PDF is scanned/image-only and needs OCR, which this pipeline does not do.
  - Each page → one `Document` with `metadata={"page_number": i+1, "source": filename}`.

**`metadata/`**
- `generator.py` — `MetadataGenerator.generate(chunks, source, analysis=None)`. Per chunk, sets `chunk_id`, `source`, `file_extension` (from the path suffix — kept distinct from the analyzer's semantic `document_type` to avoid the metadata key collision described in `PATCH_NOTES.md`), `character_count`, `word_count`, `token_estimate` (`chars / 4` approximation). If `analysis` is available, also adds `document_type`, `language`, `chunking_strategy`, `analysis_confidence`.

**`models.py`** (top level) — `DocumentChunk`, `EmbeddingRecord` (framework-agnostic dataclasses, not currently produced by the active pipeline — reserved for a future API/export layer), and `IngestionReport` (the summary returned via `analysis.metadata["ingestion_report"]`).

**`exceptions.py`** — `IngestionError` (base) with subclasses `UnsupportedDocumentError`, `DocumentTooLargeError`, `DocumentLoadError`, `EmptyDocumentError`. Callers can catch broadly or by subclass.

### 2.4 Supporting packages

- **`src/retrieval/embeddings.py`** — `EmbeddingFactory.get(model_name, normalize)`, `@lru_cache(maxsize=8)`-decorated, returns `HuggingFaceEmbeddings` (via `langchain_huggingface`, falling back to `langchain_community.embeddings` on older LangChain). Caching avoids reloading the sentence-transformers model on every `IngestionPipeline()` instantiation.
  > This file (and `src/utils/logger.py`) did **not** exist in the originally uploaded package — they're minimal, working stand-ins bundled so this package runs standalone. If a fuller version exists in a "real" retrieval repo, it can be swapped in as long as it keeps the `get(model_name, normalize)` signature.
- **`src/utils/logger.py`** — single module-level `logger` (name `"ingestion"`), guards against duplicate handlers on re-import, level from `LOG_LEVEL` env var (default `INFO`), streams to stdout. Every pipeline module logs through this instead of `print()`.

---

## 3. Configuration — `src/ingestion/config.py`

`IngestionConfig` is a `@dataclass(slots=True)`, every field overridable by env var:

| Field | Env var | Default |
|---|---|---|
| `chunk_strategy` | `INGESTION_CHUNK_STRATEGY` | `"recursive"` |
| `chunk_size` | `INGESTION_CHUNK_SIZE` | `500` |
| `chunk_overlap` | `INGESTION_CHUNK_OVERLAP` | `100` |
| `separators` | — | `("\n\n", "\n", ". ", " ", "")` |
| `embedding_model` | `INGESTION_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |
| `normalize_embeddings` | `INGESTION_NORMALIZE_EMBEDDINGS` | `True` |
| `vector_store` | `INGESTION_VECTOR_STORE` | `"faiss"` |
| `index_path` | `INGESTION_INDEX_PATH` | `"vectorstore"` |
| `max_document_size_mb` | `INGESTION_MAX_DOCUMENT_SIZE_MB` | `100` |
| `supported_extensions` | — | `(".pdf",)` |

`__post_init__` validates `chunk_size > 0`, `0 <= chunk_overlap < chunk_size`,
`max_document_size_mb > 0`, raising `ValueError` otherwise.

**Important nuance:** these are *fallback* defaults. At chunk time, the
per-document `DocumentAnalysis.recommendation` (from `PDFAnalyzer`) takes
precedence over `chunk_size`/`chunk_overlap`/`chunk_strategy`. The static
config values only apply when no analysis is available (e.g. unit tests
constructing a chunker directly).

`config.vector_store` exists but there is currently no factory dispatching on
it — FAISS is the only indexer implementation, so this field is informational
only (logged into `IngestionReport.vector_store`).

---

## 4. Testing

```bash
pip install pytest
pytest tests/ -v              # fast suite — no model download
pytest tests/ -v -m e2e       # + real-embeddings pipeline test
```

`pyproject.toml` registers the `e2e` marker and excludes it by default
(`addopts = "-m 'not e2e'"`).

- **`tests/test_pdf_analyzer.py`** — unit tests for `PDFAnalyzer` against
  hand-built `Document` objects: research-paper classification → `strategy="structure"`
  + confidence > 0.5; chunk_size growing for long unbroken paragraphs
  (with `rationale` referencing avg paragraph length); chunk_size shrinking +
  `merge_small_chunks=True` for choppy/short-paragraph text; confidence
  dropping below 0.55 for a near-empty document; overlap never exceeding half
  of chunk_size.
- **`tests/test_pipeline_e2e.py`** — against the real fixture
  `tests/fixtures/sample_research_paper.pdf`:
  - `test_load_through_metadata_on_real_pdf` (always runs, no embedding model): exercises `PDFLoader → TextCleaner → PDFAnalyzer → HybridChunker → MetadataGenerator`, asserts 3 pages load, `document_type == "research_paper"`, confidence > 0.5, no chunk more than 2× the recommended `chunk_size`, and metadata correctness.
  - `test_full_pipeline_with_real_embeddings` (`@pytest.mark.e2e`, opt-in, self-skips if `sentence_transformers` isn't installed): runs the full `IngestionPipeline.ingest()` including FAISS.
- **`tests/test_recursive_chunker.py`** — unit tests directly against `RecursiveChunker`: no chunk exceeds `chunk_size × 1.5` even with `split_large_chunks=True`; analysis recommendation overrides config defaults; consecutive chunks share overlap text; `merge_small_chunks=True` eliminates tiny fragments; empty/whitespace-only documents produce no chunks.

Together, these validate the analyzer's classification/recommendation logic,
the recursive chunker's size/overlap/pack/merge correctness, and the full
load→metadata pipeline (optionally including embeddings/FAISS) against a real PDF.

---

## 5. Quality-validation scripts (`scripts/`)

Two standalone CLIs for sanity-checking a real document without writing a
one-off notebook each time (see README §"Validating chunk & embedding quality"
for full detail and example output interpretation):

- **`scripts/validate_chunks.py`** — fast/offline, no embedding model. Runs
  `PDFLoader → TextCleaner → PDFAnalyzer → HybridChunker → MetadataGenerator`
  and reports chunk-size distribution vs. the recommended target, % of chunks
  within 0.5×–1.5× of target, near-empty/duplicate chunk detection,
  overlap-presence between consecutive chunks, and a mid-sentence-boundary
  heuristic. `--dump-samples N` prints N full random chunks for manual review.
  This is the script that caught the chunk-packing bug described in
  `PATCH_NOTES.md` — re-run it after any chunker change.
- **`scripts/validate_embeddings.py`** — loads the real embedding model.
  Vector sanity (NaN/zero vectors, norm distribution), pairwise cosine
  similarity spread, near-duplicate embedding detection (cosine > 0.999),
  `--query "..."` for a retrieval smoke test, `--eval eval_set.json` for a
  labeled hit-rate / recall@k proxy check.

---

## 6. Dependencies

| Library | Purpose |
|---|---|
| `langchain-core` | `Document` — the common data structure across every stage |
| `langchain-community` | `FAISS` vectorstore wrapper; fallback `HuggingFaceEmbeddings` import |
| `langchain-huggingface` | Preferred `HuggingFaceEmbeddings` source |
| `sentence-transformers` | Embedding model backend |
| `faiss-cpu` | Vector similarity search / index storage |
| `pypdf` | PDF parsing / text extraction |
| `pytest` | Testing (dev only) |

---

## 7. Deployment

`Dockerfile`: based on `python:3.11-slim`, installs `build-essential` (needed
for `faiss`/`pypdf` wheel builds), installs `requirements.txt`, copies only
`src/` into the image (no tests/scripts), sets `LOG_LEVEL=INFO` and
`INGESTION_INDEX_PATH=/data/vectorstore` as defaults, declares a `/data`
volume. Entrypoint is `python -m src.ingestion.pipeline` — this is a
**CLI-style batch container**, not a long-running service:

```bash
docker build -t ingestion .
docker run -v $(pwd)/data:/data -v $(pwd)/docs:/docs ingestion /docs/file.pdf
```

---

## 8. Git history

Repo: `github.com/yugmint/smart-document-ingestion-engine`.

| Commit | Summary |
|---|---|
| `064b933` | Initial commit — `.gitignore` only, no source yet. |
| `e07521c` | Extend `.gitignore` for local test-data PDFs. |
| `e3dbd6d` | **Payload commit** — entire working pipeline added in one commit (94 files): all of `src/ingestion/*`, `src/retrieval/embeddings.py`, `src/utils/logger.py`, `Dockerfile`, `README.md`, `PATCH_NOTES.md`, `pyproject.toml`, `requirements.txt`, `scripts/`, tests + fixtures. The pipeline arrives already fixed — there's no separate "broken" commit in this repo's history; that prior state is documented in `PATCH_NOTES.md`/README but predates this repo (it was an externally uploaded zip). |
| `6baf90d` | Merge commit reconciling two initial-commit lines. |
| `8483c98` | "Stop tracking local test data" — removes large real-world PDFs accidentally committed in `e3dbd6d`. At the time, didn't touch `tests/fixtures/sample_research_paper.pdf` (used by `test_pipeline_e2e.py`) since that file was never committed in the first place — see `a01b0bc` below, which fixed this. |
| `d4eb46a` | Untracked 39 `.pyc` files that had been wrongly git-tracked despite `.gitignore` covering `__pycache__/` since the first commit. |
| `1ca2667` | **feat:** standalone FastAPI service (`src/ingestion/api.py`) with `X-API-Key` auth — see §9. |
| `6706b3a` | **docs:** added this `DOCUMENTATION.md` and the numbered `docs/` set. |
| `a01b0bc` | **fix:** `tests/fixtures/sample_research_paper.pdf` was never actually committed (despite `test_pipeline_e2e.py` referencing it) — a fresh clone would fail that test. Tracked it, plus two related path-string fixes in `test_pdf_analyzer.py`. |
| `0b77220` | **chore:** added `[project]` version metadata, restructured `docs/05-roadmap.md`/`06-release-notes.md` into version milestones. |
| `f87aba6` | **HEAD.** **chore:** retagged `v0.1.0` — had briefly tagged `v1.0.0` the same day on the reasoning that the core pipeline was "done," then reconsidered: one document's worth of real-world validation wasn't enough to back a 1.0 claim. See `docs/05-roadmap.md`. |
| `2cf727e`, `cbb8e0a`, `6aee4c5` | **docs:** findings from real-world validation against two more documents in the sibling `RAG_Project_1` repo — the `book`/`research_paper` misclassification (§2.3 above) and the `average_paragraph_length` reliability issue, including a same-day controlled experiment that ruled the misclassification out as the cause of a set of retrieval failures it was initially suspected of causing. |

The `_pack()` fix (chunk-packing bug — see §2.3 `recursive_chunker.py` and
`PATCH_NOTES.md`) was found via `scripts/validate_chunks.py` during review: an
early version produced 38 chunks averaging ~215 chars against a 630-char
target (3% within the 0.5×–1.5× range); after the fix, the same document
produces 8 chunks averaging ~520 chars (75% within range).

---

## 9. API deployment (`src/ingestion/api.py`)

Alongside the CLI (`python -m src.ingestion.pipeline`), a FastAPI service
exposes ingestion over HTTP for deployment as a standalone service — meant to
be paired with `RAG_Project_1`'s own API, both pointed at the same shared
FAISS index directory. This is additive; the CLI still works unchanged.

- `GET /health` — unauthenticated (health checks shouldn't need a key).
- `POST /ingest` (multipart file upload) — runs the same
  `IngestionPipeline.ingest()` used by the CLI, writes the index to
  `config.index_path` (`INGESTION_INDEX_PATH`), and returns the
  `IngestionReport` as JSON. Built as a sync endpoint on purpose — ingestion
  is CPU-bound, and FastAPI runs sync path operations in a threadpool so a
  slow ingest doesn't block other requests' event loop. Requires an
  `X-API-Key` header matching `INGESTION_API_KEY` (`src/utils/auth.py`); if
  that env var isn't set, the endpoint runs unauthenticated with a startup
  warning. This matters more than it might seem: this service and the
  sibling RAG API share one vector store, so an unauthenticated `/ingest`
  can poison the data the "secured" RAG API trusts.

Run locally:

```bash
INGESTION_API_KEY=your-shared-secret uvicorn src.ingestion.api:app --reload --port 8000
curl -H "X-API-Key: your-shared-secret" -F "file=@path/to/file.pdf" http://localhost:8000/ingest
```

Containerized (separate from the existing batch `Dockerfile`, which stays
CLI/one-shot):

```bash
docker build -f Dockerfile.api -t ingestion-api .
docker run -p 8000:8000 -e INGESTION_API_KEY=... -v $(pwd)/data:/data ingestion-api
```

See the top-level `docker-compose.yml` (one directory up, alongside
`RAG_Project_1/`) for running both services together against a shared named
volume, including the `/reload` handshake with the RAG API.

---

## 10. Known limitations / not-yet-implemented

- Only `.pdf` is supported end-to-end (loader + analyzer both hard-code this).
- `StructureChunker`, `SemanticChunker`, `MarkdownChunker` are stubs — all
  three currently just delegate to `RecursiveChunker`.
- `CleanerFactory` has no strategy dispatch — only `TextCleaner` exists.
- `config.vector_store` is not actually used to select an indexer — FAISS is
  hard-wired as the only implementation.
- `models.py`'s `DocumentChunk` / `EmbeddingRecord` dataclasses are defined
  but not produced anywhere in the active pipeline (langchain `Document` is
  used throughout instead) — reserved for a possible future API layer.
- No OCR support — scanned/image-only PDFs raise `EmptyDocumentError` rather
  than being processed.
- `_classify_document`'s priority-ordered keyword checks can misclassify a
  dense technical/reference document as `book` instead of `research_paper`
  purely from the word "chapter" — see §2.3. Real, confirmed, not yet fixed.
- `average_paragraph_length` can be unreliable for dense multi-column
  academic PDF layouts — see §2.3.
- No rate limiting on `POST /ingest` (§9) — only auth. Since this service
  shares a vector store with the sibling `RAG_Project_1` API, an
  unthrottled `/ingest` is a real exposure if this is ever reachable
  beyond a trusted network.
