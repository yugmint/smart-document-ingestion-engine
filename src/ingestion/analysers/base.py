from abc import ABC, abstractmethod

from langchain_core.documents import Document

from src.ingestion.analysers.models import DocumentAnalysis


class BaseAnalyzer(ABC):
    """
    Base class for all document analyzers.
    """

    @abstractmethod
    def analyze(
        self,
        documents: list[Document],
        file_path: str,
    ) -> DocumentAnalysis:
        """
        Analyze the loaded document and return
        document intelligence information.
        """

        raise NotImplementedError
