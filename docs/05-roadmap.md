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

- [x] **Additional loaders — shipped 2026-07-27.** `.txt`/`.html`/`.docx`
      loaders + `LoaderFactory`/`config.supported_extensions`
      registrations, as anticipated. New `GenericAnalyzer` for the
      3 non-PDF formats (no PDF-page layout signal to detect
      equations/tables/references from) — always classifies "general"
      using the same baseline chunk profile `PDFAnalyzer` already falls
      back to for ambiguous PDFs; reuses `PDFAnalyzer._extract_statistics`
      (pure text-stats math, not actually PDF-specific) rather than
      duplicating it. Real per-format classification quality is out of
      scope here — that's v0.3.0's "real adaptive chunkers", not a
      loaders gap. New deps: `python-docx` (no lighter option parses
      real .docx); `beautifulsoup4` was already an implicit transitive
      dependency, pinned directly now. 8 new tests; validated with a
      real end-to-end `.txt` ingest through the full pipeline (loader →
      analyzer → chunker → embed → FAISS).
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
- [x] **`average_paragraph_length` unreliable on dense PDF layouts —
      fixed 2026-07-28.** Found 2026-07-24: `_extract_statistics`
      computed 43,767 chars for this metric on an 11-page paper, because
      dense multi-column layouts don't always reproduce blank-line
      (`"\n\n"`) paragraph breaks through `pypdf` extraction. Fixed with
      the sentence-based fallback already anticipated here: when
      paragraph count is implausible relative to sentence count
      (`paragraphs * 6 < sentences`), estimate from sentences grouped in
      4s instead — sentence boundaries survive column-layout extraction
      even when blank lines don't. Verified against the real airlock
      paper (10 pages, same column-layout shape): old calculation gave
      4,405 chars (2 blank-line paragraphs across the whole document,
      clearly wrong); fallback gives 379 chars, a sane real paragraph
      size. 1 new test.
- [x] **Chunk-level section-role metadata** (references/bibliography vs.
      body text) — same report, §3: a References-section chunk (a dense,
      unbroken bibliography with no paragraph breaks to split on)
      contains text formatted exactly like `Authors. Title. Venue, Year.`
      for *each citation*, which an LLM can mistake for the document's
      *own* title/authors when asked an identity-type question — a
      confidently wrong answer, not a safe refusal, the first of its kind
      across three documents tested. Fixed 2026-07-26:
      `MetadataGenerator` now attaches `is_reference_section` and
      `is_first_page` per chunk. **First attempt (same day) was wrong:**
      tried a `"References"`-heading-position cutoff (mark that chunk and
      everything after it) — looked reasonable, but tested against the
      real two-column-layout airlock paper and got it badly wrong:
      `pypdf`'s column-order text extraction put the heading itself at
      the very end of the page, *after* several actual citations
      extracted earlier, so a position-based cutoff both missed real
      citations and wrongly flagged real body content (author
      contributions, funding) that happened to sit after the
      mis-positioned heading. Replaced with a per-chunk citation-density
      signal instead (`doi:`/`Medline:` identifier count >= 2) — immune
      to extraction-order scrambling since it doesn't depend on finding
      one heading's position at all. Verified against all three
      documents with real citations (Factor Analysis, EfficientNet,
      airlock) — correctly flags actual citation-dense chunks in each,
      including on the airlock paper where the heading-based version
      failed. **Known limitation:** only catches citations carrying a
      DOI or Medline identifier — citation styles without either
      (common in older papers, humanities, some non-medical fields)
      won't be flagged. Four new tests in `test_metadata_generator.py`.
      Consumed on the `RAG_Project_1` side: the `rerank` node drops
      `is_reference_section` candidates before scoring.
- [x] **Structured-abstract research papers misclassified, `"agreement"`
      false-positiving into `legal`** — found 2026-07-25 testing a fourth
      real document (Hu et al. 2020, a COVID-19 severity study). Two
      compounding bugs in `_classify_document`: (1) medical/clinical
      journals often use a structured abstract
      (Background/Methods/Results/Conclusions) with no literal word
      "Abstract" anywhere, so the `research_paper` rule never fired; (2)
      it fell through to the bare-substring `"agreement" in text` check
      for `legal`, which matched inside "...crude **agreement** were all
      over 85%" — a statistics term (inter-rater agreement), not a legal
      one. Document was classified `legal` (confidence 0.85) instead of
      `research_paper`. Fixed: `research_paper` now also fires on >=3 of
      {background, objective(s), methods, results, conclusion(s)}
      appearing together (requires `layout.has_references` too, same as
      the literal-"abstract" path); `legal` now requires an actual
      legal-agreement phrase (`"this agreement"`, `"the parties agree"`,
      etc.) instead of the bare word. Verified against the real PDF (now
      classifies `research_paper`, confidence 0.90, was `legal`
      0.85). Two new regression tests in `test_pdf_analyzer.py`.
- [ ] **Title/author text can still get glued onto a preceding
      unrelated block when a page has no blank-line paragraph breaks at
      all** — found and root-caused testing the same document: this
      paper's front matter (masthead, author list, affiliation,
      correspondence address) is separated by single `"\n"` only, no
      `"\n\n"` anywhere, so `RecursiveChunker`'s paragraph-first
      splitting has nothing to key off, and greedy `_pack()`ing glued
      the paper's actual title onto the tail of the correspondence
      block. That in turn confused the cross-encoder reranker enough on
      `RAG_Project_1`'s side to drop the title/author chunk from the
      final top-k for a "what is the title" query.
      **Attempted and reverted 2026-07-25:** built a paragraph-aware
      version of `_pack` (tracking which fragments came from a
      force-split paragraph, refusing to glue a new paragraph onto such
      a remnant) plus a `TextCleaner` rule inserting a paragraph break
      after email addresses (a reliable "contact block just ended"
      signal). Fixed the target document's chunk boundary as intended,
      confirmed via direct chunk inspection — but re-running the full
      10-question suites against the two *already-validated* indexes
      (Factor Analysis, EfficientNet — see
      `RAG_Project_1/docs/reports/2026-07-24-reranking-validation.md`)
      surfaced two real regressions on EfficientNet (Q5 and Q9, both
      previously correct, both wrong after the change) traced to the
      same shared source passage landing outside the retrieved context.
      Reverted rather than ship a net-negative change; `_pack`/
      `_split`/`TextCleaner` are back to their pre-2026-07-25 state.
      **Lesson for whoever picks this up next:** `_pack` is shared
      across every document type — any change to it needs a full
      regression pass against Factor Analysis and EfficientNet before
      shipping, not just validation against the document that motivated
      the change. Also worth noting: even with the boundary fixed, the
      cross-encoder reranker *still* ranked the correct title chunk only
      #12/15 for a "title and authors" query — so this may not be fully
      fixable on the chunking side alone; see the identity/self-
      referential question gap already tracked in
      `RAG_Project_1/docs/reports/2026-07-24-reranking-validation.md` §4.

## v0.3.0 — Real adaptive chunkers (planned)

- [ ] Real `StructureChunker` — heading/section-hierarchy-aware splitting.
- [ ] Real `SemanticChunker` — embedding-similarity boundary detection.
- [ ] Real `MarkdownChunker` — fenced-code/table-aware splitting.
- [ ] `TextCleaner` improvements noted in its own docstring: header/footer
      removal, hyphenation repair, table cleanup. **Now has a real number
      behind it:** a 2026-07-28 E2E test on a real 117-page UPSC-style
      study-guide book (this project's stated major target document type)
      found repeating branding-header noise in 115/688 chunks (16.7%). See
      `RAG_Project_1/docs/reports/2026-07-28-history-book-e2e-test.md` §1.

## v0.4.0 — Deployment hardening

- [x] **Auto-trigger a reload on the RAG API — fixed 2026-07-26.**
      `/ingest` now POSTs to the RAG API's `/reload` after a successful
      ingestion, via `RAG_RELOAD_URL` (opt-in — unset preserves the old
      manual-call behavior for standalone/CLI-only use). Best-effort:
      a failed notification logs a warning and does not fail the
      `/ingest` call itself (the FAISS write already succeeded by
      then). Verified against a real running RAG API, including the
      auth-failure path. Wired into the shared `docker-compose.yml`.
      5 new tests (`test_ingest_api_reload.py`).
- [x] **Incremental ingestion — fixed 2026-07-26, and it was more than
      "not yet exposed."** `IngestionPipeline.ingest()` always called
      `FAISSIndexer.build()` (a fresh `FAISS.from_documents()`) and
      overwrote whatever was at the index path — every `/ingest` call
      silently **discarded every previously-ingested document**, not
      just "didn't support" incremental updates. `.load()`/`.add()`
      already existed and worked; they just weren't wired into the
      pipeline. Now: if an index already exists at the configured path,
      `ingest()` loads it and adds the new chunks instead of replacing
      it — the new default is additive. Added an explicit `replace: bool
      = False` param (CLI: `--replace`; API: a `replace` form field) for
      the case someone genuinely wants to start over. Verified with real
      embeddings: ingesting the same document twice into one path now
      leaves both ingestions' vectors present (not just the second's),
      and `replace=True` correctly leaves only the second's. 2 new e2e
      tests. **If you have an existing multi-`/ingest` deployment, its
      index likely only contains its most recent document** — re-ingest
      everything once to recover, or rebuild from source documents.
- [x] **Rate limiting on `POST /ingest` — fixed 2026-07-26.** Per-client
      (IP) limit via `slowapi`, 5/minute — stricter than the RAG API's
      `/query` limit since each call here is ~3s of real CPU-bound
      embedding work. In-memory backend, no Redis needed at this scale.
      Verified against the real endpoint: exactly 5 requests allowed
      through per minute, clean 429s after.
- [x] **CI (GitHub Actions) — added 2026-07-26.**
      `.github/workflows/tests.yml`: a `test` job runs the fast suite
      (`pytest -v`, e2e-marked tests excluded by default) on every
      push/PR, no credentials or model download needed. A separate `e2e`
      job runs the real-embedding-model tests, gated to `main`, release
      branches, and a weekly schedule — not every feature-branch push,
      since it downloads a model.
- [x] **CORS middleware — fixed 2026-07-26.** No CORS configuration at
      all -- browsers silently block every request from any frontend
      not served from the exact same origin, including a
      `file://`-opened local HTML page (exactly how the sibling
      `RAG_Project_1/../frontend/index.html` runs). Found while wiring
      that frontend up. `CORSMiddleware` added, wide open by default
      (`CORS_ALLOW_ORIGINS` env override for a real deployment that
      wants to restrict it). Verified via a real preflight request with
      `Origin: null` (what `file://` pages send) against a live server.

## v1.0.0 — Stability claim (planned, no fixed scope yet)

Once enough of v0.2.0–v0.4.0 has landed and this has seen real usage
across more than one document, revisit whether a 1.0 claim is warranted —
not before.

## Unscheduled

- [ ] Decide what to do about the real documents committed and later
      removed in git history — leave as-is if the remote is
      private/acceptable, or rewrite history if not.
- [x] **`IngestionConfig.vector_store` — fixed 2026-07-28, scoped down
      from the original ask.** Not built: an `IndexerFactory` dispatching
      to a chosen backend -- only `FAISSIndexer` exists, so a factory
      for one implementation is speculative infra, not a real dispatch.
      Fixed instead: the field was silently informational (pipeline.py
      always builds `FAISSIndexer()` regardless of its value, so setting
      `INGESTION_VECTOR_STORE=chroma` looked configured but did nothing).
      Now `IngestionConfig.__post_init__` rejects anything but `"faiss"`
      loudly at construction time instead of silently no-op'ing. Revisit
      with a real factory once a second backend is actually implemented.
      2 new tests.
