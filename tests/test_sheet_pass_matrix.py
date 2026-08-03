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

    def test_cover_plate_collision_is_repaired(self):
        """Moxy pages 23-38: an electrical keynote killed 16 guestroom sheets.

        Plan 23-01 PINNED this defect as a recorded fact and handed the repair
        to plan 23-06, gated on the four-set check: "when it lands, this
        expectation changes deliberately, in that plan." It has landed, so the
        expectation is inverted here rather than deleted — the phrase that cost
        16 sheets stays in the suite forever as the regression it is.
        """
        text = "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING MASTER"
        sheet_type, source, keyword, context = classify_sheet_type_verbose(text)
        assert sheet_type != "title_sheet", (
            "the COVER PLATE keynote is discarding drawing sheets again"
        )
        assert (sheet_type, source, keyword, context) == (
            "floor_plan", "default", "", ""
        )

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


class TestClassifierIsTotal:
    """The page text comes from an untrusted PDF; the classifier must not raise.

    A classifier that throws on an unexpected text type turns one odd page into
    a dead run — the opposite of the honest-failure contract.
    """

    @pytest.mark.parametrize("bad", [None, 123, object(), b"FLOOR PLAN", ["FLOOR PLAN"]])
    def test_a_non_string_page_text_is_ignored_not_raised(self, bad):
        assert classify_sheet_type_verbose("A2.1 FLOOR PLAN", bad)[0] == "floor_plan"
        assert classify_sheet_type_from_text("", bad) == "floor_plan"

    @pytest.mark.parametrize("bad", [None, 123, object()])
    def test_a_non_string_title_block_falls_through_to_page_text(self, bad):
        sheet_type, source, _kw, _ctx = classify_sheet_type_verbose(
            bad, "EXTERIOR ELEVATION"
        )
        assert (sheet_type, source) == ("elevation", "full_page_text")


# ---------------------------------------------------------------------------
# Plan 23-06 Task 1 — the STRUCTURAL title-block test (text_shape)
#
# These are pure-text unit tests of the predicate that decides which
# bottom-right window is the title block. The real-PDF consequences are pinned
# in tests/test_four_set_coverage.py; the window search itself is pinned in
# tests/test_sheet_name.py.
# ---------------------------------------------------------------------------

from bobbytailor.pipeline.text_shape import (  # noqa: E402
    FUNCTION_WORDS,
    MIN_TITLE_BLOCK_EVIDENCE,
    PROSE_MIN_FUNCTION_WORDS,
    PROSE_MIN_RUN_TOKENS,
    has_sheet_identifier,
    is_prose_shaped,
    is_title_shaped_match,
    looks_like_title_block,
    run_containing,
    title_block_field_labels,
    word_runs,
)


class TestLooksLikeTitleBlock:
    """A labelled field grid passes; a paragraph of keynote prose fails.

    Both strings below are the REAL text extracted from Moxy page 27 by two
    different bottom-right windows (INV-00 §1c). They are the two populations
    the predicate has to separate, and they are of comparable length — the
    defect was never that the title was absent, it was that prose outvoted it.
    """

    # x > 88% of a 3024 pt sheet: the actual title block.
    MOXY_P27_TITLE_BLOCK = (
        "CUTOUT AND AT SHEET NO. JOB NO. DATE SHEET TITLE PHASE A "
        "KING SUITE B GUESTROOM ID-411 NOT Knoxville, 90% SUBMITTAL"
    )
    # x > 55% of the same sheet: the adjacent electrical keynote column.
    MOXY_P27_KEYNOTE_PROSE = (
        "BED. COORDINATE LOCATION OF OUTLET WITH RECESS CUTOUT IN BED "
        "PLATFORM. COORDINATE LOCATION AND INSTALLATION OF OUTLET AND "
        "SWITCHES WITH PEG WALL SYSTEM. PROVIDE DEDICATED OUTLET FOR MINI "
        "FRIDGE. GANG OUTLET & SWITCHES TOGETHER AT THIS LOCATION AT HEIGHT "
        "SHOWN. MASTER SWITCH, IF REQUIRED."
    )

    def test_a_labelled_field_grid_is_a_title_block(self):
        assert looks_like_title_block(self.MOXY_P27_TITLE_BLOCK) is True

    def test_keynote_prose_of_similar_length_is_not(self):
        assert looks_like_title_block(self.MOXY_P27_KEYNOTE_PROSE) is False

    def test_both_windows_contain_the_title_words(self):
        """The point of INV-00 §1c: this is signal-to-noise, not a blind spot.

        If the losing window did NOT contain the title, this whole plan would
        be unnecessary — so the test asserts the premise it is built on.
        """
        assert "CUTOUT" in self.MOXY_P27_TITLE_BLOCK
        assert "CUTOUT" in self.MOXY_P27_KEYNOTE_PROSE

    def test_crow_title_block_convention_passes(self):
        """A second drafting office, lower-cased labels, different field names."""
        crow = (
            "NOT ISSUED FOR CONSTRUCTION Sheet No. Sheet Title Issue Date "
            "Job No. 04/24/2026 2601014 OVERALL FLOOR PLAN A-101"
        )
        assert looks_like_title_block(crow) is True

    def test_empty_and_blank_are_not_title_blocks(self):
        assert looks_like_title_block("") is False
        assert looks_like_title_block("   ") is False

    def test_one_piece_of_evidence_is_not_enough(self):
        """A cross-reference "SEE A-101" must not pass a window off as a title
        block: one sheet-ID token is one piece of evidence, and two are required."""
        assert MIN_TITLE_BLOCK_EVIDENCE == 2
        assert has_sheet_identifier("SEE A-101") is True
        assert looks_like_title_block("SEE A-101") is False

    def test_a_bare_three_digit_id_is_not_evidence(self):
        """"A111" without a hyphen is indistinguishable from a wall type or a
        keynote number, so it is deliberately not accepted as a sheet ID."""
        assert has_sheet_identifier("SEAL SHEET PROJECT INFO 24103 A111") is False

    def test_field_labels_are_reported_by_name(self):
        labels = title_block_field_labels(self.MOXY_P27_TITLE_BLOCK)
        assert {"sheet_number", "sheet_title", "job_number", "date", "phase"} <= labels


class TestProseShape:
    """Two INDEPENDENT signals — neither alone separates the populations."""

    def test_thresholds_are_the_documented_ones(self):
        assert (PROSE_MIN_RUN_TOKENS, PROSE_MIN_FUNCTION_WORDS) == (6, 2)

    def test_length_alone_would_reject_the_correct_window(self):
        """The genuine Moxy title block contains a 9-token run — longer than the
        threshold — and is saved only by carrying no function words. This is the
        measurement that proves one signal is not enough."""
        run = [r for r in word_runs(TestLooksLikeTitleBlock.MOXY_P27_TITLE_BLOCK)
               if "GUESTROOM" in [t for t, _s, _e in r]][0]
        assert len(run) >= PROSE_MIN_RUN_TOKENS
        assert is_prose_shaped(TestLooksLikeTitleBlock.MOXY_P27_TITLE_BLOCK) is False

    def test_the_keynote_paragraph_is_prose_shaped(self):
        assert is_prose_shaped(
            TestLooksLikeTitleBlock.MOXY_P27_KEYNOTE_PROSE
        ) is True

    def test_a_single_letter_is_a_designator_not_an_article(self):
        """"PHASE A" / "KING TYPE A" — counting a lone "A" as the English
        article made four genuine Moxy title blocks read as prose."""
        assert "A" not in FUNCTION_WORDS
        assert "AN" not in FUNCTION_WORDS

    def test_function_words_are_grammar_not_drawing_phrases(self):
        """A deny list of unlucky phrases fixes the collisions we have seen and
        misses the next one. Nothing domain-specific may enter this set."""
        for banned in ("COVER", "PLATE", "SWITCH", "WALL", "COVERING", "INDEX"):
            assert banned not in FUNCTION_WORDS

    def test_runs_are_broken_by_numbers_and_punctuation(self):
        runs = word_runs("CS-00 COVER SHEET 25-13.01 ELEVATE")
        assert [[t for t, _s, _e in r] for r in runs] == [
            ["COVER", "SHEET"], ["ELEVATE"],
        ]

    def test_run_containing_finds_the_enclosing_run(self):
        text = "CS-00 COVER SHEET 25-13.01"
        start = text.index("COVER")
        run = run_containing(text, start, start + len("COVER"))
        assert [t for t, _s, _e in run] == ["COVER", "SHEET"]

    def test_run_containing_returns_none_outside_any_run(self):
        text = "SHEET TITLE: COVER 25-13.01"
        assert run_containing(text, 0, 1) is not None
        start = text.index("25-13.01")
        assert run_containing(text, start, start + 3) is None


class TestIsTitleShapedMatch:
    """The predicate Task 2's keyword guard is built on."""

    def test_a_short_field_value_is_title_shaped(self):
        text = "SHEET NO. A-000 SHEET TITLE COVER JOB NO. 25-13"
        start = text.index("COVER")
        assert is_title_shaped_match(text, start, start + len("COVER")) is True

    def test_a_word_inside_a_sentence_is_not(self):
        text = (
            'MASTER SWITCH, IF REQUIRED. PROVIDE LABEL ON THE LIGHT SWITCH '
            'COVER PLATE INDICATING "MASTER SWITCH".'
        )
        start = text.index("COVER")
        assert is_title_shaped_match(text, start, start + len("COVER")) is False


# ---------------------------------------------------------------------------
# Plan 23-06 Task 2 — the keyword-context guard
#
# A bare title word ("COVER", "INDEX") is trusted only inside the title block,
# because a title_sheet verdict SKIPS THE SHEET ENTIRELY. Whole-word matching
# was not enough: "LIGHT SWITCH COVER PLATE" contains COVER as a whole word,
# and that one phrase discarded 16 Moxy guestroom prototypes (INV-08 §1.2).
# The guard tests the POSITION of the match, never the keyword.
# ---------------------------------------------------------------------------

_find_title_position_hit = _spm._find_title_position_hit
_KW_TITLE_BLOCK_ONLY = _spm._KW_TITLE_BLOCK_ONLY


class TestBareTitleKeywordContextGuard:

    # Verbatim from plan 23-01's classify_sheet_type_verbose output on Moxy
    # page 23: ('title_sheet', 'title_block', 'COVER',
    #           'ABEL ON THE LIGHT SWITCH COVER PLATE INDICATING "MASTER')
    MOXY_KEYNOTE = (
        'MASTER SWITCH, IF REQUIRED. PROVIDE LABEL ON THE LIGHT SWITCH '
        'COVER PLATE INDICATING "MASTER SWITCH". SHEET NO. JOB NO. DATE '
        'SHEET TITLE PHASE A KING TYPE A GUESTROOM ID-407'
    )
    # Real title-block text from the two genuine Moxy title sheets.
    MOXY_COVER_SHEET = (
        "ELEVATE PROJECT NUMBER: SHEET TITLE: SHEET NUMBER: & by CGS. "
        "CS-00 COVER SHEET 25-13.01 ELEVATE"
    )
    MOXY_INDEX_SHEET = (
        "ELEVATE PROJECT NUMBER: SHEET TITLE: SHEET NUMBER: "
        "CS-01 SHEET INDEX 25-13.01"
    )
    BOBS_COVER_SHEET = (
        "ARCHITECTURAL CS-1 COVER SHEET GN-1 BUILDING CODE / OCCUPANCY & "
        "LIFE SAFETY PLAN GN-2 ACCESSIBILITY DETAILS"
    )

    def test_the_electrical_keynote_is_no_longer_a_title_sheet(self):
        assert classify_sheet_type_from_text(self.MOXY_KEYNOTE) != "title_sheet"

    def test_the_keynote_sheet_is_therefore_not_skipped(self):
        """The consequence that matters: an empty pass list means the sheet is
        never measured, never rendered, never counted."""
        sheet_type = classify_sheet_type_from_text(self.MOXY_KEYNOTE)
        assert plan_passes(sheet_type, title_block_text=self.MOXY_KEYNOTE) != []

    def test_the_genuine_cover_sheet_still_classifies_as_a_title_sheet(self):
        assert classify_sheet_type_from_text(self.MOXY_COVER_SHEET) == "title_sheet"

    def test_the_genuine_index_sheet_still_classifies_as_a_title_sheet(self):
        assert classify_sheet_type_from_text(self.MOXY_INDEX_SHEET) == "title_sheet"

    def test_a_second_offices_genuine_cover_sheet_also_survives(self):
        assert classify_sheet_type_from_text(self.BOBS_COVER_SHEET) == "title_sheet"

    def test_a_wall_covering_note_is_not_a_title_sheet(self):
        note = (
            "FINISH NOTE: ALL GUESTROOM WALLS TO RECEIVE VINYL WALL COVER "
            "AS SCHEDULED BY THE INTERIOR DESIGNER"
        )
        assert classify_sheet_type_from_text(note) != "title_sheet"

    def test_a_bare_cover_in_a_title_field_still_fires(self):
        """The guard rejects a POSITION, not the word. A title block whose sheet
        title is literally "COVER" must still be recognised — otherwise the
        guard would just be a disguised deletion of the keyword."""
        text = "SHEET NO. A-000 SHEET TITLE COVER JOB NO. 25-13"
        sheet_type, source, keyword, _ctx = classify_sheet_type_verbose(text)
        assert (sheet_type, source, keyword) == ("title_sheet", "title_block", "COVER")

    def test_a_bare_index_in_a_title_field_still_fires(self):
        text = "SHEET NO. A-001 SHEET TITLE INDEX JOB NO. 25-13"
        assert classify_sheet_type_from_text(text) == "title_sheet"

    def test_a_title_block_hit_wins_over_an_earlier_note_hit(self):
        """Deterministic order is preserved: the earliest TITLE-POSITION match
        decides, so a note mentioning COVER before the title block does not
        suppress the real title."""
        text = (
            "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING MASTER. "
            "SHEET TITLE COVER JOB NO. 25-13"
        )
        assert classify_sheet_type_from_text(text) == "title_sheet"

    def test_bare_keywords_are_still_ignored_in_full_page_text(self):
        """The title-block-only restriction is unchanged by the guard."""
        assert classify_sheet_type_from_text("", "COVER") != "title_sheet"

    def test_the_keyword_set_is_untouched(self):
        """The repair is a context predicate. Adding, removing or reordering a
        keyword to make a fixture pass is forbidden by the plan."""
        assert _KW_TITLE_BLOCK_ONLY == frozenset(["INDEX", "COVER"])

    def test_the_guard_is_not_a_deny_list_of_product_phrases(self):
        """A novel compound never seen before must be rejected on shape alone."""
        novel = (
            "PROVIDE A STAINLESS ACCESS PANEL AND A HINGED INSPECTION COVER "
            "PANEL AT EACH SHAFT PER THE MANUFACTURER"
        )
        assert classify_sheet_type_from_text(novel) != "title_sheet"

    def test_the_guard_returns_the_matched_keyword_and_span(self):
        text = "SHEET TITLE COVER 25-13"
        kw, start, end = _find_title_position_hit(text, _KW_TITLE_BLOCK_ONLY)
        assert (kw, text[start:end]) == ("COVER", "COVER")

    def test_the_guard_returns_none_when_every_match_is_prose(self):
        assert _find_title_position_hit(
            self.MOXY_KEYNOTE.upper(), _KW_TITLE_BLOCK_ONLY
        ) is None


class TestVerboseEquivalenceSweepAfterTheGuard:
    """Plan 23-01's sweep, re-asserted: every input that is NOT one of the two
    collision shapes keeps its verdict, and the collision shapes change on
    purpose. Listing them explicitly is what stops a future refactor from
    quietly widening the guard."""

    COLLISION_SHAPES = {
        "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE",
    }

    def test_only_the_collision_shapes_moved(self):
        for title_block, full_page in TestVerboseEquivalenceSweep.SWEEP:
            verdict = classify_sheet_type_from_text(title_block, full_page)
            if title_block in self.COLLISION_SHAPES:
                assert verdict != "title_sheet", (
                    "%r is a keynote sentence and must no longer discard the "
                    "sheet" % title_block
                )
            elif full_page in self.COLLISION_SHAPES:
                # Bare keywords were never trusted in full-page text, so this
                # row's verdict was already floor_plan and must not move.
                assert verdict == "floor_plan"

    def test_every_non_collision_row_keeps_a_title_verdict_where_it_had_one(self):
        for title_block in ("CS-00 COVER SHEET 25-13.01", "A0.1 SHEET INDEX"):
            assert classify_sheet_type_from_text(title_block) == "title_sheet"
