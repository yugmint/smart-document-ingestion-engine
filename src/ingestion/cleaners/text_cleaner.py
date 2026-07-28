import re
from collections import Counter

from langchain_core.documents import Document

from src.ingestion.cleaners.base import BaseCleaner
from src.utils.logger import logger

# How many lines from the top/bottom of each page count as "header/footer
# territory" -- real headers/footers live in the first/last couple of
# lines, not scattered through the body. Checking a few extra lines
# (rather than just 1) catches multi-line branding blocks like the real
# one this was built against: a company-locations line followed by a
# "page N | url | phone | copyright" line followed by a bare "Student
# Notes:" label, all three repeated on every page.
_EDGE_LINES = 4

# A line pattern needs to repeat on at least this fraction of pages (and
# at least 3 pages outright, so a 2-page document doesn't get its actual
# content stripped just because both pages happen to share a line) before
# it's treated as noise rather than real content that happens to repeat.
_MIN_PAGE_FRACTION = 0.5
_MIN_PAGE_COUNT = 3


def _normalize_line(line: str) -> str:
    """
    Collapses whatever varies page-to-page (mainly page numbers) so a
    real repeated header/footer line matches across pages even though
    the literal text isn't byte-identical -- e.g. "37 www.site.com" and
    "38 www.site.com" both normalize to "# www.site.com".
    """
    normalized = re.sub(r"\d+", "#", line.strip().lower())
    return re.sub(r"\s+", " ", normalized)


def _find_repeated_lines(documents: list[Document]) -> set[str]:
    """
    Returns the set of normalized line patterns that repeat across
    enough pages to be header/footer noise rather than real content.
    """

    if len(documents) < _MIN_PAGE_COUNT:
        return set()

    counts: Counter = Counter()

    for document in documents:
        lines = [l for l in (document.page_content or "").split("\n") if l.strip()]
        edge_lines = lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]
        # A pattern should only count once per page even if it somehow
        # appears twice in that page's edge lines.
        for pattern in {_normalize_line(l) for l in edge_lines if l.strip()}:
            counts[pattern] += 1

    threshold = max(_MIN_PAGE_COUNT, int(len(documents) * _MIN_PAGE_FRACTION))

    return {pattern for pattern, count in counts.items() if count >= threshold}


class TextCleaner(BaseCleaner):
    """
    Cleans document text before chunking.

    Current operations:

    • Remove repeated header/footer lines (branding, page furniture)
    • Normalize whitespace
    • Remove extra blank lines
    • Strip leading/trailing spaces
    • Normalize line endings

    Future:

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

        # Needs every page at once -- a line is only "repeated" relative
        # to the rest of the document, not something a single page's text
        # can tell you on its own. Real 2026-07-28 finding this was built
        # for: 16.7% of chunks on a real 117-page book carried a
        # publisher branding line repeated on nearly every page.
        noise_patterns = _find_repeated_lines(documents)
        if noise_patterns:
            logger.info(f"Detected {len(noise_patterns)} repeated header/footer line(s).")

        cleaned_documents = []
        stripped_line_count = 0

        for document in documents:

            text = document.page_content or ""

            # Normalize line endings
            text = text.replace("\r\n", "\n")
            text = text.replace("\r", "\n")

            if noise_patterns:
                kept_lines = []
                for line in text.split("\n"):
                    if line.strip() and _normalize_line(line) in noise_patterns:
                        stripped_line_count += 1
                        continue
                    kept_lines.append(line)
                text = "\n".join(kept_lines)

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

        if stripped_line_count:
            logger.info(f"Stripped {stripped_line_count} repeated header/footer line(s).")

        logger.info(f"Cleaned {len(cleaned_documents)} documents.")

        return cleaned_documents
