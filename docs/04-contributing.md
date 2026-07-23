# 04 — Contributing

This is currently a single-contributor project. This document is here for
future-you, a future collaborator, or a future PR reviewer — not written as
if there's already a team.

## Before opening a PR / making a change

1. **Run the fast test suite.** `pytest tests/ -v`. If you touched a
   chunker, cleaner, analyzer, or the pipeline orchestrator, also run
   `pytest tests/ -v -m e2e` — it's the only test exercising real
   embeddings + FAISS.
2. **Run the quality scripts against a real PDF** if you changed chunking,
   cleaning, or embedding logic: `scripts/validate_chunks.py` and
   `scripts/validate_embeddings.py`. Unit tests catch regressions in
   specific assertions; these scripts catch "the output looks structurally
   fine but is actually useless" regressions (see the packing bug in
   `PATCH_NOTES.md` for a real example of exactly that).
3. **Keep new stage implementations behind the existing ABC + Factory
   pattern** (see `03-development-guide.md`). Don't special-case a new
   document type or chunking strategy directly in `pipeline.py`.

## Git hygiene

Concrete lessons from this repo's own history — not abstract advice:

- **The entire pipeline landed in one 94-file commit** (`e3dbd6d`), even
  though `PATCH_NOTES.md` describes a real sequence of distinct bug fixes.
  `git blame`/`git bisect` can't answer "which commit fixed the packing
  bug" as a result. Land future work in commits that match a real unit of
  change (one bug fix, one new chunker, one config option).
- **`.pyc` files were tracked in git** despite `.gitignore` covering
  `__pycache__/` since the first commit — `.gitignore` only stops
  *accidental* adds via `git add .`, not an explicit add that swept them
  in. Fixed 2026-07-24: `git rm -r --cached '**/__pycache__'` (39 files),
  staged and ready to commit.
- **Real documents (PDFs) were committed, then removed** (`e3dbd6d` →
  `8483c98`) — removal in a later commit doesn't remove the blobs from
  history. If any were sensitive/copyrighted and this remote is public,
  that needs a history rewrite (`git filter-repo`/BFG), not just a
  follow-up commit.
- **No tags existed**, despite `pyproject.toml` declaring a version number.
  Fixed 2026-07-24: `v1.0.0` tagged (and `pyproject.toml` bumped to match)
  now that the core pipeline is genuinely stable — see
  `05-roadmap.md`/`06-release-notes.md`. Keep tagging version milestones
  as they happen going forward, not retroactively.

One commit per logical change, a message that says *why* if it's not
obvious from the diff, and don't let compiled artifacts or real documents
get swept into a commit by a broad `git add .`.

## Scope discipline

This pipeline intentionally does **not** try to do everything:

- PDF-only (no docx/html/txt loaders yet — see `05-roadmap.md`).
- `StructureChunker`/`SemanticChunker`/`MarkdownChunker` are placeholders
  that fall back to `RecursiveChunker` — don't wire up a half-implementation
  of one of these; either implement it properly (with tests) or leave the
  placeholder as-is.
- No OCR. Scanned/image-only PDFs are meant to fail loudly
  (`EmptyDocumentError`), not be silently mishandled.

If a change would expand scope beyond "ingest a document into a good FAISS
index," raise it as a design discussion first (see `07-design-decisions.md`
for the reasoning behind the current boundaries) rather than merging it in
as a drive-by addition.

## Code style

No linter/formatter is currently enforced in CI (there is no CI configured
yet — see `05-roadmap.md`). Match the existing style: `@dataclass(slots=True)`
for data containers, typed exceptions from `exceptions.py` rather than bare
`Exception`, and logging via `src.utils.logger.logger` — no `print()`.
