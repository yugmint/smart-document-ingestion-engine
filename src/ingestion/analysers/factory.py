# src/ingestion/analysers/factory.py

from pathlib import Path

from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
from src.ingestion.analysers.generic_analyzer import GenericAnalyzer
from src.ingestion.exceptions import UnsupportedDocumentError


class AnalyzerFactory:
    """
    Returns the appropriate analyzer based on the input document.
    """

    _ANALYZERS = {
        ".pdf": PDFAnalyzer,
        ".txt": GenericAnalyzer,
        ".html": GenericAnalyzer,
        ".htm": GenericAnalyzer,
        ".docx": GenericAnalyzer,
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
