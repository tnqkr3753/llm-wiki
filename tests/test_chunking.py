"""Tests for heading-level chunking of Markdown bodies."""

from llm_wiki.chunking import DEFAULT_MAX_CHARS, split_into_chunks

NESTED = """Intro paragraph.

# Top

Top text.

## Child

Child text.

# Second

Second text.
"""


def test_a_body_without_headings_is_one_chunk() -> None:
    chunks = split_into_chunks("Just a paragraph.\n\nAnd another.")

    assert len(chunks) == 1
    assert chunks[0].heading == ""
    assert chunks[0].ordinal == 0
    assert "another" in chunks[0].text


def test_an_empty_body_yields_no_chunks() -> None:
    assert split_into_chunks("   \n\n  ") == ()


def test_each_heading_starts_a_new_chunk() -> None:
    chunks = split_into_chunks(NESTED)

    assert [chunk.heading for chunk in chunks] == [
        "",
        "Top",
        "Top > Child",
        "Second",
    ]
    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2, 3]


def test_a_chunk_carries_its_heading_path_in_the_embedded_text() -> None:
    chunks = split_into_chunks(NESTED)
    child = chunks[2]

    assert child.text.startswith("Top > Child")
    assert "Child text." in child.text


def test_a_sibling_heading_pops_the_deeper_level_off_the_path() -> None:
    chunks = split_into_chunks("## A\n\nx\n\n### B\n\ny\n\n## C\n\nz\n")

    assert [chunk.heading for chunk in chunks] == ["A", "A > B", "C"]


def test_headings_inside_fenced_code_do_not_split() -> None:
    body = "# Real\n\n```sh\n# not a heading\necho hi\n```\n\ntail\n"

    chunks = split_into_chunks(body)

    assert len(chunks) == 1
    assert "not a heading" in chunks[0].text


def test_a_section_longer_than_the_cap_splits_at_paragraph_breaks() -> None:
    paragraph = "word " * 60
    body = f"# Big\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n"

    chunks = split_into_chunks(body, max_chars=400)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 400 for chunk in chunks)
    assert all(chunk.heading == "Big" for chunk in chunks)


def test_a_single_paragraph_longer_than_the_cap_is_split_by_length() -> None:
    body = "# Big\n\n" + ("x" * 900)

    chunks = split_into_chunks(body, max_chars=300)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 300 for chunk in chunks)


def test_ordinals_stay_contiguous_across_oversized_sections() -> None:
    body = "# A\n\n" + ("x" * 900) + "\n\n# B\n\ntail\n"

    chunks = split_into_chunks(body, max_chars=300)

    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_identical_text_hashes_identically() -> None:
    first = split_into_chunks("# A\n\nsame text\n")
    second = split_into_chunks("# A\n\nsame text\n")

    assert first[0].content_hash == second[0].content_hash


def test_a_changed_heading_changes_the_hash() -> None:
    first = split_into_chunks("# A\n\nsame text\n")
    second = split_into_chunks("# B\n\nsame text\n")

    assert first[0].content_hash != second[0].content_hash


def test_an_empty_section_is_dropped() -> None:
    chunks = split_into_chunks("# Empty\n\n# Real\n\ntext\n")

    assert [chunk.heading for chunk in chunks] == ["Real"]


def test_the_default_cap_is_positive() -> None:
    assert DEFAULT_MAX_CHARS > 0
