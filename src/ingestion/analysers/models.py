# src/ingestion/analysers/models.py

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DocumentStatistics:
    """
    Low-level statistics extracted from the document.
    """

    page_count: int

    character_count: int

    word_count: int

    estimated_tokens: int

    average_page_length: float

    average_paragraph_length: float

    average_sentence_length: float

    average_line_length: float


@dataclass(slots=True)
class LayoutAnalysis:
    """
    Structural information detected within the document.
    """

    has_headings: bool = False

    has_tables: bool = False

    has_lists: bool = False

    has_images: bool = False

    has_equations: bool = False

    has_code_blocks: bool = False

    has_footnotes: bool = False

    has_references: bool = False


@dataclass(slots=True)
class ChunkingRecommendation:
    """
    Recommended chunking strategy produced by the analyzer.
    """

    strategy: str

    chunk_size: int

    chunk_overlap: int

    merge_small_chunks: bool

    split_large_chunks: bool

    # Chunks below this length (in characters) are candidates for
    # merging into a neighbor when `merge_small_chunks` is True.
    min_chunk_size: int = 0

    # Human-readable explanation of how this recommendation was
    # derived. Purely for observability/debugging -- log it, don't
    # parse it.
    rationale: str = ""


@dataclass(slots=True)
class DocumentAnalysis:
    """
    Final analysis object passed to the HybridChunker.
    """

    source: str

    file_type: str

    document_type: str

    language: str

    statistics: DocumentStatistics

    layout: LayoutAnalysis

    recommendation: ChunkingRecommendation

    # Confidence (0-1) in `document_type` and, by extension, the
    # derived recommendation. Low confidence (e.g. very short or
    # ambiguous documents) is surfaced so callers can decide to
    # fall back to a safe default strategy or flag for review.
    confidence: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)
