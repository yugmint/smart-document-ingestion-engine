from langchain_core.documents import Document

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.factory import ChunkerFactory

from src.ingestion.analysers.models import DocumentAnalysis
from src.ingestion.config import IngestionConfig

from src.utils.logger import logger


class HybridChunker(BaseChunker):
    """
    Orchestrates chunking by delegating to the
    appropriate chunking strategy selected by the
    ChunkerFactory, using the analyzer's per-document
    recommendation (strategy, chunk_size, chunk_overlap,
    merge/split behavior).
    """

    def __init__(self, config: IngestionConfig):
        self.config = config

    def chunk(
        self,
        documents: list[Document],
        analysis: DocumentAnalysis,
    ) -> list[Document]:

        logger.info("=" * 80)
        logger.info("HybridChunker: Selecting chunking strategy.")

        chunker = ChunkerFactory.build(
            recommendation=analysis.recommendation,
            config=self.config,
        )

        return chunker.chunk(documents, analysis)
