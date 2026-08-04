"""Pipeline-level deterministic-first tests (21-13, validation layer 3).

All offline — canned analyzers only, ZERO real API calls. Pins the
integrated V3-ACC-01/03 data flow at the TakeoffPipeline level:

- vector sheets are measured deterministically end-to-end with vision as a
  semantic labeler only (the provenance invariant: no ``vision_ensemble``
  quantity can exist on a vector sheet);
- raster sheets go through the ensemble-voted estimate path with every
  quantity capped ≤ medium and flagged unless the votes are unanimous;
- the per-run BudgetGuard makes exhaustion loud (``budget_exhausted``
  flags), never a silent partial;
- RunSettings is the shared env-driven configuration both entry points
  construct (parity foundation for 21-15).

NOTE on the Crow scale assertion: the 21-13 plan text carried the stale
"main-plan fpi ≈ 20" research note; the hand-verified truth table
(tests/fixtures/crow_cass/scale_truth.json) and the 21-07 STATE decision pin
Crow page 0 at 1" = 40' (1136' spans 2058pt on a 3024pt-wide sheet — 20 fpi
is geometrically impossible). The tests assert the verified truth.
"""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from bobbytailor.pipeline.takeoff_pipeline import (
    RunSettings,
    TakeoffPipeline,
    VECTOR_MIN_DRAWING_ITEMS,
    VECTOR_MIN_WORDS,
    is_vector_sheet,
)
from bobbytailor.vision.fusion import PROVENANCE_RANK

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"

# Vision extraction pass types that may produce quantities — they must NEVER
# run on the vector path (semantic labeling passes are the only vision work).
_EXTRACTION_PASSES = {"count", "measure", "schedule", "legend"}
_SEMANTIC_PASSES = {"semantic", "symbol_gallery"}


# ---------------------------------------------------------------------------
# Canned analyzers (no API)
# ---------------------------------------------------------------------------


class CannedSemanticAnalyzer:
    """Answers semantic/gallery structured-output requests from the schema.

    Labels are canned; IDs are read off the enum constraints so the answers
    are always grounded — exactly what a real structured-output response
    guarantees (grammar-constrained sampling).
    """

    def __init__(self, cost_usd: float = 0.01):
        self.cost_usd = cost_usd
        self.pass_types: list = []

    def __call__(
        self,
        screenshot_path,
        sheet_name="",
        pass_type="measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
    ):
        self.pass_types.append(pass_type)
        meta = {
            "_cost_usd": self.cost_usd,
            "_tokens_in": 100,
            "_tokens_out": 50,
            "_model_used": "canned-model",
        }
        if pass_type == "semantic":
            props = output_schema["properties"]
            regions = props["main_plan_region"]["enum"]
            wall_ids = props["wall_class_labels"]["items"]["properties"][
                "wall_class_id"
            ]["enum"]
            answer = {
                "main_plan_region": regions[0],
                "wall_class_labels": [
                    {
                        "wall_class_id": wid,
                        "label": "Wall Class %s" % wid,
                        "confidence": "high",
                    }
                    for wid in wall_ids
                ],
                "confidence": "high",
            }
            answer.update(meta)
            return answer
        if pass_type == "symbol_gallery":
            items = output_schema["properties"]["matches"]["items"]["properties"]
            symbol_ids = items["symbol_id"]["enum"]
            labels = items["label"]["enum"]
            answer = {
                "matches": [
                    {"symbol_id": sid, "label": labels[0], "confidence": "medium"}
                    for sid in symbol_ids
                ],
            }
            answer.update(meta)
            return answer
        # Extraction passes must never be requested on the vector path — the
        # empty result makes any such call visible in assertions.
        answer = {"components": [], "measurements": []}
        answer.update(meta)
        return answer


class RasterEnsembleStub:
    """N-sample raster extraction stub with a per-call component script."""

    def __init__(self, per_call_components, cost_usd: float = 0.01):
        self.per_call_components = per_call_components
        self.cost_usd = cost_usd
        self.calls = 0
        self.pass_types: list = []
        self.schemas: list = []

    def __call__(
        self,
        screenshot_path,
        sheet_name="",
        pass_type="measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
    ):
        idx = min(self.calls, len(self.per_call_components) - 1)
        self.calls += 1
        self.pass_types.append(pass_type)
        self.schemas.append(output_schema)
        return {
            "components": [dict(c) for c in self.per_call_components[idx]],
            "_cost_usd": self.cost_usd,
            "_tokens_in": 10,
            "_tokens_out": 5,
            "_model_used": "canned-raster",
        }


def _make_raster_pdf(tmp_path: Path) -> Path:
    """A one-page PDF with no drawings and no text — raster by heuristic."""
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    path = tmp_path / "raster.pdf"
    doc.save(str(path))
    doc.close()
    return path


def _make_vector_pdf(tmp_path: Path, n_lines: int = 250) -> Path:
    """A one-page PDF with enough vector paths to classify as vector."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(n_lines):
        y = 10 + (i % 70) * 10.0
        x = 10 + (i // 70) * 140.0
        page.draw_line(fitz.Point(x, y), fitz.Point(x + 100, y))
    path = tmp_path / "vector.pdf"
    doc.save(str(path))
    doc.close()
    return path


# ---------------------------------------------------------------------------
# 1. Vector sheet end-to-end (Crow page 0 + canned semantic labels)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def crow_vector():
    """Run the full deterministic-first flow ONCE on Crow page 0."""
    if not CROW_PDF.exists():
        pytest.skip("Crow fixture PDF not available")
    analyzer = CannedSemanticAnalyzer()
    pipeline = TakeoffPipeline(analyzer=analyzer, settings=RunSettings())
    result = pipeline.run_sheet(
        image_path="A-101.png",
        sheet_name="A-101",
        sheet_type="floor_plan",
        pdf_path=str(CROW_PDF),
        page_index=0,
    )
    return analyzer, result


def test_vector_sheet_measured_deterministically(crow_vector):
    _, result = crow_vector
    assert result.get("measurement_mode") == "vector"
    assert "deterministic" in result.get("_passes_run", [])
    components = result.get("components") or []
    assert components, "vector flow must produce deterministic components"
    for comp in components:
        assert comp.get("provenance") in PROVENANCE_RANK, (
            "every vector-sheet item must carry a known provenance: %r" % comp
        )


def test_vector_sheet_no_vision_ensemble_quantities(crow_vector):
    """THE provenance invariant (V3-ACC-01): on a vector sheet, no item with
    provenance == "vision_ensemble" may carry a quantity — vision labels,
    geometry/text supply every number."""
    _, result = crow_vector
    offenders = [
        c
        for c in result.get("components") or []
        if c.get("provenance") == "vision_ensemble" and c.get("quantity") is not None
    ]
    assert offenders == [], (
        "vision_ensemble quantities on a vector sheet: %r" % offenders
    )


def test_vector_sheet_vision_saw_only_semantic_passes(crow_vector):
    """Vision extraction passes (count/measure/schedule/legend) never run on
    the vector path — quantities are grammatically impossible for vision."""
    analyzer, _ = crow_vector
    seen = set(analyzer.pass_types)
    assert seen, "the semantic labeling pass should have run"
    assert seen <= _SEMANTIC_PASSES, (
        "vector path issued vision extraction passes: %r" % sorted(seen)
    )
    assert not (seen & _EXTRACTION_PASSES)


def test_off_scale_detail_viewports_excluded_from_geometry():
    """Multi-scale page guard: Crow page 0 carries the OVERALL FLOOR PLAN at
    1" = 40'-0" AND four S.C.C.P. details at 1 1/2" = 1'-0" (60x apart). Every
    quantity is computed at the ONE resolved page scale, so detail linework must
    be EXCLUDED — measuring it at the plan's scale is 60x wrong and would emit
    junk take-off rows (and double-count objects the plan already shows).
    """
    if not CROW_PDF.exists():
        pytest.skip("Crow fixture PDF not available")
    from bobbytailor.deterministic.printed_scale import (
        extract_printed_scales,
        match_scales_to_viewports,
    )
    from bobbytailor.deterministic.viewports import segment_viewports

    pipeline = TakeoffPipeline(analyzer=CannedSemanticAnalyzer(), settings=RunSettings())
    doc = fitz.open(str(CROW_PDF))
    page = doc[0]
    bundle = pipeline._deterministic_bundle(
        page, doc, str(CROW_PDF), 0, "A-101", "floor_plan"
    )
    resolved_fpp = bundle["fpp"]
    assert resolved_fpp == pytest.approx(40.0 / 72.0, rel=1e-3)  # 1" = 40'

    # The off-scale (detail) viewport rectangles on this page.
    vps = segment_viewports(page)
    by_region = match_scales_to_viewports(extract_printed_scales(page), vps)
    off_boxes = [
        vp.bbox_pt for vp in vps
        if (ps := by_region.get(vp.region_id)) is not None
        and abs(ps.feet_per_point - resolved_fpp) > 0.05 * resolved_fpp
    ]
    assert off_boxes, "fixture must carry at least one off-scale detail viewport"

    def _inside(x, y, box):
        return box[0] <= x <= box[2] and box[1] <= y <= box[3]

    for group in bundle["symbol_groups"]:
        for bx in group.instance_bboxes_pt:
            cx, cy = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
            for box in off_boxes:
                assert not _inside(cx, cy, box), (
                    "symbol %s has an instance inside an off-scale detail "
                    "viewport — it is being measured at the wrong scale"
                    % group.candidate_id
                )
    doc.close()


def test_multi_scale_guard_keeps_main_plan_measurements_intact():
    """The guard must remove ONLY off-scale geometry: the main plan's own
    footprint (the golden-passing 397,600 SF / 2,972 LF) is untouched."""
    if not CROW_PDF.exists():
        pytest.skip("Crow fixture PDF not available")
    pipeline = TakeoffPipeline(analyzer=CannedSemanticAnalyzer(), settings=RunSettings())
    doc = fitz.open(str(CROW_PDF))
    bundle = pipeline._deterministic_bundle(
        doc[0], doc, str(CROW_PDF), 0, "A-101", "floor_plan"
    )
    fp = bundle["footprint"]
    assert fp is not None
    assert fp.area_sf == pytest.approx(397600.0, rel=0.01)
    assert fp.perimeter_lf == pytest.approx(2972.0, rel=0.01)
    doc.close()


def test_vector_sheet_scale_confidence_main_plan_fpi_40(crow_vector):
    """Main-plan solve lands at the hand-verified 1" = 40' (scale_truth.json;
    the plan's "≈ 20" figure was the stale research note corrected in 21-07)."""
    _, result = crow_vector
    scale_confidence = result.get("scale_confidence") or []
    assert scale_confidence, "scale_confidence list must be present"
    main = [v for v in scale_confidence if v.get("is_main")]
    assert main, "a main-plan viewport must be selected"
    fpi = main[0].get("fpi")
    assert fpi is not None
    assert abs(fpi - 40.0) / 40.0 <= 0.02, "Crow p0 truth is 40 fpi, got %r" % fpi
    assert main[0].get("confidence") in ("high", "medium")
    # ViewportScale dict fields surfaced for the report (Task 2 contract).
    for key in ("n_inliers", "inlier_share", "printed_agreement", "method"):
        assert key in main[0]


def test_vector_sheet_budget_and_audit_metadata(crow_vector):
    _, result = crow_vector
    budget = result.get("_budget")
    assert budget is not None
    assert budget["cap_usd"] == pytest.approx(RunSettings.from_env().budget_usd)
    assert budget["spent_usd"] > 0  # the semantic pass was charged
    assert budget["exhausted"] is False
    assert isinstance(result.get("fusion_rejected"), list)
    assert result.get("main_plan_region")


# ---------------------------------------------------------------------------
# 2. Raster sheet — ensemble path
# ---------------------------------------------------------------------------


def test_raster_sheet_runs_ensemble_n_times_all_flagged(tmp_path):
    raster_pdf = _make_raster_pdf(tmp_path)
    script = [
        # Bollard unanimous 28/28/28; Column disagrees 10/10/13.
        [
            {"name": "Bollard", "count_estimate": 28, "unit": "ea", "confidence": "high"},
            {"name": "Column", "count_estimate": 10, "unit": "ea", "confidence": "high"},
        ],
        [
            {"name": "Bollard", "count_estimate": 28, "unit": "ea", "confidence": "high"},
            {"name": "Column", "count_estimate": 10, "unit": "ea", "confidence": "high"},
        ],
        [
            {"name": "Bollard", "count_estimate": 28, "unit": "ea", "confidence": "high"},
            {"name": "Column", "count_estimate": 13, "unit": "ea", "confidence": "high"},
        ],
    ]
    stub = RasterEnsembleStub(script)
    pipeline = TakeoffPipeline(
        analyzer=stub, settings=RunSettings(ensemble_n=3, budget_usd=10.0)
    )
    result = pipeline.run_sheet(
        image_path="raster.png",
        sheet_name="R-1",
        sheet_type="floor_plan",
        pdf_path=str(raster_pdf),
        page_index=0,
    )

    # Ensemble fan-out: exactly N analyzer invocations, raster schema on each.
    assert stub.calls == 3
    assert all(s is not None for s in stub.schemas), "raster schema required"
    assert result.get("measurement_mode") == "raster"
    assert result.get("_passes_run") == ["raster_ensemble"]

    components = {c["name"]: c for c in result["components"]}
    assert set(components) == {"Bollard", "Column"}
    for comp in components.values():
        # Estimates never exceed medium confidence; provenance is the vision floor.
        assert comp["confidence"] in ("medium", "low")
        assert comp["provenance"] == "vision_ensemble"
        assert "votes" in comp  # audit: full vote vector persisted

    bollard = components["Bollard"]
    assert bollard["quantity"] == 28
    assert bollard["confidence"] == "medium"  # unanimous → medium (never high)
    assert bollard["needs_review"] is False

    column = components["Column"]
    assert column["quantity"] == 10  # median of 10/10/13
    assert column["needs_review"] is True  # not unanimous → flagged
    assert column["confidence"] == "low"


def test_raster_force_overrides_vector_detection(tmp_path):
    vector_pdf = _make_vector_pdf(tmp_path)
    stub = RasterEnsembleStub(
        [[{"name": "Door", "count_estimate": 4, "unit": "ea", "confidence": "high"}]]
    )
    pipeline = TakeoffPipeline(
        analyzer=stub,
        settings=RunSettings(ensemble_n=3, budget_usd=10.0, raster_force=True),
    )
    result = pipeline.run_sheet(
        image_path="forced.png",
        sheet_name="F-1",
        sheet_type="floor_plan",
        pdf_path=str(vector_pdf),
        page_index=0,
    )
    assert result.get("measurement_mode") == "raster"
    assert stub.calls == 3


# ---------------------------------------------------------------------------
# 3. Budget exhaustion mid-run — partial but honest, never silent
# ---------------------------------------------------------------------------


def test_budget_exhaustion_mid_run_flags_remaining(tmp_path):
    raster_pdf = _make_raster_pdf(tmp_path)
    stub = RasterEnsembleStub(
        [[{"name": "Bollard", "count_estimate": 28, "unit": "ea", "confidence": "high"}]],
        cost_usd=6.0,  # 2nd charge (12.0) blows the $10 cap
    )
    pipeline = TakeoffPipeline(
        analyzer=stub, settings=RunSettings(ensemble_n=3, budget_usd=10.0)
    )
    pages = [
        {
            "image_path": "r%d.png" % i,
            "sheet_name": "R-%d" % i,
            "sheet_type_hint": "floor_plan",
            "pdf_path": str(raster_pdf),
            "page_index": 0,
        }
        for i in (1, 2)
    ]

    # The run COMPLETES — budget exhaustion never raises out of run_project.
    all_extracted, all_estimates, project_type = pipeline.run_project(pages)

    assert len(all_extracted) == 2
    assert isinstance(project_type, str)

    sheet1, sheet2 = all_extracted
    # Sheet 1: one paid sample, then the refused charge flags everything.
    assert sheet1["_budget_exhausted"] is True
    assert sheet1["review_reason"] == "budget_exhausted"
    assert sheet1["components"], "the paid sample's items are kept (honest partial)"
    for comp in sheet1["components"]:
        assert comp["needs_review"] is True
        assert "budget_exhausted" in comp["review_reason"]

    # Sheet 2: no charge fits — empty but explicitly flagged, never silent.
    assert sheet2["_budget_exhausted"] is True
    assert sheet2["review_reason"] == "budget_exhausted"
    assert sheet2["components"] == []

    # Final run-level accounting on every sheet: only paid work in the ledger.
    for sheet in all_extracted:
        assert sheet["_budget"]["cap_usd"] == 10.0
        assert sheet["_budget"]["spent_usd"] == pytest.approx(6.0)
        # C2: the run STOPPED doing scheduled work. `exhausted` alone cannot
        # say so — $4.00 of the $10.00 cap is still unspent here, exactly the
        # shape that let Crow's truncated run present as complete.
        assert sheet["_budget"]["exhausted"] is False
        assert sheet["_budget"]["refused_charges"] >= 1
        assert sheet["_budget"]["truncated"] is True


def test_budget_truncation_marks_the_coverage_ledger_not_measured(tmp_path):
    """C2: a sheet cut short by the cap must not read `measured` in the ledger.

    Crow's A-401 and A-601 skipped their remaining passes on an exhausted
    budget and BOTH ledger rows said "measured", with the phrase "budget
    exhausted" appearing zero times in the report. The coverage loss was
    silent — the class of defect phase 23 abolished everywhere else.
    """
    from bobbytailor.pipeline.coverage import (
        CoverageLedger, MEASURED_TRUNCATED,
    )

    raster_pdf = _make_raster_pdf(tmp_path)
    stub = RasterEnsembleStub(
        [[{"name": "Bollard", "count_estimate": 28, "unit": "ea", "confidence": "high"}]],
        cost_usd=6.0,  # 2nd charge (12.0) blows the $10 cap
    )
    pipeline = TakeoffPipeline(
        analyzer=stub, settings=RunSettings(ensemble_n=3, budget_usd=10.0)
    )
    ledger = CoverageLedger(pages_in_source=1)
    ledger.register_page(0, sheet_name="R-1")
    pages = [{
        "image_path": "r1.png",
        "sheet_name": "R-1",
        "sheet_type_hint": "floor_plan",
        "pdf_path": str(raster_pdf),
        "page_index": 0,
    }]

    pipeline.run_project(pages, coverage=ledger)

    row = ledger.sheet(0)
    assert row.budget_truncated is True
    assert row.disposition == MEASURED_TRUNCATED
    assert "budget was exhausted" in row.reason

    summary = ledger.summary()
    assert summary["sheets_budget_truncated"] == 1
    assert summary["sheets_measured"] == 0
    # The run cannot present as complete.
    assert summary["coverage_pct_pages"] == 0.0
    assert "budget" in " ".join(ledger.warnings()).lower()


# ---------------------------------------------------------------------------
# 4. RunSettings.from_env — env-driven shared configuration
# ---------------------------------------------------------------------------


def test_run_settings_from_env_honors_ensemble_n_and_budget(monkeypatch):
    """ENSEMBLE_N / API_BUDGET_PER_RUN_USD flow through ensemble_settings()
    (the single reader — 21-11 decision) into RunSettings."""
    from bobbytailor import config

    monkeypatch.setattr(config, "ENSEMBLE_N", 7, raising=False)
    monkeypatch.setattr(config, "API_BUDGET_PER_RUN_USD", 3.5, raising=False)
    settings = RunSettings.from_env()
    assert settings.ensemble_n == 7
    assert settings.budget_usd == 3.5


def test_run_settings_from_env_boolean_flags(monkeypatch):
    monkeypatch.setenv("RASTER_FORCE", "1")
    monkeypatch.setenv("DETERMINISTIC_ENABLED", "false")
    monkeypatch.setenv("LEARNING_ENABLED", "no")
    monkeypatch.setenv("VERIFY_RETRY_ENABLED", "true")
    settings = RunSettings.from_env()
    assert settings.raster_force is True
    assert settings.deterministic_enabled is False
    assert settings.learning_enabled is False
    assert settings.verify_retry_enabled is True


def test_run_settings_defaults():
    settings = RunSettings()
    assert settings.deterministic_enabled is True
    assert settings.learning_enabled is True
    assert settings.verify_retry_enabled is True
    assert settings.raster_force is False
    assert settings.to_dict()["ensemble_n"] == settings.ensemble_n


# ---------------------------------------------------------------------------
# 5. is_vector_sheet threshold cases (RESEARCH §2 heuristic)
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, n_drawings: int, n_words: int):
        self._drawings = [{"items": []}] * n_drawings
        self._words = [(0, 0, 1, 1, "w", 0, 0, 0)] * n_words

    def get_drawings(self):
        return list(self._drawings)

    def get_text(self, kind):
        assert kind == "words"
        return list(self._words)


@pytest.mark.parametrize(
    "n_drawings,n_words,expected",
    [
        (199, 99, False),   # both below threshold → raster
        (5000, 500, True),  # rich vector CAD → vector
        (199, 100, True),   # words alone cross the threshold
        (200, 0, True),     # drawings alone cross the threshold
        (0, 0, False),      # empty page → raster
    ],
)
def test_is_vector_sheet_thresholds(n_drawings, n_words, expected):
    assert VECTOR_MIN_DRAWING_ITEMS == 200 and VECTOR_MIN_WORDS == 100
    assert is_vector_sheet(_FakePage(n_drawings, n_words)) is expected


def test_is_vector_sheet_unreadable_page_is_raster():
    class _Broken:
        def get_drawings(self):
            raise RuntimeError("corrupt page")

        def get_text(self, kind):
            raise RuntimeError("corrupt page")

    assert is_vector_sheet(_Broken()) is False


# ═════════════════════════════════════════════════════════════════════════════
# 23-14 — elevations reach the deterministic path WITHOUT opening the plan path
# ═════════════════════════════════════════════════════════════════════════════

BOBS_UPLOAD = Path("uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf")
CHELSEA_UPLOAD = Path(
    "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
)


def test_routing_opened_and_the_plan_path_is_untouched():
    """The single-restraint invariant: only the DETERMINISTIC set grew. The
    plan tuple is what gates wall extraction, room extraction, symbol
    clustering and footprint measurement, so leaving it alone preserves the
    21-13 no-fabricated-walls guarantee BY CONSTRUCTION."""
    from bobbytailor.pipeline.takeoff_pipeline import (
        _DETERMINISTIC_SHEET_TYPES as D,
        _PLAN_SHEET_TYPES as P,
    )

    assert "elevation" in D
    assert "elevation" not in P
    assert P == ("floor_plan", "civil_site", "roof_plan")


@pytest.fixture(scope="module")
def bobs_elevation_bundles():
    """Bob's page 1 (floor plan — the independent footprint) then page 4
    (elevation), measured ONCE through one pipeline, as a run would."""
    if not BOBS_UPLOAD.exists():
        pytest.skip("the real Bob's plan set is not present")
    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(str(BOBS_UPLOAD))
    try:
        plan = pipe._deterministic_bundle(
            doc[1], doc, str(BOBS_UPLOAD), 1, "A2.0", "floor_plan"
        )
        elevation = pipe._deterministic_bundle(
            doc[4], doc, str(BOBS_UPLOAD), 4, "A4.0", "elevation"
        )
        forced = pipe._deterministic_bundle(
            doc[4], doc, str(BOBS_UPLOAD), 4, "A4.0", "floor_plan"
        )
    finally:
        doc.close()
    return plan, elevation, forced


def test_the_elevation_path_fabricates_no_walls_and_no_thickness_classes(
    bobs_elevation_bundles,
):
    """THE negative test. The elevation bundle returns an EMPTY wall list AND
    an EMPTY thickness-class mapping AND no footprint — while the elevation
    areas are non-empty. The contrast is pinned in the same test: forcing the
    same page to floor_plan pairs facade linework into fabricated walls
    (measured today: 30 walls / 8 thickness classes; INV-03's earlier probe
    of the same failure mode read 22/4 — the property protected is that the
    elevation path emits ZERO, whatever the fabrication count of the day)."""
    _plan, elevation, forced = bobs_elevation_bundles
    assert elevation["walls"] == []
    assert elevation["wall_lf_by_class"] == {}
    assert elevation["footprint"] is None
    assert len(elevation["elevation_areas"]) >= 3

    # Contrast: the floor-plan path on the SAME page fabricates walls.
    assert len(forced["walls"]) >= 20
    assert len(forced["wall_lf_by_class"]) >= 4
    # The elevation path must NEVER do that — the assertion above, restated
    # as the invariant: zero, not merely fewer.
    assert len(elevation["walls"]) == 0
    assert len(elevation["wall_lf_by_class"]) == 0


def test_bobs_front_elevation_width_matches_the_independent_footprint(
    bobs_elevation_bundles,
):
    """Position validation, never count-tuning: the front facade blob's width
    lands between 245 and 255 ft against the page-1 footprint's independently
    measured depth of 250.0 ft. No golden painting figure is consulted."""
    plan, elevation, _forced = bobs_elevation_bundles
    footprint = plan["footprint"]
    assert footprint is not None
    assert abs(float(footprint.depth_ft) - 250.0) < 0.1

    facades = {f.title: f for f in elevation["elevation_areas"]}
    front = facades["FRONT ELEVATION NEW"]
    assert 245.0 <= front.bbox_ft[0] <= 255.0
    assert not front.excluded
    # Width-validated by the independent measurement: the front facade needs
    # no review even though Bob's prints no datum ladder.
    assert front.needs_review is False, front.review_reason


def test_the_demolition_elevation_is_present_but_excluded(bobs_elevation_bundles):
    _plan, elevation, _forced = bobs_elevation_bundles
    facades = {f.title: f for f in elevation["elevation_areas"]}
    demo = facades["FRONT ELEVATION DEMOLITION"]
    assert demo.excluded is True
    assert "demolition" in demo.excluded_reason.lower()
    assert demo.area_sf > 5000.0, "measured, on the record — just never billed"


def test_a_surviving_same_orientation_pair_flags_both():
    """The backstop for a missed demolition title: two surviving FRONT
    facades flag each other; an excluded demolition creates no pair."""
    from bobbytailor.deterministic.room_fill import FacadeResult
    from bobbytailor.pipeline.takeoff_pipeline import _flag_same_orientation_pairs

    a = FacadeResult(area_sf=6245.0, title="FRONT ELEVATION NEW",
                     orientation="FRONT")
    b = FacadeResult(area_sf=6134.0, title="FRONT ELEVATION DEMOLITION",
                     orientation="FRONT")
    _flag_same_orientation_pairs([a, b])
    assert a.needs_review and b.needs_review
    assert "FRONT" in a.review_reason and "demolition" in a.review_reason.lower()

    c = FacadeResult(area_sf=6245.0, title="FRONT ELEVATION NEW",
                     orientation="FRONT")
    d = FacadeResult(area_sf=6134.0, title="FRONT ELEVATION DEMOLITION",
                     orientation="FRONT", excluded=True,
                     excluded_reason="demolition")
    _flag_same_orientation_pairs([c, d])
    assert c.needs_review is False, "an excluded demolition creates no pair"


def test_chelsea_yields_one_dominant_component_per_titled_elevation():
    """Generality across a different drafting office, same code, no tuning:
    the elevation pass over pages 9-12, 13-16 and 18 returns exactly one
    dominant component per titled elevation. 29 exterior elevation drawings
    are titled on those pages (INV-03 §1.3 tallied 21 before the dedicated
    title-line recovery landed; the count is measured, not assumed)."""
    if not CHELSEA_UPLOAD.exists():
        pytest.skip("the real Chelsea plan set is not present")
    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(str(CHELSEA_UPLOAD))
    measured = 0
    try:
        for pno in (9, 10, 11, 12, 13, 14, 15, 16, 18):
            page = doc[pno]
            facades, _drops = pipe._measure_elevation_areas(page, [], "p%d" % pno)
            live = [f for f in facades if not f.excluded]
            for f in live:
                assert f.area_sf > 0, "%s p%d measured nothing" % (f.title, pno)
                assert f.fill_ratio >= 0.4, (
                    "%s p%d: fill %.2f — annotation, not a facade"
                    % (f.title, pno, f.fill_ratio)
                )
                dominant_ok = (
                    f.component_count == 1
                    or not f.sub_components
                    or f.area_sf >= 2.0 * f.sub_components[0]["area_sf"]
                )
                assert dominant_ok, (
                    "%s p%d: dominant %.0f SF vs runner-up %.0f SF"
                    % (f.title, pno, f.area_sf,
                       f.sub_components[0]["area_sf"] if f.sub_components else 0)
                )
                measured += 1
    finally:
        doc.close()
    assert measured == 29


def test_a_raster_elevation_still_falls_back_to_the_legacy_flow():
    """_route_deterministic's raster branch refuses non-plan types, so a
    scanned elevation degrades to the legacy vision flow unchanged."""
    import inspect

    from bobbytailor.pipeline import takeoff_pipeline as tp

    src = inspect.getsource(tp.TakeoffPipeline._route_deterministic)
    assert "resolved_type not in _PLAN_SHEET_TYPES" in src, (
        "the raster guard that keeps a scanned elevation on the legacy flow"
    )
