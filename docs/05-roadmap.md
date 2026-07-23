# 05 — Roadmap

Status as of this writing: core pipeline logic is considered done for a
v1.0.0 (tested, adaptive chunking works end to end, quality-validated via
`scripts/`). This roadmap is what's deliberately *not* in that v1, in rough
priority order — not a promise of when any of it lands.

## Now / next (tighten what exists)

- [ ] Tag `v1.0.0` and bump `pyproject.toml` to match (see `04-contributing.md`'s Git hygiene section).
- [x] Stop tracking `__pycache__/*.pyc` in git — fixed 2026-07-24
      (`git rm -r --cached`, 39 files), staged and ready to commit.
- [ ] Decide what to do about the real documents committed and later removed
      in git history (`e3dbd6d` → `8483c98`) — leave as-is if the remote is
      private/acceptable, or rewrite history if not.
- [ ] Add CI (GitHub Actions): run `pytest tests/ -v` on every push; run the
      `e2e` marker on a schedule or on release branches only, since it
      downloads a model.
- [x] **Basic authentication on `POST /ingest`** — fixed 2026-07-24.
      Shared-secret `X-API-Key` header against `INGESTION_API_KEY`
      (`src/utils/auth.py`), no-op if unset (dev convenience, warns loudly).
      **Rate limiting is still outstanding** — worth adding before any real
      external exposure, not just before "a private network."

## Ingestion coverage

- [ ] Additional loaders beyond PDF: `.docx`, `.html`, `.txt` at minimum.
      `LoaderFactory`/`AnalyzerFactory` are already structured for this —
      it's new classes + registrations, not a redesign.
- [ ] OCR path for scanned/image-only PDFs. Currently these deliberately
      fail with `EmptyDocumentError` rather than being mishandled; OCR would
      be a new loader variant, not a change to the existing one.

## Chunking

- [ ] Real `StructureChunker` — heading/section-hierarchy-aware splitting.
      Currently a placeholder delegating to `RecursiveChunker`.
- [ ] Real `SemanticChunker` — embedding-similarity boundary detection.
      Same placeholder status.
- [ ] Real `MarkdownChunker` — fenced-code/table-aware splitting.
- [ ] Header/footer removal, hyphenation repair, and table cleanup in
      `TextCleaner` — currently noted as future work in its own docstring.

## Indexing

- [ ] Make `IngestionConfig.vector_store` actually dispatch to a chosen
      indexer (today it's informational-only; FAISS is hard-wired). Only
      worth doing once a second vector store is actually needed — see the
      [deployment discussion](../DOCUMENTATION.md) about whether FAISS-on-disk
      remains sufficient once ingestion and retrieval are two independent
      services sharing a volume.

## Deployment

- [ ] Auto-trigger a reload on the RAG API after a successful `/ingest`
      call, instead of requiring a manual `POST /reload` on the other side
      (deliberately not built yet — see `docker-compose.yml` comments).
- [ ] Incremental ingestion via `FAISSIndexer.add()` (already implemented,
      not yet exposed over the API) so re-ingesting one updated document
      doesn't require rebuilding the whole index.
