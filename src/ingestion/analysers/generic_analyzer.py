# src/ingestion/analysers/generic_analyzer.py

from langchain_core.documents import Document

from src.ingestion.analysers.base import BaseAnalyzer
from src.ingestion.analysers.models import (
    ChunkingRecommendation,
    DocumentAnalysis,
    LayoutAnalysis,
)
from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer, _BASE_PROFILES

from src.utils.logger import logger


class GenericAnalyzer(BaseAnalyzer):
    """
    Analyzer for non-PDF formats (.txt/.html/.docx) that have no
    PDF-specific layout signal (equations/tables/references detection
    is all PDF-page-structure-driven -- see PDFAnalyzer). Always
    classifies "general" with the same baseline chunk profile PDFAnalyzer
    already falls back to for ambiguous documents -- real per-format
    classification is future work (ingestion_fixed v0.3.0's "real
    adaptive chunkers"), not required just to make these formats
    ingestable.

    Reuses PDFAnalyzer._extract_statistics -- pure text-stats math, not
    actually PDF-specific -- rather than duplicating it.
    """

    def analyze(self, documents: list[Document], file_path: str) -> DocumentAnalysis:

        logger.info("=" * 80)
        logger.info("Analyzing Document (generic)")

        statistics = PDFAnalyzer()._extract_statistics(documents)

        profile = _BASE_PROFILES["general"]

        recommendation = ChunkingRecommendation(
            strategy=profile["strategy"],
            chunk_size=profile["chunk_size"],
            chunk_overlap=profile["chunk_overlap"],
            merge_small_chunks=profile["merge_small_chunks"],
            split_large_chunks=profile["split_large_chunks"],
            rationale="non-PDF format -- base 'general' profile, no layout analysis available",
        )

        return DocumentAnalysis(
            source=file_path,
            file_type="document",
            document_type="general",
            language="english",
            statistics=statistics,
            layout=LayoutAnalysis(),
            recommendation=recommendation,
            confidence=0.5,
        )
