import re

from langchain_core.documents import Document

from src.ingestion.cleaners.base import BaseCleaner
from src.utils.logger import logger


class TextCleaner(BaseCleaner):
    """
    Cleans document text before chunking.

    Current operations:

    • Normalize whitespace
    • Remove extra blank lines
    • Strip leading/trailing spaces
    • Normalize line endings

    Future:

    • Header/Footer removal
    • OCR cleanup
    • Unicode normalization
    • Hyphenation repair
    • Table cleanup
    """

    def clean(
        self,
        documents: list[Document],
    ) -> list[Document]:

        logger.info("=" * 80)
        logger.info("Cleaning Documents")

        cleaned_documents = []

        for document in documents:

            text = document.page_content or ""

            # Normalize line endings
            text = text.replace("\r\n", "\n")
            text = text.replace("\r", "\n")

            # Remove multiple blank lines
            text = re.sub(r"\n{3,}", "\n\n", text)

            # Remove repeated spaces/tabs
            text = re.sub(r"[ \t]+", " ", text)

            # Trim each line
            text = "\n".join(line.strip() for line in text.split("\n"))

            # Final strip
            text = text.strip()

            document.page_content = text

            cleaned_documents.append(document)

        logger.info(f"Cleaned {len(cleaned_documents)} documents.")

        return cleaned_documents
