from orchestrator.utils.docx_helpers import estimate_row_height_in


def test_short_cell_estimates_within_a_single_line():
    height = estimate_row_height_in(["Short text."], [1.7], 10)
    # One short line at 10pt: well under half an inch.
    assert 0 < height < 0.3


def test_long_single_paragraph_estimates_multiple_lines():
    long_text = "A" * 1000
    height = estimate_row_height_in([long_text], [1.7], 10)
    short_height = estimate_row_height_in(["Short."], [1.7], 10)
    assert height > short_height


def test_row_height_is_the_tallest_cell_not_the_sum():
    # Two cells: one short, one long. Row height must match the long one,
    # not short + long combined.
    long_text = "B" * 500
    row_height = estimate_row_height_in(["Short.", long_text], [1.7, 1.7], 10)
    long_alone = estimate_row_height_in([long_text], [1.7], 10)
    assert row_height == long_alone


def test_multiline_cell_sums_its_own_wrapped_lines():
    # A cell with several newline-separated items must sum their wrapped
    # heights, not just take the single longest item -- this was a real
    # bug caught before it shipped (max() instead of sum() per cell).
    single_item = estimate_row_height_in(["1. " + "C" * 100], [1.7], 10)
    three_items = estimate_row_height_in(
        ["1. " + "C" * 100 + "\n2. " + "C" * 100 + "\n3. " + "C" * 100], [1.7], 10
    )
    assert three_items >= single_item * 2.5


def test_reproduces_the_observed_meridian_req001_overflow():
    # The real case that surfaced this defect: a 1629-character Acceptance
    # Criteria cell in a 1.7in column estimates taller than a full
    # landscape-letter page's ~7.3in usable height.
    ac_text = "x" * 1629
    height = estimate_row_height_in([ac_text], [1.7], 10)
    assert height > 7.3


def test_empty_cells_do_not_crash_and_estimate_minimal_height():
    height = estimate_row_height_in(["", "", ""], [1.0, 1.0, 1.0], 10)
    assert height > 0
