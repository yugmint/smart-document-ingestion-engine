# src/ingestion/config.py

"""
Global configuration for the ingestion pipeline.

Values can be overridden via environment variables for
containerized/prod deployments, e.g.:

    INGESTION_CHUNK_SIZE=800 INGESTION_INDEX_PATH=/data/vectorstore \
        python -m ingestion.pipeline
"""

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(slots=True)
class IngestionConfig:
    """
    Configuration used throughout the ingestion pipeline.

    These are *defaults*. Per-document values recommended by the
    analyzer (`DocumentAnalysis.recommendation`) take precedence
    over `chunk_size` / `chunk_overlap` / `chunk_strategy` at
    chunk time -- these fields exist mainly as the fallback used
    when no analysis is available (e.g. unit tests) and as the
    baseline the analyzer's recommendation logic adjusts from.
    """

    # -----------------------------
    # Chunking (fallback defaults)
    # -----------------------------
    chunk_strategy: str = field(
        default_factory=lambda: _env_str("INGESTION_CHUNK_STRATEGY", "recursive")
    )

    chunk_size: int = field(
        default_factory=lambda: _env_int("INGESTION_CHUNK_SIZE", 500)
    )

    chunk_overlap: int = field(
        default_factory=lambda: _env_int("INGESTION_CHUNK_OVERLAP", 100)
    )

    separators: tuple[str, ...] = (
        "\n\n",
        "\n",
        ". ",
        " ",
        "",
    )

    # -----------------------------
    # Embeddings
    # -----------------------------
    embedding_model: str = field(
        default_factory=lambda: _env_str(
            "INGESTION_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
    )

    normalize_embeddings: bool = field(
        default_factory=lambda: _env_bool("INGESTION_NORMALIZE_EMBEDDINGS", True)
    )

    # -----------------------------
    # Indexing
    # -----------------------------
    vector_store: str = field(
        default_factory=lambda: _env_str("INGESTION_VECTOR_STORE", "faiss")
    )

    index_path: str = field(
        default_factory=lambda: _env_str("INGESTION_INDEX_PATH", "vectorstore")
    )

    # -----------------------------
    # Metadata
    # -----------------------------
    include_page_number: bool = True

    include_source: bool = True

    include_chunk_id: bool = True

    include_token_count: bool = True

    # -----------------------------
    # Validation
    # -----------------------------
    max_document_size_mb: int = field(
        default_factory=lambda: _env_int("INGESTION_MAX_DOCUMENT_SIZE_MB", 100)
    )

    supported_extensions: tuple[str, ...] = (".pdf", ".txt", ".html", ".htm", ".docx")

    def __post_init__(self):
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer.")

        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative.")

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than "
                f"chunk_size ({self.chunk_size})."
            )

        if self.max_document_size_mb <= 0:
            raise ValueError("max_document_size_mb must be a positive integer.")

        # Only FAISSIndexer exists -- pipeline.py always builds one
        # regardless of this value, so silently accepting e.g. "chroma"
        # here would look configured but do nothing. Fail loudly instead
        # of at query time weeks later. Revisit if a second backend is
        # ever actually implemented.
        if self.vector_store != "faiss":
            raise ValueError(
                f"Unsupported vector_store: '{self.vector_store}' -- only "
                f"'faiss' is currently implemented."
            )
