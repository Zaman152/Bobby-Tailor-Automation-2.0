"""Verify-retry arbitration tests (21-14, V3-ACC-05). All offline — stubbed
analyzers only, ZERO real API calls.

Engine tests (``-k engine``) pin the bounded/grounded/budget-charged
contract of ``retry_flagged_items``; pipeline tests pin the takeoff_pipeline
wiring (queue construction, resolution merge-back, flag-never-suppress) and
the removal of the legacy env-flag verify-retry logging stub from source.
"""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

import bobbytailor.pipeline.takeoff_pipeline as tp
from bobbytailor.pipeline.takeoff_pipeline import RunSettings, TakeoffPipeline
from bobbytailor.vision.ensemble import BudgetGuard
from bobbytailor.vision.verify_retry import (
    MAX_RETRIES_PER_ITEM,
    retry_flagged_items,
)

SYM_BBOXES = {
    "SYM-1": (100.0, 100.0, 160.0, 160.0),
    "SYM-2": (200.0, 200.0, 260.0, 260.0),
    "SYM-3": (300.0, 300.0, 360.0, 360.0),
}


def _registry(kind: str = "symbol_group") -> dict:
    return {cid: {"bbox_pt": bbox, "kind": kind} for cid, bbox in SYM_BBOXES.items()}


@pytest.fixture(scope="module")
def vector_page():
    """A real fitz page so render_clip_crop exercises the true render path."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(250):
        y = 10 + (i % 70) * 10.0
        x = 10 + (i // 70) * 140.0
        page.draw_line(fitz.Point(x, y), fitz.Point(x + 100, y))
    for bbox in SYM_BBOXES.values():
        page.draw_rect(fitz.Rect(bbox))
    yield page
    doc.close()


class RetryStub:
    """Analyzer stub answering verify_retry questions from a script.

    ``answer_for(user_hint, call_index)`` decides the answer; every call is
    recorded with its schema/hint/images so grounding can be asserted.
    """

    def __init__(self, answer_for, cost_usd: float = 0.01):
        self.answer_for = answer_for
        self.cost_usd = cost_usd
        self.calls: list = []

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
        self.calls.append(
            {
                "pass_type": pass_type,
                "sheet_type": sheet_type,
                "user_hint": user_hint,
                "output_schema": output_schema,
                "images": images,
            }
        )
        answer = self.answer_for(user_hint or "", len(self.calls) - 1)
        return {
            "answer": answer,
            "confidence": "high",
            "_cost_usd": self.cost_usd,
            "_tokens_in": 50,
            "_tokens_out": 5,
            "_model_used": "canned-dense",
        }


def _oob_flag(item: str, cid, qty=99999, unit="ea") -> dict:
    flag = {
        "sheet": "A1",
        "item": item,
        "qty": qty,
        "unit": unit,
        "rule": {"min": 1, "max": 5000},
        "flag_type": "out_of_band",
    }
    if cid:
        flag["candidate_id"] = cid
    return flag


# ---------------------------------------------------------------------------
# Engine — bounded, grounded, budget-charged arbitration
# ---------------------------------------------------------------------------


class TestRetryEngine:
    def test_engine_confirmed_flags_single_attempt_each(self, vector_page):
        """3 flags, stub answering confirmed → all carry retry_history with
        exactly 1 attempt each (plan acceptance criterion)."""
        stub = RetryStub(lambda hint, i: "yes")
        guard = BudgetGuard(10.0)
        flags = [
            _oob_flag("Ladder", "SYM-1"),
            _oob_flag("Bollard", "SYM-2"),
            _oob_flag("Column", "SYM-3"),
        ]

        results = retry_flagged_items(
            flags, vector_page, _registry(), stub, guard, sheet_type="floor_plan"
        )

        assert len(results) == 3
        for rec in results:
            assert rec["resolution"] == "confirmed"
            assert len(rec["retry_history"]) == 1
            entry = rec["retry_history"][0]
            for key in ("question", "answer", "confidence", "model", "cost_usd"):
                assert key in entry
            assert entry["answer"] == "yes"
            assert entry["model"] == "canned-dense"
        assert len(stub.calls) == 3
        # Every retry call is charged to the run budget guard.
        assert guard.spent_usd == pytest.approx(0.03)
        # All calls used the verify_retry pass with a choice-grounded schema.
        for call in stub.calls:
            assert call["pass_type"] == "verify_retry"
            assert call["output_schema"]["properties"]["answer"]["enum"] == [
                "yes", "no", "unclear",
            ]
            assert call["images"], "the clip crop must be sent"

    def test_engine_relabel_touches_label_only(self, vector_page):
        """Label dispute: answer picks a different legend label → relabeled;
        quantity/unit pass through untouched (no quantity-mutation path)."""
        stub = RetryStub(lambda hint, i: "Stair")
        flag = _oob_flag("Ladder", "SYM-1", qty=99999, unit="ea")
        flag["choices"] = ["Bollard", "Stair", "Ladder"]

        results = retry_flagged_items(
            [flag], vector_page, _registry(), stub, BudgetGuard(10.0)
        )

        rec = results[0]
        assert rec["resolution"] == "relabeled"
        assert rec["new_label"] == "Stair"
        assert rec["qty"] == 99999 and rec["unit"] == "ea"  # never mutated
        assert len(rec["retry_history"]) == 1
        # Schema enum = caller choices + the "unclear" decline sentinel.
        enum = stub.calls[0]["output_schema"]["properties"]["answer"]["enum"]
        assert enum == ["Bollard", "Stair", "Ladder", "unclear"]

    def test_engine_label_answer_matching_current_name_confirms(self, vector_page):
        stub = RetryStub(lambda hint, i: "Ladder")
        flag = _oob_flag("Ladder", "SYM-1")
        flag["choices"] = ["Bollard", "Stair", "Ladder"]

        results = retry_flagged_items(
            [flag], vector_page, _registry(), stub, BudgetGuard(10.0)
        )

        assert results[0]["resolution"] == "confirmed"
        assert "new_label" not in results[0]

    def test_engine_unclear_retries_then_unresolved(self, vector_page):
        """Unclear answers retry with a wider crop, bounded at the cap; the
        flag is kept with resolution 'unresolved' (flag, never suppress)."""
        stub = RetryStub(lambda hint, i: "unclear")

        results = retry_flagged_items(
            [_oob_flag("Ladder", "SYM-1")], vector_page, _registry(), stub,
            BudgetGuard(10.0),
        )

        rec = results[0]
        assert MAX_RETRIES_PER_ITEM == 2
        assert len(stub.calls) == 2
        assert len(rec["retry_history"]) == 2
        assert rec["resolution"] == "unresolved"

    def test_engine_deny_is_definite_single_attempt(self, vector_page):
        """'no' is a definite answer — flag kept unresolved, no second call."""
        stub = RetryStub(lambda hint, i: "no")

        results = retry_flagged_items(
            [_oob_flag("Ladder", "SYM-1")], vector_page, _registry(), stub,
            BudgetGuard(10.0),
        )

        assert len(stub.calls) == 1
        assert results[0]["resolution"] == "unresolved"
        assert results[0]["retry_history"][0]["answer"] == "no"

    def test_engine_no_geometry_anchor_skipped(self, vector_page):
        """Flags without a registry anchor are skipped with zero API calls
        and stay flagged unresolved."""
        stub = RetryStub(lambda hint, i: "yes")
        flags = [
            _oob_flag("Mystery Item", None),          # no candidate_id at all
            _oob_flag("Ghost", "SYM-UNKNOWN"),        # id not in registry
        ]

        results = retry_flagged_items(
            flags, vector_page, _registry(), stub, BudgetGuard(10.0)
        )

        assert stub.calls == []
        for rec in results:
            assert rec["resolution"] == "unresolved"
            assert rec["retry_history"] == []
            assert rec["retry_skipped"] == "no_geometry_anchor"

    def test_engine_budget_exhausted_skips_pass_entirely(self, vector_page):
        """Exhausted guard → zero calls; flags returned untouched."""
        stub = RetryStub(lambda hint, i: "yes")
        flags = [_oob_flag("Ladder", "SYM-1"), _oob_flag("Bollard", "SYM-2")]

        results = retry_flagged_items(
            flags, vector_page, _registry(), stub, BudgetGuard(0.0)
        )

        assert stub.calls == []
        assert results == [dict(f) for f in flags]
        for rec in results:
            assert "retry_history" not in rec and "resolution" not in rec

    def test_engine_budget_refused_charge_stops_mid_queue(self, vector_page):
        """A refused charge discards the answer and leaves the remaining
        flags untouched — the ledger only holds paid-and-accepted work."""
        stub = RetryStub(lambda hint, i: "yes")
        guard = BudgetGuard(0.015)  # 1st charge (0.01) fits, 2nd (0.02) refused
        flags = [
            _oob_flag("Ladder", "SYM-1"),
            _oob_flag("Bollard", "SYM-2"),
            _oob_flag("Column", "SYM-3"),
        ]

        results = retry_flagged_items(flags, vector_page, _registry(), stub, guard)

        assert len(stub.calls) == 2  # 2nd call completed but its charge was refused
        assert guard.spent_usd == pytest.approx(0.01)
        assert results[0]["resolution"] == "confirmed"
        # The refused-charge item: answer discarded, stays flagged.
        assert results[1]["resolution"] == "unresolved"
        assert results[1]["retry_history"] == []
        # Remaining flag untouched — never reached.
        assert "resolution" not in results[2] and "retry_history" not in results[2]


# ---------------------------------------------------------------------------
# Pipeline wiring — QuantityVerifier flags routed to the retry loop
# ---------------------------------------------------------------------------


def _make_vector_pdf(tmp_path: Path) -> Path:
    """A one-page PDF with enough vector paths to classify as vector."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(250):
        y = 10 + (i % 70) * 10.0
        x = 10 + (i // 70) * 140.0
        page.draw_line(fitz.Point(x, y), fitz.Point(x + 100, y))
    for bbox in SYM_BBOXES.values():
        page.draw_rect(fitz.Rect(bbox))
    path = tmp_path / "vector.pdf"
    doc.save(str(path))
    doc.close()
    return path


LEGEND_ROWS = [{"ITEM": "Bollard"}, {"ITEM": "Stair"}, {"ITEM": "Ladder"}]


def _canned_bundle(legend_rows=None) -> dict:
    schedules = []
    if legend_rows:
        schedules = [
            {
                "name": "LEGEND",
                "rows": list(legend_rows),
                "bbox_pt": (0.0, 0.0, 0.0, 0.0),
                "page_index": 0,
            }
        ]
    return {
        "symbol_groups": [],
        "walls": [],
        "wall_lf_by_class": {},
        "rooms": [],
        "viewports": [],
        "schedules": schedules,
        "footprint": None,
        "fpp": 0.05,
        "sheet_name": "A1",
        "_viewports_with_scales": [],
        "_main_plan_region": None,
        "_scale_result": None,
    }


class PipelineRetryStub(RetryStub):
    """RetryStub that also answers (ignores) any non-retry pass cleanly."""

    def __call__(self, screenshot_path, sheet_name="", pass_type="measure", **kwargs):
        if pass_type != "verify_retry":
            return {"components": [], "measurements": [], "_cost_usd": 0.0}
        return super().__call__(
            screenshot_path, sheet_name, pass_type=pass_type, **kwargs
        )


def _run_vector_sheet(
    monkeypatch,
    tmp_path,
    analyzer,
    fused_components,
    registry,
    legend_rows=None,
    settings=None,
):
    """Run the deterministic-first vector flow with canned bundle/fusion."""
    pdf = _make_vector_pdf(tmp_path)
    bundle = _canned_bundle(legend_rows)
    monkeypatch.setattr(
        TakeoffPipeline,
        "_deterministic_bundle",
        lambda self, *a, **k: {
            k2: (list(v) if isinstance(v, list) else v) for k2, v in bundle.items()
        },
    )
    monkeypatch.setattr(tp, "build_registry", lambda b: dict(registry))
    monkeypatch.setattr(
        tp,
        "fuse_sheet",
        lambda b, v, r: {
            "components": [dict(c) for c in fused_components],
            "measurements": [],
            "fusion_rejected": [],
        },
    )
    pipeline = TakeoffPipeline(analyzer=analyzer, settings=settings or RunSettings())
    return pipeline.run_sheet(
        image_path="A1.png",
        sheet_name="A1",
        sheet_type="floor_plan",
        pdf_path=str(pdf),
        page_index=0,
    )


def _oob_component(name: str, cid: str, qty=99999) -> dict:
    return {
        "name": name,
        "quantity": qty,
        "unit": "ea",
        "confidence": "high",
        "provenance": "geometry",
        "candidate_id": cid,
        "needs_review": False,
        "review_reason": "",
    }


class TestPipelineWiring:
    def test_out_of_band_retry_relabels_one_and_keeps_one_flagged(
        self, monkeypatch, tmp_path
    ):
        """Canned fused result with 2 out-of-band items; the stub relabels
        one and leaves one unresolved → final result has 1 renamed item with
        retry_history and 1 still-flagged item (plan test b)."""

        def answer(hint, i):
            if "Ladder" in hint:
                return "Stair"  # relabel: wrong semantics explained the flag
            return "unclear"  # Bollard: cannot settle → stays flagged

        stub = PipelineRetryStub(answer)
        result = _run_vector_sheet(
            monkeypatch,
            tmp_path,
            stub,
            fused_components=[
                _oob_component("Ladder", "SYM-1", qty=99999),
                _oob_component("Bollard", "SYM-2", qty=88888),
            ],
            registry=_registry(),
            legend_rows=LEGEND_ROWS,
        )

        components = {c["name"]: c for c in result["components"]}
        # Relabeled: renamed, quantity UNCHANGED, retry_history attached.
        assert "Stair" in components and "Ladder" not in components
        stair = components["Stair"]
        assert stair["quantity"] == 99999  # semantics only — never the number
        assert stair["resolution"] == "relabeled"
        assert len(stair["retry_history"]) == 1
        assert stair["needs_review"] is False

        # Unresolved: flag kept with the retry history attached.
        bollard = components["Bollard"]
        assert bollard["resolution"] == "unresolved"
        assert len(bollard["retry_history"]) == 2

        flags = {f["item"]: f for f in result["_verifier_flags"]}
        assert flags["Ladder"]["resolution"] == "relabeled"
        assert flags["Ladder"]["new_label"] == "Stair"
        assert flags["Bollard"]["resolution"] == "unresolved"
        # Full audit trail also persisted run-wide.
        assert len(result["_verify_retry"]) == 2
        # 1 relabel call + 2 bounded attempts for the unresolved item.
        assert len(stub.calls) == 3

    def test_ensemble_disagreement_flags_enter_retry_queue(
        self, monkeypatch, tmp_path
    ):
        """needs_review-from-vote components join the retry queue and a
        confirmation downgrades the flag to a note (plan test d)."""
        stub = PipelineRetryStub(lambda hint, i: "yes")
        result = _run_vector_sheet(
            monkeypatch,
            tmp_path,
            stub,
            fused_components=[
                {
                    "name": "Column",
                    "quantity": 10,
                    "unit": "ea",
                    "confidence": "low",
                    "provenance": "vision_ensemble",
                    "candidate_id": "SYM-3",
                    "needs_review": True,
                    "review_reason": "raster vision estimate (ensemble not unanimous)",
                },
            ],
            registry=_registry(),
        )

        assert len(stub.calls) == 1
        assert "Column" in (stub.calls[0]["user_hint"] or "")
        column = next(c for c in result["components"] if c["name"] == "Column")
        assert column["resolution"] == "confirmed"
        assert len(column["retry_history"]) == 1
        assert column["needs_review"] is False
        assert "confirmed by verify-retry" in column["review_reason"]
        assert result["_verify_retry"][0]["flag_type"] == "ensemble_disagreement"

    def test_budget_exhausted_skips_retry_items_stay_flagged(
        self, monkeypatch, tmp_path
    ):
        """Budget exhausted → the retry pass issues zero calls and the flags
        persist untouched (plan test c)."""
        stub = PipelineRetryStub(lambda hint, i: "yes")
        result = _run_vector_sheet(
            monkeypatch,
            tmp_path,
            stub,
            fused_components=[_oob_component("Ladder", "SYM-1")],
            registry=_registry(),
            legend_rows=LEGEND_ROWS,
            settings=RunSettings(budget_usd=0.0),
        )

        retry_calls = [c for c in stub.calls if c["pass_type"] == "verify_retry"]
        assert retry_calls == []
        # The flag is still there — never suppressed on budget exhaustion.
        flags = result["_verifier_flags"]
        assert len(flags) == 1 and flags[0]["item"] == "Ladder"
        assert "retry_history" not in flags[0]
        ladder = next(c for c in result["components"] if c["name"] == "Ladder")
        assert "retry_history" not in ladder

    def test_verify_retry_disabled_setting_skips_pass(self, monkeypatch, tmp_path):
        stub = PipelineRetryStub(lambda hint, i: "yes")
        result = _run_vector_sheet(
            monkeypatch,
            tmp_path,
            stub,
            fused_components=[_oob_component("Ladder", "SYM-1")],
            registry=_registry(),
            legend_rows=LEGEND_ROWS,
            settings=RunSettings(verify_retry_enabled=False),
        )

        assert [c for c in stub.calls if c["pass_type"] == "verify_retry"] == []
        assert "_verify_retry" not in result
        assert len(result["_verifier_flags"]) == 1  # flag intact

    def test_retry_flagged_items_is_module_level_patchable(
        self, monkeypatch, tmp_path
    ):
        """The pipeline calls the module-level name so tests can patch
        `takeoff_pipeline.retry_flagged_items` (patchability convention)."""
        seen = {}

        def spy(flags, page, registry, analyze_call, budget=None, **kwargs):
            seen["flags"] = [dict(f) for f in flags]
            seen["registry"] = dict(registry)
            seen["budget"] = budget
            return [dict(f) for f in flags]

        monkeypatch.setattr(tp, "retry_flagged_items", spy)
        stub = PipelineRetryStub(lambda hint, i: "yes")
        _run_vector_sheet(
            monkeypatch,
            tmp_path,
            stub,
            fused_components=[_oob_component("Ladder", "SYM-1")],
            registry=_registry(),
            legend_rows=LEGEND_ROWS,
        )

        assert seen["flags"], "the retry queue must reach retry_flagged_items"
        rec = seen["flags"][0]
        assert rec["flag_type"] == "out_of_band"
        assert rec["candidate_id"] == "SYM-1"
        # Symbol-anchored out-of-band flags carry the plausible legend labels.
        assert rec["choices"] == ["Bollard", "Stair", "Ladder"]
        assert seen["budget"] is not None
        assert "SYM-1" in seen["registry"]


# ---------------------------------------------------------------------------
# Source hygiene — the legacy env-flag stub is gone
# ---------------------------------------------------------------------------


def test_legacy_env_stub_gone_from_source():
    """The old env-flag logging stub must not survive anywhere under src/
    (the needle is built dynamically so this file never matches itself)."""
    needle = "ENABLE_" + "VERIFY_RETRY"
    src_root = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        str(path)
        for path in src_root.rglob("*.py")
        if needle in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], "legacy verify-retry env stub still present: %r" % offenders
