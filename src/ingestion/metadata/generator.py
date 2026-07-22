from pathlib import Path

from langchain_core.documents import Document

from src.ingestion.analysers.models import DocumentAnalysis
from src.utils.logger import logger


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
