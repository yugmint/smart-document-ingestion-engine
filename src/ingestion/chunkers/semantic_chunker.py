from langchain_core.documents import Document

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.recursive_chunker import RecursiveChunker

from src.ingestion.config import IngestionConfig

from src.ingestion.analysers.models import DocumentAnalysis

from src.utils.logger import logger


class SemanticChunker(BaseChunker):
    """
    Semantic-aware chunker.

    V1
    ---
    Delegates to RecursiveChunker (recommendation-aware).

    Future versions will:

    • detect semantic boundaries via embedding similarity
    • preserve topic continuity
    • avoid splitting related concepts
    • optimize retrieval quality
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
        logger.info("SemanticChunker (V1)")
        logger.info("Using RecursiveChunker fallback (recommendation-aware).")

        return self.recursive.chunk(documents, analysis)
