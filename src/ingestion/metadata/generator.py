import re
from pathlib import Path

from langchain_core.documents import Document

from src.ingestion.analysers.models import DocumentAnalysis
from src.utils.logger import logger

# Per-chunk citation-density signal, not a "heading, then everything
# after" cutoff. A "References" heading looked reliable until tested
# against a real two-column-layout PDF: pypdf's column-order extraction
# put the heading itself at the very end of the page's text, *after*
# several actual citations that were extracted earlier -- a
# heading-position cutoff got the boundary badly wrong on that document,
# excluding real body content and missing several real citations. `doi:`
# and `Medline:` identifiers, by contrast, only ever appear inside
# citations themselves (never body prose) and survive column-order
# scrambling since they're evaluated per-chunk, not by position relative
# to a single detected heading. See docs/05-roadmap.md.
_CITATION_MARKER_RE = re.compile(r"\bdoi:|\bmedline:", re.IGNORECASE)
_MIN_CITATION_MARKERS = 2


class MetadataGenerator:
    """
    Enrich document chunks with metadata.

    This stage prepares chunks for indexing and
    future metadata-aware retrieval.
    """

    def generate(
        self,
        chunks: list[Document],
        source: str,
        analysis: DocumentAnalysis | None = None,
    ) -> list[Document]:

        logger.info("=" * 80)
        logger.info("Generating Metadata")

        filename = Path(source).name

        for chunk_id, chunk in enumerate(chunks):

            metadata = dict(chunk.metadata)

            metadata.update(
                {
                    "chunk_id": chunk_id,
                    "source": filename,
                    # NOTE: this is the *file extension* (e.g. "pdf"),
                    # not the semantic classification the analyzer
                    # produces (e.g. "research_paper"). Those used to
                    # collide under the same "document_type" key --
                    # kept distinct here so retrieval-time filters
                    # can't accidentally match the wrong thing.
                    "file_extension": Path(source).suffix.lower().replace(".", ""),
                    "character_count": len(chunk.page_content),
                    "word_count": len(chunk.page_content.split()),
                    # Approximation
                    "token_estimate": int(len(chunk.page_content) / 4),
                    # Section-role hints for retrieval-time filtering --
                    # e.g. excluding bibliography noise from the
                    # candidate pool, or preferring title-page content
                    # for "what is this document" style questions.
                    # Found necessary via a real failure: a citation
                    # formatted like "Authors. Title. Venue, Year." in a
                    # reference list got mistaken for the document's own
                    # title by the generation step. See
                    # docs/05-roadmap.md.
                    "is_reference_section": (
                        len(_CITATION_MARKER_RE.findall(chunk.page_content))
                        >= _MIN_CITATION_MARKERS
                    ),
                    "is_first_page": chunk.metadata.get("page_number") == 1,
                }
            )

            if analysis is not None:
                metadata.update(
                    {
                        "document_type": analysis.document_type,
                        "language": analysis.language,
                        "chunking_strategy": analysis.recommendation.strategy,
                        "analysis_confidence": analysis.confidence,
                    }
                )

            chunk.metadata = metadata

        logger.info(f"Metadata generated for {len(chunks)} chunks.")

        return chunks
