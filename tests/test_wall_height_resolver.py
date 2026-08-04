"""Offline tests for the autonomous wall/clear-height resolver (manifest
replacement, plans-only). No API calls — pure text parsing + a stub learned
context. Pins:
- a T.O. WALL / CLEAR callout in the plan text layer is read as the height,
  source "plan";
- empty text falls back to the flagged 30 ft industrial default;
- a learned wall_height_ft assumption takes precedence over the plan text;
- out-of-band tokens (plan dimensions, spec codes) are ignored; the robust
  (max plausible, 8'-60') value wins.
"""
import os

import fitz
import pytest

from bobbytailor.pipeline.takeoff_pipeline import _resolve_project_wall_height

CROW = "tests/fixtures/crow_cass/crow_cass_plans.pdf"


def test_resolves_plan_height_from_to_wall_callout():
    text = "GENERAL NOTES\n3. T.O. WALL 35'-0\" TYP. U.N.O.\n"
    height, source = _resolve_project_wall_height(text)
    assert abs(height - 35.0) < 0.01
    assert source == "plan"


def test_resolves_height_near_tilt_panel_token():
    text = "TILT-UP PANEL 41'-6\" MAX HEIGHT"
    height, source = _resolve_project_wall_height(text)
    assert abs(height - 41.5) < 0.01
    assert source == "plan"


def test_empty_text_returns_flagged_default():
    assert _resolve_project_wall_height("") == (30.0, "default")
    assert _resolve_project_wall_height(None) == (30.0, "default")


def test_no_matching_callout_returns_default():
    # Numbers exist but not near any wall/clear keyword → default (never invent).
    assert _resolve_project_wall_height("DETAIL 5/A501  SCALE 1/8\"=1'-0\"") == (
        30.0,
        "default",
    )


def test_learned_wall_height_takes_precedence_over_plan_text():
    class _Ctx:
        def get_assumption_value(self, key):
            return 22.0 if key == "wall_height_ft" else None

    assert _resolve_project_wall_height("T.O. WALL 35'-0\"", None, _Ctx()) == (
        22.0,
        "learned",
    )


def test_takes_max_plausible_ignoring_out_of_band():
    # 300' overall plan dim is out of the 8-60 band; 24' clear height wins.
    text = "CLR HT 24'-0\"   OVERALL BLDG 300'-0\"   CLEAR 18'-0\""
    height, source = _resolve_project_wall_height(text)
    assert source == "plan"
    assert abs(height - 24.0) < 0.01


def test_clear_callout_beats_material_dimension_number():
    # The Crow bug: a "48' - 4\"" bay dimension sits near the S.C.C.P./PANEL text,
    # while the printed clear height is "36' CLEAR". Tier 1 (CLEAR) must win.
    text = (
        "ALL SITE CAST CONCRETE PANEL WIDTHS 48' - 4\"  48' - 4\"\n"
        "BUILDING TO BE 36' CLEAR JUST PAST THE OFFICE POD\n"
    )
    height, source = _resolve_project_wall_height(text)
    assert source == "plan"
    assert abs(height - 36.0) < 0.01


def test_clearance_and_clear_color_not_read_as_height():
    # "CLEAR ANODIZED" (a color) and "MIN. CLEARANCE 4'-0\"" are NOT clear heights;
    # 4' is below the plausible band anyway → flagged default (never invented).
    text = "COLOR: CLEAR ANODIZED\nMIN. CLEARANCE\n4'-0\" O.C."
    assert _resolve_project_wall_height(text) == (30.0, "default")


def test_inch_aff_value_not_read_as_clear_height():
    # "48\" A.F.F. TO CLEAR Z-GUARD" — 48 inches, not 48 feet, and not a CLEAR
    # height callout → must not resolve 48.
    text = "MOUNTED ABOVE 48\" A.F.F. TO CLEAR Z-GUARD"
    height, _ = _resolve_project_wall_height(text)
    assert height != 48.0


@pytest.mark.skipif(not os.path.isfile(CROW), reason="Crow plans fixture not present")
def test_crow_plan_resolves_36_clear_not_48():
    doc = fitz.open(CROW)
    full = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    height, source = _resolve_project_wall_height(full)
    assert source == "plan"
    assert abs(height - 36.0) < 0.01, "Crow clear height must be 36' (printed), not 48'"


def test_learning_failure_never_raises():
    class _BoomCtx:
        def get_assumption_value(self, key):
            raise RuntimeError("db down")

    # A raising learned context must not break resolution — plan text still read.
    assert _resolve_project_wall_height("T.O. WALL 20'-0\"", None, _BoomCtx()) == (
        20.0,
        "plan",
    )


# ── Tier 0: the elevation datum span (23-14) ─────────────────────────────────
#
# The drawing set's own printed vertical ruler — top datum to finish floor —
# is the authoritative wall height: it IS the wall being measured stating its
# own height. It beats every keyword tier and the default; a prior HUMAN
# correction (learned) still outranks it.


def test_a_datum_span_beats_every_keyword_tier():
    height, source = _resolve_project_wall_height(
        "GENERAL NOTES\n3. T.O. WALL 35'-0\" TYP. U.N.O.\n36' CLEAR",
        datum_span_ft=45.17,
    )
    assert abs(height - 45.17) < 0.01
    assert source == "datum"


def test_a_datum_span_beats_the_default():
    assert _resolve_project_wall_height("", datum_span_ft=48.0) == (48.0, "datum")


def test_no_datum_span_returns_exactly_what_it_returns_today():
    text = "GENERAL NOTES\n3. T.O. WALL 35'-0\" TYP. U.N.O.\n"
    assert _resolve_project_wall_height(text) == _resolve_project_wall_height(
        text, datum_span_ft=None
    )
    assert _resolve_project_wall_height("", datum_span_ft=None) == (30.0, "default")


def test_a_learned_human_correction_still_outranks_the_datum():
    class _Ctx:
        def get_assumption_value(self, key):
            return 22.0 if key == "wall_height_ft" else None

    assert _resolve_project_wall_height(
        "T.O. WALL 35'-0\"", None, _Ctx(), datum_span_ft=45.17
    ) == (22.0, "learned")


def test_an_invalid_datum_span_is_ignored():
    assert _resolve_project_wall_height("", datum_span_ft=0.0) == (30.0, "default")
    assert _resolve_project_wall_height("", datum_span_ft=-3.0) == (30.0, "default")
    assert _resolve_project_wall_height("", datum_span_ft="junk") == (30.0, "default")
