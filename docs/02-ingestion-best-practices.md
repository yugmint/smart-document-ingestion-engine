# 02 — Ingestion Best Practices

Domain-specific practices for building/maintaining a document ingestion
pipeline — grounded in decisions already made in this codebase (and, in a
few places, bugs this codebase specifically had and fixed — see
`PATCH_NOTES.md`), not generic advice.

## Chunking

- **Don't apply one fixed chunk size to every document.** A research
  paper's dense paragraphs and an invoice's line items don't compress the
  same way. This pipeline's whole reason for having `PDFAnalyzer` is to
  avoid this — see `07-design-decisions.md`. If you're building ingestion
  for a new document type, decide the chunk profile deliberately
  (`_BASE_PROFILES` in `pdf_analyzer.py`), don't just inherit `general`.
- **Prefer semantic boundaries over hard character slicing.** `separators`
  is ordered `\n\n → \n → ". " → " " → ""` on purpose — paragraph breaks are
  tried before word breaks, and a hard character slice (`""`) is the last
  resort, not the default. If you add a new chunker, keep this ordering
  philosophy: structure-aware splits produce more coherent chunks than
  fixed-offset ones.
- **A chunker that respects `chunk_size` isn't automatically a good
  chunker.** This is the single most concrete lesson in this codebase: an
  earlier version of `RecursiveChunker` split text into fragments that were
  each individually `<= chunk_size`, but never recombined the small ones —
  it "worked" (no crash, no failed assertion) while producing chunks at a
  third of the intended size. Always validate the *distribution*, not just
  the max, via `scripts/validate_chunks.py`.
- **Overlap should be proportional to chunk size, not a fixed constant.**
  This pipeline derives `chunk_overlap` as roughly 20% of `chunk_size`,
  bounded by a minimum — a fixed absolute overlap (e.g. always 100 chars)
  becomes meaningless at very small or very large chunk sizes.
- **Track near-duplicate and near-empty chunks as defects**, not noise.
  Both waste embedding calls and dilute retrieval — `validate_chunks.py`
  flags both explicitly for this reason.

## Document analysis / classification

- **Log the rationale for every automated recommendation**, not just the
  output. `ChunkingRecommendation.rationale` exists specifically so a human
  debugging "why did this document get such a large chunk size" doesn't
  have to reverse-engineer the heuristic from scratch.
- **Attach a confidence score to classification, and treat low-confidence
  results differently.** A 3-word document shouldn't be trusted with the
  same "research_paper, chunk_size=900" recommendation as a clearly-detected
  50-page paper — `PDFAnalyzer._score_confidence` exists to make "we're not
  sure" visible instead of silently applying the wrong strategy with full
  confidence.
- **Layout signals (headings, tables, equations) are cheap corroborating
  evidence** — use them to adjust confidence, not as the sole classifier.
  Keyword-only classification is fragile; keyword classification backed by
  "and does the layout look like what we'd expect" is more robust without
  much more cost.

## Embeddings

- **Normalize embeddings when using cosine/inner-product similarity
  search**, and keep it consistent between ingestion and retrieval — a
  mismatch here degrades retrieval silently (no error, just worse results).
  This pipeline's `normalize_embeddings=True` default and the sibling RAG
  project's retrieval-side embedding config both need to agree, since
  they're produced/consumed by two separate codebases now.
- **Cache the embedding model instance.** Reloading a sentence-transformers
  model per call is expensive; `EmbeddingFactory.get()`'s `@lru_cache` (and
  reusing one `IngestionPipeline`/one API process across requests) is what
  keeps `/ingest` calls fast after the first one.
- **Validate embedding quality directly, not just "did it run."** Near-1.0
  mean pairwise similarity across a whole document means the embedding
  space has no discriminative power — usually a sign of degenerate chunks
  or the wrong model, not a retrieval-algorithm problem. This is exactly
  what `scripts/validate_embeddings.py`'s similarity report is for; run it
  on any new document type before trusting retrieval over it.

## Metadata

- **Keep semantic metadata and mechanical metadata in separate fields.**
  This pipeline's own `document_type`-key-collision bug (semantic
  classification vs. file extension sharing one key — see `PATCH_NOTES.md`)
  is the canonical example of why. Namespace or clearly distinguish fields
  that come from *what the document is* versus fields that come from *how
  it was processed*.
- **Store enough metadata to trace a chunk back to its source and location**
  (`source`, `page_number`, `chunk_id`) at ingestion time. This is cheap to
  add now and effectively impossible to backfill later once chunks are
  embedded and dispersed into an index — needed for citations, debugging a
  bad retrieval, and reprocessing a single document without a full rebuild.

## Robustness

- **Fail loudly and specifically, not silently.** A scanned/image-only PDF
  should raise `EmptyDocumentError`, not produce an empty or garbage chunk
  that later shows up as an inexplicably bad retrieval result three layers
  downstream. Typed exceptions (`exceptions.py`) let a caller distinguish
  "skip and log" from "retry" from "needs OCR, route elsewhere."
- **Refuse to build an empty index rather than silently shipping one.**
  `FAISSIndexer.build()` already does this — keep this instinct for any new
  indexer/vector store integration.
- **Handle the specific ways real documents break**: encrypted PDFs,
  individual unparsable pages within an otherwise-fine document, zero-byte
  files. One bad document in a batch job shouldn't take down the whole
  batch — `PDFLoader` already logs and continues on a per-page failure
  rather than aborting the whole document.

## Index management

- **Treat the index directory as a build artifact, not a hand-edited
  store.** Always regenerate via the pipeline; never patch `index.faiss`/
  `index.pkl` directly.
- **Know exactly which index is "live" and how it was built.** The sibling
  `RAG_Project_1` repo currently has three different FAISS index
  directories of different vintages sitting on disk, and the one actually
  wired up isn't the most recent one — a direct, real example of what
  happens without this discipline (see its `DOCUMENTATION.md` §8). A
  lightweight fix worth adopting: write a small manifest (timestamp, source
  documents, embedding model, chunk config) alongside every index build so
  a consumer can tell what they're loading without archaeology.
- **Support incremental indexing for growing corpora.** `FAISSIndexer.add()`
  already exists for this; prefer it over a full rebuild once a corpus is
  large enough that re-embedding everything on every ingest becomes the
  bottleneck.

## Testing & validation discipline

- **Unit test chunking/analysis logic without a real embedding model** —
  fast, deterministic, safe to run on every commit (`tests/test_pdf_analyzer.py`,
  `tests/test_recursive_chunker.py`).
- **Reserve real-embedding, real-FAISS tests for pre-release checks** — this
  repo's `-m e2e` marker pattern exists specifically so the expensive path
  doesn't slow down every-day development.
- **Run the quality-validation scripts against a real, representative
  document whenever chunking/cleaning/embedding logic changes.** Unit tests
  catch specific regressions against fixed assertions; they do not catch
  "technically passes, but structurally useless" — which is exactly what
  the chunk-packing bug was. `scripts/validate_chunks.py` and
  `scripts/validate_embeddings.py` are the tools that catch that class of
  problem.
