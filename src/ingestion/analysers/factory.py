# src/ingestion/analysers/factory.py

from pathlib import Path

from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
from src.ingestion.exceptions import UnsupportedDocumentError


class AnalyzerFactory:
    """
    Returns the appropriate analyzer based on the input document.
    """

    _ANALYZERS = {
        ".pdf": PDFAnalyzer,
    }

    @staticmethod
    def build(file_path: str):

        extension = Path(file_path).suffix.lower()

        analyzer_cls = AnalyzerFactory._ANALYZERS.get(extension)

        if analyzer_cls is None:
            raise UnsupportedDocumentError(
                f"No analyzer available for '{extension}'."
            )

        return analyzer_cls()
