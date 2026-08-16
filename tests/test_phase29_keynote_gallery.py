"""A placed keynote is never a question for the paid model. ZERO API.

29-03 wired placed keynotes into the pipeline as ``KEY-<n>`` SymbolGroups
carrying the legend's own note text. Because they carry text they were not
caught by the anchor-absence restriction, so every one of them was marked on
the Set-of-Mark overlay and asked about in the paid symbol pass — measured on
Crow page 0: 9 of 41 candidates are keynotes.

That question has already been answered on the paper. The drafter printed the
name in the sheet's keynote legend, so asking spends tokens and image budget on
a known answer and lets a stochastic reply RENAME a deterministic count between
two identical runs. The anchor-absence restriction and this one sit at opposite
ends of the same axis: there the drawing says NOTHING (asking is asking for a
shape to be named, the 0.03-0.39 regime), here the drawing says it DEFINITIVELY.

What withholding must NOT do is lose the row. These tests pin both halves: the
keynote leaves the request, and it stays a counted, flagged, named candidate
everywhere else.
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.pipeline import takeoff_pipeline as tp  # noqa: E402
from bobbytailor.pipeline.takeoff_pipeline import (  # noqa: E402
    BudgetGuard,
    RunSettings,
    TakeoffPipeline,
)

NOTE_TEXT = "ACCESS LADDER, SEE DETAIL 3/A-501"
LEGEND_LABELS = ["Column", "Ladder", "Handrail"]


# ─────────────────────────────────────────────────────────────────────────────
# Harness — the vector flow with the page-reading seams stubbed.
#
# `_deterministic_bundle` is replaced by a hand-built bundle so the candidate
# set under test is exact, and `_render_overlay` by a marker recorder so the
# set actually PRESENTED to the model is observable without rendering a page.
# No network, no API key, no PDF fixture required.
# ─────────────────────────────────────────────────────────────────────────────


class _Img:
    """An overlay image stand-in carrying the ids drawn on it."""

    def __init__(self, ids):
        self.info = {"overlay_ids": list(ids)}


def _group(cid, count, texts, bbox=(10.0, 10.0, 30.0, 30.0)):
    return {
        "candidate_id": cid,
        "count": count,
        "signature_hash": "sig-%s" % cid,
        "instance_bboxes_pt": [tuple(bbox)],
        "representative_bbox_pt": tuple(bbox),
        "bbox_size_ft": (1.0, 1.0),
        "contained_texts": list(texts),
        "confidence": "high",
        "needs_review": True,
    }


def _bundle(groups, anchors=None):
    return {
        "symbol_groups": list(groups),
        # Walls/rooms/viewports are deliberately empty: the semantic pass then
        # never runs and the only request this harness can produce is the
        # symbol one under test.
        "walls": [],
        "wall_lf_by_class": {},
        "rooms": [],
        "viewports": [],
        "schedules": [],
        "footprint": None,
        "fpp": 40.0 / 72.0,
        "sheet_name": "A-101",
        "candidate_anchors": dict(anchors or {}),
        "mask_rects": [],
        "_viewports_with_scales": [],
        "_main_plan_region": None,
        "_scale_result": None,
    }


class _Recorder:
    """Records the candidates marked, and the ids the request's schema asks."""

    def __init__(self):
        self.marked = None
        self.asked = None
        self.pass_types: list = []

    # patched in for takeoff_pipeline._render_overlay
    def render(self, page, candidates, kind_colors=None, anchors=None):
        self.marked = dict(candidates)
        return [_Img(candidates.keys())]

    # the analyzer stub — grounded, answers off the schema's own enums
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
            "_cost_usd": 0.0,
            "_tokens_in": 1,
            "_tokens_out": 1,
            "_model_used": "stub",
        }
        if pass_type == "symbol_gallery":
            items = output_schema["properties"]["matches"]["items"]["properties"]
            self.asked = list(items["symbol_id"]["enum"])
            labels = items["label"]["enum"]
            # A distinct label per candidate, off the schema's own enum: two
            # clusters answered the same name fuse into ONE line item, which
            # would hide a candidate that stopped being asked about.
            answer = {
                "matches": [
                    {
                        "symbol_id": sid,
                        "label": labels[i % len(labels)],
                        "confidence": "medium",
                    }
                    for i, sid in enumerate(self.asked)
                ],
            }
            answer.update(meta)
            return answer
        answer = {"components": [], "measurements": []}
        answer.update(meta)
        return answer


def _run(monkeypatch, bundle):
    """Drive the vector flow over *bundle*; return (recorder, fused result)."""
    rec = _Recorder()
    monkeypatch.setattr(tp, "_render_overlay", rec.render)
    monkeypatch.setattr(
        TakeoffPipeline, "_deterministic_bundle",
        lambda self, *a, **k: bundle,
    )
    pipeline = TakeoffPipeline(
        analyzer=rec,
        settings=RunSettings(verify_retry_enabled=False),
    )
    pipeline._project_vocab_labels = list(LEGEND_LABELS)
    doc = fitz.open()
    page = doc.new_page()
    result = pipeline._run_sheet_vector(
        page=page,
        doc=doc,
        image_path="A-101.png",
        sheet_name="A-101",
        resolved_type="floor_plan",
        pdf_path="A-101.pdf",
        page_index=0,
        guard=BudgetGuard(max_usd=1.0),
    )
    return rec, result


# ─────────────────────────────────────────────────────────────────────────────
# 1. The keynote leaves the request.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_keynote_is_not_marked_and_not_asked_about(monkeypatch):
    """KEY-9 is neither drawn on the overlay nor named in the schema's enum.

    Withheld at the point of ASKING, like the unanchored restriction — not
    asked and then discarded. Not asking is what makes it cheaper, and an
    answer that is never received cannot flip a name.
    """
    groups = [
        _group("SYM-1", 12, ["COL"]),
        _group("KEY-9", 7, [NOTE_TEXT], bbox=(40.0, 40.0, 60.0, 60.0)),
    ]
    anchors = {
        "SYM-1": {"anchor_text": "COL", "anchor_kind": "word"},
        "KEY-9": {"anchor_text": "LADDER", "anchor_kind": "word"},
    }
    rec, _ = _run(monkeypatch, _bundle(groups, anchors))

    assert rec.marked is not None, "no overlay was rendered — nothing was asked"
    assert "KEY-9" not in rec.marked, (
        "the keynote was marked on the paid overlay: %r" % sorted(rec.marked)
    )
    assert rec.asked is not None, "the symbol pass never ran"
    assert "KEY-9" not in rec.asked, (
        "the keynote was asked about: %r" % (rec.asked,)
    )
    assert not [c for c in rec.asked if c.startswith("KEY-")]


# ─────────────────────────────────────────────────────────────────────────────
# 2. The row survives the withholding — the whole safety case.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_withheld_keynote_is_still_a_counted_named_candidate(monkeypatch):
    """Not asking is not deleting.

    The group stays in ``symbol_groups`` with its note text, and fusion still
    publishes it — named from the drawing's own printed text, quantity from the
    deterministic placement count, and flagged. The name never comes from the
    candidate id.
    """
    groups = [
        _group("SYM-1", 12, ["COL"]),
        _group("KEY-9", 7, [NOTE_TEXT], bbox=(40.0, 40.0, 60.0, 60.0)),
    ]
    anchors = {"SYM-1": {"anchor_text": "COL", "anchor_kind": "word"}}
    bundle = _bundle(groups, anchors)
    _, result = _run(monkeypatch, bundle)

    kept = {g["candidate_id"]: g for g in bundle["symbol_groups"]}
    assert "KEY-9" in kept, "the keynote was dropped from the bundle"
    assert kept["KEY-9"]["contained_texts"] == [NOTE_TEXT]
    assert kept["KEY-9"]["count"] == 7

    published = [
        c for c in result.get("components") or []
        if c.get("candidate_id") == "KEY-9"
    ]
    assert published, (
        "the keynote produced no line item and no name: %r"
        % [c.get("candidate_id") for c in result.get("components") or []]
    )
    comp = published[0]
    assert comp["quantity"] == 7
    assert comp["name"] == NOTE_TEXT, comp["name"]
    assert comp["name"] != "KEY-9"
    assert comp.get("name_source") == "contained_text"
    assert comp.get("needs_review") is True


def test_a_keynote_the_anchor_pass_named_publishes_from_the_anchor(monkeypatch):
    """The other admissible source, with the same outcome: still named.

    When 24-01 recorded an anchor for the keynote, the naming ladder reads it
    (``text_anchor``) instead of the cluster's own text. Both branches are the
    drawing's printed words; neither needs the model. This is the branch the
    restriction actually changes, since a keynote with a RECORDED ABSENCE was
    already withheld by the anchor rule.
    """
    groups = [
        _group("SYM-1", 12, ["COL"]),
        _group("KEY-9", 7, [NOTE_TEXT], bbox=(40.0, 40.0, 60.0, 60.0)),
    ]
    anchors = {
        "SYM-1": {"anchor_text": "COL", "anchor_kind": "word"},
        "KEY-9": {
            "anchor_text": "ACCESS LADDER",
            "anchor_kind": "word",
            "anchor_dist_pt": 4.0,
            "anchor_source": "plan_text",
        },
    }
    _, result = _run(monkeypatch, _bundle(groups, anchors))

    comp = next(
        c for c in result.get("components") or []
        if c.get("candidate_id") == "KEY-9"
    )
    assert comp["name"] == "ACCESS LADDER"
    assert comp.get("name_source") == "text_anchor"
    assert comp["quantity"] == 7
    assert comp.get("needs_review") is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. The gallery itself is untouched.
# ─────────────────────────────────────────────────────────────────────────────


def test_an_anchored_symbol_group_is_still_presented(monkeypatch):
    """The restriction is keyed on the namespace, not on carrying text.

    A SYM-n cluster the drawing names is exactly what the paid pass exists for
    and must still be marked and asked about.
    """
    groups = [
        _group("SYM-1", 12, ["COL"]),
        _group("SYM-2", 4, [], bbox=(70.0, 70.0, 90.0, 90.0)),
        _group("KEY-9", 7, [NOTE_TEXT], bbox=(40.0, 40.0, 60.0, 60.0)),
    ]
    anchors = {
        "SYM-1": {"anchor_text": "COL", "anchor_kind": "word"},
        # A RECORDED ABSENCE — still excluded, by the older rule.
        "SYM-2": {"anchor_text": None},
        "KEY-9": {"anchor_text": "LADDER", "anchor_kind": "word"},
    }
    rec, _ = _run(monkeypatch, _bundle(groups, anchors))

    assert "SYM-1" in rec.marked, "the anchored cluster stopped being marked"
    assert rec.asked == ["SYM-1"], rec.asked


def test_a_page_with_no_keynotes_asks_exactly_what_it_asked_before(monkeypatch):
    """No keynote on the sheet ⇒ the request is the one the old code built.

    The restriction is a filter over a namespace this page does not mint, so
    the marked set, the asked set and the fused names are the pre-29-08 ones.
    """
    groups = [
        _group("SYM-1", 12, ["COL"]),
        _group("SYM-2", 4, ["BOL"], bbox=(70.0, 70.0, 90.0, 90.0)),
        _group("SYM-3", 2, [], bbox=(95.0, 95.0, 99.0, 99.0)),
    ]
    anchors = {
        "SYM-1": {"anchor_text": "COL", "anchor_kind": "word"},
        "SYM-2": {"anchor_text": "BOL", "anchor_kind": "word"},
        "SYM-3": {"anchor_text": None},
    }
    rec, result = _run(monkeypatch, _bundle(groups, anchors))

    assert sorted(rec.marked) == ["SYM-1", "SYM-2"], sorted(rec.marked)
    assert sorted(rec.asked) == ["SYM-1", "SYM-2"], rec.asked
    quantities = {
        c.get("candidate_id"): c.get("quantity")
        for c in result.get("components") or []
    }
    assert quantities.get("SYM-1") == 12
    assert quantities.get("SYM-2") == 4


# ─────────────────────────────────────────────────────────────────────────────
# 4. One namespace, one spelling.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_minted_id_and_the_withheld_prefix_are_the_same_string():
    """The adapter mints the namespace the gallery restriction withholds.

    Two readers, one constant: a keynote id spelled differently in either place
    would silently put keynotes back into the paid request.
    """

    class _Callout:
        number = "9"
        header = "KEYNOTES"
        note_text = NOTE_TEXT
        callout_count = 7
        instance_bboxes_pt = [(10.0, 10.0, 30.0, 30.0)]

    group = tp._keynote_callout_as_symbol_group(_Callout(), 40.0 / 72.0)
    assert group.candidate_id.startswith(tp._KEYNOTE_CANDIDATE_PREFIX)
    assert group.candidate_id == "KEY-9"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
