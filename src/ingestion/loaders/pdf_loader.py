# src/ingestion/loaders/pdf_loader.py

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from langchain_core.documents import Document

from src.ingestion.loaders.base import BaseLoader
from src.ingestion.exceptions import DocumentLoadError, EmptyDocumentError

from src.utils.logger import logger


class PDFLoader(BaseLoader):
    """
    PDF document loader.
    """

    def load(
        self,
        file_path: str,
    ) -> list[Document]:

        logger.info("=" * 80)
        logger.info("Loading PDF Document")

        path = Path(file_path)

        if not path.exists():
            raise DocumentLoadError(f"File not found: {file_path}")

        try:
            reader = PdfReader(str(path))
        except PdfReadError as exc:
            raise DocumentLoadError(
                f"'{path.name}' could not be parsed as a PDF: {exc}"
            ) from exc

        if reader.is_encrypted:
            # Try an empty password first (some PDFs are "encrypted"
            # only to disable printing/editing but open freely).
            try:
                reader.decrypt("")
            except Exception as exc:
                raise DocumentLoadError(
                    f"'{path.name}' is password-protected and could not "
                    f"be opened: {exc}"
                ) from exc

        documents: list[Document] = []
        failed_pages = 0

        for index, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                # Don't let one malformed page take down the whole
                # document -- log it, keep the page as empty text,
                # and keep going.
                logger.warning(
                    f"Failed to extract text from page {index + 1} "
                    f"of '{path.name}': {exc}"
                )
                text = ""
                failed_pages += 1

            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "page_number": index + 1,
                        "source": path.name,
                    },
                )
            )

        if failed_pages:
            logger.warning(
                f"{failed_pages}/{len(documents)} page(s) failed text "
                f"extraction in '{path.name}'."
            )

        total_chars = sum(len(d.page_content) for d in documents)

        if total_chars == 0:
            raise EmptyDocumentError(
                f"'{path.name}' produced no extractable text on any of "
                f"{len(documents)} page(s) -- it may be a scanned/"
                f"image-only PDF and needs OCR before ingestion."
            )

        logger.info(f"Pages Loaded : {len(documents)}")

        return documents
