from pathlib import Path

from src.ingestion.loaders.pdf_loader import PDFLoader
from src.ingestion.exceptions import UnsupportedDocumentError


class LoaderFactory:
    """
    Returns the appropriate document loader.
    """

    _LOADERS = {
        ".pdf": PDFLoader,
    }

    @staticmethod
    def build(file_path: str):

        extension = Path(file_path).suffix.lower()

        loader_cls = LoaderFactory._LOADERS.get(extension)

        if loader_cls is None:
            raise UnsupportedDocumentError(
                f"Unsupported document type: {extension}"
            )

        return loader_cls()
