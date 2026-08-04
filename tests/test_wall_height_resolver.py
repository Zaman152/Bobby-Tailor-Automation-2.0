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

from bobbytailor.pipeline.takeoff_pipeline import (
    _resolve_project_wall_height,
    _wall_height_cross_check_note,
)

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


# ── The elevation datum span is a CROSS-CHECK, not an override (D-11) ────────
#
# 23-14 made the datum ladder beat every keyword tier, on the argument that
# Crow's "36' CLEAR" understates the panels by 20%. The live run falsified it:
# the ladder reads 48 ft, and 2,972 LF of measured perimeter x 48 ft published
# 142,661 SF of tilt-up wall against a golden 108,443 SF (31.6% error) where
# the plan's own 36' CLEAR gives 1.3%. That published figure is precisely the
# perimeter x datum-height product the elevation binder's coverage note
# promises never to publish — the datum height had simply left the elevation
# route through this resolver.
#
# So the ladder now sits BELOW the plan's own statement and only flags
# disagreement. It still beats a blind default, because where the plan states
# nothing there is no first route to displace.


def test_the_plans_own_stated_height_outranks_the_datum_ladder():
    """D-11: a second measurement route cross-checks the first, never
    replaces it. Reversing this was the Crow tilt-up regression."""
    height, source = _resolve_project_wall_height(
        "GENERAL NOTES\n3. T.O. WALL 35'-0\" TYP. U.N.O.\n36' CLEAR",
        datum_span_ft=45.17,
    )
    assert abs(height - 36.0) < 0.01
    assert source == "plan"


def test_the_datum_ladder_flags_its_disagreement_and_publishes_nothing():
    note = _wall_height_cross_check_note(36.0, "plan", 48.0)
    assert note is not None
    assert "DISAGREES" in note
    assert "publishes no height (D-11)" in note
    assert "36" in note and "48" in note


def test_the_datum_ladder_records_agreement_too():
    note = _wall_height_cross_check_note(36.0, "plan", 35.0)
    assert note is not None
    assert "agrees" in note
    assert "publishes no height (D-11)" in note


def test_no_cross_check_note_when_the_ladder_is_the_published_height():
    """Nothing to reconcile: the ladder was the only measured route."""
    assert _wall_height_cross_check_note(48.0, "datum", 48.0) is None


def test_no_cross_check_note_without_a_ladder():
    assert _wall_height_cross_check_note(36.0, "plan", None) is None
    assert _wall_height_cross_check_note(36.0, "plan", 0.0) is None
    assert _wall_height_cross_check_note(None, "plan", 48.0) is None
    assert _wall_height_cross_check_note(36.0, "plan", "junk") is None


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
