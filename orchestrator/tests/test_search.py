"""Tests for the direct-from-markdown knowledge-base search that replaced
the Chroma vector store.

The properties worth pinning here are the ones the vector store couldn't
offer: what comes back is the note's own text at its own path, the same
query over unchanged notes ranks the same way twice, and an unconfigured or
empty source is an ordinary empty answer rather than an error.
"""

import pytest

from orchestrator.knowledge_base import search
from orchestrator.utils import workspace


@pytest.fixture
def vaults(monkeypatch, tmp_path):
    """An attached folder with `Knowledge Base/` (`vault` source) and
    `Requirements/` (`reading` source) subfolders."""
    kb = tmp_path / "Knowledge Base"
    reading = tmp_path / "Requirements"
    kb.mkdir()
    reading.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: tmp_path)
    return kb, reading


@pytest.fixture
def empty_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: tmp_path)
    return tmp_path


# --- split_sections -------------------------------------------------------


def test_sections_carry_the_full_heading_trail():
    sections = search.split_sections(
        "# Domain Rules\nintro\n## KYC\nkyc body\n### Session Expiry\nexpires in 24 hours\n"
    )

    assert [s["heading_path"] for s in sections] == [
        "Domain Rules",
        "Domain Rules > KYC",
        "Domain Rules > KYC > Session Expiry",
    ]


def test_sibling_heading_pops_the_trail_back():
    sections = search.split_sections("## A\na\n### A1\na1\n## B\nb\n")

    assert [s["heading_path"] for s in sections] == ["A", "A > A1", "B"]


def test_content_before_the_first_heading_is_its_own_untitled_section():
    sections = search.split_sections("preamble text\n\n# Heading\nbody\n")

    assert sections[0]["heading_path"] == ""
    assert "preamble text" in sections[0]["text"]


def test_note_with_no_headings_is_one_section():
    sections = search.split_sections("just a flat note\nwith two lines\n")

    assert len(sections) == 1
    assert sections[0]["heading_path"] == ""


def test_section_text_is_the_real_markdown_not_a_reconstruction():
    body = "# Checkout\n\n- Tax is **8.25%**\n- `SAUCE10` gives 10% off\n"
    sections = search.split_sections(body)

    assert sections[0]["text"] == body.strip()


def test_long_sections_are_never_split_by_length():
    long_body = "# Big\n" + ("word " * 5000)

    sections = search.split_sections(long_body)

    assert len(sections) == 1
    assert len(sections[0]["text"]) > 20000


# --- search ---------------------------------------------------------------


def test_search_returns_the_matching_section_with_its_source_file(vaults):
    kb, _ = vaults
    (kb / "checkout.md").write_text(
        "# Checkout\n\n## Tax\nSales tax is 8.25% on the subtotal.\n", encoding="utf-8"
    )
    (kb / "login.md").write_text("# Login\n\nLocked-out users see a banner.\n", encoding="utf-8")

    results = search.search("sales tax rate")

    assert results[0]["source_file"] == "checkout.md"
    assert results[0]["heading_path"] == "Checkout > Tax"
    assert "8.25%" in results[0]["text"]


def test_heading_match_outranks_a_passing_body_mention(vaults):
    kb, _ = vaults
    (kb / "titled.md").write_text("## Session Expiry\nAfter a while.\n", encoding="utf-8")
    (kb / "passing.md").write_text(
        "## Misc\nLots of unrelated prose here about other topics, and session expiry "
        "is mentioned once in passing among many other things entirely.\n",
        encoding="utf-8",
    )

    results = search.search("session expiry")

    assert results[0]["source_file"] == "titled.md"


def test_covering_more_query_terms_outranks_repeating_one(vaults):
    kb, _ = vaults
    (kb / "broad.md").write_text("## Notes\ncheckout tax coupon\n", encoding="utf-8")
    (kb / "narrow.md").write_text("## Notes\ncoupon coupon coupon coupon\n", encoding="utf-8")

    results = search.search("checkout tax coupon")

    assert results[0]["source_file"] == "broad.md"
    assert set(results[0]["matched_terms"]) == {"checkout", "tax", "coupon"}


def test_non_matching_sections_are_left_out_entirely(vaults):
    kb, _ = vaults
    (kb / "a.md").write_text("## Tax\nSales tax details.\n## Shipping\nFlat rate.\n", encoding="utf-8")

    results = search.search("tax")

    assert [r["heading_path"] for r in results] == ["Tax"]


def test_search_returns_every_match_uncapped(vaults):
    kb, _ = vaults
    for i in range(6):
        (kb / f"n{i}.md").write_text(f"## Section {i}\ncoupon rules {i}\n", encoding="utf-8")

    assert len(search.search("coupon")) == 6


def test_ranking_is_stable_across_runs(vaults):
    kb, _ = vaults
    for name in ("b.md", "a.md", "c.md"):
        (kb / name).write_text("## Same\nidentical coupon text\n", encoding="utf-8")

    first = [r["source_file"] for r in search.search("coupon")]
    second = [r["source_file"] for r in search.search("coupon")]

    assert first == second == ["a.md", "b.md", "c.md"]


def test_reading_source_reads_the_other_configured_folder(vaults):
    kb, reading = vaults
    (kb / "kb.md").write_text("## Glossary\nA widget is a thing.\n", encoding="utf-8")
    (reading / "req.md").write_text("## Glossary\nA sprocket is a thing.\n", encoding="utf-8")

    assert search.search("glossary")[0]["source_file"] == "kb.md"
    assert search.search("glossary", source="reading")[0]["source_file"] == "req.md"


def test_unknown_source_is_a_programming_error(vaults):
    with pytest.raises(ValueError):
        search.search("anything", source="nope")


def test_no_match_is_an_empty_list(vaults):
    kb, _ = vaults
    (kb / "a.md").write_text("## Tax\nSales tax details.\n", encoding="utf-8")

    assert search.search("kubernetes ingress") == []


def test_missing_subfolder_is_an_empty_list_not_an_error(empty_workspace):
    assert search.search("anything") == []
    assert search.search("anything", source="reading") == []
    assert search.list_notes() == []


def test_all_stopword_query_still_searches_rather_than_matching_nothing(vaults):
    kb, _ = vaults
    (kb / "a.md").write_text("## Notes\nwhat is this\n", encoding="utf-8")

    assert search.search("what is this")


def test_dot_directories_and_node_modules_are_skipped(vaults):
    kb, _ = vaults
    for folder in (".obsidian", ".history", "node_modules"):
        (kb / folder).mkdir()
        (kb / folder / "junk.md").write_text("## Coupon\nnoise\n", encoding="utf-8")
    (kb / "real.md").write_text("## Coupon\nsignal\n", encoding="utf-8")

    results = search.search("coupon")

    assert [r["source_file"] for r in results] == ["real.md"]


def test_nested_notes_report_a_posix_relative_path(vaults):
    kb, _ = vaults
    (kb / "domain").mkdir()
    (kb / "domain" / "kyc.md").write_text("## KYC\nrules\n", encoding="utf-8")

    assert search.search("kyc")[0]["source_file"] == "domain/kyc.md"


def test_unreadable_note_is_skipped_without_failing_the_search(vaults):
    kb, _ = vaults
    (kb / "bad.md").write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    (kb / "good.md").write_text("## Coupon\nsignal\n", encoding="utf-8")

    results = search.search("coupon")

    assert [r["source_file"] for r in results] == ["good.md"]


# --- oversized sections ---------------------------------------------------


def test_section_under_the_cap_comes_back_whole_and_untruncated(vaults):
    kb, _ = vaults
    (kb / "a.md").write_text("## Tax\nSales tax is 8.25%.\n", encoding="utf-8")

    result = search.search("tax")[0]

    assert result["truncated"] is False
    assert result["text"] == "## Tax\nSales tax is 8.25%."


def test_headingless_note_is_excerpted_around_the_match_not_dumped_whole(vaults):
    """A Word-exported PRD with no `#` headings is one section spanning the
    whole file. The answer has to survive without the other 30 KB coming
    with it."""
    kb, _ = vaults
    filler = "\n".join(f"unrelated prose line {i}" for i in range(400))
    (kb / "prd.md").write_text(
        f"{filler}\nThe locked_out_user account is blocked at login.\n{filler}\n",
        encoding="utf-8",
    )

    result = search.search("locked_out_user")[0]

    assert result["truncated"] is True
    assert "The locked_out_user account is blocked at login." in result["text"]
    assert len(result["text"]) <= search.DEFAULT_MAX_CHARS
    # Elided on both sides, and it says so rather than reading as the note's
    # own opening and closing lines.
    assert result["text"].startswith("[...]")
    assert result["text"].endswith("[...]")


def test_an_excerpt_is_still_verbatim_note_text(vaults):
    kb, _ = vaults
    filler = "\n".join(f"line {i}" for i in range(2000))
    (kb / "big.md").write_text(f"{filler}\ncoupon SAUCE10 gives 10% off\n", encoding="utf-8")

    result = search.search("coupon")[0]
    note = (kb / "big.md").read_text(encoding="utf-8")
    blocks = [b for b in result["text"].split("[...]") if b.strip()]

    assert blocks
    for block in blocks:
        assert block.strip() in note


def test_excerpt_keeps_context_lines_either_side_of_the_match(vaults):
    kb, _ = vaults
    lines = [f"line {i}" for i in range(2000)]
    lines[1000] = "the coupon rule"
    (kb / "big.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    text = search.search("coupon")[0]["text"]

    assert "line 998" in text and "line 1002" in text


def test_max_chars_zero_returns_the_whole_oversized_section(vaults):
    kb, _ = vaults
    body = "coupon\n" + ("filler line\n" * 2000)
    (kb / "big.md").write_text(body, encoding="utf-8")

    result = search.search("coupon", max_chars=0)[0]

    assert result["truncated"] is False
    assert len(result["text"]) > search.DEFAULT_MAX_CHARS


def test_every_result_carries_an_absolute_path_to_read_the_full_note(vaults):
    kb, _ = vaults
    (kb / "a.md").write_text("## Tax\nSales tax is 8.25%.\n", encoding="utf-8")

    assert search.search("tax")[0]["path"] == str(kb / "a.md")


def test_a_single_line_longer_than_the_budget_is_cut_rather_than_dropped(vaults):
    kb, _ = vaults
    (kb / "wide.md").write_text("coupon " + ("x" * 9000) + "\n", encoding="utf-8")

    result = search.search("coupon")[0]

    assert result["truncated"] is True
    assert 0 < len(result["text"]) <= search.DEFAULT_MAX_CHARS


# --- list_notes -----------------------------------------------------------


def test_list_notes_maps_every_note_to_its_outline_and_real_path(vaults):
    kb, _ = vaults
    (kb / "checkout.md").write_text("# Checkout\n## Tax\n8.25%\n", encoding="utf-8")

    notes = search.list_notes()

    assert notes[0]["source_file"] == "checkout.md"
    assert notes[0]["path"] == str(kb / "checkout.md")
    assert notes[0]["headings"] == ["Checkout", "Checkout > Tax"]
    assert notes[0]["chars"] > 0
