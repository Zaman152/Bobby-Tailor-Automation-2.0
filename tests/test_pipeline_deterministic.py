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


# ---------------------------------------------------------------------------
# 4. RunSettings.from_env — env-driven shared configuration
# ---------------------------------------------------------------------------


def test_run_settings_from_env_honors_ensemble_n_and_budget(monkeypatch):
    """ENSEMBLE_N / API_BUDGET_PER_RUN_USD flow through ensemble_settings()
    (the single reader — 21-11 decision) into RunSettings."""
    import config

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
