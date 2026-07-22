"""
Document ingestion pipeline: load -> clean -> analyze -> chunk ->
enrich metadata -> embed -> index.

Entry point: `ingestion.pipeline.IngestionPipeline`.
"""

from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.exceptions import IngestionError

__all__ = ["IngestionPipeline", "IngestionError"]
