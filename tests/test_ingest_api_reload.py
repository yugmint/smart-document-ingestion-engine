"""
Tests for src/ingestion/api.py::_notify_rag_reload -- the best-effort
POST to the sibling RAG API's /reload after a successful /ingest.

Importing src.ingestion.api triggers `pipeline = IngestionPipeline()` at
module level, which loads a real embedding model (~15s) -- that's fine
for the actual service, but far too slow for a unit test of one HTTP
helper function. Faking IngestionPipeline out *before* the import (via
sys.modules, since Python caches imports) keeps this fast and avoids
needing real model weights in CI.
"""

import sys
from unittest.mock import Mock, patch

import pytest
import requests


@pytest.fixture(scope="module")
def api_module():
    with patch("src.ingestion.pipeline.IngestionPipeline") as fake_pipeline_cls:
        fake_pipeline_cls.return_value = Mock()
        sys.modules.pop("src.ingestion.api", None)
        import src.ingestion.api as module

        yield module

    sys.modules.pop("src.ingestion.api", None)


def test_skips_when_url_not_configured(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", None)

    result = api_module._notify_rag_reload()

    assert result.startswith("skipped")


def test_returns_ok_on_successful_reload(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", "http://rag-api:8001/reload")
    monkeypatch.setattr(api_module, "_RAG_API_KEY", "secret")

    fake_response = Mock()
    fake_response.raise_for_status = Mock()

    with patch.object(api_module.requests, "post", return_value=fake_response) as mock_post:
        result = api_module._notify_rag_reload()

    assert result == "ok"
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {"X-API-Key": "secret"}


def test_omits_auth_header_when_no_key_configured(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", "http://rag-api:8001/reload")
    monkeypatch.setattr(api_module, "_RAG_API_KEY", None)

    fake_response = Mock()
    fake_response.raise_for_status = Mock()

    with patch.object(api_module.requests, "post", return_value=fake_response) as mock_post:
        api_module._notify_rag_reload()

    _, kwargs = mock_post.call_args
    assert kwargs["headers"] == {}


def test_does_not_raise_when_reload_fails(api_module, monkeypatch):
    # This is the whole point -- a failed notification must never
    # propagate and fail the /ingest call it's attached to.
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", "http://rag-api:8001/reload")

    with patch.object(
        api_module.requests, "post", side_effect=requests.ConnectionError("refused")
    ):
        result = api_module._notify_rag_reload()

    assert result.startswith("failed")


def test_treats_non_2xx_response_as_failure(api_module, monkeypatch):
    monkeypatch.setattr(api_module, "_RAG_RELOAD_URL", "http://rag-api:8001/reload")

    fake_response = Mock()
    fake_response.raise_for_status = Mock(
        side_effect=requests.HTTPError("500 Server Error")
    )

    with patch.object(api_module.requests, "post", return_value=fake_response):
        result = api_module._notify_rag_reload()

    assert result.startswith("failed")
