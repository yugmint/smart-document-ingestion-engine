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


def test_average_paragraph_length_falls_back_to_sentences_when_no_blank_lines():
    """
    Real bug: dense multi-column academic layouts often don't reproduce
    blank-line paragraph breaks through pypdf extraction, so the whole
    document comes back as ONE "paragraph" and average_paragraph_length
    blows up to the entire document's length (a real 11-page paper hit
    43,767 chars this way). Sentence boundaries survive column-layout
    extraction even when blank lines don't, so this should fall back to
    a sentence-grouped estimate instead of the raw single-blob length.
    """
    analyzer = PDFAnalyzer()
    # 40 real sentences, single \n only (no \n\n) -- exactly the
    # column-layout extraction shape that broke this.
    sentences = "This is a real sentence about the topic. " * 40
    docs = _pages(sentences.replace(". ", ".\n"))

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\dense_layout.pdf")

    # A single giant "paragraph" would be ~1,600+ chars; the
    # sentence-grouped fallback should land far below that, close to a
    # real ~4-sentence paragraph's actual size.
    assert analysis.statistics.average_paragraph_length < 400


def test_confidence_drops_for_very_short_documents():
    analyzer = PDFAnalyzer()
    docs = _pages("Hi.")

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\airlock-on-edge_woolf_default_26.pdf")

    assert analysis.confidence < 0.55


def test_overlap_never_exceeds_half_chunk_size():
    analyzer = PDFAnalyzer()
    docs = _pages("this agreement " * 500)

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


def test_numbered_toc_dot_leaders_classify_as_book_without_literal_chapter():
    # Regression test for a real 117-page UPSC exam-prep history book:
    # its contents page is headed "Contents" (not "Table of Contents")
    # and sections are numbered ("1. ANCIENT HISTORY ... 5"), never the
    # literal word "chapter" -- fell through to "general" (chunk_size
    # 500) instead of "book" (800). See docs/05-roadmap.md and
    # docs/reports/2026-07-28-history-book-e2e-test.md.
    analyzer = PDFAnalyzer()
    docs = _pages(
        "Contents\n"
        "Preface " + ("." * 100) + " 4\n"
        "1. ANCIENT HISTORY AND ART & CULTURE OF INDIA " + ("." * 80) + " 5\n"
        "1.1. India's Culture and its Continuity " + ("." * 80) + " 5\n"
        "1.2. Stone Age " + ("." * 90) + " 9\n",
        "1. Ancient History\n\n" + ("Body text about ancient history. " * 100),
    )

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\history-book.pdf")

    assert analysis.document_type == "book"


def test_structured_abstract_without_literal_word_abstract_is_research_paper():
    # Regression test for a real misclassification (Hu et al. 2020,
    # a COVID-19 severity study): medical journals often use a
    # structured abstract (Background/Methods/Results/Conclusions) and
    # never print the literal word "Abstract" -- the old rule fell
    # through this entirely and the document ended up "legal" instead
    # (see the next test). See docs/05-roadmap.md.
    analyzer = PDFAnalyzer()
    docs = _pages(
        "Background As an emergent disease, this pandemic has caused harm.\n"
        "Methods All confirmed patients were enrolled in this study.\n"
        "Results A total of 40 patients were enrolled.\n"
        "Conclusions The model might help clinicians identify patients.\n"
        + ("Body text. " * 50),
        "References\n[1] Someone, Somewhere.",
    )

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\airlock-on-edge_woolf_default_27.pdf")

    assert analysis.document_type == "research_paper"


def test_bare_agreement_word_does_not_force_legal_classification():
    # Regression test for the same real document: "...crude agreement
    # were all over 85%" (a statistics term, not a legal one) used to
    # trip the "legal" rule on the word "agreement" alone.
    analyzer = PDFAnalyzer()
    docs = _pages(
        "The positive predictive value, negative predictive value and "
        "crude agreement were all over 85%. " * 20
    )

    analysis = analyzer.analyze(docs, r"local/tests\data\rag_test_files\airlock-on-edge_woolf_default_27.pdf")

    assert analysis.document_type != "legal"
