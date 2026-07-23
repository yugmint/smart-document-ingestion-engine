# 05 — Roadmap

Versioned by milestone (semver — `1.MINOR.0` for a meaningful batch of
work, `1.0.PATCH` for small fixes between them). First tag is `v1.0.0`:
core pipeline logic is genuinely done — tested, adaptive chunking works
end to end, quality-validated via `scripts/`, standalone API deployed and
authenticated. Unlike the sibling `RAG_Project_1` (still actively
changing, tagged `v0.0.1`), this one earned the 1.0 claim. See
`06-release-notes.md` for the per-version changelog this file's "Shipped"
section is summarized from.

---

## v1.0.0 — Stable core pipeline (2026-07-24)

**Shipped:**
- Full `load → clean → analyze → chunk → generate metadata → embed → index`
  pipeline with document-type-aware adaptive chunking.
- The original upload's bugs fixed (chunker never enforcing `chunk_size`/
  overlap, analyzer recommendations computed but unused, a `document_type`
  metadata key collision, and others) — see `PATCH_NOTES.md`.
- The chunk-packing bug found via `scripts/validate_chunks.py` during
  review, also fixed: fragments weren't recombined toward the target
  size (38 chunks averaging ~215 chars against a 630-char target → 8
  chunks averaging ~520 chars after the fix).
- Unit + e2e test suite (12 tests, one real-PDF e2e case) plus two
  standalone quality-validation CLIs (`validate_chunks.py`,
  `validate_embeddings.py`).
- Standalone FastAPI service (`src/ingestion/api.py`) with `X-API-Key`
  auth, deployable alongside `RAG_Project_1`'s own API over a shared
  FAISS volume (see the top-level `docker-compose.yml`).
- Git hygiene fixed: 39 wrongly-tracked `.pyc` files untracked; the e2e
  test's fixture PDF (previously never actually committed, despite the
  code referencing it) now properly tracked.
- Full documentation set: `DOCUMENTATION.md` + numbered `docs/`
  (architecture, ingestion-specific best practices, development guide,
  contributing, roadmap, release notes, design decisions).

**Known limitations carried into v1.1.0+** (not blockers for calling this
stable, just not yet done):
- PDF-only — no `.docx`/`.html`/`.txt` loaders yet.
- `StructureChunker`/`SemanticChunker`/`MarkdownChunker` are documented
  stubs, all delegating to `RecursiveChunker`.
- No OCR — scanned/image-only PDFs raise `EmptyDocumentError` by design.
- No rate limiting on `POST /ingest`.
- Real documents were committed then removed in early git history
  (`e3dbd6d` → `8483c98`) — still present in history if the remote is
  public and that matters.

---

## v1.1.0 — Ingestion coverage (planned)

- [ ] Additional loaders beyond PDF: `.docx`, `.html`, `.txt` at minimum.
      `LoaderFactory`/`AnalyzerFactory` are already structured for this —
      new classes + registrations, not a redesign.
- [ ] OCR path for scanned/image-only PDFs — a new loader variant, not a
      change to the existing one.

## v1.2.0 — Real adaptive chunkers (planned)

- [ ] Real `StructureChunker` — heading/section-hierarchy-aware splitting.
- [ ] Real `SemanticChunker` — embedding-similarity boundary detection.
- [ ] Real `MarkdownChunker` — fenced-code/table-aware splitting.
- [ ] `TextCleaner` improvements noted in its own docstring: header/footer
      removal, hyphenation repair, table cleanup.

## v1.3.0 — Deployment hardening (planned)

- [ ] Auto-trigger a reload on the RAG API after a successful `/ingest`
      call, instead of requiring a manual `POST /reload` on the other side
      (deliberately not built yet — see `docker-compose.yml` comments).
- [ ] Incremental ingestion via `FAISSIndexer.add()` (already implemented,
      not yet exposed over the API).
- [ ] Rate limiting on `POST /ingest`.
- [ ] CI (GitHub Actions): run `pytest tests/ -v` on every push; run the
      `e2e` marker on a schedule or release branches only, since it
      downloads a model.

## Unscheduled

- [ ] Decide what to do about the real documents committed and later
      removed in git history — leave as-is if the remote is
      private/acceptable, or rewrite history if not.
- [ ] Make `IngestionConfig.vector_store` actually dispatch to a chosen
      indexer (today it's informational-only; FAISS is hard-wired). Only
      worth doing once a second vector store is actually needed.
