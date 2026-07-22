# Patch: e2e test + chunk/embedding quality validation + packing fix

Drop these files into your existing `ingestion_fixed/` project,
overwriting the ones that already exist there.

## Files in this patch

- `src/ingestion/chunkers/recursive_chunker.py` **(overwrite -- bug fix)**
  Added a `_pack()` step: fragments produced by `_split()` were each
  guaranteed to be `<= chunk_size`, but nothing recombined small
  fragments back up toward the target size. On PDFs with lots of
  short extracted lines, this meant chunks landing at a fraction of
  the intended size. Now fixed -- see README "Validating chunk &
  embedding quality" section for the before/after numbers.

- `pyproject.toml` **(overwrite)**
  Registers a new `e2e` pytest marker and excludes it by default
  (`addopts = "-m 'not e2e'"`), so the new real-embedding-model test
  doesn't slow down your everyday `pytest` runs.

- `README.md` **(overwrite)**
  Adds the "Validating chunk & embedding quality" section documenting
  the two new scripts.

- `tests/test_pipeline_e2e.py` **(new)**
  Runs the real `PDFLoader -> TextCleaner -> PDFAnalyzer ->
  HybridChunker -> MetadataGenerator` stack against an actual PDF
  file (fast, no embedding model). Also includes an opt-in
  `test_full_pipeline_with_real_embeddings` (`pytest -m e2e`) that
  exercises the complete pipeline including FAISS -- skips itself
  automatically if `sentence-transformers` isn't installed.

- `tests/data/sample_research_paper.pdf` **(new)**
  Small generated fixture PDF (abstract / methodology / references
  pages) used by the e2e test and as example input for the scripts
  below.

- `scripts/validate_chunks.py` **(new)**
  Standalone CLI: chunk-size distribution, overlap presence,
  duplicate/near-empty chunk detection, mid-sentence boundary rate.
  No embedding model required -- fast and offline.

  ```bash
  python scripts/validate_chunks.py path/to/file.pdf --dump-samples 5
  ```

- `scripts/validate_embeddings.py` **(new)**
  Standalone CLI: vector sanity (NaN/zero/norm checks), pairwise
  similarity distribution, near-duplicate embedding detection, a
  retrieval smoke test against a real question, and an optional
  labeled hit-rate check over a small JSON eval set.

  ```bash
  python scripts/validate_embeddings.py path/to/file.pdf --query "your question here"
  ```

## After applying

```bash
python -m pytest tests -v          # fast suite, 11 tests, no model download
python -m pytest tests -v -m e2e   # + the real-embeddings pipeline test
```
