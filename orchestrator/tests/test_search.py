"""Tests for the direct-from-markdown knowledge-base search that replaced
the Chroma vector store.

The properties worth pinning here are the ones the vector store couldn't
offer: what comes back is the note's own text at its own path, the same
query over unchanged notes ranks the same way twice, and a missing folder
or empty result is an ordinary empty answer rather than an error. This
module now only ever reads `Requirements/` -- the general domain-background
source (`Knowledge Base/`) is read whole by the agents themselves instead.
"""

import pytest

from orchestrator.knowledge_base import search
from orchestrator.utils import workspace


@pytest.fixture
def reading(monkeypatch, tmp_path):
    """An attached folder with a `Requirements/` subfolder."""
    folder = tmp_path / "Requirements"
    folder.mkdir()
    monkeypatch.setattr(workspace, "workspace_root", lambda: tmp_path)
    return folder


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


def test_search_returns_the_matching_section_with_its_source_file(reading):
    (reading / "checkout.md").write_text(
        "# Checkout\n\n## Tax\nSales tax is 8.25% on the subtotal.\n", encoding="utf-8"
    )
    (reading / "login.md").write_text("# Login\n\nLocked-out users see a banner.\n", encoding="utf-8")

    results = search.search("sales tax rate")

    assert results[0]["source_file"] == "checkout.md"
    assert results[0]["heading_path"] == "Checkout > Tax"
    assert "8.25%" in results[0]["text"]


def test_heading_match_outranks_a_passing_body_mention(reading):
    (reading / "titled.md").write_text("## Session Expiry\nAfter a while.\n", encoding="utf-8")
    (reading / "passing.md").write_text(
        "## Misc\nLots of unrelated prose here about other topics, and session expiry "
        "is mentioned once in passing among many other things entirely.\n",
        encoding="utf-8",
    )

    results = search.search("session expiry")

    assert results[0]["source_file"] == "titled.md"


def test_covering_more_query_terms_outranks_repeating_one(reading):
    (reading / "broad.md").write_text("## Notes\ncheckout tax coupon\n", encoding="utf-8")
    (reading / "narrow.md").write_text("## Notes\ncoupon coupon coupon coupon\n", encoding="utf-8")

    results = search.search("checkout tax coupon")

    assert results[0]["source_file"] == "broad.md"
    assert set(results[0]["matched_terms"]) == {"checkout", "tax", "coupon"}


def test_non_matching_sections_are_left_out_entirely(reading):
    (reading / "a.md").write_text("## Tax\nSales tax details.\n## Shipping\nFlat rate.\n", encoding="utf-8")

    results = search.search("tax")

    assert [r["heading_path"] for r in results] == ["Tax"]


def test_search_returns_every_match_uncapped(reading):
    for i in range(6):
        (reading / f"n{i}.md").write_text(f"## Section {i}\ncoupon rules {i}\n", encoding="utf-8")

    assert len(search.search("coupon")) == 6


def test_ranking_is_stable_across_runs(reading):
    for name in ("b.md", "a.md", "c.md"):
        (reading / name).write_text("## Same\nidentical coupon text\n", encoding="utf-8")

    first = [r["source_file"] for r in search.search("coupon")]
    second = [r["source_file"] for r in search.search("coupon")]

    assert first == second == ["a.md", "b.md", "c.md"]


def test_folder_override_reads_a_custom_named_folder_when_given(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: tmp_path)
    custom = tmp_path / "Specs"
    custom.mkdir()
    (custom / "a.md").write_text("## Glossary\nA widget is a thing.\n", encoding="utf-8")

    assert search.search("glossary", folder_override="Specs")[0]["source_file"] == "a.md"
    assert search.search("glossary") == []  # 'Requirements' still doesn't exist


def test_no_match_is_an_empty_list(reading):
    (reading / "a.md").write_text("## Tax\nSales tax details.\n", encoding="utf-8")

    assert search.search("kubernetes ingress") == []


def test_missing_subfolder_is_an_empty_list_not_an_error(empty_workspace):
    assert search.search("anything") == []
    assert search.list_notes() == []


def test_all_stopword_query_still_searches_rather_than_matching_nothing(reading):
    (reading / "a.md").write_text("## Notes\nwhat is this\n", encoding="utf-8")

    assert search.search("what is this")


def test_dot_directories_and_node_modules_are_skipped(reading):
    for folder_name in (".obsidian", ".history", "node_modules"):
        (reading / folder_name).mkdir()
        (reading / folder_name / "junk.md").write_text("## Coupon\nnoise\n", encoding="utf-8")
    (reading / "real.md").write_text("## Coupon\nsignal\n", encoding="utf-8")

    results = search.search("coupon")

    assert [r["source_file"] for r in results] == ["real.md"]


def test_nested_notes_report_a_posix_relative_path(reading):
    (reading / "domain").mkdir()
    (reading / "domain" / "kyc.md").write_text("## KYC\nrules\n", encoding="utf-8")

    assert search.search("kyc")[0]["source_file"] == "domain/kyc.md"


def test_unreadable_note_is_skipped_without_failing_the_search(reading):
    (reading / "bad.md").write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    (reading / "good.md").write_text("## Coupon\nsignal\n", encoding="utf-8")

    results = search.search("coupon")

    assert [r["source_file"] for r in results] == ["good.md"]


# --- oversized sections ---------------------------------------------------


def test_section_under_the_cap_comes_back_whole_and_untruncated(reading):
    (reading / "a.md").write_text("## Tax\nSales tax is 8.25%.\n", encoding="utf-8")

    result = search.search("tax")[0]

    assert result["truncated"] is False
    assert result["text"] == "## Tax\nSales tax is 8.25%."


def test_headingless_note_is_excerpted_around_the_match_not_dumped_whole(reading):
    """A Word-exported PRD with no `#` headings is one section spanning the
    whole file. The answer has to survive without the other 30 KB coming
    with it."""
    filler = "\n".join(f"unrelated prose line {i}" for i in range(400))
    (reading / "prd.md").write_text(
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


def test_an_excerpt_is_still_verbatim_note_text(reading):
    filler = "\n".join(f"line {i}" for i in range(2000))
    (reading / "big.md").write_text(f"{filler}\ncoupon SAUCE10 gives 10% off\n", encoding="utf-8")

    result = search.search("coupon")[0]
    note = (reading / "big.md").read_text(encoding="utf-8")
    blocks = [b for b in result["text"].split("[...]") if b.strip()]

    assert blocks
    for block in blocks:
        assert block.strip() in note


def test_excerpt_keeps_context_lines_either_side_of_the_match(reading):
    lines = [f"line {i}" for i in range(2000)]
    lines[1000] = "the coupon rule"
    (reading / "big.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    text = search.search("coupon")[0]["text"]

    assert "line 998" in text and "line 1002" in text


def test_max_chars_zero_returns_the_whole_oversized_section(reading):
    body = "coupon\n" + ("filler line\n" * 2000)
    (reading / "big.md").write_text(body, encoding="utf-8")

    result = search.search("coupon", max_chars=0)[0]

    assert result["truncated"] is False
    assert len(result["text"]) > search.DEFAULT_MAX_CHARS


def test_every_result_carries_an_absolute_path_to_read_the_full_note(reading):
    (reading / "a.md").write_text("## Tax\nSales tax is 8.25%.\n", encoding="utf-8")

    assert search.search("tax")[0]["path"] == str(reading / "a.md")


def test_a_single_line_longer_than_the_budget_is_cut_rather_than_dropped(reading):
    (reading / "wide.md").write_text("coupon " + ("x" * 9000) + "\n", encoding="utf-8")

    result = search.search("coupon")[0]

    assert result["truncated"] is True
    assert 0 < len(result["text"]) <= search.DEFAULT_MAX_CHARS


# --- list_notes -----------------------------------------------------------


def test_list_notes_maps_every_note_to_its_outline_and_real_path(reading):
    (reading / "checkout.md").write_text("# Checkout\n## Tax\n8.25%\n", encoding="utf-8")

    notes = search.list_notes()

    assert notes[0]["source_file"] == "checkout.md"
    assert notes[0]["path"] == str(reading / "checkout.md")
    assert notes[0]["headings"] == ["Checkout", "Checkout > Tax"]
    assert notes[0]["chars"] > 0
