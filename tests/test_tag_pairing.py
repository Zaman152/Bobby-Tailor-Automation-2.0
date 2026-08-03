"""Layer-1 tests for the direction-generic two-token tag primitive (SP-6).

The load-bearing property is that ONE code path resolves a tag whichever way the
drawing rotated it.  ``INV-05-finish-schedule-binding.md`` §2 Key A records a
first-pass reader that handled only the vertically stacked layout: it found tags
on Moxy pages 15/16 and returned nothing on 18/19/20.  Every real-layout test
below therefore feeds the rotated and the unrotated tag through the SAME call.
"""
from __future__ import annotations

from typing import List

import pytest

from bobbytailor.deterministic.tag_pairing import (
    ACROSS,
    ALONG,
    CARDINAL_DIRS,
    MAX_GAP_PT,
    PERP_TOL_PT,
    TagLine,
    normalise_text,
    pair_two_token_tags,
    project_bbox,
    round_dir,
    union_bbox,
)


def _is_wc(text: str) -> bool:
    return normalise_text(text) == "WC"


def _is_number(text: str) -> bool:
    t = normalise_text(text)
    return len(t) == 2 and t.isdigit()


def _line(text: str, bbox, text_dir) -> TagLine:
    return TagLine(text=text, bbox_pt=tuple(bbox), text_dir=tuple(text_dir))


# ── project_bbox: the rotation into the line's own reading frame ─────────────


def test_project_bbox_covers_all_four_cardinal_directions():
    """Each direction maps onto (start, end, perp_lo, perp_hi) with start < end."""
    bbox = (100.0, 200.0, 120.0, 212.0)
    seen = {}
    for d in CARDINAL_DIRS:
        proj = project_bbox(bbox, d)
        assert proj is not None, d
        start, end, lo, hi = proj
        assert start < end, (d, proj)
        assert lo < hi, (d, proj)
        seen[d] = proj
    # The four projections are genuinely different frames, not one rule reused.
    assert len(set(seen.values())) == 4


def test_project_bbox_matches_the_documented_mapping():
    x0, y0, x1, y1 = 100.0, 200.0, 120.0, 212.0
    b = (x0, y0, x1, y1)
    assert project_bbox(b, (1, 0)) == (x0, x1, y0, y1)
    assert project_bbox(b, (-1, 0)) == (-x1, -x0, -y1, -y0)
    assert project_bbox(b, (0, -1)) == (-y1, -y0, x0, x1)
    assert project_bbox(b, (0, 1)) == (y0, y1, -x1, -x0)


def test_project_bbox_perp_axis_advances_the_way_text_lines_stack():
    """perp increases in the direction the drawing stacks successive lines.

    This is what lets a room tag (name over number) use the same projection as
    a material tag (prefix beside number).  Without the negations on ``(-1,0)``
    and ``(0,1)`` the second line of a tag would project *behind* the first.
    """
    first = (100.0, 200.0, 140.0, 212.0)
    # Where the next text line sits on the page, per reading direction.
    next_line = {
        (1, 0): (100.0, 214.0, 140.0, 226.0),    # below
        (-1, 0): (100.0, 186.0, 140.0, 198.0),   # above
        (0, -1): (142.0, 200.0, 154.0, 212.0),   # to the right
        (0, 1): (86.0, 200.0, 98.0, 212.0),      # to the left
    }
    for d, nxt in next_line.items():
        pf = project_bbox(first, d)
        ps = project_bbox(nxt, d)
        assert ps[2] >= pf[3], (d, pf, ps)
        assert ps[2] - pf[3] == pytest.approx(2.0, abs=0.001), (d, pf, ps)


def test_project_bbox_rejects_a_non_cardinal_direction():
    assert project_bbox((0.0, 0.0, 10.0, 10.0), (0.7, 0.7)) is None
    assert round_dir((0.7, 0.7)) is None
    assert round_dir(("x", "y")) is None


def test_project_bbox_normalises_an_inverted_bbox():
    assert project_bbox((120.0, 212.0, 100.0, 200.0), (1, 0)) == (100.0, 120.0, 200.0, 212.0)


# ── pair_two_token_tags: all four directions, one code path ─────────────────


def _adjacent_pair(d, gap: float = 10.0) -> List[TagLine]:
    """A 'WC' + '07' tag drawn so the number follows the prefix in reading order."""
    if d == (1, 0):
        return [
            _line("WC", (100.0, 200.0, 120.0, 212.0), d),
            _line("07", (120.0 + gap, 200.0, 132.0 + gap, 212.0), d),
        ]
    if d == (-1, 0):
        return [
            _line("WC", (130.0, 200.0, 150.0, 212.0), d),
            _line("07", (118.0 - gap, 200.0, 130.0 - gap, 212.0), d),
        ]
    if d == (0, -1):
        return [
            _line("WC", (100.0, 200.0, 112.0, 220.0), d),
            _line("07", (100.0, 188.0 - gap, 112.0, 200.0 - gap), d),
        ]
    return [
        _line("WC", (100.0, 200.0, 112.0, 220.0), d),
        _line("07", (100.0, 220.0 + gap, 112.0, 232.0 + gap), d),
    ]


@pytest.mark.parametrize("text_dir", CARDINAL_DIRS)
def test_a_prefix_and_number_pair_in_every_orientation(text_dir):
    pairs = pair_two_token_tags(_adjacent_pair(text_dir), _is_wc, _is_number)
    assert len(pairs) == 1, text_dir
    assert (pairs[0][0].text, pairs[0][1].text) == ("WC", "07")


def test_all_four_orientations_resolve_in_ONE_call():
    """The must-have: one code path, not a per-direction branch at the caller."""
    lines: List[TagLine] = []
    for d in CARDINAL_DIRS:
        lines.extend(_adjacent_pair(d))
    pairs = pair_two_token_tags(lines, _is_wc, _is_number)
    assert len(pairs) == 4
    assert {p[0].text_dir for p in pairs} == set(CARDINAL_DIRS)


# ── Negative cases: what must NOT pair ───────────────────────────────────────


def test_a_gap_beyond_the_maximum_does_not_pair():
    just_under = pair_two_token_tags(_adjacent_pair((1, 0), gap=MAX_GAP_PT - 0.5),
                                     _is_wc, _is_number)
    assert len(just_under) == 1
    beyond = pair_two_token_tags(_adjacent_pair((1, 0), gap=MAX_GAP_PT + 0.5),
                                 _is_wc, _is_number)
    assert beyond == []


def test_a_negative_gap_does_not_pair():
    """A number BEFORE the prefix in reading order is not this tag's number."""
    d = (1, 0)
    lines = [
        _line("WC", (130.0, 200.0, 150.0, 212.0), d),
        _line("07", (100.0, 200.0, 112.0, 212.0), d),
    ]
    assert pair_two_token_tags(lines, _is_wc, _is_number) == []


def test_non_overlapping_perpendicular_ranges_do_not_pair():
    d = (1, 0)
    lines = [
        _line("WC", (100.0, 200.0, 120.0, 212.0), d),
        # 8 pt clear of the prefix row — well past PERP_TOL_PT.
        _line("07", (130.0, 220.0, 142.0, 232.0), d),
    ]
    assert PERP_TOL_PT < 8.0
    assert pair_two_token_tags(lines, _is_wc, _is_number) == []


def test_perpendicular_slip_inside_the_tolerance_still_pairs():
    d = (1, 0)
    lines = [
        _line("WC", (100.0, 200.0, 120.0, 212.0), d),
        _line("07", (130.0, 214.0, 142.0, 226.0), d),  # 2 pt clear, inside 3 pt
    ]
    assert len(pair_two_token_tags(lines, _is_wc, _is_number)) == 1


def test_two_lines_with_different_directions_do_not_pair():
    lines = [
        _line("WC", (100.0, 200.0, 120.0, 212.0), (1, 0)),
        _line("07", (130.0, 200.0, 142.0, 212.0), (0, -1)),
    ]
    assert pair_two_token_tags(lines, _is_wc, _is_number) == []


def test_one_number_cannot_serve_two_prefixes():
    d = (1, 0)
    lines = [
        _line("WC", (100.0, 200.0, 120.0, 212.0), d),
        _line("WC", (100.0, 214.0, 120.0, 226.0), d),
        _line("07", (130.0, 207.0, 142.0, 219.0), d),
    ]
    pairs = pair_two_token_tags(lines, _is_wc, _is_number)
    assert len(pairs) == 1


def test_the_nearest_candidate_wins():
    d = (1, 0)
    lines = [
        _line("WC", (100.0, 200.0, 120.0, 212.0), d),
        _line("77", (134.0, 200.0, 146.0, 212.0), d),
        _line("07", (124.0, 200.0, 136.0, 212.0), d),
    ]
    pairs = pair_two_token_tags(lines, _is_wc, _is_number)
    assert [p[1].text for p in pairs] == ["07"]


def test_an_unknown_axis_is_rejected_rather_than_guessed():
    with pytest.raises(ValueError):
        pair_two_token_tags([], _is_wc, _is_number, axis="diagonal")


# ── The two REAL Moxy layouts, through the same call ────────────────────────

# INV-05 §2 Key A, transcribed verbatim from the probe output.
MOXY_P15_ROTATED = [
    ("WC", (116.6, 2123.2, 128.3, 2138.5), (0, -1)),
    ("01", (116.6, 2103.0, 128.3, 2112.5), (0, -1)),
    ("WALLCOVERING", (116.6, 2021.1, 128.3, 2090.3), (0, -1)),
]
MOXY_P18_UNROTATED = [
    ("WC", (908.4, 217.4, 923.7, 228.8), (1, 0)),
    ("07", (934.2, 217.4, 943.6, 228.8), (1, 0)),
    ("WALLCOVERING", (956.4, 217.4, 1025.7, 228.8), (1, 0)),
]


def test_both_real_moxy_layouts_pair_through_the_same_code_path():
    lines = [_line(*rec) for rec in MOXY_P15_ROTATED + MOXY_P18_UNROTATED]
    pairs = pair_two_token_tags(lines, _is_wc, _is_number)
    assert len(pairs) == 2, "the rotated OR the unrotated layout was lost"
    assert sorted(p[1].text for p in pairs) == ["01", "07"]
    # And the rotated one is genuinely rotated — this is the regression guard.
    assert {p[0].text_dir for p in pairs} == {(0, -1), (1, 0)}


def test_the_spelled_out_material_word_is_not_read_as_a_number():
    """WALLCOVERING sits 12.7 pt after the number — inside the gap window.

    The gap alone therefore does NOT exclude it; the number predicate does.
    Pinning this stops a future widening of the vocabulary from swallowing it.
    """
    lines = [_line(*rec) for rec in MOXY_P15_ROTATED]
    proj_num = project_bbox(lines[1].bbox_pt, lines[1].text_dir)
    proj_word = project_bbox(lines[2].bbox_pt, lines[2].text_dir)
    assert 0 < proj_word[0] - proj_num[1] < MAX_GAP_PT
    assert not _is_number("WALLCOVERING")


def test_the_real_tag_bbox_is_the_union_of_its_two_tokens():
    lines = [_line(*rec) for rec in MOXY_P18_UNROTATED[:2]]
    assert union_bbox(lines[0].bbox_pt, lines[1].bbox_pt) == (908.4, 217.4, 943.6, 228.8)


# ── The ACROSS axis: the second token is the next text LINE ──────────────────

# Measured on Moxy page index 7 (ID-001 unit key plan).
MOXY_ROOM_TAG = [
    ("KING A", (625.0, 1336.0, 636.7, 1369.4), (0, -1)),
    ("204", (637.9, 1346.7, 649.6, 1358.5), (0, -1)),
]


def _is_name(text: str) -> bool:
    t = normalise_text(text)
    return bool(t) and not t.replace(" ", "").isdigit() and any(c.isalpha() for c in t)


def _is_room_number(text: str) -> bool:
    t = normalise_text(text)
    return len(t) == 3 and t.isdigit()


def test_a_room_tag_pairs_across_the_reading_axis_not_along_it():
    lines = [_line(*rec) for rec in MOXY_ROOM_TAG]
    assert pair_two_token_tags(lines, _is_name, _is_room_number, axis=ALONG) == []
    across = pair_two_token_tags(lines, _is_name, _is_room_number,
                                 max_gap_pt=6.0, axis=ACROSS)
    assert [(p[0].text, p[1].text) for p in across] == [("KING A", "204")]


@pytest.mark.parametrize("text_dir", CARDINAL_DIRS)
def test_the_across_axis_is_direction_generic_too(text_dir):
    name = (600.0, 1000.0, 640.0, 1012.0)
    projected = project_bbox(name, text_dir)
    assert projected is not None
    # Place the number 2 pt further along the advance axis, centred on the name.
    offsets = {
        (1, 0): (610.0, 1014.0, 628.0, 1026.0),
        (-1, 0): (610.0, 986.0, 628.0, 998.0),
        (0, -1): (642.0, 1002.0, 654.0, 1010.0),
        (0, 1): (586.0, 1002.0, 598.0, 1010.0),
    }
    lines = [_line("KING A", name, text_dir), _line("204", offsets[text_dir], text_dir)]
    pairs = pair_two_token_tags(lines, _is_name, _is_room_number,
                                max_gap_pt=6.0, axis=ACROSS)
    assert len(pairs) == 1, text_dir


# ── Threat T-23-19: the scan stays bounded on a dense sheet ──────────────────


def test_a_dense_sheet_does_not_become_a_quadratic_scan():
    """4,000 lines in a tight column: an all-pairs scan is 16M comparisons."""
    d = (1, 0)
    lines: List[TagLine] = []
    for i in range(2000):
        y = 200.0 + i * 0.01  # deliberately piled into a few buckets
        lines.append(_line("WC", (100.0, y, 120.0, y + 12.0), d))
        lines.append(_line("07", (130.0, y, 142.0, y + 12.0), d))
    pairs = pair_two_token_tags(lines, _is_wc, _is_number)
    assert len(pairs) == 2000


def test_pairing_is_deterministic_across_repeated_calls():
    lines = [_line(*rec) for rec in MOXY_P15_ROTATED + MOXY_P18_UNROTATED]
    first = [(a.text, b.text) for a, b in pair_two_token_tags(lines, _is_wc, _is_number)]
    for _ in range(5):
        again = [(a.text, b.text) for a, b in pair_two_token_tags(lines, _is_wc, _is_number)]
        assert again == first
