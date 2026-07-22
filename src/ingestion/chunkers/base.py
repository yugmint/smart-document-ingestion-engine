from abc import ABC, abstractmethod

from langchain_core.documents import Document

from src.ingestion.analysers.models import DocumentAnalysis


class BaseChunker(ABC):
    """
    Base interface for every chunking strategy.
    """

    @abstractmethod
    def chunk(
        self,
        documents: list[Document],
        analysis: DocumentAnalysis | None = None,
    ) -> list[Document]:

        raise NotImplementedError
