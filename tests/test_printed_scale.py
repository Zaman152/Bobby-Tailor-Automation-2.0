"""Offline tests for printed-scale reading (PRIMARY scale source).

No PDF, no network, no paid calls — synthetic fitz-like pages and viewports.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bobbytailor.deterministic.geometry_takeoff import ScaleResult
from bobbytailor.deterministic.printed_scale import (
    PrintedScale,
    _number_and_title,
    extract_printed_scales,
    identify_main_plan_scale,
    match_scales_to_viewports,
    parse_scale_ratio,
)
from bobbytailor.deterministic.scale_solver import ViewportScale, resolve_scale_v2
from bobbytailor.deterministic.viewports import Viewport


# ── parse_scale_ratio ─────────────────────────────────────────────────────────


def test_parse_engineering_forty():
    assert parse_scale_ratio('SCALE: 1" = 40\'-0"') == 40.0


def test_parse_engineering_twenty_no_inches():
    assert parse_scale_ratio('1" = 20\'') == 20.0


def test_parse_quarter_inch():
    assert parse_scale_ratio('1/4" = 1\'-0"') == 4.0


def test_parse_eighth_inch():
    assert parse_scale_ratio('1/8" = 1\'-0"') == 8.0


def test_parse_three_thirtyseconds():
    assert abs(parse_scale_ratio('3/32" = 1\'-0"') - 10.667) < 0.01


def test_parse_one_and_half_inch():
    assert abs(parse_scale_ratio('1 1/2" = 1\'-0"') - 0.6667) < 1e-3


def test_parse_half_inch():
    assert parse_scale_ratio('1/2" = 1\'-0"') == 2.0


def test_parse_three_quarter_inch():
    assert abs(parse_scale_ratio('3/4" = 1\'-0"') - 1.333) < 1e-3


def test_parse_smart_quotes_and_whitespace():
    # Curly double-prime / prime and messy spacing must still parse.
    assert parse_scale_ratio('SCALE:  1″  =  40′-0″') == 40.0


# ── Dropped-slash stacked-fraction repair ─────────────────────────────────────
#
# CAD exports typeset the fraction as ONE stacked glyph in its own text span, so
# the PDF text layer flattens '1/8" = 1'-0"' to '18" = 1'-0"' (real spans from
# Bob's page 4: ['SCALE: ', '18', '" = 1\'-0"']). Read literally that is 0.056
# ft/in instead of 8.0 — a 144x scale error that corrupts every quantity on the
# sheet. The literal readings ("18 paper inches = 1 foot") are architecturally
# impossible, so the repair cannot rewrite a legitimate scale.


@pytest.mark.parametrize("text,expected", [
    ('SCALE: 18" = 1\'-0"', 8.0),          # 1/8"  = 1'-0"
    ('SCALE: 14" = 1\'-0"', 4.0),          # 1/4"  = 1'-0"
    ('SCALE: 12" = 1\'-0"', 2.0),          # 1/2"  = 1'-0"
    ('SCALE: 34" = 1\'-0"', 4.0 / 3.0),    # 3/4"  = 1'-0"
    ('SCALE: 38" = 1\'-0"', 8.0 / 3.0),    # 3/8"  = 1'-0"
    ('SCALE: 316" = 1\'-0"', 16.0 / 3.0),  # 3/16" = 1'-0"
    ('SCALE: 116" = 1\'-0"', 16.0),        # 1/16" = 1'-0"
    ('SCALE: 132" = 1\'-0"', 32.0),        # 1/32" = 1'-0"
    ('SCALE: 332" = 1\'-0"', 32.0 / 3.0),  # 3/32" = 1'-0"
])
def test_parse_dropped_slash_stacked_fraction(text, expected):
    assert abs(parse_scale_ratio(text) - expected) < 1e-3


@pytest.mark.parametrize("text,expected", [
    ('SCALE: 1" = 40\'-0"', 40.0),         # whole inch — untouched
    ('SCALE: 3" = 1\'-0"', 1.0 / 3.0),     # legit whole-inch detail scale
    ('SCALE: 1 1/2" = 1\'-0"', 2.0 / 3.0),  # mixed number — untouched
    ('SCALE: 1/8" = 1\'-0"', 8.0),         # literal slash still wins
])
def test_dropped_slash_repair_never_rewrites_a_valid_scale(text, expected):
    assert abs(parse_scale_ratio(text) - expected) < 1e-3


def test_parse_garbage_returns_none():
    assert parse_scale_ratio("OVERALL FLOOR PLAN") is None
    assert parse_scale_ratio("") is None
    assert parse_scale_ratio(None) is None


# ── SP-2: anchored right-to-left paper-inch parse ─────────────────────────────
#
# INV-04 §4's verified fix table, pinned row for row. Two independent defects
# made every Bob's page 16-32x wrong linearly and 256-1024x wrong by area:
#
#   BUG-A  the stacked fraction glyph flattens to a SPACE, not only to a
#          concatenation, so 'SCALE: 3 32" = 1\'-0"' read the first digit run
#          "3" -> 0.333 ft/in instead of 10.667.
#   BUG-B  the paper-inch scan was unanchored, so a drawing number printed
#          BEFORE the ratio won: '2 SCALE: 18" = 1\'-0" ...' -> 0.5 not 8.0.
#
# The fix anchors on the last inch mark before '=' and parses LEFTWARD from it,
# because the paper-inch measure is by construction the token the inch mark
# belongs to. Each row records expected / pre-change / why.

_FIX_TABLE = [
    # (text, expected_fpi, pre_change_fpi, note)
    # ── the three forms that were WRONG before the fix ────────────────────
    ('SCALE: 3 32" = 1\'-0"', 32.0 / 3.0, 1.0 / 3.0,
     "BUG-A split stacked 3/32 — Bob's A1.1/A2.0/A3.0 plan sheets"),
    ('2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW', 8.0, 0.5,
     "BUG-B leading drawing number 2 was read as 2 paper inches"),
    ('3 REAR ELEVATION NEW SCALE: 18" = 1\'-0"', 8.0, 1.0 / 3.0,
     "BUG-B leading drawing number 3 was read as 3 paper inches"),
    ('5 ENLARGED GLAZING AND ENTRY DOORS SCALE: 14" = 1\'-0"'
     ' 4 TRUCK DOCK ELEVATION NEW', 4.0, 0.2,
     "BUG-B leading drawing number 5 was read as 5 paper inches"),
    ('1 SCALE: 2" = 1\'-0"', 0.5, 1.0,
     "BUG-B leading drawing number 1 was read as 1 paper inch"),
    ('SCALE: 1 12" = 1\'-0"', 2.0 / 3.0, 1.0,
     "split stacked mixed number 1 1/2 — only the SECOND token is a key"),
    ('SCALE: 1 16" = 1\'-0"', 16.0, 1.0,
     "split stacked 1/16 — the CONCATENATION is a key, so it wins over 1+1/6"),
    # ── forms that already parsed correctly and must NOT move ─────────────
    ('SCALE: 14" = 1\'-0"', 4.0, 4.0, "concatenated stacked 1/4, unchanged"),
    ('SCALE: 12" = 1\'-0"', 2.0, 2.0, "concatenated stacked 1/2, unchanged"),
    ('SCALE: 1" = 1\'-0"', 1.0, 1.0, "whole-inch detail scale, unchanged"),
    ('1" = 40\'-0"', 40.0, 40.0, "engineering scale, no SCALE keyword"),
    ('1" = 20\'', 20.0, 20.0, "engineering scale, feet only, no SCALE keyword"),
    ('1/4" = 1\'-0"', 4.0, 4.0, "literal slash, unchanged"),
    ('3/32" = 1\'-0"', 32.0 / 3.0, 32.0 / 3.0, "literal slash, unchanged"),
    ('1 1/2" = 1\'-0"', 2.0 / 3.0, 2.0 / 3.0, "literal mixed number, unchanged"),
]


@pytest.mark.parametrize(
    "text,expected,note",
    [(t, e, n) for t, e, _pre, n in _FIX_TABLE],
    ids=[n[:40] for _t, _e, _p, n in _FIX_TABLE],
)
def test_inv04_verified_fix_table(text, expected, note):
    got = parse_scale_ratio(text)
    assert got is not None, f"{note}: {text!r} failed to parse"
    assert abs(got - expected) < 1e-3, f"{note}: {text!r} -> {got}, want {expected}"


@pytest.mark.parametrize(
    "text,pre_change",
    [(t, p) for t, e, p, _n in _FIX_TABLE if abs(e - p) < 1e-9],
)
def test_previously_correct_forms_did_not_move(text, pre_change):
    """The eight rows that already parsed correctly return their old value.

    A scale parser change is high-blast-radius — every quantity on a sheet is
    scaled by it, and an area error is the square. These rows are the guard
    that the fix corrected only what was broken.
    """
    assert abs(parse_scale_ratio(text) - pre_change) < 1e-3


def test_triple_token_stacked_fraction_is_a_known_limitation():
    """'1 1 2' (a hypothetical fully-split mixed number) is NOT solved here.

    INV-04 §4 scores the recipe 14/15 and names this the one failure. The form
    appears in NONE of the four plan sets, so inventing a rule for it would be
    a constant justified by nothing observed (D-07). It returns the safe value
    2.0 (reading the trailing '1 2' as the stacked 1/2) and the caller flags.
    """
    assert abs(parse_scale_ratio('SCALE: 1 1 2" = 1\'-0"') - 2.0) < 1e-3


def test_hyphenated_mixed_number_keeps_its_pre_change_value():
    """Bob's A8.3 prints 'SCALE: 1-1/2" = 1'-0"', parsed as 1/2 -> 2.0.

    Architecturally that is 1.5 paper inches (0.667 ft/in), so 2.0 is wrong —
    but it is wrong BEFORE this change too, it is a different defect from
    BUG-A/BUG-B, and correcting it here would break the pinned four-fixture
    sweep this plan exists to establish. Pinned as-is; see the deferred item.
    """
    assert abs(parse_scale_ratio('SCALE: 1-1/2" = 1\'-0"') - 2.0) < 1e-3


def test_bare_ratio_without_scale_keyword_takes_the_legacy_path():
    """Moxy prints 40 sheets of bare ratios with no SCALE keyword.

    Those must take a literally unchanged code path — the anchor exists to
    disambiguate a callout that also carries a drawing number and a title.
    """
    assert parse_scale_ratio('1/4" = 1\'-0"') == 4.0
    assert parse_scale_ratio('1/8" = 1\'-0"') == 8.0
    assert abs(parse_scale_ratio('1 1/2" = 1\'-0"') - 2.0 / 3.0) < 1e-3


def test_anchored_parse_is_linear_on_adversarial_text():
    """T-23-06: a long adversarial callout must not blow up the regex engine.

    Callout text is attacker-controlled (it comes out of the PDF text layer).
    Every anchored pattern uses bounded {1,4} quantifiers with no nested
    repetition, so a pathological string returns promptly rather than hanging.
    """
    import time

    nasty = "SCALE: " + "1 " * 5000 + '9" = 1\'-0"'
    t0 = time.time()
    parse_scale_ratio(nasty)
    assert time.time() - t0 < 1.0


# ── SP-2: a drawing number printed BEFORE the ratio ───────────────────────────
#
# The left-side digit strip in _number_and_title removes every digit run — it
# cannot tell a leading drawing number from the paper-inch measure it exists to
# delete — so Bob's, which prints the number first, lost it entirely. Crow
# prints the number AFTER the ratio and was never affected. Titles already
# survived in every INV-03 probe; the fallback runs after the title is built so
# it can only add a number, never move a title string.
#
# Each expected TITLE below is the value the pre-change parser produced on the
# real PDF, so these rows double as the byte-identical-title assertion.

_NUMBER_AND_TITLE_ROWS = [
    # (text, expected_number, expected_title_unchanged_by_this_change, note)
    ('2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW', "2", "FRONT ELEVATION NEW",
     "Bob's A4.0 — number leads, title trails"),
    ('3 REAR ELEVATION NEW SCALE: 18" = 1\'-0"', "3", "REAR ELEVATION NEW",
     "Bob's A4.0 — number leads, title sits between number and ratio"),
    ('5 ENLARGED GLAZING AND ENTRY DOORS SCALE: 14" = 1\'-0"'
     ' 4 TRUCK DOCK ELEVATION NEW', "4",
     "ENLARGED GLAZING AND ENTRY DOORS TRUCK DOCK ELEVATION NEW",
     "Bob's A4.0 — two callouts in one block; the trailing 4 already won, "
     "so the fallback must NOT fire and overwrite it with the leading 5"),
    ('SCALE: 1" = 40\'-0"  1  OVERALL FLOOR PLAN', "1", "OVERALL FLOOR PLAN",
     "Crow-shaped — number FOLLOWS the ratio, unchanged by this change"),
    ('SCALE: 1 1/2" = 1\'-0"  2  TYP. S.C.C.P. MITERED CORNER', "2",
     "TYP. S.C.C.P. MITERED CORNER",
     "Crow-shaped detail — number FOLLOWS the ratio, unchanged"),
    ('SCALE: 3 32" = 1\'-0"', None, "",
     "Bob's plan sheets — a bare callout has neither number nor title; the "
     "leading token is the paper-inch measure, not a drawing number"),
]


@pytest.mark.parametrize(
    "text,number,title,note",
    _NUMBER_AND_TITLE_ROWS,
    ids=[n[:44] for _t, _n, _ti, n in _NUMBER_AND_TITLE_ROWS],
)
def test_number_and_title_rows(text, number, title, note):
    got_number, got_title = _number_and_title(text)
    assert got_number == number, f"{note}: number {got_number!r} != {number!r}"
    assert got_title == title, f"{note}: title {got_title!r} != {title!r}"


@pytest.mark.parametrize("text,title", [
    ('2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW', "FRONT ELEVATION NEW"),
    ('3 REAR ELEVATION NEW SCALE: 18" = 1\'-0"', "REAR ELEVATION NEW"),
    ('5 ENLARGED GLAZING AND ENTRY DOORS SCALE: 14" = 1\'-0"'
     ' 4 TRUCK DOCK ELEVATION NEW',
     "ENLARGED GLAZING AND ENTRY DOORS TRUCK DOCK ELEVATION NEW"),
])
def test_leading_number_recovery_never_moves_a_title(text, title):
    """The three Bob's page-4 callouts keep byte-identical titles.

    These strings are pasted from the real PDF and the expectations are the
    pre-change parser's own output. Recovering the drawing number restores
    ONLY ``drawing_number``; the title picker is untouched.
    """
    assert _number_and_title(text)[1] == title


@pytest.mark.parametrize("text", [
    '1/4" = 1\'-0"',            # leading token is a fraction numerator
    '3/32" = 1\'-0"',           # leading token is a fraction numerator
    '1 1/2" = 1\'-0"',          # leading token is the whole part of a mixed no.
    'SCALE: 3 32" = 1\'-0"',    # leading token is the split stacked numerator
    'SCALE: 18" = 1\'-0"',      # leading token is a concatenated stacked frac.
])
def test_a_leading_measure_is_never_read_as_a_drawing_number(text):
    """The fallback requires a LONE integer: digits, whitespace, non-numeric.

    A leading paper-inch measure is always followed by a digit, '/', '.' or an
    inch mark — never by whitespace and a word — so it cannot reach the
    fallback. This is the guard that keeps Moxy's 40 sheets of bare ratios and
    every stacked-fraction callout out of it.
    """
    assert _number_and_title(text)[0] is None


# ── SP-2: the four-fixture invariance pin (real PDFs) ─────────────────────────
#
# D-05 / D-07: a scale change is accepted on the four-plan-set diff, never on
# "closer to a golden quantity". A wrong feet-per-point is a squared error on
# every area, so the contract is that this parser corrects exactly the seven
# Bob's callouts INV-03 §4.1 identified and moves NOTHING on the other three
# drafting offices. The 'before' side is frozen in
# tests/fixtures/printed_scale_pre_sp2.json, captured from the pre-SP-2 parser.

_PRE_SP2_FIXTURE = (
    Path(__file__).parent / "fixtures" / "printed_scale_pre_sp2.json"
)

# The seven corrections, by fixture / page / pre-change fpi / post-change fpi.
# Every one is on Bob's; INV-03 §4.1 lists them in exactly this order.
_EXPECTED_CHANGES = [
    ("Bob's", 1, 0.3333, 10.6667, 'SCALE: 3 32" = 1\'-0"'),
    ("Bob's", 2, 0.3333, 10.6667, 'SCALE: 3 32" = 1\'-0"'),
    ("Bob's", 3, 0.3333, 10.6667, 'SCALE: 3 32" = 1\'-0"'),
    ("Bob's", 4, 0.5, 8.0, '2 SCALE: 18" = 1\'-0" FRONT ELEVATION NEW'),
    ("Bob's", 4, 0.3333, 8.0, '3 REAR ELEVATION NEW SCALE: 18" = 1\'-0"'),
    ("Bob's", 4, 0.2, 4.0,
     '5 ENLARGED GLAZING AND ENTRY DOORS SCALE: 14" = 1\'-0"'
     ' 4 TRUCK DOCK ELEVATION NEW'),
    ("Bob's", 5, 1.0, 0.5, '1 SCALE: 2" = 1\'-0"'),
]

# The three offices whose sheets must not move at all.
_UNMOVED_FIXTURES = ("Crow", "Moxy", "Invitation to Bid")


def _sweep_rows(pre_rows):
    """Re-parse every pinned callout with TODAY's parser, in fixture order.

    Reads the callout texts from the frozen fixture rather than re-extracting
    them from the PDFs, so this test isolates the PARSE. Block extraction is
    covered separately by the probe acceptance in the plan.
    """
    from bobbytailor.deterministic.printed_scale import (
        _number_and_title as nt,
        parse_scale_ratio as p,
    )
    out = []
    for r in pre_rows:
        fpi = p(r["text"])
        number, title = nt(r["text"])
        out.append({
            "pdf": r["pdf"], "page": r["page"], "text": r["text"],
            "fpi": None if fpi is None else round(fpi, 4),
            "number": number, "title": title,
        })
    return out


def _load_pre_sp2():
    if not _PRE_SP2_FIXTURE.exists():
        pytest.skip(f"pre-SP-2 baseline missing: {_PRE_SP2_FIXTURE}")
    return json.loads(_PRE_SP2_FIXTURE.read_text())


def test_four_fixture_scale_sweep_is_pinned():
    """changed=7 unchanged=383 across Moxy / Crow / Bob's / Chelsea at once.

    A single assertion over all four plan sets, per D-05: improving one fixture
    while regressing another is rejected, so the totals are asserted together
    and not per-office.
    """
    pre = _load_pre_sp2()
    pre_rows = pre["rows"]
    now_rows = _sweep_rows(pre_rows)

    changed = unchanged = 0
    for old, new in zip(pre_rows, now_rows):
        if old["fpi"] is None and new["fpi"] is None:
            continue  # never parsed either side — "NOT TO SCALE", notes
        if old["fpi"] != new["fpi"]:
            changed += 1
        else:
            unchanged += 1

    assert (changed, unchanged) == (7, 383), (
        f"four-fixture scale sweep moved: changed={changed} unchanged={unchanged}, "
        f"expected changed=7 unchanged=383 (INV-03 §4.1)"
    )


def test_the_seven_changes_are_exactly_the_bobs_corrections():
    """Each correction is asserted by fixture, page, text and both values.

    A bare total could be satisfied by seven *different* movements, which is
    precisely the silent corruption T-23-07 registers.
    """
    pre_rows = _load_pre_sp2()["rows"]
    now_rows = _sweep_rows(pre_rows)

    moved = [
        (old["pdf"], old["page"], old["fpi"], new["fpi"], old["text"])
        for old, new in zip(pre_rows, now_rows)
        if not (old["fpi"] is None and new["fpi"] is None)
        and old["fpi"] != new["fpi"]
    ]
    assert len(moved) == len(_EXPECTED_CHANGES)
    for got, want in zip(moved, _EXPECTED_CHANGES):
        pdf, page, old_fpi, new_fpi, text = got
        w_pdf, w_page, w_old, w_new, w_text = want
        assert pdf.startswith(w_pdf), f"{got} moved on an unexpected fixture"
        assert page == w_page, f"{got}: page {page} != {w_page}"
        assert text == w_text, f"{got}: text != {w_text!r}"
        assert abs(old_fpi - w_old) < 1e-3, f"{got}: pre-change {old_fpi} != {w_old}"
        assert abs(new_fpi - w_new) < 1e-3, f"{got}: post-change {new_fpi} != {w_new}"


@pytest.mark.parametrize("office", _UNMOVED_FIXTURES)
def test_crow_moxy_and_chelsea_parse_byte_identically(office):
    """Zero movement on the three offices SP-2 was not aimed at.

    The whole point of the pin is that the parser generalises across four
    drafting offices — a fix validated on Bob's alone would be the documented
    fixture-blindness trap.
    """
    pre_rows = _load_pre_sp2()["rows"]
    now_rows = _sweep_rows(pre_rows)

    diffs = [
        (old["page"], old["fpi"], new["fpi"], old["text"][:70])
        for old, new in zip(pre_rows, now_rows)
        if old["pdf"].startswith(office) and old["fpi"] != new["fpi"]
    ]
    assert diffs == [], f"{office} scales moved: {diffs}"


def test_no_title_string_moved_on_any_fixture():
    """Recovering a drawing number must not perturb a single extracted title.

    Titles already survived in every INV-03 probe, so any movement here means
    the number fallback reached into the title picker.
    """
    pre_rows = _load_pre_sp2()["rows"]
    now_rows = _sweep_rows(pre_rows)

    moved = [
        (old["pdf"][:6], old["page"], old["title"], new["title"])
        for old, new in zip(pre_rows, now_rows)
        if old["title"] != new["title"]
    ]
    assert moved == [], f"titles moved: {moved}"


def test_recovered_drawing_numbers_are_purely_additive():
    """Every drawing-number movement fills a None — none overwrites a value."""
    pre_rows = _load_pre_sp2()["rows"]
    now_rows = _sweep_rows(pre_rows)

    overwritten = [
        (old["pdf"][:6], old["page"], old["number"], new["number"], old["text"][:60])
        for old, new in zip(pre_rows, now_rows)
        if old["number"] is not None and old["number"] != new["number"]
    ]
    assert overwritten == [], f"drawing numbers overwritten: {overwritten}"


def test_pre_sp2_fixture_matches_todays_block_extraction():
    """The frozen callout set still matches what the four PDFs actually contain.

    Guards the pin against silently decaying if block extraction or
    `_looks_like_scale_label` changes: the fixture would then be pinning texts
    the parser no longer sees. Skips when the upload PDFs are absent.
    """
    fitz = pytest.importorskip("fitz")
    from bobbytailor.deterministic.printed_scale import (
        _looks_like_scale_label, _normalize, _page_blocks,
    )

    pre = _load_pre_sp2()
    uploads = Path(__file__).resolve().parents[1] / "uploads"
    # Order of FIRST APPEARANCE in the fixture, so `observed` and `pinned` are
    # directly comparable lists (the fixture is in plan-set order, not sorted).
    names = list(dict.fromkeys(r["pdf"] for r in pre["rows"]))
    missing = [n for n in names if not (uploads / n).exists()]
    if missing:
        pytest.skip(f"fixture PDFs absent: {missing}")

    observed = []
    for name in names:
        doc = fitz.open(str(uploads / name))
        try:
            for i in range(doc.page_count):
                for _x0, _y0, _x1, _y1, text in _page_blocks(doc[i]):
                    if _looks_like_scale_label(text):
                        observed.append(
                            (name, i, " ".join(_normalize(text).split()))
                        )
        finally:
            doc.close()

    pinned = [(r["pdf"], r["page"], r["text"]) for r in pre["rows"]]
    assert observed == pinned, (
        "the printed-scale callout set on disk no longer matches the frozen "
        "pre-SP-2 baseline — regenerate the fixture deliberately, do not "
        "loosen this assertion"
    )


# ── Synthetic fitz page ───────────────────────────────────────────────────────


class _FakePage:
    """Minimal stand-in exposing get_text('blocks')."""

    def __init__(self, blocks):
        self._blocks = blocks

    def get_text(self, kind):  # noqa: D401
        if kind == "blocks":
            return self._blocks
        return []


def test_extract_printed_scales_two_blocks():
    # (x0, y0, x1, y1, text, block_no, block_type)
    blocks = [
        (2100, 1990, 2470, 2050,
         'SCALE: 1" = 40\'-0"  1  OVERALL FLOOR PLAN', 0, 0),
        (2180, 320, 2500, 380,
         'SCALE: 1 1/2" = 1\'-0"  2  TYP. S.C.C.P. MITERED CORNER', 1, 0),
    ]
    scales = extract_printed_scales(_FakePage(blocks))
    assert len(scales) == 2

    main = scales[0]
    assert main.feet_per_inch == 40.0
    assert abs(main.feet_per_point - 40.0 / 72.0) < 1e-9
    assert main.drawing_number == "1"
    assert "OVERALL FLOOR PLAN" in main.title.upper()
    assert main.center_pt == (2285.0, 2020.0)

    detail = scales[1]
    assert abs(detail.feet_per_inch - 0.6667) < 1e-3
    assert abs(detail.feet_per_point - detail.feet_per_inch / 72.0) < 1e-9
    assert detail.drawing_number == "2"
    assert "CORNER" in detail.title.upper()


def _vp(region_id, bbox, kind="unknown"):
    return Viewport(
        region_id=region_id, bbox_pt=bbox, kind=kind, detection_method="fallback"
    )


def test_match_label_inside_viewport_bbox():
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(300.0, 500.0), bbox_pt=(250.0, 480.0, 350.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    inside = _vp("R1", (100.0, 100.0, 600.0, 600.0))
    other = _vp("R2", (700.0, 100.0, 900.0, 300.0))
    matched = match_scales_to_viewports([ps], [inside, other])
    assert matched == {"R1": ps}


def test_match_label_below_viewport_binds_above_region():
    # Label sits just BELOW the drawing (outside its bbox) — bind to the region
    # directly above it, not the far-away region.
    ps = PrintedScale(
        scale_text='1/4" = 1\'-0"', feet_per_inch=4.0, feet_per_point=4.0 / 72.0,
        center_pt=(300.0, 630.0), bbox_pt=(250.0, 615.0, 350.0, 645.0),
        drawing_number="3", title="ENLARGED PLAN",
    )
    above = _vp("R1", (100.0, 100.0, 500.0, 600.0))
    far = _vp("R2", (100.0, 1000.0, 500.0, 1400.0))
    matched = match_scales_to_viewports([ps], [above, far])
    assert list(matched.keys()) == ["R1"]


def test_match_skips_mask_kinds():
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(300.0, 300.0), bbox_pt=(250.0, 280.0, 350.0, 320.0),
        drawing_number="1", title="FLOOR PLAN",
    )
    title_block = _vp("R1", (0.0, 0.0, 600.0, 600.0), kind="title_block")
    drawing = _vp("R2", (100.0, 100.0, 500.0, 500.0), kind="main_plan")
    matched = match_scales_to_viewports([ps], [title_block, drawing])
    assert matched == {"R2": ps}


def test_identify_main_plan_prefers_overall_floor_plan():
    main = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(2285.0, 2020.0), bbox_pt=(2100.0, 1990.0, 2470.0, 2050.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    detail = PrintedScale(
        scale_text='1 1/2" = 1\'-0"', feet_per_inch=0.6667,
        feet_per_point=0.6667 / 72.0, center_pt=(2340.0, 348.0),
        bbox_pt=(2180.0, 320.0, 2500.0, 380.0), drawing_number="2",
        title="TYPICAL DETAIL",
    )
    chosen = identify_main_plan_scale([detail, main])
    assert chosen is main


def test_identify_main_plan_none_when_only_details():
    detail = PrintedScale(
        scale_text='1 1/2" = 1\'-0"', feet_per_inch=0.6667,
        feet_per_point=0.6667 / 72.0, center_pt=(0.0, 0.0),
        bbox_pt=(0.0, 0.0, 10.0, 10.0), drawing_number="2",
        title="TYPICAL S.C.C.P. JOINT DETAIL",
    )
    assert identify_main_plan_scale([detail]) is None


# ── Priority chain: printed label wins over RANSAC ────────────────────────────


def _solved(fpp, region="R1"):
    return ViewportScale(
        fpp=fpp, fpi=fpp * 72.0, confidence="high", n_inliers=10,
        inlier_share=0.9, printed_agreement=True, door_check=None,
        method="ransac_consensus",
    )


def test_printed_label_wins_over_ransac():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    # RANSAC solved a (deliberately different) value; printed label must win.
    solved = _solved(0.60)  # ~43.2 ft/in
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(500.0, 500.0), bbox_pt=(480.0, 480.0, 520.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    result = resolve_scale_v2(
        page=None,
        viewports_with_scales=[(vp, solved)],
        printed_scales={"R1": ps},
    )
    assert isinstance(result, ScaleResult)
    assert result.method == "printed_label"
    assert result.confidence == "high"
    assert abs(result.feet_per_point - 40.0 / 72.0) < 1e-9
    # RANSAC disagreed > 5% -> cross-check note flags it but printed is kept.
    assert "needs_review" in result.detail


def test_printed_label_crosscheck_agrees():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    solved = _solved(40.0 / 72.0)  # agrees with the printed 40 ft/in
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(500.0, 500.0), bbox_pt=(480.0, 480.0, 520.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    result = resolve_scale_v2(
        page=None, viewports_with_scales=[(vp, solved)], printed_scales={"R1": ps}
    )
    assert result.method == "printed_label"
    assert "agrees" in result.detail
    assert "needs_review" not in result.detail


def test_no_printed_label_uses_ransac_unchanged():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    solved = _solved(0.60)
    # No printed_scales / main_plan_scale supplied -> RANSAC dimension solve.
    result = resolve_scale_v2(page=None, viewports_with_scales=[(vp, solved)])
    assert result.method == "dimension_solve"
    assert abs(result.feet_per_point - 0.60) < 1e-9


def test_override_still_outranks_printed_label():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    solved = _solved(0.60)
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(500.0, 500.0), bbox_pt=(480.0, 480.0, 520.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    result = resolve_scale_v2(
        page=None, viewports_with_scales=[(vp, solved)],
        override_feet_per_inch=48.0, printed_scales={"R1": ps},
    )
    assert result.method == "override"
    assert abs(result.feet_per_point - 48.0 / 72.0) < 1e-9
