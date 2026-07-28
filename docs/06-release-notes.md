# 06 — Release Notes

[Keep a Changelog](https://keepachangelog.com/)-style, anchored on tags.
`v0.1.0` is the first tag this repo has — everything before it is
reconstructed from `git log`, without version numbers of its own (it was
never tagged at the time).

**Note:** this was briefly tagged `v1.0.0` on 2026-07-24, then retagged
`v0.1.0` the same day — reconsidered that a 1.0 claim was premature (one
document's worth of real-world validation, several roadmap items still
open). See `05-roadmap.md`.

## [0.4.7] — 2026-07-28

**Added:**
- Observability. New `GET /metrics` (Prometheus text format,
  auth-protected), mirroring `RAG_Project_1`'s. Per-stage timing,
  run outcomes, chunk count/size, duplicate chunks, and header/footer
  noise percentage -- all recorded from the single
  `IngestionPipeline.ingest()` call point. New pure
  `noise_page_percentage()` in `text_cleaner.py` (deliberately not an
  instance attribute, to avoid a race on the API's shared pipeline
  instance under concurrent requests). New explicit dependency:
  `prometheus_client`. 3 new tests.

**Validated:** real ingestion run correctly recorded
`ingestion_noise_percentage_sum=98.3`, `duplicate_chunks=0`, per-stage
timings, and chunk count 653 against the same real history book used
elsewhere this session.

## [0.4.6] — 2026-07-28

**Added:**
- `TextCleaner` now detects and strips repeated header/footer lines
  across a document's pages before its existing whitespace cleanup --
  normalizes away page-number-like variation so a line repeating with a
  different number on each page is still recognized as the same
  pattern. 6 new tests.

**Validated:** re-ingested the real 117-page book that motivated this
(`docs/05-roadmap.md` v0.2.0) -- branding noise in chunks: 16.7% → 0%
(target was <2%). Generation quality on the cleaned index spot-checked
unchanged/improved against the original E2E report's questions.

## [0.4.5] — 2026-07-28

**Fixed:**
- `IngestionConfig.vector_store` was silently informational -- setting
  `INGESTION_VECTOR_STORE=chroma` looked configured but did nothing
  (pipeline.py always builds `FAISSIndexer()` regardless). Now rejects
  anything but `"faiss"` loudly at construction time. Scoped down from
  the roadmap's original "dispatch to a chosen indexer" ask -- a
  factory for the one implementation that exists is speculative infra;
  revisit once a second backend is real. 2 new tests.

## [0.4.4] — 2026-07-28

**Fixed:**
- `average_paragraph_length` unreliable on dense multi-column PDF
  layouts (blank-line paragraph breaks don't always survive `pypdf`
  extraction, once seen skewing this stat to 43,767 chars on an
  11-page paper). Falls back to a sentence-grouped estimate when
  paragraph count looks implausible. Verified on the real airlock
  paper: 4,405 → 379 chars. 1 new test.

## [0.4.3] — 2026-07-27

**Added:**
- `.txt`/`.html`/`.docx` loaders (`TextLoader`/`HTMLLoader`/`DocxLoader`)
  + factory/config registrations. New `GenericAnalyzer` for these 3
  formats -- classifies "general" with the same baseline profile
  `PDFAnalyzer` uses for ambiguous PDFs, reusing its statistics helper
  rather than duplicating it. New deps: `python-docx`, `beautifulsoup4`
  (latter was already transitive, pinned directly now). 8 new tests.

**Validated:** real end-to-end `.txt` ingest through the full pipeline
(loader → analyzer → chunker → embed → FAISS) — 2 chunks produced,
correct source metadata, indexed cleanly.

## [0.4.2] — 2026-07-27

Docs only — no code changed. `docs/05-roadmap.md`'s v0.4.0 section was
missing the CORS middleware fix (it landed without a corresponding
checkbox). Added it in its proper place so the roadmap accurately
reflects what's actually shipped.

## [0.4.1] — 2026-07-26

**Added:**
- `src/ingestion/api.py` — CORS middleware (`CORSMiddleware`, wide open
  by default, `CORS_ALLOW_ORIGINS` env override). Without this, browsers
  silently block every request from any frontend not served from this
  exact origin -- including the sibling `RAG_Project_1/../frontend/index.html`,
  opened as a plain `file://` page. Found necessary while wiring up that
  frontend: this API had no CORS configured at all before this. Verified
  via a real CORS preflight request with `Origin: null` (what `file://`
  pages send) against a live server.

## [0.4.0] — 2026-07-26

Closes out the "Deployment hardening" milestone in one batch, alongside
the equivalent work in the sibling `RAG_Project_1` `v0.4.0`.

**Fixed:**
- **`IngestionPipeline.ingest()` silently discarded every
  previously-ingested document on each new call.** `FAISSIndexer.build()`
  (a fresh `FAISS.from_documents()`) always overwrote the index at the
  configured path — not "incremental ingestion wasn't supported yet," a
  real data-loss bug for any multi-document use. `.load()`/`.add()`
  already existed and worked; wired them in. New default: additive (an
  existing index gets added to, not replaced). New `replace: bool =
  False` param (CLI `--replace`, API `replace` form field) for
  intentionally starting over. Verified with real embeddings: ingesting
  the same document twice now leaves both ingestions' vectors present.
  **If you have an existing deployment that called `/ingest` more than
  once, its index likely only contains the most recent document** —
  re-ingest everything to recover.
- `src/utils/auth.py` — auth now fails closed: outside
  `APP_ENV=development` (the default), a missing `INGESTION_API_KEY` is
  a startup-time `RuntimeError`, not a warn-and-allow-everything no-op.

**Added:**
- `src/ingestion/api.py` — per-client (IP) rate limiting via `slowapi`:
  `/ingest` at 5/minute (stricter than the RAG API's `/query` limit --
  each call here is ~3s of real CPU-bound embedding work).
- `/ingest` now auto-notifies the sibling RAG API's `/reload` after a
  successful ingestion, via `RAG_RELOAD_URL` (opt-in — unset preserves
  the old manual-call behavior). Best-effort: a failed notification
  logs a warning, doesn't fail the `/ingest` call. Wired into the
  shared `docker-compose.yml`.
- `.github/workflows/tests.yml` — fast suite on every push/PR (no
  credentials/model download needed); a separate `e2e` job (real
  embedding model) gated to `main`, release branches, and weekly.

**Validated:** full test suite (28 fast + 3 e2e) re-run after all of
the above, plus a live integration check against a real running RAG API
for the auto-reload notification (including the wrong-key failure path).

## [0.2.0] — 2026-07-26

**Added:**
- `MetadataGenerator` now attaches `is_reference_section` and
  `is_first_page` per chunk — section-role hints so downstream retrieval
  can exclude bibliography noise from the candidate pool. Consumed on
  the `RAG_Project_1` side (`rerank` node).

**Fixed (same-day self-correction):**
- First attempt detected the reference section via `"References"`
  heading *position* (that chunk and everything after it). Tested
  against the real two-column-layout airlock paper and found it wrong:
  `pypdf` extracts multi-column PDFs in a way that put the heading
  itself at the very end of the page, *after* several actual citations
  extracted earlier — a position-based cutoff both missed real
  citations and wrongly flagged real body content (funding, author
  contributions) as reference-section. Replaced with a per-chunk
  citation-density signal (`doi:`/`Medline:` identifier count >= 2),
  which doesn't depend on any single heading's position and is immune to
  extraction-order scrambling. Verified against all three documents with
  real citations. Known limitation: only catches citations carrying a
  DOI or Medline identifier. Four new tests.

**Validated:** re-ingesting and re-running the full 20-question
regression suite (Factor Analysis + EfficientNet, both previously
validated) plus the airlock paper's 6-question suite on the
`RAG_Project_1` side after this change: 20/20 correct on the two
10-question suites (up from 16/20 before today's session — see that
repo's release notes), zero regressions found.

## [0.1.3] — 2026-07-25

**Fixed:**
- `PDFAnalyzer._classify_document` misclassified a structured-abstract
  medical paper (Hu et al. 2020) as `legal` (confidence 0.85). Two
  compounding causes, both fixed: the paper's structured abstract
  (Background/Methods/Results/Conclusions) has no literal word "Abstract",
  so `research_paper` never fired; it then fell through to a bare
  substring match on `"agreement"`, which matched inside "...crude
  **agreement** were all over 85%" (a statistics term). `research_paper`
  now also recognizes >=3 structured-abstract markers together (still
  requires `layout.has_references`); `legal` now requires an actual
  legal-agreement phrase instead of the bare word. Verified against the
  real PDF (now `research_paper`, 0.90, was `legal`, 0.85). Two new tests.

**Investigated, not shipped:**
- A related chunk-boundary issue (this paper's front matter has no
  blank-line paragraph breaks at all, so its title got glued onto the
  tail of an unrelated address block) was found, root-caused, and a fix
  was built and verified against the target document — but re-validating
  against the already-shipped Factor Analysis/EfficientNet indexes
  surfaced two real regressions (previously-correct answers became
  wrong), so it was reverted rather than shipped net-negative. Full
  writeup and lesson learned: `docs/05-roadmap.md` v0.2.0.

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
