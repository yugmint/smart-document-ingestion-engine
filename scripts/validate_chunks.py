#!/usr/bin/env python
"""
Validate chunking quality for a given document.

Usage:
    python scripts/validate_chunks.py path/to/file.pdf
    python scripts/validate_chunks.py path/to/file.pdf --dump-samples 5

What it checks (and why each one matters):

- Size distribution vs the recommended chunk_size
      Are chunks actually landing near the target size, or is
      something (e.g. an over-aggressive merge/split) skewing them?
- Empty / near-empty chunks
      Symptom of a cleaning or splitting bug producing junk chunks
      that add noise to the index without adding retrievable content.
- Exact duplicate chunks
      Usually means the same page/section is being processed twice,
      or a merge step is looping.
- Overlap between consecutive chunks
      If chunk_overlap > 0 in the recommendation but consecutive
      chunks share ~0 characters, the overlap logic isn't doing
      anything, which hurts retrieval at chunk boundaries.
- Mid-sentence boundary rate
      Rough proxy for "are we cutting through the middle of ideas."
      Not perfect (paragraph/heading breaks are legitimate), but a
      persistently high rate is a real signal to look at the
      strategy being used for this document type.

This intentionally does NOT require an embedding model -- it only
exercises load -> clean -> analyze -> chunk -> metadata, so it's fast
and works offline.
"""

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.loaders.pdf_loader import PDFLoader
from src.ingestion.cleaners.text_cleaner import TextCleaner
from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
from src.ingestion.chunkers.hybrid_chunker import HybridChunker
from src.ingestion.metadata.generator import MetadataGenerator
from src.ingestion.config import IngestionConfig

SENTENCE_ENDINGS = (".", "!", "?", '."', '!"', '?"', ":", ";")


def build_chunks(file_path: str):
    documents = PDFLoader().load(file_path)
    documents = TextCleaner().clean(documents)

    analysis = PDFAnalyzer().analyze(documents, file_path)

    config = IngestionConfig()
    chunks = HybridChunker(config).chunk(documents, analysis)
    chunks = MetadataGenerator().generate(chunks, file_path, analysis)

    return chunks, analysis


def overlap_length(a: str, b: str, max_check: int = 300) -> int:
    """Longest suffix of `a` that is a prefix-containing substring of `b`."""
    a_tail = a[-max_check:]
    for size in range(min(len(a_tail), len(b)), 0, -1):
        if a_tail[-size:] in b:
            return size
    return 0


def report(chunks, analysis):
    sizes = [len(c.page_content) for c in chunks]
    target = analysis.recommendation.chunk_size

    print("=" * 70)
    print("CHUNK SIZE DISTRIBUTION")
    print("=" * 70)
    print(f"count           : {len(sizes)}")
    print(f"target size     : {target}  (overlap={analysis.recommendation.chunk_overlap})")
    print(f"min / max       : {min(sizes)} / {max(sizes)}")
    print(f"mean / median   : {statistics.mean(sizes):.0f} / {statistics.median(sizes):.0f}")
    if len(sizes) > 1:
        print(f"stdev           : {statistics.stdev(sizes):.0f}")

    within_range = sum(1 for s in sizes if 0.5 * target <= s <= 1.5 * target)
    print(
        f"within 0.5x-1.5x target : {within_range}/{len(sizes)} "
        f"({100 * within_range / len(sizes):.0f}%)"
    )

    tiny = [c for c in chunks if len(c.page_content) < 20]
    print(f"\nnear-empty chunks (<20 chars): {len(tiny)}")
    for c in tiny[:5]:
        print(f"  - {c.page_content!r}")

    texts = [c.page_content for c in chunks]
    duplicates = len(texts) - len(set(texts))
    print(f"\nexact duplicate chunks: {duplicates}")

    print("\n" + "=" * 70)
    print("OVERLAP BETWEEN CONSECUTIVE CHUNKS")
    print("=" * 70)
    if analysis.recommendation.chunk_overlap == 0:
        print("chunk_overlap recommended as 0 for this document -- skipping.")
    else:
        overlaps = [
            overlap_length(chunks[i].page_content, chunks[i + 1].page_content)
            for i in range(len(chunks) - 1)
        ]
        zero_overlap = sum(1 for o in overlaps if o == 0)
        print(f"avg overlap length : {statistics.mean(overlaps):.0f} chars "
              f"(target ~{analysis.recommendation.chunk_overlap})")
        print(f"pairs with 0 overlap: {zero_overlap}/{len(overlaps)}")

    print("\n" + "=" * 70)
    print("BOUNDARY QUALITY (heuristic)")
    print("=" * 70)
    mid_sentence = sum(
        1 for c in chunks
        if c.page_content and not c.page_content.rstrip().endswith(SENTENCE_ENDINGS)
    )
    print(
        f"chunks NOT ending on sentence punctuation: {mid_sentence}/{len(chunks)} "
        f"({100 * mid_sentence / len(chunks):.0f}%)"
    )
    print(
        "(some of these are legitimate -- headings, list items, table rows --"
        " but a rate above ~30-40% is worth a manual look)"
    )


def dump_samples(chunks, n):
    print("\n" + "=" * 70)
    print(f"RANDOM SAMPLE OF {n} CHUNKS (for manual spot-check)")
    print("=" * 70)
    sample = random.sample(chunks, min(n, len(chunks)))
    for i, c in enumerate(sample):
        print(f"\n--- sample {i + 1} | {len(c.page_content)} chars | "
              f"page {c.metadata.get('page_number')} ---")
        print(c.page_content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path")
    parser.add_argument(
        "--dump-samples", type=int, default=0,
        help="Print N random full chunks for manual review.",
    )
    args = parser.parse_args()

    chunks, analysis = build_chunks(args.file_path)

    print(f"document_type   : {analysis.document_type}  "
          f"(confidence={analysis.confidence:.2f})")
    print(f"strategy        : {analysis.recommendation.strategy}")
    print(f"rationale       : {analysis.recommendation.rationale}\n")

    report(chunks, analysis)

    if args.dump_samples:
        dump_samples(chunks, args.dump_samples)


if __name__ == "__main__":
    main()
