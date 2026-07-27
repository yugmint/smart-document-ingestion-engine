from pathlib import Path

from langchain_core.documents import Document

from src.ingestion.loaders.base import BaseLoader
from src.ingestion.exceptions import DocumentLoadError, EmptyDocumentError


class TextLoader(BaseLoader):
    """
    Plain-text loader (.txt). No page concept -- one Document for the
    whole file, page_number left unset (None), same convention
    citations.py already expects for non-paginated sources.
    """

    def load(self, file_path: str) -> list[Document]:

        path = Path(file_path)

        if not path.exists():
            raise DocumentLoadError(f"File not found: {file_path}")

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise DocumentLoadError(f"'{path.name}' could not be read: {exc}") from exc

        if not text.strip():
            raise EmptyDocumentError(f"'{path.name}' is empty.")

        return [Document(page_content=text, metadata={"source": path.name})]
