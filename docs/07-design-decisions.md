# 07 — Design Decisions

Short ADR-style entries: the decision, the alternative considered, and why
the chosen option won. Not exhaustive — only decisions that would confuse a
reader if left unexplained.

---

### Adaptive, per-document chunking instead of one global chunk size

**Decision:** `PDFAnalyzer` classifies each document and emits a
`ChunkingRecommendation` (size, overlap, strategy, merge/split flags) that
overrides the static `IngestionConfig` defaults for that document.

**Alternative considered:** one fixed `chunk_size`/`chunk_overlap` for every
document (this is what `IngestionConfig` still provides as a fallback).

**Why:** a research paper's dense paragraphs and an invoice's sparse
line-items don't compress into retrieval-sized chunks the same way. A single
global setting is either too small for prose-heavy documents or too large
for terse ones. The cost is complexity (an extra analysis stage, a
recommendation object threaded through the pipeline) — judged worth it
because chunk quality directly determines retrieval quality downstream, and
`scripts/validate_chunks.py` exists specifically to keep that complexity
honest (measurable, not just assumed better).

---

### ABC + Factory per stage, not a single monolithic pipeline function

**Decision:** every stage (`loaders`, `cleaners`, `analysers`, `chunkers`,
`embedders`, `indexers`) has a `base.py` ABC, and most have a `factory.py`
dispatching on file extension or strategy name.

**Alternative considered:** a single `ingest()` function with `if/elif`
branches per format, as the earlier broken version's now-dead
`ingestion_pipeline.py` sketch (`build_vector_db()`, fully commented out)
suggests was the original shape.

**Why:** adding a new document type or chunking strategy should mean adding
a class and a factory registration — not editing a growing conditional in
`pipeline.py`. This is the concrete mechanism behind `05-roadmap.md`'s
"additional loaders" and "real Structure/Semantic/Markdown chunkers" items
being additive work, not rewrites.

---

### FAISS, and a file (not a client-server database)

**Decision:** `FAISSIndexer` wraps `langchain_community.vectorstores.FAISS`,
persisted via `save_local()`/`load_local()` to a directory.

**Alternative considered:** a client-server vector database (Qdrant,
pgvector, Weaviate).

**Why (for now):** this pipeline's actual usage pattern is batch ingest →
persist → some other process reads the result — not concurrent multi-writer
access. FAISS-on-disk is zero extra infrastructure and matches that pattern
exactly. The tradeoff is explicit, not accidental: once ingestion and
retrieval became two independently deployable services (see the API
deployment section of `DOCUMENTATION.md`), "sharing" the index means sharing
a mounted volume, which only works cleanly for periodic-refresh consumption,
not real-time concurrent read/write. If that stops being good enough,
`indexers/faiss_indexer.py` is the one place that would need to change.

---

### langchain `Document` as the common data structure, not a custom type

**Decision:** every stage passes `langchain_core.documents.Document` objects
between them. `models.py` defines a framework-agnostic `DocumentChunk`
dataclass but nothing in the pipeline actually produces it.

**Why:** the embedding and FAISS integration this pipeline depends on
(`langchain-huggingface`, `langchain_community.vectorstores.FAISS`) already
speaks `Document` natively. Introducing a custom type would mean a
conversion layer at both ends for no current benefit. `DocumentChunk` is
kept as a deliberately-unused placeholder for a possible future API/export
layer that shouldn't need a langchain dependency just to describe a chunk —
not dead code by accident, dead code on purpose, pending an actual need.

---

### Typed exception hierarchy (`IngestionError` + subclasses)

**Decision:** `UnsupportedDocumentError`, `DocumentTooLargeError`,
`DocumentLoadError`, `EmptyDocumentError`, all subclassing `IngestionError`.
`IngestionPipeline.ingest()` wraps any unexpected exception into
`IngestionError` before it propagates.

**Why:** a caller (the CLI, the API, or a future batch worker) can catch
`IngestionError` broadly for "log and move to the next file," or catch
`EmptyDocumentError` specifically to route a scanned PDF to an OCR queue
instead of discarding it. A bare `except Exception` at the call site can't
make that distinction. This was one of the explicit fixes documented in
`PATCH_NOTES.md` relative to the earlier version.

---

### CLI and HTTP API as two entrypoints to the same pipeline object

**Decision:** `src/ingestion/pipeline.py`'s `_main()` and
`src/ingestion/api.py`'s `/ingest` handler both call the same
`IngestionPipeline.ingest()` — neither reimplements it.

**Why:** batch/offline ingestion (a directory of documents, a cron job) and
on-demand ingestion (a service another system calls) are both real use
cases, and duplicating pipeline logic between them would be a correctness
risk for no benefit. Two thin entrypoints, one implementation — see
`Dockerfile` vs `Dockerfile.api` for how each gets deployed differently
without the source diverging.

---

### `StructureChunker`/`SemanticChunker`/`MarkdownChunker` left as explicit stubs

**Decision:** these three classes exist, are registered in
`ChunkerFactory`, and are reachable via `analysis.recommendation.strategy`
— but each just delegates to `RecursiveChunker`. Their docstrings say so.

**Alternative considered:** not registering them until implemented, so an
unimplemented strategy would be a `KeyError`/explicit failure instead of a
silent fallback.

**Why the current approach:** `PDFAnalyzer._recommend_chunking` already
picks a strategy per document type (e.g. `research_paper` → `"structure"`).
If `"structure"` weren't registered at all, every research paper would hit
`ChunkerFactory`'s unknown-strategy fallback-with-warning path instead — a
noisier, less honest version of exactly what's happening now. Registering
the stub keeps the recommendation pipeline fully wired end to end while the
real implementation is pending, and the docstring is the record that it's
intentional, not forgotten.
