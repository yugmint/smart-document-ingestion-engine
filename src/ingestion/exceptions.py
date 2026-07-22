# src/ingestion/exceptions.py

"""
Exception hierarchy for the ingestion pipeline.

Callers (APIs, batch jobs, workers) can catch `IngestionError` to
handle any pipeline failure uniformly, or catch a specific subclass
to react differently (e.g. retry on `EmbeddingError`, skip-and-log
on `UnsupportedDocumentError`).
"""


class IngestionError(Exception):
    """Base class for all ingestion pipeline failures."""


class UnsupportedDocumentError(IngestionError):
    """Raised when a document type/extension has no loader or analyzer."""


class DocumentTooLargeError(IngestionError):
    """Raised when a document exceeds `IngestionConfig.max_document_size_mb`."""


class DocumentLoadError(IngestionError):
    """Raised when a document exists but cannot be parsed/loaded."""


class EmptyDocumentError(IngestionError):
    """Raised when a document loads successfully but yields no usable text."""
