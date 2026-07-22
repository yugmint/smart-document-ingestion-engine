from langchain_core.documents import Document

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.recursive_chunker import RecursiveChunker

from src.ingestion.config import IngestionConfig

from src.ingestion.analysers.models import DocumentAnalysis

from src.utils.logger import logger


class MarkdownChunker(BaseChunker):
    """
    Markdown-aware chunker.

    V1
    ---
    Delegates to RecursiveChunker (recommendation-aware).

    Future versions will preserve:

    • headings
    • code blocks
    • tables
    • fenced regions
    • lists
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
        logger.info("MarkdownChunker (V1)")
        logger.info("Using RecursiveChunker fallback (recommendation-aware).")

        return self.recursive.chunk(documents, analysis)
