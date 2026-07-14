"""Verify-retry arbitration tests (21-14, V3-ACC-05). All offline — stubbed
analyzers only, ZERO real API calls.

Engine tests (``-k engine``) pin the bounded/grounded/budget-charged
contract of ``retry_flagged_items``; pipeline tests pin the takeoff_pipeline
wiring (queue construction, resolution merge-back, flag-never-suppress) and
the removal of the old ``ENABLE_VERIFY_RETRY`` env stub from source.
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
