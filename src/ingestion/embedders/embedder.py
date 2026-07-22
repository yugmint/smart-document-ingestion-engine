# src/ingestion/embedders/embedder.py

from src.ingestion.config import IngestionConfig
from src.retrieval.embeddings import EmbeddingFactory


class Embedder:
    """
    Thin wrapper around the application's embedding model.

    Keeping this indirection means `ingestion` never needs to know
    how `src.retrieval.embeddings` builds/caches models internally
    -- it just asks for "the embedding model this config points at."
    """

    @staticmethod
    def get(config: IngestionConfig):
        return EmbeddingFactory.get(
            model_name=config.embedding_model,
            normalize=config.normalize_embeddings,
        )
