# src/ingestion/analysers/pdf_analyzer.py
from pathlib import Path
import re

from langchain_core.documents import Document

from src.ingestion.analysers.base import BaseAnalyzer

from src.ingestion.analysers.models import (
    ChunkingRecommendation,
    DocumentAnalysis,
    DocumentStatistics,
    LayoutAnalysis,
)

from src.utils.logger import logger

# --------------------------------------------------------------
# Baseline chunking profiles per document type.
#
# These are *starting points*. `_recommend_chunking` adjusts
# chunk_size/overlap/merge/split away from these baselines using
# the document's actual statistics (see below), so two "book"
# documents with very different paragraph structure won't get the
# identical recommendation.
# --------------------------------------------------------------
_BASE_PROFILES: dict[str, dict] = {
    "research_paper": dict(
        strategy="structure",
        chunk_size=450,
        chunk_overlap=100,
        merge_small_chunks=True,
        split_large_chunks=True,
    ),
    "book": dict(
        strategy="recursive",
        chunk_size=800,
        chunk_overlap=150,
        merge_small_chunks=True,
        split_large_chunks=False,
    ),
    "legal": dict(
        strategy="structure",
        chunk_size=1000,
        chunk_overlap=150,
        merge_small_chunks=False,
        split_large_chunks=False,
    ),
    "invoice": dict(
        strategy="structure",
        chunk_size=300,
        chunk_overlap=50,
        merge_small_chunks=True,
        split_large_chunks=True,
    ),
    "general": dict(
        strategy="recursive",
        chunk_size=500,
        chunk_overlap=100,
        merge_small_chunks=True,
        split_large_chunks=True,
    ),
}

_MIN_CHUNK_SIZE = 100
_MAX_CHUNK_SIZE = 2000
_MIN_OVERLAP = 20

# Many medical/clinical journals use a structured abstract
# (Background/Objective/Methods/Results/Conclusions) with no literal word
# "Abstract" printed anywhere -- found via a real paper (Hu et al. 2020,
# COVID-19 severity study) that fell through the literal-"abstract" check
# entirely. Each tuple is one concept; a single incidental word match
# (e.g. "results" in ordinary prose) shouldn't count as much as several
# structured-abstract section headers appearing together.
_STRUCTURED_ABSTRACT_CONCEPTS: tuple[tuple[str, ...], ...] = (
    ("background",),
    ("objective", "objectives"),
    ("methods", "methodology"),
    ("results",),
    ("conclusion", "conclusions"),
)
_STRUCTURED_ABSTRACT_MIN_HITS = 3

# A bare "agreement" substring matches plenty of non-legal prose -- found
# via the same paper: "...crude agreement were all over 85%" (a
# statistics term for inter-rater agreement) misclassified the whole
# document `legal`. Require an actual legal-agreement phrase instead.
_LEGAL_PHRASES = (
    "this agreement",
    "the parties agree",
    "in witness whereof",
    "governing law",
    "entered into this agreement",
)


class PDFAnalyzer(BaseAnalyzer):
    """
    Performs structural analysis of PDF documents.

    The analyzer does NOT modify the document.

    It only extracts information that helps the ingestion pipeline
    choose the optimal chunking strategy, and how confident it is
    in that choice.
    """

    def analyze(
        self,
        documents: list[Document],
        file_path: str,
    ) -> DocumentAnalysis:

        logger.info("=" * 80)
        logger.info("Analyzing PDF Document")

        statistics = self._extract_statistics(documents)

        layout = self._analyze_layout(documents)

        document_type = self._classify_document(documents, layout)

        recommendation = self._recommend_chunking(
            document_type,
            statistics,
        )

        confidence = self._score_confidence(
            document_type,
            layout,
            statistics,
        )

        analysis = DocumentAnalysis(
            source=Path(file_path).name,
            file_type="pdf",
            language="english",
            document_type=document_type,
            statistics=statistics,
            layout=layout,
            recommendation=recommendation,
            confidence=confidence,
            metadata={
                "pages": statistics.page_count,
                "words": statistics.word_count,
            },
        )

        logger.info(f"Detected Document Type : {document_type}")
        logger.info(f"Confidence              : {confidence:.2f}")
        logger.info(f"Recommended Chunker     : {recommendation.strategy}")
        logger.info(
            f"Chunk Size/Overlap      : "
            f"{recommendation.chunk_size}/{recommendation.chunk_overlap}"
        )
        logger.info(f"Rationale               : {recommendation.rationale}")

        return analysis

    # --------------------------------------------------
    # Statistics
    # --------------------------------------------------

    def _extract_statistics(
        self,
        documents: list[Document],
    ) -> DocumentStatistics:

        text = "\n".join(document.page_content for document in documents)

        pages = len(documents)
        characters = len(text)
        words = len(text.split())
        estimated_tokens = int(words * 1.3)

        paragraphs = [
            p.strip() for p in text.split("\n\n") if p.strip()
        ]

        sentences = [
            s for s in re.split(r"[.!?]", text) if s.strip()
        ]

        lines = [line for line in text.splitlines() if line.strip()]

        return DocumentStatistics(
            page_count=pages,
            character_count=characters,
            word_count=words,
            estimated_tokens=estimated_tokens,
            average_page_length=characters / max(pages, 1),
            average_paragraph_length=(
                sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)
            ),
            average_sentence_length=(
                sum(len(s) for s in sentences) / max(len(sentences), 1)
            ),
            average_line_length=(
                sum(len(line) for line in lines) / max(len(lines), 1)
            ),
        )

    # --------------------------------------------------
    # Layout
    # --------------------------------------------------

    def _analyze_layout(
        self,
        documents: list[Document],
    ) -> LayoutAnalysis:

        text = "\n".join(d.page_content for d in documents)

        headings = bool(
            re.search(
                r"^(chapter|abstract|introduction|references|conclusion)",
                text,
                re.IGNORECASE | re.MULTILINE,
            )
        )

        tables = "|" in text

        bullets = bool(re.search(r"^\s*[-•*]", text, re.MULTILINE))

        equations = bool(re.search(r"[=+\-*/]{2,}", text))

        references = bool(re.search(r"references", text, re.IGNORECASE))

        return LayoutAnalysis(
            has_headings=headings,
            has_tables=tables,
            has_lists=bullets,
            has_equations=equations,
            has_references=references,
            has_images=False,
            has_code_blocks=False,
            has_footnotes=False,
        )

    # --------------------------------------------------
    # Classification
    # --------------------------------------------------

    def _classify_document(self, documents, layout) -> str:

        text = "\n".join(d.page_content.lower() for d in documents[:5])

        has_literal_abstract = "abstract" in text
        structured_abstract_hits = sum(
            any(keyword in text for keyword in concept)
            for concept in _STRUCTURED_ABSTRACT_CONCEPTS
        )
        looks_like_structured_abstract = (
            structured_abstract_hits >= _STRUCTURED_ABSTRACT_MIN_HITS
        )

        if (
            (has_literal_abstract or looks_like_structured_abstract)
            and layout.has_references
        ):
            return "research_paper"

        if "invoice" in text:
            return "invoice"

        # "chapter"/"table of contents" alone isn't enough -- a dense
        # technical/reference document (equations, tables) that happens to
        # open with "Chapter N" is not the narrative prose "book" is tuned
        # for (chunk_size=800, split_large_chunks=False). Corroborate
        # against layout signals already computed for other purposes
        # before committing to "book"; a false positive here fell through
        # to a worse-fitting profile than "general" would have. See
        # docs/05-roadmap.md and the 2026-07-24 academic-document report.
        looks_technical = layout.has_equations or layout.has_tables
        if ("chapter" in text or "table of contents" in text) and not looks_technical:
            return "book"

        if any(phrase in text for phrase in _LEGAL_PHRASES):
            return "legal"

        return "general"

    # --------------------------------------------------
    # Chunk Recommendation
    # --------------------------------------------------

    def _recommend_chunking(
        self,
        document_type: str,
        statistics: DocumentStatistics,
    ) -> ChunkingRecommendation:

        profile = _BASE_PROFILES.get(document_type, _BASE_PROFILES["general"])

        chunk_size = profile["chunk_size"]
        merge_small_chunks = profile["merge_small_chunks"]
        split_large_chunks = profile["split_large_chunks"]

        rationale = [f"base profile for document_type='{document_type}'"]

        avg_paragraph = statistics.average_paragraph_length

        # Dense, long-form prose (e.g. legal boilerplate, long
        # unbroken narrative): widen the window so we don't slice
        # a paragraph mid-thought.
        if avg_paragraph > chunk_size * 2:
            grown = min(int(chunk_size * 1.4), _MAX_CHUNK_SIZE)
            rationale.append(
                f"avg paragraph length ({avg_paragraph:.0f} chars) is large "
                f"relative to the base window; growing chunk_size to {grown}"
            )
            chunk_size = grown

        # Short, choppy paragraphs (lists, dialogue, line-item
        # tables): shrink the window and make sure tiny leftover
        # chunks get merged back in downstream.
        elif 0 < avg_paragraph < chunk_size * 0.15:
            shrunk = max(int(chunk_size * 0.7), _MIN_CHUNK_SIZE)
            rationale.append(
                f"avg paragraph length ({avg_paragraph:.0f} chars) is small "
                f"(list/dialogue/tabular-like); shrinking chunk_size to "
                f"{shrunk} and forcing merge_small_chunks"
            )
            chunk_size = shrunk
            merge_small_chunks = True

        # Overlap scales with the final chunk_size (~20%), bounded
        # so it's never trivially small or larger than half the
        # window.
        chunk_overlap = max(
            _MIN_OVERLAP,
            min(int(chunk_size * 0.2), chunk_size // 2),
        )

        # If paragraphs are still far larger than the chunk window
        # even after adjustment (common in scanned/columnar PDFs
        # with poor paragraph breaks), force hard splitting even if
        # the type profile said to preserve unbroken units --
        # otherwise we'd emit a single oversized "chunk" per
        # paragraph.
        if avg_paragraph > chunk_size * 3 and not split_large_chunks:
            rationale.append(
                f"avg paragraph length ({avg_paragraph:.0f} chars) exceeds "
                f"3x chunk_size even after adjustment; overriding "
                f"split_large_chunks=True to avoid oversized chunks"
            )
            split_large_chunks = True

        min_chunk_size = max(_MIN_CHUNK_SIZE, int(chunk_size * 0.25))

        return ChunkingRecommendation(
            strategy=profile["strategy"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            merge_small_chunks=merge_small_chunks,
            split_large_chunks=split_large_chunks,
            min_chunk_size=min_chunk_size,
            rationale="; ".join(rationale),
        )

    # --------------------------------------------------
    # Confidence
    # --------------------------------------------------

    def _score_confidence(
        self,
        document_type: str,
        layout: LayoutAnalysis,
        statistics: DocumentStatistics,
    ) -> float:
        """
        Heuristic confidence (0-1) in the document_type classification
        (and therefore in the derived recommendation).

        This is intentionally simple (v1): a keyword-based classifier
        can't give a real posterior probability, so this rewards
        corroborating signals (e.g. a "research_paper" call backed by
        a references section) and penalizes documents too short to
        classify reliably in the first place.
        """

        score = 0.55 if document_type == "general" else 0.80

        if layout.has_headings:
            score += 0.05

        if document_type == "research_paper" and layout.has_references:
            score += 0.05

        if statistics.word_count < 50:
            score -= 0.35
        elif statistics.word_count < 150:
            score -= 0.15

        return round(max(0.05, min(0.99, score)), 2)
