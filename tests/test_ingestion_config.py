import pytest

from src.ingestion.config import IngestionConfig


def test_faiss_vector_store_is_accepted():
    config = IngestionConfig(vector_store="faiss")
    assert config.vector_store == "faiss"


def test_unsupported_vector_store_raises():
    # Only FAISSIndexer exists -- pipeline.py always builds one
    # regardless of this value, so an unsupported value must fail
    # loudly here instead of silently doing nothing.
    with pytest.raises(ValueError, match="vector_store"):
        IngestionConfig(vector_store="chroma")
