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
from bobbytailor.pipeline.takeoff_pipeline import _resolve_project_wall_height


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


def test_learning_failure_never_raises():
    class _BoomCtx:
        def get_assumption_value(self, key):
            raise RuntimeError("db down")

    # A raising learned context must not break resolution — plan text still read.
    assert _resolve_project_wall_height("T.O. WALL 20'-0\"", None, _BoomCtx()) == (
        20.0,
        "plan",
    )
