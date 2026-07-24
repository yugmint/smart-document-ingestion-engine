from langchain_core.documents import Document

# from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
from src.ingestion.analysers.pdf_analyzer import PDFAnalyzer
def _pages(*texts):
    return [
        Document(page_content=t, metadata={"page_number": i + 1, "source": "x.pdf"})
        for i, t in enumerate(texts)
    ]


def test_research_paper_gets_structure_strategy():
    analyzer = PDFAnalyzer()
    docs = _pages(
        "Abstract\nThis paper studies things.\n\n" + ("Body text. " * 200),
        "References\n[1] Someone, Somewhere.",
    )

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\Computer Vision_2.pdf")

    assert analysis.document_type == "research_paper"
    assert analysis.recommendation.strategy == "structure"
    assert analysis.confidence > 0.5


def test_chunk_size_grows_for_long_unbroken_paragraphs():
    analyzer = PDFAnalyzer()
    # One single giant paragraph, far larger than the "general" base
    # chunk_size of 500 -- should trigger the size-growth branch and
    # the split_large_chunks override.
    huge_paragraph = "word " * 3000
    docs = _pages(huge_paragraph)

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\Grandma's Bag of Stories by Sudha Murthy.pdf")

    assert analysis.recommendation.chunk_size > 500
    assert analysis.recommendation.split_large_chunks is True
    assert "avg paragraph length" in analysis.recommendation.rationale


def test_chunk_size_shrinks_and_merge_enabled_for_choppy_text():
    analyzer = PDFAnalyzer()
    # Lots of very short paragraphs (list/dialogue-like).
    docs = _pages("\n\n".join(["Hi."] * 100))

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\Factor_Analysis.pdf")

    assert analysis.recommendation.chunk_size < 500
    assert analysis.recommendation.merge_small_chunks is True


def test_confidence_drops_for_very_short_documents():
    analyzer = PDFAnalyzer()
    docs = _pages("Hi.")

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\airlock-on-edge_woolf_default_26.pdf")

    assert analysis.confidence < 0.55


def test_overlap_never_exceeds_half_chunk_size():
    analyzer = PDFAnalyzer()
    docs = _pages("agreement " * 500)

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\Yugendra_Ratna_Salunke_IN_[External]_Offer_Letter_Thane.docx.pdf")

    rec = analysis.recommendation
    assert rec.chunk_overlap <= rec.chunk_size // 2


def test_chapter_keyword_does_not_force_book_when_document_looks_technical():
    # Regression test for the misclassification found via a real document
    # (Factor_Analysis.pdf opens with "Chapter 420" but is a dense
    # statistics manual, not narrative prose) -- see docs/05-roadmap.md.
    # Equations (chi-square formula) should stop "chapter" from
    # short-circuiting straight to "book".
    analyzer = PDFAnalyzer()
    docs = _pages(
        "Chapter 420: Factor Analysis\n\n"
        "The chi-square statistic is computed as x2 == sum((o - e) ** 2 / e).\n"
        + ("Body text. " * 50)
    )

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\Factor_Analysis.pdf")

    assert analysis.document_type != "book"


def test_chapter_keyword_still_classifies_narrative_prose_as_book():
    # Guards against overcorrecting: a genuine narrative book with no
    # equations/tables should still be classified "book".
    analyzer = PDFAnalyzer()
    docs = _pages(
        "Chapter One\n\n" + ("Once upon a time, in a quiet village. " * 50)
    )

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\Grandma's Bag of Stories by Sudha Murthy.pdf")

    assert analysis.document_type == "book"
