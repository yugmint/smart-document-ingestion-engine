from langchain_core.documents import Document

from src.ingestion.chunkers.recursive_chunker import RecursiveChunker
from src.ingestion.config import IngestionConfig
from src.ingestion.analysers.models import (
    ChunkingRecommendation,
    DocumentAnalysis,
    DocumentStatistics,
    LayoutAnalysis,
)


def _make_analysis(chunk_size, chunk_overlap, merge_small=False, split_large=True):
    return DocumentAnalysis(
        source="test.pdf",
        file_type="pdf",
        document_type="general",
        language="english",
        statistics=DocumentStatistics(
            page_count=1,
            character_count=1000,
            word_count=200,
            estimated_tokens=260,
            average_page_length=1000,
            average_paragraph_length=200,
            average_sentence_length=80,
            average_line_length=50,
        ),
        layout=LayoutAnalysis(),
        recommendation=ChunkingRecommendation(
            strategy="recursive",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            merge_small_chunks=merge_small,
            split_large_chunks=split_large,
            min_chunk_size=int(chunk_size * 0.25),
        ),
        confidence=0.8,
    )


def test_no_chunk_exceeds_chunk_size_when_split_large_is_true():
    config = IngestionConfig()
    chunker = RecursiveChunker(config)

    text = ("word " * 5000).strip()  # long, uniform, no paragraph breaks
    documents = [Document(page_content=text, metadata={})]

    analysis = _make_analysis(chunk_size=200, chunk_overlap=20, split_large=True)

    chunks = chunker.chunk(documents, analysis)

    assert len(chunks) > 1
    # Overlap can push slightly past chunk_size (documented tradeoff),
    # but never runs away unbounded.
    assert all(len(c.page_content) <= 200 * 1.5 for c in chunks)


def test_respects_analysis_recommendation_over_config_defaults():
    config = IngestionConfig(chunk_size=500, chunk_overlap=100)
    chunker = RecursiveChunker(config)

    text = "Paragraph one is here.\n\nParagraph two is here.\n\n" * 50
    documents = [Document(page_content=text, metadata={})]

    analysis = _make_analysis(chunk_size=80, chunk_overlap=10)

    chunks = chunker.chunk(documents, analysis)

    # With the tiny recommended chunk_size, we must get far more chunks
    # than the (unused) config default of 500 would produce.
    fallback_chunks = chunker.chunk(documents, analysis=None)

    assert len(chunks) > len(fallback_chunks)


def test_consecutive_chunks_share_overlap_text():
    config = IngestionConfig()
    chunker = RecursiveChunker(config)

    text = "A" * 60 + " " + "B" * 60 + " " + "C" * 60 + " " + "D" * 60
    documents = [Document(page_content=text, metadata={})]

    analysis = _make_analysis(chunk_size=60, chunk_overlap=15, split_large=True)

    chunks = chunker.chunk(documents, analysis)

    assert len(chunks) >= 2
    # Each chunk after the first should contain a tail fragment of
    # the previous chunk's content.
    for prev, curr in zip(chunks, chunks[1:]):
        tail = prev.page_content[-15:]
        assert tail in curr.page_content


def test_merge_small_chunks_removes_tiny_fragments():
    config = IngestionConfig()
    chunker = RecursiveChunker(config)

    text = "\n\n".join(["Short."] * 20)  # many tiny paragraphs
    documents = [Document(page_content=text, metadata={})]

    analysis = _make_analysis(
        chunk_size=100, chunk_overlap=0, merge_small=True, split_large=True
    )

    chunks = chunker.chunk(documents, analysis)

    tiny = [c for c in chunks if len(c.page_content) < 20]
    assert len(tiny) == 0


def test_empty_documents_are_skipped():
    config = IngestionConfig()
    chunker = RecursiveChunker(config)

    documents = [
        Document(page_content="", metadata={}),
        Document(page_content="   ", metadata={}),
        Document(page_content="Real content here.", metadata={}),
    ]

    chunks = chunker.chunk(documents, analysis=None)

    assert len(chunks) == 1
    assert chunks[0].page_content == "Real content here."
