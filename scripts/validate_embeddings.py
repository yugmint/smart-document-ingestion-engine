#!/usr/bin/env python
"""
Validate embedding + retrieval quality for a given document.

Usage:
    python scripts/validate_embeddings.py path/to/file.pdf
    python scripts/validate_embeddings.py path/to/file.pdf --query "what strategy was used for chunking?"
    python scripts/validate_embeddings.py path/to/file.pdf --eval eval_set.json

What it checks (and why each one matters):

- Vector sanity (NaNs, zero vectors, dimension consistency)
      Catches a broken embedding call before it silently corrupts
      the index -- a zero vector matches nothing and nothing matches
      it; a NaN can poison similarity search entirely.
- Norm distribution
      If `normalize_embeddings=True`, norms should cluster ~1.0.
      Norms all near 0, or wildly inconsistent, usually means the
      model/config isn't doing what you think it's doing.
- Near-duplicate embedding rate
      If many *different* chunks produce near-identical vectors
      (cosine similarity > 0.999), the model isn't discriminating
      between them -- often a sign of a degenerate/mismatched model,
      or chunks so short they carry no distinguishing content.
- Pairwise similarity distribution
      A sanity check on whether the embedding space has any spread
      at all. If everything is close to everything else, retrieval
      can't discriminate; if it's this document's whole content,
      some clustering (similar sections closer than unrelated ones)
      is expected and good.
- Retrieval smoke test (--query)
      The most important check: embed a real question and look at
      what actually comes back. Automated metrics catch structural
      problems; only a human looking at "did I get the right chunk"
      catches semantic ones.
- Retrieval hit-rate (--eval)
      A lightweight, labeled-eval-set version of the same idea:
      supply {"query": ..., "expected_keyword": ...} pairs and this
      reports what fraction of top-k results actually contain the
      expected keyword -- a lightweight proxy for recall@k you can
      grow over time as you find retrieval failures worth guarding
      against.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.loaders.pdf_loader import PDFLoader
from src.ingestion.cleaners.text_cleaner import TextCleaner
from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
from src.ingestion.chunkers.hybrid_chunker import HybridChunker
from src.ingestion.metadata.generator import MetadataGenerator
from src.ingestion.config import IngestionConfig
from src.ingestion.embedders.embedder import Embedder


def build_chunks(file_path: str):
    documents = PDFLoader().load(file_path)
    documents = TextCleaner().clean(documents)
    analysis = PDFAnalyzer().analyze(documents, file_path)
    config = IngestionConfig()
    chunks = HybridChunker(config).chunk(documents, analysis)
    chunks = MetadataGenerator().generate(chunks, file_path, analysis)
    return chunks, analysis, config


def cosine_sim_matrix(vectors: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vectors, axis=1, keepdims=True)
    norm[norm == 0] = 1e-8
    unit = vectors / norm
    return unit @ unit.T


def vector_sanity(vectors: np.ndarray):
    print("=" * 70)
    print("VECTOR SANITY")
    print("=" * 70)
    print(f"count           : {vectors.shape[0]}")
    print(f"dimension       : {vectors.shape[1]}")

    nan_count = int(np.isnan(vectors).any(axis=1).sum())
    zero_count = int((np.linalg.norm(vectors, axis=1) < 1e-8).sum())
    print(f"vectors with NaN: {nan_count}")
    print(f"zero vectors    : {zero_count}")

    norms = np.linalg.norm(vectors, axis=1)
    print(f"norm mean/std   : {norms.mean():.3f} / {norms.std():.3f}")
    print(f"norm min/max    : {norms.min():.3f} / {norms.max():.3f}")


def similarity_report(vectors: np.ndarray, chunks):
    sims = cosine_sim_matrix(vectors)
    n = sims.shape[0]

    off_diagonal = sims[~np.eye(n, dtype=bool)]

    print("\n" + "=" * 70)
    print("PAIRWISE SIMILARITY (off-diagonal, all chunk pairs)")
    print("=" * 70)
    print(f"mean / std      : {off_diagonal.mean():.3f} / {off_diagonal.std():.3f}")
    print(f"min / max       : {off_diagonal.min():.3f} / {off_diagonal.max():.3f}")

    near_dupes = 0
    dupe_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if sims[i, j] > 0.999:
                near_dupes += 1
                dupe_pairs.append((i, j))

    print(f"\nnear-duplicate pairs (cosine > 0.999): {near_dupes}")
    for i, j in dupe_pairs[:5]:
        print(f"  - chunk {i} <-> chunk {j}")
        print(f"      [{i}] {chunks[i].page_content[:80]!r}")
        print(f"      [{j}] {chunks[j].page_content[:80]!r}")

    if off_diagonal.mean() > 0.9:
        print(
            "\n[!] average similarity is very high (>0.9) -- embeddings may "
            "not be discriminating between chunks. Check the embedding "
            "model and whether chunks are too short/repetitive."
        )


def embed_query(embedder, query: str) -> np.ndarray:
    return np.array(embedder.embed_query(query))


def retrieval_smoke_test(embedder, vectors, chunks, query: str, k: int = 3):
    q_vec = embed_query(embedder, query)
    sims = cosine_sim_matrix(np.vstack([vectors, q_vec]))[-1, :-1]

    top_k = np.argsort(sims)[::-1][:k]

    print("\n" + "=" * 70)
    print(f"RETRIEVAL SMOKE TEST -- query: {query!r}")
    print("=" * 70)
    for rank, idx in enumerate(top_k, start=1):
        preview = chunks[idx].page_content[:150].replace("\n", " ")
        print(f"[{rank}] score={sims[idx]:.3f} | page={chunks[idx].metadata.get('page_number')}")
        print(f"    {preview}")


def eval_hit_rate(embedder, vectors, chunks, eval_path: str, k: int = 3):
    cases = json.loads(Path(eval_path).read_text())

    print("\n" + "=" * 70)
    print(f"RETRIEVAL HIT-RATE (top-{k}) -- {eval_path}")
    print("=" * 70)

    hits = 0
    for case in cases:
        query = case["query"]
        expected = case["expected_keyword"].lower()

        q_vec = embed_query(embedder, query)
        sims = cosine_sim_matrix(np.vstack([vectors, q_vec]))[-1, :-1]
        top_k = np.argsort(sims)[::-1][:k]

        found = any(
            expected in chunks[idx].page_content.lower() for idx in top_k
        )
        hits += int(found)

        status = "HIT " if found else "MISS"
        print(f"[{status}] {query!r} (expected keyword: {expected!r})")

    print(f"\nhit-rate: {hits}/{len(cases)} ({100 * hits / len(cases):.0f}%)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path")
    parser.add_argument("--query", help="Run a single retrieval smoke test query.")
    parser.add_argument(
        "--eval",
        help='JSON file: [{"query": "...", "expected_keyword": "..."}, ...]',
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    chunks, analysis, config = build_chunks(args.file_path)
    embedder = Embedder.get(config)

    print(f"document_type: {analysis.document_type} | chunks: {len(chunks)}\n")

    vectors = np.array(embedder.embed_documents([c.page_content for c in chunks]))

    vector_sanity(vectors)
    similarity_report(vectors, chunks)

    if args.query:
        retrieval_smoke_test(embedder, vectors, chunks, args.query, args.top_k)

    if args.eval:
        eval_hit_rate(embedder, vectors, chunks, args.eval, args.top_k)

    if not args.query and not args.eval:
        print(
            "\nTip: pass --query \"some question about the document\" to see "
            "actual retrieval results, or --eval eval_set.json for a "
            "labeled hit-rate check."
        )


if __name__ == "__main__":
    main()
