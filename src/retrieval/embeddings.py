# src/retrieval/embeddings.py

"""
Embedding model factory used by both ingestion (to embed chunks)
and retrieval (to embed queries) so both sides always agree on
which model + normalization settings are in play.

NOTE: this module wasn't part of the uploaded zip (only `ingestion/`
was included) but is imported by `ingestion.pipeline`. This is a
minimal, working stand-in so the package runs end-to-end. If you
already have a fuller `src/retrieval/embeddings.py` in your real
repo, drop this one and keep yours -- just make sure `get()` accepts
`model_name` / `normalize` so the ingestion pipeline can pass the
values from `IngestionConfig` through.
"""

from functools import lru_cache

from src.utils.logger import logger

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingFactory:
    """
    Builds (and caches) embedding model instances.

    Caching matters in prod: loading a sentence-transformers model
    is expensive (disk + GPU/CPU init). Without caching, every
    IngestionPipeline() instantiation would reload the model from
    scratch.
    """

    @staticmethod
    @lru_cache(maxsize=8)
    def get(
        model_name: str = DEFAULT_MODEL,
        normalize: bool = True,
    ):
        logger.info(f"Loading embedding model: {model_name}")

        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            # Fallback for older langchain installs.
            from langchain_community.embeddings import (
                HuggingFaceEmbeddings,
            )

        return HuggingFaceEmbeddings(
            model_name=model_name,
            encode_kwargs={"normalize_embeddings": normalize},
        )
