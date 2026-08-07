"""
Tests for src/ingestion/api.py::ingest's temp-file naming -- the real
uploaded filename must survive into the path handed to
pipeline.ingest(), since MetadataGenerator derives every chunk's
"source" (and therefore every citation) from that path's name. Found
live via a demo smoke test: citations showed a random tempfile name
("tmp8f3ks.txt") instead of the file the user actually uploaded.

Same fake-out-IngestionPipeline-before-import pattern as
test_ingest_api_reload.py, for the same reason (avoids loading a real
embedding model in a unit test).
"""

import io
import sys
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_module():
    with patch("src.ingestion.pipeline.IngestionPipeline") as fake_pipeline_cls:
        fake_pipeline_cls.return_value = Mock()
        sys.modules.pop("src.ingestion.api", None)
        import src.ingestion.api as module

        yield module

    sys.modules.pop("src.ingestion.api", None)


def test_uploaded_filename_survives_into_pipeline_ingest_path(api_module, monkeypatch):
    from src.ingestion.analysers.models import ChunkingRecommendation, DocumentAnalysis

    fake_analysis = DocumentAnalysis(
        source="x",
        file_type="txt",
        document_type="general",
        language="english",
        statistics=None,
        layout=None,
        recommendation=ChunkingRecommendation(
            strategy="recursive",
            chunk_size=500,
            chunk_overlap=100,
            merge_small_chunks=False,
            split_large_chunks=False,
        ),
        confidence=0.5,
    )
    api_module.pipeline.ingest = Mock(return_value=([], fake_analysis))
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", None)

    client = TestClient(api_module.app)
    response = client.post(
        "/ingest",
        files={"file": ("my real document.txt", io.BytesIO(b"hello world"), "text/plain")},
    )

    assert response.status_code == 200
    called_path = api_module.pipeline.ingest.call_args[0][0]
    assert called_path.endswith("my real document.txt")
    assert "tmp" not in called_path.split("\\")[-1].split("/")[-1].lower()


def test_path_traversal_in_filename_is_stripped(api_module, monkeypatch):
    from src.ingestion.analysers.models import ChunkingRecommendation, DocumentAnalysis

    fake_analysis = DocumentAnalysis(
        source="x",
        file_type="txt",
        document_type="general",
        language="english",
        statistics=None,
        layout=None,
        recommendation=ChunkingRecommendation(
            strategy="recursive",
            chunk_size=500,
            chunk_overlap=100,
            merge_small_chunks=False,
            split_large_chunks=False,
        ),
        confidence=0.5,
    )
    api_module.pipeline.ingest = Mock(return_value=([], fake_analysis))
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", None)

    client = TestClient(api_module.app)
    response = client.post(
        "/ingest",
        files={"file": ("../../etc/passwd", io.BytesIO(b"x"), "text/plain")},
    )

    assert response.status_code == 200
    called_path = api_module.pipeline.ingest.call_args[0][0]
    assert ".." not in called_path
