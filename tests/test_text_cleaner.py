from langchain_core.documents import Document

from src.ingestion.cleaners.text_cleaner import TextCleaner, noise_page_percentage


def _pages(*texts):
    return [Document(page_content=t, metadata={"page_number": i + 1}) for i, t in enumerate(texts)]


def test_repeated_branding_header_removed_across_pages():
    # Real shape this was built against: a constant company-locations
    # line, a "page N | url | phone" line where only the number varies,
    # and a bare repeated label -- all three on every page.
    docs = _pages(
        "AHMEDABAD | BENGALURU | RANCHI\n1 www.example.com # 555 (c)Corp\nStudent Notes:\nReal content page one.",
        "AHMEDABAD | BENGALURU | RANCHI\n2 www.example.com # 555 (c)Corp\nStudent Notes:\nReal content page two.",
        "AHMEDABAD | BENGALURU | RANCHI\n3 www.example.com # 555 (c)Corp\nStudent Notes:\nReal content page three.",
    )

    cleaned = TextCleaner().clean(docs)

    for i, doc in enumerate(cleaned, start=1):
        assert "AHMEDABAD" not in doc.page_content
        assert "www.example.com" not in doc.page_content
        assert "Student Notes:" not in doc.page_content
        assert f"Real content page {['one', 'two', 'three'][i-1]}." in doc.page_content


def test_content_that_happens_to_repeat_on_two_pages_is_kept():
    # Below _MIN_PAGE_COUNT (3) -- shouldn't be treated as noise even
    # though it repeats on both pages given.
    docs = _pages(
        "A recurring section title\nBody text one.",
        "A recurring section title\nBody text two.",
    )

    cleaned = TextCleaner().clean(docs)

    assert "A recurring section title" in cleaned[0].page_content
    assert "A recurring section title" in cleaned[1].page_content


def test_body_content_not_in_edge_lines_is_never_stripped():
    # A phrase that happens to repeat but sits in the genuine middle of
    # every page (well outside header/footer territory) must survive.
    # Padded with enough filler that the mid-page line falls outside
    # both the first-4 and last-4 edge windows.
    def _page(intro, unique):
        return (
            "Header line one.\nSecond header line.\nThird header-ish line.\nFourth edge line.\n"
            f"{intro}\nThe same recurring mid-page phrase.\n{unique}\n"
            "Padding A.\nPadding B.\nPadding C.\n"
            "Footer one.\nFooter two.\nFooter three.\nFooter four."
        )

    docs = _pages(
        _page("Some intro.", "More unique text."),
        _page("Different intro.", "Other unique text."),
        _page("Another intro.", "Yet more text."),
    )

    cleaned = TextCleaner().clean(docs)

    for doc in cleaned:
        assert "The same recurring mid-page phrase." in doc.page_content
        assert "Header line one." not in doc.page_content
        assert "Footer one." not in doc.page_content


def test_no_repeated_lines_leaves_content_untouched_besides_whitespace():
    docs = _pages(
        "Completely unique page one content.",
        "Totally different page two content.",
        "Yet another unrelated page three.",
    )

    cleaned = TextCleaner().clean(docs)

    assert cleaned[0].page_content == "Completely unique page one content."
    assert cleaned[1].page_content == "Totally different page two content."


def test_single_page_document_skips_repetition_detection():
    docs = _pages("Only one page here, nothing to compare against.")

    cleaned = TextCleaner().clean(docs)

    assert cleaned[0].page_content == "Only one page here, nothing to compare against."


def test_existing_whitespace_normalization_still_works():
    docs = _pages(
        "line one\r\n\r\n\r\n\r\nline two   with   spaces  \n   trailing/leading   ",
        "another page\n\n\ncontent",
        "third page\ncontent here",
    )

    cleaned = TextCleaner().clean(docs)

    assert "\n\n\n" not in cleaned[0].page_content
    assert "line two with spaces" in cleaned[0].page_content
    assert cleaned[0].page_content == cleaned[0].page_content.strip()


def test_noise_page_percentage_all_pages_noisy():
    docs = _pages(
        "AHMEDABAD | BENGALURU | RANCHI\n1 www.example.com\nReal content page one.",
        "AHMEDABAD | BENGALURU | RANCHI\n2 www.example.com\nReal content page two.",
        "AHMEDABAD | BENGALURU | RANCHI\n3 www.example.com\nReal content page three.",
    )

    assert noise_page_percentage(docs) == 100.0


def test_noise_page_percentage_zero_when_nothing_repeats():
    docs = _pages(
        "Completely unique page one content.",
        "Totally different page two content.",
        "Yet another unrelated page three.",
    )

    assert noise_page_percentage(docs) == 0.0


def test_noise_page_percentage_matches_clean_stripped_lines():
    # Same document TextCleaner strips lines from -- the percentage
    # should agree with what clean() actually did, not just what it
    # detected in isolation. 3 of 4 pages branded (>= both the absolute
    # _MIN_PAGE_COUNT=3 and the 50% fraction threshold).
    branded = "AHMEDABAD | BENGALURU | RANCHI\n{n} www.example.com\nReal content page {n}."
    docs = _pages(
        branded.format(n=1),
        branded.format(n=2),
        branded.format(n=3),
        "Different, unrelated fourth page with no branding at all here today.",
    )

    pct = noise_page_percentage(docs)
    cleaned = TextCleaner().clean(docs)

    assert pct == 75.0
    assert "AHMEDABAD" not in cleaned[0].page_content
    assert "AHMEDABAD" not in cleaned[1].page_content
    assert "AHMEDABAD" not in cleaned[2].page_content
