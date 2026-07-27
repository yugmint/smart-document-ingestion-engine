from pathlib import Path

from bs4 import BeautifulSoup
from langchain_core.documents import Document

from src.ingestion.loaders.base import BaseLoader
from src.ingestion.exceptions import DocumentLoadError, EmptyDocumentError


class HTMLLoader(BaseLoader):
    """
    HTML loader (.html/.htm). Uses BeautifulSoup (already an installed
    transitive dependency -- no new one added for this). Strips
    script/style tags before extracting text; no page concept, same as
    TextLoader.
    """

    def load(self, file_path: str) -> list[Document]:

        path = Path(file_path)

        if not path.exists():
            raise DocumentLoadError(f"File not found: {file_path}")

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise DocumentLoadError(f"'{path.name}' could not be read: {exc}") from exc

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()

        text = soup.get_text(separator="\n").strip()

        if not text:
            raise EmptyDocumentError(f"'{path.name}' has no extractable text.")

        return [Document(page_content=text, metadata={"source": path.name})]
