"""
End-to-end tests against a real PDF file (not hand-built Document
objects like the other test files use).

Two tiers:

1. `test_load_through_metadata_on_real_pdf` -- always runs, fast.
   Exercises PDFLoader -> TextCleaner -> PDFAnalyzer -> HybridChunker
   -> MetadataGenerator against an actual file on disk. No embedding
   model is loaded, so this runs in CI / offline without downloading
   anything.

2. `test_full_pipeline_with_real_embeddings` -- opt-in only
   (`pytest -m e2e`), since it downloads/loads a real
   sentence-transformers model and builds a real FAISS index. Skips
   itself automatically if sentence-transformers isn't installed.
"""

from pathlib import Path

import pytest

from src.ingestion.loaders.pdf_loader import PDFLoader
from src.ingestion.cleaners.text_cleaner import TextCleaner
from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
from src.ingestion.chunkers.hybrid_chunker import HybridChunker
from src.ingestion.metadata.generator import MetadataGenerator
from src.ingestion.config import IngestionConfig

SAMPLE_PDF = Path(__file__).parent / "fixtures" / "sample_research_paper.pdf"

def test_load_through_metadata_on_real_pdf():
    assert SAMPLE_PDF.exists(), f"Missing test fixture: {SAMPLE_PDF}"

    documents = PDFLoader().load(str(SAMPLE_PDF))
    assert len(documents) == 3  # abstract page, methodology page, references page
    assert all(d.page_content.strip() for d in documents)

    documents = TextCleaner().clean(documents)

    analysis = PDFAnalyzer().analyze(documents, str(SAMPLE_PDF))
    assert analysis.document_type == "research_paper"
    assert analysis.confidence > 0.5

    config = IngestionConfig()
    chunks = HybridChunker(config).chunk(documents, analysis)

    assert len(chunks) > 0
    # No chunk should wildly exceed the recommended window -- some
    # slack is expected/documented (overlap can push slightly past
    # chunk_size), but nothing should be, say, 3x over.
    max_allowed = analysis.recommendation.chunk_size * 2
    oversized = [c for c in chunks if len(c.page_content) > max_allowed]
    assert not oversized, (
        f"{len(oversized)} chunk(s) exceeded {max_allowed} chars "
        f"(recommended chunk_size={analysis.recommendation.chunk_size})"
    )

    chunks = MetadataGenerator().generate(chunks, str(SAMPLE_PDF), analysis)

    for chunk in chunks:
        assert chunk.metadata["source"] == SAMPLE_PDF.name
        assert chunk.metadata["file_extension"] == "pdf"
        assert chunk.metadata["document_type"] == "research_paper"
        assert "chunk_id" in chunk.metadata


@pytest.mark.e2e
def test_full_pipeline_with_real_embeddings():
    pytest.importorskip("sentence_transformers")

    from src.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline()
    chunks, analysis = pipeline.ingest(str(SAMPLE_PDF), save_index=False)

    assert len(chunks) > 0
    assert analysis.document_type == "research_paper"
    assert "ingestion_report" in analysis.metadata
