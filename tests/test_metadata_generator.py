from langchain_core.documents import Document

from src.ingestion.metadata.generator import MetadataGenerator


def _chunk(text: str, page_number: int) -> Document:
    return Document(page_content=text, metadata={"page_number": page_number})


def test_body_text_is_not_marked_as_reference_section():
    chunks = [
        _chunk("Intro text.", 1),
        _chunk("Body text about the study's findings.", 2),
    ]

    result = MetadataGenerator().generate(chunks, "paper.pdf")

    assert all(not c.metadata["is_reference_section"] for c in result)


def test_citation_dense_chunk_is_marked():
    # Regression test: a "References" heading position is not a
    # reliable cutoff on real two-column PDFs (pypdf's column-order
    # extraction can put the heading after several actual citations) --
    # see docs/05-roadmap.md. Detect citation-list content directly via
    # doi:/Medline: density instead, independent of chunk position.
    chunks = [
        _chunk("Intro text, no citations here.", 1),
        _chunk(
            "3 Chen N, et al. Epidemiological study. Lancet. 2020. "
            "Medline:32007143 doi:10.1016/S0140-6736(20)30211-7\n"
            "4 Guan WJ, et al. Clinical Characteristics. N Engl J Med. 2020. "
            "Medline:32109013 doi:10.1056/NEJMoa2002032",
            11,
        ),
    ]

    result = MetadataGenerator().generate(chunks, "paper.pdf")

    assert result[0].metadata["is_reference_section"] is False
    assert result[1].metadata["is_reference_section"] is True


def test_single_incidental_doi_mention_does_not_trigger():
    # One doi: mention (e.g. citing a single related work inline) isn't
    # enough on its own -- requires citation *density*, not just presence.
    chunks = [_chunk("This finding aligns with prior work (doi:10.1000/xyz).", 5)]

    result = MetadataGenerator().generate(chunks, "paper.pdf")

    assert result[0].metadata["is_reference_section"] is False


def test_first_page_chunks_are_flagged():
    chunks = [
        _chunk("Title and authors.", 1),
        _chunk("Abstract text.", 1),
        _chunk("Introduction.", 2),
    ]

    result = MetadataGenerator().generate(chunks, "paper.pdf")

    assert result[0].metadata["is_first_page"] is True
    assert result[1].metadata["is_first_page"] is True
    assert result[2].metadata["is_first_page"] is False
