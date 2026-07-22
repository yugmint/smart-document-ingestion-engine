# src/ingestion/models.py

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DocumentChunk:
    """
    Represents a processed chunk ready for embedding.

    Not currently produced by the pipeline itself (which works with
    langchain `Document` objects throughout), but kept as a stable,
    framework-agnostic shape for other layers (APIs, batch exports)
    that shouldn't need a langchain dependency just to describe a
    chunk.
    """

    chunk_id: int

    text: str

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddingRecord:
    """
    Represents an embedded chunk.
    """

    chunk: DocumentChunk

    embedding_dimension: int


@dataclass(slots=True)
class IngestionReport:
    """
    Summary of an ingestion run. Returned via
    `DocumentAnalysis.metadata["ingestion_report"]` after
    `IngestionPipeline.ingest()` completes.
    """

    source: str

    total_pages: int

    total_chunks: int

    average_chunk_size: float

    embedding_model: str

    vector_store: str

    processing_time: float

    document_type: str = ""

    chunking_strategy: str = ""

    confidence: float = 0.0
