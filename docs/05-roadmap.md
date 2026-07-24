# 05 — Roadmap

Versioned by milestone, standard semver. **Revised 2026-07-24, same day as
the first tag:** initially tagged `v1.0.0` on the reasoning that the core
pipeline was "done." Reconsidered — needs to prove out more (real-world
usage beyond one document, a few more roadmap items) before earning a 1.0
claim, so retagged `v0.1.0` instead. Pre-1.0 convention going forward:
bump MINOR (`0.2.0`, `0.3.0`, ...) for real feature/fix batches, PATCH
(`0.1.1`) for trivial fixes only, and don't jump to `1.0.0` until that's a
deliberate decision, not a default. See `06-release-notes.md` for the
per-version changelog this file's "Shipped" section is summarized from.

---

## v0.1.0 — Stable core pipeline (2026-07-24)

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
- Real-world validation: used directly to rebuild `RAG_Project_1`'s
  production index from a 136-page real document, producing 314
  well-formed chunks — see `RAG_Project_1/DOCUMENTATION.md` §8.

**Known limitations carried forward** (not blockers for calling this a
stable baseline, just not yet done — and part of why this is `v0.1.0`
rather than `v1.0.0`):
- PDF-only — no `.docx`/`.html`/`.txt` loaders yet.
- `StructureChunker`/`SemanticChunker`/`MarkdownChunker` are documented
  stubs, all delegating to `RecursiveChunker`.
- No OCR — scanned/image-only PDFs raise `EmptyDocumentError` by design.
- No rate limiting on `POST /ingest`.
- Real documents were committed then removed in early git history
  (`e3dbd6d` → `8483c98`) — still present in history if the remote is
  public and that matters.

**Real-world validation, round 2 (2026-07-24, same day):** ran a dense,
citation-and-formula-heavy technical PDF (`Factor_Analysis.pdf`, a
statistics-software manual chapter) through the pipeline — the first
structurally different document tested (the first validation used a
narrative fiction book). Found a precise, explainable misclassification:
`PDFAnalyzer._classify_document` checks for the literal word `"chapter"`
before any signal that distinguishes a technical/reference document from a
narrative book, so this document was classified `book` (not
`research_paper`) purely because it opens with "Chapter 420" — even though
it has citations, equations, and no `research_paper`-disqualifying traits
other than lacking a literal "Abstract" heading. Initially suspected as the
cause of two retrieval failures in the same test; a same-day controlled
follow-up (forcing `research_paper` classification and rerunning the exact
same questions) showed the failures persisted regardless of chunk size, so
that hypothesis was refuted. The misclassification is still real and worth
fixing on its own merits (correctness/predictability), just not as a
retrieval fix. Full writeup:
`RAG_Project_1/docs/reports/2026-07-24-academic-document-e2e-test.md` (see
its §5).

---

## v0.1.1 — Patch fixes

- [x] `scripts/validate_chunks.py --dump-samples` crashed on Windows with
      `UnicodeEncodeError` the moment a sampled chunk contains a character
      outside cp1252 (found via a real chunk containing "χ" from a
      chi-square formula) — `print()` inherits the console's default
      encoding. Fixed by reconfiguring `sys.stdout` to UTF-8 with
      `errors="replace"` at the top of `main()`, so the script no longer
      depends on `PYTHONIOENCODING` being set manually. See the 2026-07-24
      report referenced above.

## v0.2.0 — Ingestion coverage & classification robustness (planned)

- [ ] Additional loaders beyond PDF: `.docx`, `.html`, `.txt` at minimum.
      `LoaderFactory`/`AnalyzerFactory` are already structured for this —
      new classes + registrations, not a redesign.
- [ ] OCR path for scanned/image-only PDFs — a new loader variant, not a
      change to the existing one.
- [x] Corroborate the `"chapter"` → `book` classification against
      `layout.has_equations`/`has_tables` before committing to `book` —
      see the 2026-07-24 report above for the exact mechanism. Fixed in
      `PDFAnalyzer._classify_document`: `"chapter"`/`"table of contents"`
      no longer force `book` when the document also looks technical
      (equations or tables present); such documents now fall through to
      `general` instead (confirmed against the real `Factor_Analysis.pdf`
      — now classifies `general`, not `book`). As already established by
      the same-day controlled follow-up in that report (§5), this is a
      classification-correctness fix, not a retrieval-quality one — see
      the reranking/dedup items in `RAG_Project_1`'s roadmap for what
      actually addresses that.
- [ ] Equation-aware handling: `layout.has_equations` is detected but
      nothing currently changes behavior based on it. Equation-heavy PDF
      text extraction produces low-signal, barely-readable chunk content
      today (`pypdf` extracts embedded math as garbled character
      sequences) — confirmed in the same report.
- [ ] **`average_paragraph_length` is unreliable for some real academic
      PDF layouts** — found 2026-07-24 testing a third document (a
      genuine, correctly-classified research paper this time):
      `_extract_statistics` computed 43,767 chars for this metric on an
      11-page paper, because dense multi-column academic layouts don't
      always reproduce blank-line (`"\n\n"`) paragraph breaks through
      `pypdf` extraction. Harmless in this instance (the downstream
      "paragraph too large" branch still made a reasonable call), but the
      input signal itself was close to meaningless — investigate a
      sentence-based fallback when paragraph count is implausibly low
      relative to page/word count. See
      `RAG_Project_1/docs/reports/2026-07-24-efficientnet-research-paper-e2e-test.md` §1.
- [ ] **Chunk-level section-role metadata** (references/bibliography vs.
      body text) — same report, §3: a References-section chunk (a dense,
      unbroken bibliography with no paragraph breaks to split on)
      contains text formatted exactly like `Authors. Title. Venue, Year.`
      for *each citation*, which an LLM can mistake for the document's
      *own* title/authors when asked an identity-type question — a
      confidently wrong answer, not a safe refusal, the first of its kind
      across three documents tested. `MetadataGenerator` already attaches
      several per-chunk fields; a `section`/`is_reference_list` hint
      (even a cheap heuristic — density of citation-like patterns, or
      proximity to a detected `"References"` heading) would let
      `RAG_Project_1`'s generation layer treat these chunks differently
      for identity-type queries. Cross-repo fix: metadata origin here,
      consumption on the `RAG_Project_1` side.

## v0.3.0 — Real adaptive chunkers (planned)

- [ ] Real `StructureChunker` — heading/section-hierarchy-aware splitting.
- [ ] Real `SemanticChunker` — embedding-similarity boundary detection.
- [ ] Real `MarkdownChunker` — fenced-code/table-aware splitting.
- [ ] `TextCleaner` improvements noted in its own docstring: header/footer
      removal, hyphenation repair, table cleanup.

## v0.4.0 — Deployment hardening (planned)

- [ ] Auto-trigger a reload on the RAG API after a successful `/ingest`
      call, instead of requiring a manual `POST /reload` on the other side
      (deliberately not built yet — see `docker-compose.yml` comments).
- [ ] Incremental ingestion via `FAISSIndexer.add()` (already implemented,
      not yet exposed over the API).
- [ ] Rate limiting on `POST /ingest`.
- [ ] CI (GitHub Actions): run `pytest tests/ -v` on every push; run the
      `e2e` marker on a schedule or release branches only, since it
      downloads a model.

## v1.0.0 — Stability claim (planned, no fixed scope yet)

Once enough of v0.2.0–v0.4.0 has landed and this has seen real usage
across more than one document, revisit whether a 1.0 claim is warranted —
not before.

## Unscheduled

- [ ] Decide what to do about the real documents committed and later
      removed in git history — leave as-is if the remote is
      private/acceptable, or rewrite history if not.
- [ ] Make `IngestionConfig.vector_store` actually dispatch to a chosen
      indexer (today it's informational-only; FAISS is hard-wired). Only
      worth doing once a second vector store is actually needed.
