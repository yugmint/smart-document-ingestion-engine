from langchain_core.documents import Document

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.recursive_chunker import RecursiveChunker

from src.ingestion.config import IngestionConfig

from src.ingestion.analysers.models import DocumentAnalysis

from src.utils.logger import logger


class StructureChunker(BaseChunker):
    """
    Structure-aware chunker.

    V1
    ---
    Delegates to RecursiveChunker, which means it already benefits
    from the analyzer's per-document chunk_size/overlap/merge/split
    recommendation -- it just doesn't yet use heading/section
    boundaries to decide *where* to cut.

    Future versions will preserve document hierarchy:

    Document
        ├── Title
        ├── Chapter
        ├── Section
        ├── Subsection
        ├── Paragraph
        ├── Table
        └── Figure

    before applying recursive chunking within each unit.
    """

    def __init__(self, config: IngestionConfig):
        self.config = config
        self.recursive = RecursiveChunker(config)

    def chunk(
        self,
        documents: list[Document],
        analysis: DocumentAnalysis | None = None,
    ) -> list[Document]:

        logger.info("=" * 80)
        logger.info("StructureChunker (V1)")

        if analysis is not None:
            logger.info(f"Document Type : {analysis.document_type}")

        logger.info("Using RecursiveChunker fallback (recommendation-aware).")

        return self.recursive.chunk(documents, analysis)
