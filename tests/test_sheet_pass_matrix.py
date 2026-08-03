"""
tests/test_sheet_pass_matrix.py — Unit tests for sheet_pass_matrix.py.

Tests cover:
  - PASS_MATRIX structure and coverage
  - plan_passes() routing (including title_sheet skip and unknown fallback)
  - classify_sheet_type_from_text() keyword heuristics
  - pick_model_for_pass() model selection priority
  - No PDF files or API keys required.
"""

import sys
import os
import importlib
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module-level fixture: import with mocked config and claude_analyzer to
# ensure tests run without ANTHROPIC_API_KEY or installed dependencies.
# ---------------------------------------------------------------------------

# Provide minimal config stubs before importing the module under test.
# Values mirror the conftest.py env pins so assertions hold regardless of
# whether the mock or the real config wins the import-order race.
_CONFIG_MOCK = MagicMock()
_CONFIG_MOCK.CLAUDE_MODEL = "claude-haiku-4-5"
_CONFIG_MOCK.CLAUDE_MODEL_SCHEDULES = "claude-sonnet-4-5"
_CONFIG_MOCK.CLAUDE_MODEL_SEMANTIC = "claude-sonnet-5"
_CONFIG_MOCK.CLAUDE_MODEL_DENSE = "claude-opus-4-8"
_CONFIG_MOCK.CLAUDE_MODEL_ESCALATION = "claude-fable-5"
_CONFIG_MOCK.CLAUDE_MODEL_CLASSIFY = "claude-haiku-4-5-classify"
# Phase 22 (Step 1c): explicit tmp-path strings on every dir attribute so a
# SOLO run of this file never produces a literal "MagicMock/..." dir at the
# repo root via os.fspath on a child mock.
_CONFIG_MOCK.OUTPUT_DIR = "/tmp/bt-spm-out"
_CONFIG_MOCK.SCREENSHOTS_DIR = "/tmp/bt-spm-out/screenshots"

_CA_MOCK = MagicMock()
_CA_MOCK._pick_model.return_value = "claude-haiku-4-5"

# Patch at sys.modules level so the import inside sheet_pass_matrix resolves
sys.modules.setdefault("bobbytailor.config", _CONFIG_MOCK)
sys.modules.setdefault("bobbytailor.vision.claude_analyzer", _CA_MOCK)

# Now import the module under test (after stubs are in place)
import importlib.util, pathlib

# Phase 21 (V3-STRUCT-01): the real module lives under src/bobbytailor/pipeline/.
# Spec-load it under an isolated name so the stubs above bind without touching
# the canonical package module.
_MODULE_PATH = (
    pathlib.Path(__file__).parent.parent
    / "src" / "bobbytailor" / "pipeline" / "sheet_pass_matrix.py"
)
_spec = importlib.util.spec_from_file_location("sheet_pass_matrix", _MODULE_PATH)
_spm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_spm)

PASS_MATRIX              = _spm.PASS_MATRIX
MODEL_ROUTING            = _spm.MODEL_ROUTING
WILDCARD_SHEET_TYPE      = _spm.WILDCARD_SHEET_TYPE
classify_sheet_type_from_text = _spm.classify_sheet_type_from_text
classify_sheet_type_verbose   = _spm.classify_sheet_type_verbose
plan_passes              = _spm.plan_passes
pick_model_for_pass      = _spm.pick_model_for_pass
resolve_routed_model     = _spm.resolve_routed_model


# ---------------------------------------------------------------------------
# PASS_MATRIX structure
# ---------------------------------------------------------------------------

class TestPassMatrix:
    EXPECTED_SHEET_TYPES = {
        "floor_plan", "elevation", "civil_site", "schedule",
        "detail", "title_sheet", "roof_plan", "mep_plan",
    }

    def test_covers_all_eight_sheet_types(self):
        assert set(PASS_MATRIX.keys()) == self.EXPECTED_SHEET_TYPES

    def test_title_sheet_is_empty(self):
        assert PASS_MATRIX["title_sheet"] == [], (
            "title_sheet must have empty pass list (zero API cost)"
        )

    def test_civil_site_is_measure_only(self):
        assert PASS_MATRIX["civil_site"] == ["measure"]

    def test_schedule_is_schedule_only(self):
        assert PASS_MATRIX["schedule"] == ["schedule"]

    def test_floor_plan_has_count_measure_and_schedule(self):
        passes = PASS_MATRIX["floor_plan"]
        assert passes == ["count", "measure", "schedule"]

    def test_floor_plan_schedule_pass_without_title_block_keywords(self):
        passes = plan_passes("floor_plan", title_block_text="OVERALL FLOOR PLAN")
        assert passes == ["count", "measure", "schedule"]

    def test_elevation_has_count_and_measure(self):
        passes = PASS_MATRIX["elevation"]
        assert "count" in passes
        assert "measure" in passes

    def test_all_non_title_sheet_types_are_non_empty(self):
        for sheet_type, passes in PASS_MATRIX.items():
            if sheet_type == "title_sheet":
                continue
            assert passes, f"{sheet_type} must have at least one pass"


# ---------------------------------------------------------------------------
# plan_passes()
# ---------------------------------------------------------------------------

class TestPlanPasses:
    def test_title_sheet_returns_empty(self):
        result = plan_passes("title_sheet")
        assert result == []

    def test_elevation_returns_count_and_measure(self):
        result = plan_passes("elevation")
        assert "count" in result
        assert "measure" in result

    def test_civil_site_returns_measure_only(self):
        assert plan_passes("civil_site") == ["measure"]

    def test_schedule_returns_schedule_only(self):
        assert plan_passes("schedule") == ["schedule"]

    def test_roof_plan_returns_count_and_measure(self):
        result = plan_passes("roof_plan")
        assert "count" in result
        assert "measure" in result

    def test_mep_plan_returns_count_and_measure(self):
        result = plan_passes("mep_plan")
        assert "count" in result
        assert "measure" in result

    def test_unknown_sheet_type_falls_back_to_measure(self):
        result = plan_passes("unknown_custom_type")
        assert result == ["measure"], (
            "Unknown types must never be silently dropped"
        )

    def test_returns_copy_not_reference(self):
        """Mutating the returned list must not affect PASS_MATRIX."""
        result = plan_passes("floor_plan")
        result.clear()
        assert PASS_MATRIX["floor_plan"] != []


# ---------------------------------------------------------------------------
# classify_sheet_type_from_text()
# ---------------------------------------------------------------------------

class TestTitleSheetFalsePositives:
    """title_sheet SKIPS the sheet entirely (zero API, no geometry), so a false
    positive silently deletes a drawing from the take-off. A bare substring test
    made "COVER" match "WALL COVERING" and dropped 27 of Moxy's 40 sheets —
    every guestroom floor plan, i.e. all 129,521 SF of Gyp Wall. Keyword hits
    must be WHOLE WORDS, and the bare words are trusted only in the title block.
    """

    def test_wall_covering_note_is_not_a_title_sheet(self):
        """THE Moxy bug: a hotel floor plan whose notes say "WALL COVERING"."""
        page = "LEVEL 3 FLOOR PLAN\nNOTES: PROVIDE VINYL WALL COVERING AT ALL GUESTROOMS"
        assert classify_sheet_type_from_text("", page) == "floor_plan"

    @pytest.mark.parametrize("page_text", [
        "GUESTROOM FLOOR PLAN — WALL COVERING SCHEDULE REFERENCE",
        "FLOOR PLAN\nCOVERING: SEE FINISH LEGEND",
        "LEVEL 2 FLOOR PLAN\nRECOVER EXISTING ROOF WHERE INDICATED",
    ])
    def test_cover_substring_never_skips_a_real_plan(self, page_text):
        assert classify_sheet_type_from_text("", page_text) != "title_sheet"

    def test_indexed_substring_does_not_skip(self):
        page = "FLOOR PLAN\nSEE INDEXED KEYNOTES BELOW"
        assert classify_sheet_type_from_text("", page) != "title_sheet"

    # -- genuine title sheets must STILL be detected ------------------------

    @pytest.mark.parametrize("text", [
        "COVER SHEET", "SHEET INDEX", "DRAWING INDEX", "TITLE SHEET",
    ])
    def test_real_title_sheet_phrases_still_detected_anywhere(self, text):
        assert classify_sheet_type_from_text("", text) == "title_sheet"

    @pytest.mark.parametrize("tb", ["COVER", "INDEX"])
    def test_bare_title_words_still_work_in_the_title_block(self, tb):
        assert classify_sheet_type_from_text(tb, "") == "title_sheet"

    def test_bare_cover_in_page_text_alone_is_not_a_title_sheet(self):
        """A bare word in FULL-PAGE text is not enough to delete a sheet."""
        assert classify_sheet_type_from_text("", "COVER") != "title_sheet"


class TestMixedSheetIsMeasurable:
    """A sheet is a COLLECTION of drawings; its type is only the dominant one.
    Moxy's guestroom prototypes carry interior elevations AND the AR/RCP plans
    holding every guestroom quantity — classified "elevation" they never reach
    the deterministic engine, so the sheets that matter most get skipped.
    An explicit "<NAME> - AR/RCP PLAN" viewport title outranks a stray
    ELEVATION keyword.
    """

    def test_guestroom_sheet_with_elevations_and_an_ar_plan_is_measurable(self):
        page = ("KING SUITE B ENTRY - A\nKING SUITE B - ELEVATION F\n"
                "KING SUITE B - AR PLAN\nKING SUITE B - RCP PLAN")
        assert classify_sheet_type_from_text("", page) == "floor_plan"

    def test_rcp_plan_title_alone_is_measurable(self):
        assert classify_sheet_type_from_text("", "QQ A - RCP PLAN") == "floor_plan"

    def test_pure_elevation_sheet_is_still_an_elevation(self):
        page = "POP-UP HUB ELEVATION A\nHUB CORRIDOR ELEVATION B\nNORTH ELEVATION"
        assert classify_sheet_type_from_text("", page) == "elevation"

    def test_furniture_and_electrical_plans_do_not_make_a_sheet_measurable(self):
        """FF/EM/FC plans carry no take-off geometry of their own."""
        page = "KING A - FF PLAN\nKING A - EM PLAN\nNORTH ELEVATION"
        assert classify_sheet_type_from_text("", page) == "elevation"

    def test_roof_plan_still_wins_over_the_viewport_rule(self):
        assert classify_sheet_type_from_text("", "ROOF PLAN\nQQ A - AR PLAN") == "roof_plan"


class TestKeywordWordBoundaries:
    """Every keyword set matches whole words — the substring flaw that hit
    "COVER"/"COVERING" equally hits PLAN/PLANT and SECTION/SECTIONAL."""

    def test_plant_is_not_a_plan(self):
        assert classify_sheet_type_from_text("PLANTING SCHEDULE") != "floor_plan"

    def test_sectional_is_not_a_section(self):
        # "SECTIONAL" must not trip the DETAIL set on its own.
        assert classify_sheet_type_from_text("SECTIONAL OVERHEAD DOOR ELEVATION") == "elevation"

    def test_multiword_keywords_still_match(self):
        assert classify_sheet_type_from_text("OVERALL FLOOR PLAN") == "floor_plan"
        assert classify_sheet_type_from_text("ROOF PLAN") == "roof_plan"


class TestClassifySheetType:
    def test_overall_floor_plan(self):
        assert classify_sheet_type_from_text("OVERALL FLOOR PLAN") == "floor_plan"

    def test_level_1_floor_plan(self):
        assert classify_sheet_type_from_text("LEVEL 1 FLOOR PLAN") == "floor_plan"

    def test_roof_plan(self):
        assert classify_sheet_type_from_text("ROOF PLAN") == "roof_plan"

    def test_elevation(self):
        assert classify_sheet_type_from_text("NORTH ELEVATION") == "elevation"

    def test_elevations_plural(self):
        assert classify_sheet_type_from_text("EXTERIOR ELEVATIONS") == "elevation"

    def test_civil_site_plan(self):
        assert classify_sheet_type_from_text("OVERALL SITE PLAN") == "civil_site"

    def test_grading_plan(self):
        assert classify_sheet_type_from_text("GRADING AND DRAINAGE PLAN") == "civil_site"

    def test_schedule_keyword(self):
        assert classify_sheet_type_from_text("DOOR SCHEDULE") == "schedule"

    def test_panel_schedule(self):
        assert classify_sheet_type_from_text("PANEL SCHEDULE") == "schedule"

    def test_detail_keyword(self):
        assert classify_sheet_type_from_text("WALL DETAILS") == "detail"

    def test_section_keyword(self):
        assert classify_sheet_type_from_text("BUILDING SECTIONS") == "detail"

    def test_title_sheet_index(self):
        assert classify_sheet_type_from_text("SHEET INDEX") == "title_sheet"

    def test_title_sheet_cover(self):
        assert classify_sheet_type_from_text("COVER SHEET") == "title_sheet"

    def test_mep_prefix_with_plan(self):
        # MEP sheet: first token is M/P/E + digit, "PLAN" in title
        assert classify_sheet_type_from_text("M1 MECHANICAL PLAN") == "mep_plan"

    def test_mep_electrical_prefix(self):
        assert classify_sheet_type_from_text("E2 ELECTRICAL PLAN") == "mep_plan"

    def test_empty_title_falls_back_to_full_page(self):
        result = classify_sheet_type_from_text("", "DOOR SCHEDULE")
        assert result == "schedule"

    def test_empty_both_defaults_to_floor_plan(self):
        assert classify_sheet_type_from_text("") == "floor_plan"

    def test_roof_plan_wins_over_plain_plan(self):
        """ROOF PLAN must not be classified as floor_plan."""
        assert classify_sheet_type_from_text("ROOF PLAN AND EQUIPMENT LAYOUT") == "roof_plan"

    def test_title_sheet_wins_over_schedule(self):
        """'SHEET INDEX' (title) must not be mislabeled as 'schedule'."""
        result = classify_sheet_type_from_text("SHEET INDEX AND SCHEDULE")
        assert result == "title_sheet"

    def test_case_insensitive(self):
        assert classify_sheet_type_from_text("floor plan") == "floor_plan"
        assert classify_sheet_type_from_text("Roof Plan") == "roof_plan"


# ---------------------------------------------------------------------------
# pick_model_for_pass()
# ---------------------------------------------------------------------------

class TestPickModelForPass:
    # Read the model slugs straight from the module under test so the routing
    # invariants ("schedules model" vs "default model") hold regardless of
    # whether the mock or the real `config` won the import-order race. conftest
    # guarantees all values are pairwise distinct.
    SONNET   = _spm.CLAUDE_MODEL_SCHEDULES   # count/measure quality slug
    HAIKU    = _spm.CLAUDE_MODEL             # the default slug
    SEMANTIC = _spm.CLAUDE_MODEL_SEMANTIC    # semantic-labeling workhorse
    DENSE    = _spm.CLAUDE_MODEL_DENSE       # dense small-text / arbitration
    CLASSIFY = _spm.CLAUDE_MODEL_CLASSIFY    # cheap classification slug

    def test_elevation_measure_returns_sonnet(self):
        model = pick_model_for_pass("elevation", "measure")
        assert model == self.SONNET

    def test_detail_count_returns_sonnet(self):
        model = pick_model_for_pass("detail", "count")
        assert model == self.SONNET

    def test_detail_measure_returns_sonnet(self):
        model = pick_model_for_pass("detail", "measure")
        assert model == self.SONNET

    def test_schedule_schedule_returns_dense(self):
        """v2: dense table structuring routes to the DENSE (Opus-class) slug."""
        model = pick_model_for_pass("schedule", "schedule")
        assert model == self.DENSE

    def test_roof_plan_measure_returns_sonnet(self):
        model = pick_model_for_pass("roof_plan", "measure")
        assert model == self.SONNET

    def test_mep_plan_measure_returns_sonnet(self):
        model = pick_model_for_pass("mep_plan", "measure")
        assert model == self.SONNET

    def test_floor_plan_count_uses_sonnet(self):
        """floor_plan count routes to Sonnet for grid/symbol accuracy."""
        model = pick_model_for_pass("floor_plan", "count")
        assert model == self.SONNET

    def test_floor_plan_measure_uses_sonnet(self):
        model = pick_model_for_pass("floor_plan", "measure")
        assert model == self.SONNET

    def test_elevation_count_returns_none(self):
        """elevation count is not in MODEL_ROUTING — should be None (Haiku)."""
        model = pick_model_for_pass("elevation", "count")
        assert model is None

    def test_sheet_name_fallback_when_no_routing(self):
        """When MODEL_ROUTING has no entry, _pick_model fallback is used."""
        # Make _ca_pick_model return Sonnet for this specific sheet name
        _CA_MOCK._pick_model.return_value = self.SONNET
        try:
            model = pick_model_for_pass("floor_plan", "count", sheet_name="E3.1")
            assert model == self.SONNET
        finally:
            _CA_MOCK._pick_model.return_value = self.HAIKU

    def test_floor_plan_count_routed_without_sheet_name(self):
        """MODEL_ROUTING applies even when sheet_name is empty."""
        model = pick_model_for_pass("floor_plan", "count", sheet_name="")
        assert model == self.SONNET


# ---------------------------------------------------------------------------
# MODEL_ROUTING v2 (21-05) — RESEARCH §5 routing table
# ---------------------------------------------------------------------------

class TestModelRoutingV2:
    SONNET   = _spm.CLAUDE_MODEL_SCHEDULES
    HAIKU    = _spm.CLAUDE_MODEL
    SEMANTIC = _spm.CLAUDE_MODEL_SEMANTIC
    DENSE    = _spm.CLAUDE_MODEL_DENSE
    CLASSIFY = _spm.CLAUDE_MODEL_CLASSIFY

    # -- dense small-text structuring (legend/schedule) → DENSE ------------

    def test_floor_plan_schedule_returns_dense(self):
        assert pick_model_for_pass("floor_plan", "schedule") == self.DENSE

    def test_floor_plan_legend_returns_dense(self):
        assert pick_model_for_pass("floor_plan", "legend") == self.DENSE

    def test_legend_wildcard_covers_any_sheet_type(self):
        """Legend pass on a sheet type without an exact row → wildcard DENSE."""
        assert pick_model_for_pass("mep_plan", "legend") == self.DENSE

    def test_schedule_wildcard_covers_any_sheet_type(self):
        assert pick_model_for_pass("elevation", "schedule") == self.DENSE

    # -- semantic labeling → DENSE (wildcard row) ---------------------------
    # The semantic pass (and the symbol gallery, which routes through it) picks
    # WHICH geometry candidate is Columns/Bollards and WHICH wall class is CMU.
    # On the Sonnet row those bindings flipped between identical runs (CMU
    # 8 ↔ 11,294 SF) — the #1 accuracy blocker — so they run on the best model.
    # The schemas carry no numeric fields, so this buys binding reliability and
    # can never buy a hallucinated quantity.

    @pytest.mark.parametrize("sheet_type", [
        "floor_plan", "roof_plan", "mep_plan", "elevation", "civil_site",
    ])
    def test_semantic_pass_returns_dense_slug(self, sheet_type):
        assert pick_model_for_pass(sheet_type, "semantic") == self.DENSE

    @pytest.mark.parametrize("sheet_type", ["floor_plan", "civil_site"])
    def test_vocabulary_pass_returns_dense_slug(self, sheet_type):
        """The once-per-project vocabulary read seeds every downstream name."""
        assert pick_model_for_pass(sheet_type, "vocabulary") == self.DENSE

    # -- verify-retry arbitration → DENSE (wildcard row) --------------------

    @pytest.mark.parametrize("sheet_type", ["floor_plan", "schedule", "detail"])
    def test_verify_retry_returns_dense(self, sheet_type):
        assert pick_model_for_pass(sheet_type, "verify_retry") == self.DENSE

    # -- AI naming/reading pass → DENSE (Opus) on ANY sheet type -------------
    # The project's ONE reader / manifest-builder must run on Opus so it emits a
    # valid naming manifest on every plan (the #1 generalization surface).

    @pytest.mark.parametrize("sheet_type", [
        "floor_plan", "roof_plan", "mep_plan", "elevation", "civil_site",
        "detail", "schedule", "", "unknown_type",
    ])
    def test_naming_conventions_routes_to_dense_opus(self, sheet_type):
        assert pick_model_for_pass(sheet_type, "naming_conventions") == self.DENSE

    def test_naming_conventions_resolve_routed_model_is_dense(self):
        assert resolve_routed_model("floor_plan", "naming_conventions") == self.DENSE

    def test_naming_conventions_not_semantic(self):
        """Regression: the reader pass must NOT resolve to the Sonnet row."""
        assert pick_model_for_pass("floor_plan", "naming_conventions") != self.SEMANTIC

    # -- classification → CLASSIFY (wildcard row) ---------------------------

    def test_classify_pass_returns_classify_slug(self):
        assert pick_model_for_pass("floor_plan", "classify") == self.CLASSIFY

    # -- fallback behavior ---------------------------------------------------

    def test_unknown_pass_falls_back_to_default(self):
        """No exact row, no wildcard row → None (caller uses CLAUDE_MODEL)."""
        assert pick_model_for_pass("floor_plan", "nonexistent_pass") is None

    def test_unknown_sheet_and_pass_falls_back_to_default(self):
        assert pick_model_for_pass("unknown_type", "count") is None

    def test_exact_key_beats_wildcard(self):
        """(schedule, schedule) exact row resolves before the wildcard row."""
        exact = MODEL_ROUTING[("schedule", "schedule")]
        assert resolve_routed_model("schedule", "schedule") == exact

    # -- resolve_routed_model (pure table lookup) ----------------------------

    def test_resolve_routed_model_exact(self):
        assert resolve_routed_model("elevation", "measure") == self.SONNET

    def test_resolve_routed_model_wildcard(self):
        assert resolve_routed_model("roof_plan", "semantic") == self.DENSE

    def test_resolve_routed_model_none(self):
        assert resolve_routed_model("elevation", "count") is None

    def test_resolve_routed_model_ignores_name_heuristic(self):
        """Pure lookup — takes no sheet_name, cannot recurse into _pick_model."""
        import inspect
        params = inspect.signature(resolve_routed_model).parameters
        assert list(params) == ["sheet_type", "pass_type"]

    # -- structure invariants -------------------------------------------------

    def test_routing_dict_shape_intact(self):
        """dict[tuple[str, str], str-like] — _pick_model consumers unchanged."""
        for key, value in MODEL_ROUTING.items():
            assert isinstance(key, tuple) and len(key) == 2
            assert isinstance(key[0], str) and isinstance(key[1], str)
            assert value, "routing values must be truthy model slugs"

    def test_no_hardcoded_model_literals_in_routing_source(self):
        """Every MODEL_ROUTING value must come from config — no 'claude-'
        string literal may appear inside the MODEL_ROUTING dict source."""
        source = _MODULE_PATH.read_text()
        start = source.index("MODEL_ROUTING: dict")
        end = source.index("}", start)
        routing_block = source[start:end]
        assert '"claude-' not in routing_block
        assert "'claude-" not in routing_block

    def test_wildcard_rows_present_for_new_pass_types(self):
        for pass_type in ("classify", "semantic", "legend", "schedule", "verify_retry"):
            assert (WILDCARD_SHEET_TYPE, pass_type) in MODEL_ROUTING


# ---------------------------------------------------------------------------
# classify_sheet_type_verbose — the classifier states its reason (23-01 / INV-08)
# ---------------------------------------------------------------------------

class TestClassifySheetTypeVerbose:
    """The verbose form reports WHICH keyword decided a verdict, and where.

    'No artifact anywhere records it' is the Gap 8 defect. These tests pin the
    reason-reporting contract; they change no classification outcome.
    """

    # -- shape ---------------------------------------------------------------

    def test_returns_a_four_tuple(self):
        result = classify_sheet_type_verbose("A2.1 FLOOR PLAN")
        assert isinstance(result, tuple) and len(result) == 4
        assert all(isinstance(x, str) for x in result)

    def test_wrapper_signature_is_unchanged(self):
        """CRITICAL-risk symbol: 3 direct callers depend on the 2-arg shape."""
        import inspect
        params = inspect.signature(classify_sheet_type_from_text).parameters
        assert list(params) == ["title_block_text", "full_page_text"]

    # -- the live COVER PLATE defect, recorded as a fact ---------------------

    def test_cover_plate_collision_is_recorded_not_repaired(self):
        """Moxy pages 23-38: an electrical keynote kills 16 guestroom sheets.

        This test PINS the live defect (INV-08 §1.2) as a recorded fact. The
        structural repair belongs to plan 23-06, gated on the four-set check —
        when it lands, this expectation changes deliberately, in that plan.
        """
        text = "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING MASTER"
        sheet_type, source, keyword, context = classify_sheet_type_verbose(text)
        assert sheet_type == "title_sheet"
        assert source == "title_block"
        assert keyword == "COVER"
        assert "PLATE" in context

    def test_bare_cover_is_not_trusted_in_full_page_text(self):
        """The same phrase in page text must NOT reach the title_sheet branch."""
        sheet_type, source, keyword, _ctx = classify_sheet_type_verbose(
            "", "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE"
        )
        assert sheet_type != "title_sheet"
        assert (sheet_type, source, keyword) == ("floor_plan", "default", "")

    # -- source attribution --------------------------------------------------

    def test_source_is_title_block_when_the_title_block_decides(self):
        assert classify_sheet_type_verbose("A2.1 FLOOR PLAN", "NOTES")[1] == "title_block"

    def test_source_is_full_page_text_when_the_title_block_is_empty(self):
        sheet_type, source, keyword, _ctx = classify_sheet_type_verbose(
            "", "OVERALL FLOOR PLAN"
        )
        assert (sheet_type, source) == ("floor_plan", "full_page_text")
        assert keyword == "FLOOR PLAN"

    def test_source_is_default_when_nothing_matches(self):
        assert classify_sheet_type_verbose("", "") == ("floor_plan", "default", "", "")
        assert classify_sheet_type_verbose("ZZZ 12345") == (
            "floor_plan", "default", "", "",
        )

    # -- keyword attribution per branch --------------------------------------

    @pytest.mark.parametrize(
        "text,expected_type,expected_keyword",
        [
            ("CS-00 COVER SHEET",            "title_sheet", "COVER SHEET"),
            ("A0.1 SHEET INDEX",             "title_sheet", "SHEET INDEX"),
            ("E2.0 PANEL SCHEDULE",          "schedule",    "PANEL SCHEDULE"),
            ("A3.0 ROOF PLAN",               "roof_plan",   "ROOF PLAN"),
            ("A5.1 EXTERIOR ELEVATION",      "elevation",   "ELEVATION"),
            ("C1.0 SITE PLAN",               "civil_site",  "SITE PLAN"),
            ("A9.1 WALL SECTION",            "detail",      "SECTION"),
            ("A2.1 FLOOR PLAN",              "floor_plan",  "FLOOR PLAN"),
            ("M2.1 MECHANICAL PLAN",         "mep_plan",    "M2.1"),
        ],
    )
    def test_keyword_names_the_deciding_match(self, text, expected_type,
                                              expected_keyword):
        sheet_type, _source, keyword, context = classify_sheet_type_verbose(text)
        assert sheet_type == expected_type
        assert keyword == expected_keyword
        assert keyword in context or expected_type == "mep_plan"

    def test_plan_viewport_title_reports_the_matched_phrase(self):
        sheet_type, _source, keyword, context = classify_sheet_type_verbose(
            "KING SUITE B - RCP PLAN"
        )
        assert sheet_type == "floor_plan"
        assert "RCP" in keyword and "PLAN" in keyword
        assert "KING SUITE B" in context

    # -- context is bounded and auditable ------------------------------------

    def test_context_is_bounded(self):
        """T-23-03: the context is a phrase, never a dump of the drawing."""
        long_text = "X" * 500 + " FLOOR PLAN " + "Y" * 500
        _t, _s, keyword, context = classify_sheet_type_verbose(long_text)
        assert keyword == "FLOOR PLAN"
        assert len(context) <= len(keyword) + 2 * 25 + 2
        assert "FLOOR PLAN" in context

    def test_context_is_empty_only_when_nothing_matched(self):
        assert classify_sheet_type_verbose("QQ 999")[3] == ""
        assert classify_sheet_type_verbose("A2.1 FLOOR PLAN")[3] != ""

    # -- determinism ---------------------------------------------------------

    def test_keyword_choice_is_deterministic_across_repeated_calls(self):
        """A frozenset iterates in hash order; the recorded reason must not."""
        text = "A9.1 ENLARGED DETAIL AND BUILDING SECTION"
        results = {classify_sheet_type_verbose(text) for _ in range(25)}
        assert len(results) == 1

    def test_earliest_match_wins_when_several_keywords_hit(self):
        """'DETAIL' precedes 'SECTION' in the text, so DETAIL is the reason."""
        assert classify_sheet_type_verbose(
            "ENLARGED DETAIL AND BUILDING SECTION"
        )[2] == "DETAIL"
        assert classify_sheet_type_verbose(
            "BUILDING SECTION AND ENLARGED DETAIL"
        )[2] == "SECTION"


class TestVerboseEquivalenceSweep:
    """classify_sheet_type_from_text is a projection — NO outcome may move.

    Shape 3 of the Validation Architecture (invariance / no-regression diff).
    This task adds reporting; a single differing verdict here is a routing
    change, and a routing change here is 16 sheets appearing or vanishing.
    """

    SWEEP = [
        # (title_block_text, full_page_text)
        ("CS-00 COVER SHEET 25-13.01", ""),
        ("A0.1 SHEET INDEX", "DRAWING INDEX"),
        ("E2.0 PANEL SCHEDULE", "PANEL SCHEDULE NOTES"),
        ("A3.0 ROOF PLAN", "ROOF PLAN AND GAS PIPING"),
        ("A5.1 EXTERIOR ELEVATIONS", "NORTH ELEVATION"),
        ("C1.0 GRADING PLAN", "SITE PLAN"),
        ("A9.1 WALL SECTIONS AND DETAILS", "TYPICAL DETAIL"),
        ("A2.1 OVERALL FLOOR PLAN", "FLOOR PLAN"),
        ("M2.1 MECHANICAL PLAN", "MECHANICAL PLAN"),
        ("", ""),
        ("", "OVERALL FLOOR PLAN"),
        ("ID-411", "KING SUITE B - RCP PLAN"),
        ("PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE", ""),
        ("", "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE"),
        ("A1.0 LEVEL 7", "LEVEL 7 - AR PLAN"),
        ("ZZZ 12345", "NO KEYWORDS ANYWHERE"),
    ]

    def test_sweep_covers_every_branch(self):
        assert len(self.SWEEP) >= 12
        produced = {classify_sheet_type_from_text(t, f) for t, f in self.SWEEP}
        for expected in ("title_sheet", "schedule", "roof_plan", "elevation",
                         "civil_site", "detail", "floor_plan", "mep_plan"):
            assert expected in produced, "sweep does not exercise %r" % expected

    @pytest.mark.parametrize("title_block,full_page", SWEEP)
    def test_wrapper_equals_verbose_first_element(self, title_block, full_page):
        assert classify_sheet_type_from_text(title_block, full_page) == \
            classify_sheet_type_verbose(title_block, full_page)[0]

    @pytest.mark.parametrize("title_block,full_page", SWEEP)
    def test_verbose_always_reports_a_source(self, title_block, full_page):
        _t, source, keyword, context = classify_sheet_type_verbose(
            title_block, full_page
        )
        assert source in ("title_block", "full_page_text", "default")
        if source == "default":
            assert (keyword, context) == ("", "")
        else:
            assert keyword != ""
