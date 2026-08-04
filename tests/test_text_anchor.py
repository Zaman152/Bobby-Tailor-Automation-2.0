"""Contract for the nearest-plan-text anchor primitive (V4-DET-01, plan 24-01).

ZERO API. Every test here runs free: synthetic word lists for the unit
contract, and the real Crow PDF (skipped when absent) for the committed
measurement baseline.

Two disciplines inherited from the phase-23 gates and enforced here:

* **A check either ASSERTS or SKIPS** (``test_phase23_acceptance.py`` rule 3).
  Nothing in this module may pass because its fixture was missing.
* **Assert SHAPES, POSITIONS and SETS — never a scored total**
  (``test_four_set_coverage.py``).  Nothing here moves the 56-mark bollard
  cluster toward the 28 in the human take-off, or the 136-mark cluster toward
  its 132.  Both apparent hits were PROVEN coincidental (collinear dimension
  ticks at ``yspan=0``; ``_dedup_colocated_count(56) -> 56``) in ground truth
  sections 10 and 11.0.  Phase 25 owns whether those counts are right; this
  phase owns only whether they can be NAMED.

The paid-script and credential names this gate greps for are assembled from
fragments below rather than spelled out, because the phase's own acceptance
one-liner greps THIS FILE for those literals and must find none.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.deterministic.text_anchor import (  # noqa: E402
    ANCHOR_RADIUS_PT,
    ANCHOR_RADIUS_TEXT_HEIGHTS,
    anchor_record,
    anchors_for_candidates,
    box_distance_pt,
    nearest_anchor,
    page_radius_pt,
    page_words,
)

MODULE_PATH = ROOT / "src" / "bobbytailor" / "deterministic" / "text_anchor.py"

# Assembled, never spelled — see the module docstring.
FORBIDDEN_CREDENTIAL = "ANTHROPIC" + "_API_KEY"
FORBIDDEN_PAID = (
    FORBIDDEN_CREDENTIAL,
    "accuracy" + "_gate",
    "vision_only" + "_benchmark",
    "gold" + "en_convergence",
    "gold" + "en",
)

ANCHOR_KEYS = {
    "candidate_id",
    "anchor_text",
    "anchor_kind",
    "anchor_dist_pt",
    "anchor_source",
    "ambiguity_reason",
}


# ---------------------------------------------------------------------------
# Synthetic page — the unit contract is provable with no PDF at all.
# ---------------------------------------------------------------------------


class FakePage:
    """The two ``get_text`` shapes this module reads, and nothing else."""

    number = 0

    def __init__(self, words, lines=None):
        # PyMuPDF's own 8-tuple shape, so the harvest is exercised as it ships.
        self._words = [
            (w[0], w[1], w[2], w[3], w[4], 0, 0, i) for i, w in enumerate(words)
        ]
        self._lines = list(lines or [])

    def get_text(self, kind):
        if kind == "words":
            return list(self._words)
        if kind == "dict":
            return {"blocks": [{"lines": list(self._lines)}]}
        raise ValueError("unexpected get_text(%r)" % kind)


def _line(text, bbox, text_dir=(1.0, 0.0)):
    return {"dir": text_dir, "bbox": tuple(bbox), "spans": [{"text": text}]}


def _word(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text)


# ---------------------------------------------------------------------------
# Behaviour 1 — a word inside the bbox is a contained anchor at distance zero.
# ---------------------------------------------------------------------------


def test_a_word_inside_the_bbox_is_a_contained_anchor():
    words = [_word(105.0, 102.0, 125.0, 112.0, "PUMP")]
    rec = nearest_anchor((100.0, 100.0, 140.0, 120.0), words, candidate_id="SYM-1")
    assert rec["anchor_text"] == "PUMP"
    assert rec["anchor_kind"] == "contained"
    assert rec["anchor_dist_pt"] == 0.0
    assert rec["anchor_source"] == "page_words"
    assert rec["candidate_id"] == "SYM-1"


def test_a_contained_word_outranks_a_nearer_looking_outside_word():
    """Precedence is contained-first, not smallest-number-first."""
    words = [
        _word(141.0, 105.0, 150.0, 115.0, "OUTSIDE"),  # 1 pt away, but outside
        _word(105.0, 102.0, 125.0, 112.0, "INSIDE"),
    ]
    rec = nearest_anchor((100.0, 100.0, 140.0, 120.0), words, radius_pt=40.0)
    assert rec["anchor_text"] == "INSIDE"
    assert rec["anchor_kind"] == "contained"


# ---------------------------------------------------------------------------
# Behaviour 2 — a masked word is never the anchor, however near it sits.
# ---------------------------------------------------------------------------


def test_a_masked_word_is_never_the_anchor():
    """A door-schedule tag column must not become a plan-body anchor (T-24-02)."""
    words = [
        _word(142.0, 105.0, 160.0, 115.0, "SCHEDULE-TAG"),  # nearest, but masked
        _word(200.0, 105.0, 240.0, 115.0, "BOLLARD"),
    ]
    mask = [(140.0, 100.0, 180.0, 130.0)]
    rec = nearest_anchor(
        (100.0, 100.0, 140.0, 120.0), words, mask_rects=mask, radius_pt=200.0
    )
    assert rec["anchor_text"] == "BOLLARD"
    assert rec["anchor_kind"] == "nearest_word"


def test_masking_can_leave_a_candidate_with_no_anchor_at_all():
    words = [_word(142.0, 105.0, 160.0, 115.0, "SCHEDULE-TAG")]
    mask = [(140.0, 100.0, 180.0, 130.0)]
    rec = nearest_anchor(
        (100.0, 100.0, 140.0, 120.0), words, mask_rects=mask, radius_pt=200.0
    )
    assert rec["anchor_text"] is None
    assert rec["anchor_kind"] is None


# ---------------------------------------------------------------------------
# Behaviour 3 — no text in range records an ABSENCE, never a substitute.
# ---------------------------------------------------------------------------


def test_no_text_in_range_records_an_absence_not_a_guess():
    words = [_word(1000.0, 1000.0, 1040.0, 1010.0, "FAR AWAY")]
    rec = nearest_anchor((100.0, 100.0, 140.0, 120.0), words, radius_pt=38.0)
    assert rec["anchor_text"] is None
    assert rec["anchor_kind"] is None
    assert rec["anchor_dist_pt"] is None
    assert rec["anchor_source"] is None
    # The absence is not filled from the candidate's own id or shape.
    assert "SYM" not in json.dumps(rec)


def test_an_empty_page_yields_an_absence_for_every_candidate():
    page = FakePage(words=[], lines=[])
    out = anchors_for_candidates(page, {"SYM-1": (10.0, 10.0, 20.0, 20.0)})
    assert set(out) == {"SYM-1"}
    assert out["SYM-1"]["anchor_text"] is None


# ---------------------------------------------------------------------------
# Behaviour 4 — ties resolve identically on every call (document order).
# ---------------------------------------------------------------------------


def test_equal_distance_words_resolve_by_document_order_every_call():
    box = (100.0, 100.0, 140.0, 120.0)
    words = [
        _word(150.0, 100.0, 170.0, 120.0, "RIGHT"),  # 10 pt right
        _word(70.0, 100.0, 90.0, 120.0, "LEFT"),  # 10 pt left — same distance
    ]
    first = nearest_anchor(box, words, radius_pt=38.0)
    assert first["anchor_dist_pt"] == 10.0
    assert first["anchor_text"] == "RIGHT"  # earlier in document order
    for _ in range(5):
        assert nearest_anchor(box, words, radius_pt=38.0) == first
    # Reversing document order reverses the winner — proving the tie really is
    # broken by order and not by geometry luck.
    flipped = nearest_anchor(box, list(reversed(words)), radius_pt=38.0)
    assert flipped["anchor_text"] == "LEFT"


def test_the_nearest_word_wins_when_distances_differ():
    box = (100.0, 100.0, 140.0, 120.0)
    words = [
        _word(160.0, 100.0, 180.0, 120.0, "FURTHER"),
        _word(145.0, 100.0, 165.0, 120.0, "NEARER"),
    ]
    rec = nearest_anchor(box, words, radius_pt=38.0)
    assert rec["anchor_text"] == "NEARER"
    assert rec["anchor_dist_pt"] == 5.0


# ---------------------------------------------------------------------------
# Behaviour 5 — a two-token tag is ONE anchor, not two words.
# ---------------------------------------------------------------------------


def test_a_paired_tag_is_returned_as_one_anchor():
    box = (60.0, 100.0, 95.0, 110.0)
    tag_pairs = [_word(100.0, 100.0, 118.0, 110.0, "B 1")]
    rec = nearest_anchor(box, [], tag_pairs=tag_pairs, radius_pt=38.0)
    assert rec["anchor_text"] == "B 1"
    assert rec["anchor_kind"] == "tag"
    assert rec["anchor_source"] == "tag_pairing"
    assert rec["anchor_dist_pt"] == 5.0


def test_a_page_printed_tag_pairs_through_sp6_and_hides_its_own_tokens():
    """The SP-6 pairer runs on the page, and 'B' alone never becomes an anchor."""
    words = [_word(100.0, 100.0, 108.0, 110.0, "B"), _word(112.0, 100.0, 118.0, 110.0, "1")]
    lines = [
        _line("B", (100.0, 100.0, 108.0, 110.0)),
        _line("1", (112.0, 100.0, 118.0, 110.0)),
    ]
    page = FakePage(words, lines)
    out = anchors_for_candidates(page, {"SYM-1": (60.0, 100.0, 95.0, 110.0)})
    rec = out["SYM-1"]
    assert rec["anchor_text"] == "B 1"
    assert rec["anchor_kind"] == "tag"
    assert rec["anchor_source"] == "tag_pairing"


def test_a_rotated_sheet_pairs_the_same_tag():
    """SP-6's whole point: a y-stacked reader returns nothing on dir=(0,-1)."""
    words = [
        _word(100.0, 100.0, 110.0, 118.0, "B"),
        _word(100.0, 80.0, 110.0, 96.0, "1"),
    ]
    lines = [
        _line("B", (100.0, 100.0, 110.0, 118.0), text_dir=(0.0, -1.0)),
        _line("1", (100.0, 80.0, 110.0, 96.0), text_dir=(0.0, -1.0)),
    ]
    page = FakePage(words, lines)
    out = anchors_for_candidates(page, {"SYM-1": (100.0, 122.0, 110.0, 132.0)})
    assert out["SYM-1"]["anchor_kind"] == "tag"
    assert out["SYM-1"]["anchor_text"] == "B 1"


# ---------------------------------------------------------------------------
# Behaviour 6 — a contested anchor leaves BOTH candidates unanchored.
# ---------------------------------------------------------------------------


def test_a_contested_anchor_leaves_both_candidates_unanchored():
    """SP-7c bind_or_flag: never round-robin a name to whoever was scanned first."""
    words = [_word(100.0, 100.0, 140.0, 110.0, "PUMP")]
    page = FakePage(words, [_line("PUMP", (100.0, 100.0, 140.0, 110.0))])
    out = anchors_for_candidates(
        page,
        {
            "SYM-1": (80.0, 100.0, 90.0, 110.0),  # 10 pt left of PUMP
            "SYM-2": (150.0, 100.0, 160.0, 110.0),  # 10 pt right of PUMP
        },
        radius_pt=38.0,
    )
    for cid in ("SYM-1", "SYM-2"):
        assert out[cid]["anchor_text"] is None, cid
        assert out[cid]["anchor_kind"] is None, cid
        assert "PUMP" in out[cid]["ambiguity_reason"], cid
        assert "SYM-1" in out[cid]["ambiguity_reason"], cid
        assert "SYM-2" in out[cid]["ambiguity_reason"], cid


def test_an_uncontested_anchor_still_binds_when_a_neighbour_has_its_own():
    words = [
        _word(100.0, 100.0, 140.0, 110.0, "PUMP"),
        _word(200.0, 100.0, 240.0, 110.0, "TANK"),
    ]
    page = FakePage(
        words,
        [
            _line("PUMP", (100.0, 100.0, 140.0, 110.0)),
            _line("TANK", (200.0, 100.0, 240.0, 110.0)),
        ],
    )
    out = anchors_for_candidates(
        page,
        {
            "SYM-1": (80.0, 100.0, 90.0, 110.0),
            "SYM-2": (250.0, 100.0, 260.0, 110.0),
        },
        radius_pt=38.0,
    )
    assert out["SYM-1"]["anchor_text"] == "PUMP"
    assert out["SYM-2"]["anchor_text"] == "TANK"


# ---------------------------------------------------------------------------
# Behaviour 7 — records are plain, JSON-serialisable dicts.
# ---------------------------------------------------------------------------


def test_anchor_records_are_plain_json_serialisable_dicts():
    rec = anchor_record("SYM-1", "B 1", "tag", 4.25, "tag_pairing")
    assert isinstance(rec, dict)
    assert set(rec) == ANCHOR_KEYS
    assert json.loads(json.dumps(rec)) == rec
    absent = anchor_record("SYM-2", None, None, None, None, "contested")
    assert json.loads(json.dumps(absent)) == absent
    assert absent["ambiguity_reason"] == "contested"


# ---------------------------------------------------------------------------
# The radius — a POSITIONAL rule, never an accuracy dial.
# ---------------------------------------------------------------------------


def test_the_radius_bounds_the_search_by_position():
    """Hand-provable: 20 pt away is in at r=38, out at r=10."""
    box = (100.0, 100.0, 140.0, 120.0)
    words = [_word(160.0, 100.0, 180.0, 120.0, "LABEL")]
    assert box_distance_pt(box, (160.0, 100.0, 180.0, 120.0)) == 20.0
    assert nearest_anchor(box, words, radius_pt=38.0)["anchor_text"] == "LABEL"
    assert nearest_anchor(box, words, radius_pt=10.0)["anchor_text"] is None


def test_the_radius_is_expressed_in_text_heights_of_the_page_it_reads():
    """The same rule gives a different radius on a differently-drafted sheet.

    Measured free this session over ``page.get_text("words")``: Crow 9.56 pt,
    Moxy 9.64, Chelsea 7.56, Bob's 26.41 — a 3.5x spread on the identical
    3024 x 2160 pt sheet.  A single absolute constant is ~5 text-heights of
    reach on one set and ~1.4 on another, which is the one-plan-set defect
    ``test_four_set_coverage.py`` exists to catch.
    """
    small = [_word(0.0, 0.0, 10.0, 8.0, "A"), _word(0.0, 20.0, 10.0, 28.0, "B")]
    large = [_word(0.0, 0.0, 10.0, 24.0, "A"), _word(0.0, 40.0, 10.0, 64.0, "B")]
    assert page_radius_pt(small) == pytest.approx(8.0 * ANCHOR_RADIUS_TEXT_HEIGHTS)
    assert page_radius_pt(large) == pytest.approx(24.0 * ANCHOR_RADIUS_TEXT_HEIGHTS)
    # A page with no measurable text falls back to the absolute constant.
    assert page_radius_pt([]) == ANCHOR_RADIUS_PT


def test_the_fallback_radius_is_four_nominal_text_heights():
    assert ANCHOR_RADIUS_TEXT_HEIGHTS == 4.0
    assert ANCHOR_RADIUS_PT == pytest.approx(38.0)


# ---------------------------------------------------------------------------
# Determinism and shape of the page-scale entry point.
# ---------------------------------------------------------------------------


def test_anchors_for_candidates_is_byte_identical_on_repeat():
    words = [
        _word(100.0, 100.0, 140.0, 110.0, "PUMP"),
        _word(200.0, 100.0, 240.0, 110.0, "TANK"),
        _word(300.0, 100.0, 340.0, 110.0, "BOLLARD"),
    ]
    lines = [_line(w[4], w[:4]) for w in words]
    page = FakePage(words, lines)
    candidates = {
        "SYM-3": (150.0, 100.0, 160.0, 110.0),
        "SYM-1": (80.0, 100.0, 90.0, 110.0),
        "SYM-2": (345.0, 100.0, 355.0, 110.0),
    }
    first = anchors_for_candidates(page, candidates)
    second = anchors_for_candidates(page, candidates)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert set(first) == set(candidates)


def test_every_candidate_gets_exactly_one_well_formed_record():
    page = FakePage([_word(0.0, 0.0, 10.0, 10.0, "X")], [_line("X", (0, 0, 10, 10))])
    candidates = {"SYM-1": (500.0, 500.0, 510.0, 510.0), "ROOM-1": (0.0, 0.0, 10.0, 10.0)}
    out = anchors_for_candidates(page, candidates)
    assert set(out) == set(candidates)
    for cid, rec in out.items():
        assert set(rec) == ANCHOR_KEYS
        assert rec["candidate_id"] == cid


def test_a_candidate_with_an_unusable_bbox_is_an_absence_not_a_crash():
    page = FakePage([_word(0.0, 0.0, 10.0, 10.0, "X")], [_line("X", (0, 0, 10, 10))])
    out = anchors_for_candidates(page, {"WALL-TC1": ()})
    assert out["WALL-TC1"]["anchor_text"] is None


def test_page_words_survives_an_unreadable_text_layer():
    class Broken:
        number = 0

        def get_text(self, kind):
            raise RuntimeError("corrupt text layer")

    assert page_words(Broken()) == []
    assert anchors_for_candidates(Broken(), {"SYM-1": (0.0, 0.0, 1.0, 1.0)})[
        "SYM-1"
    ]["anchor_text"] is None


# ---------------------------------------------------------------------------
# The committed Crow baseline — a measurement, not an assumption.
#
# PROVENANCE. The population figures quoted here were measured by a ZERO-API
# deterministic-bundle probe over all four Crow sheets during Phase 24 planning
# (2026-08-05), and re-measured by this plan's execution:
#
#     107 symbol groups across the four sheets
#      81 carry NO ``contained_texts`` at all
#      26 carry ``contained_texts`` that are 100% drafting noise
#       0 carry a ``contained_texts`` that is a genuine object name
#
# That is the committed answer to 24-RESEARCH Open Question #4 — *"does the
# bollard cluster have a text anchor at all?"* — and the answer is **NO**.
# The consequence is load-bearing and must not be softened: the
# ``contained_texts`` branch of the anchor ladder contributes NOTHING on the
# mission's primary plan set, so the nearest-non-masked-word query is not an
# enhancement to the ladder, it IS the ladder.
#
# The tests below assert the SHAPE of that finding on page 0 (the two
# largest-count clusters carry no contained text), never a count. The
# largest is SYM-1 at 1.0 x 0.4 ft; the second is SYM-2 at 0.8 x 0.87 ft — the
# bollard cluster. NEITHER is asserted toward the number in the human take-off
# and NEITHER is touched: ground truth section 10 proved the larger cluster's
# instances are collinear dimension ticks (``yspan=0``) and section 11.0 proved
# ``_dedup_colocated_count`` leaves the bollard cluster unchanged. Both
# apparent hits are coincidences. Phase 25 owns detection; this phase owns
# only naming and flagging.
# ---------------------------------------------------------------------------

CROW_PDF = ROOT / "uploads" / "Crow - Cass White Road-Plans.pdf"


def _field(obj, name, default=None):
    """Read a field from a dataclass-like object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@pytest.fixture(scope="module")
def crow_page_0():
    """Page 0's real deterministic bundle. SKIPS when the PDF is absent.

    Follows ``test_four_set_coverage.py:86`` — a check either ASSERTS or SKIPS;
    none of the checks below may pass for having looked at nothing.
    """
    if not CROW_PDF.exists():
        pytest.skip("fixture PDF %r is not present in uploads/" % CROW_PDF.name)
    fitz = pytest.importorskip("fitz")
    from bobbytailor.pipeline.takeoff_pipeline import (  # noqa: PLC0415
        _MASK_VIEWPORT_KINDS,
        TakeoffPipeline,
    )

    doc = fitz.open(str(CROW_PDF))
    pipeline = TakeoffPipeline(analyzer=lambda *a, **k: {})
    bundle = pipeline._deterministic_bundle(
        doc[0], doc, str(CROW_PDF), 0, "crow-p0", "floor_plan"
    )
    masks = [
        b for b in (_field(s, "bbox_pt", None) for s in bundle.get("schedules") or []) if b
    ]
    masks += [
        vp.bbox_pt
        for vp in bundle.get("viewports") or []
        if vp.kind in _MASK_VIEWPORT_KINDS
    ]
    try:
        yield doc[0], bundle, pipeline, masks
    finally:
        doc.close()


def test_the_contained_text_branch_is_empty_on_the_crow_plan_set(crow_page_0):
    """24-RESEARCH Open Question #4, answered NO and committed.

    The two largest symbol clusters on Crow page 0 — the one the pipeline
    coincidentally reads as columns, and the bollard cluster — carry no
    contained text whatsoever. Neither can be named from text inside its own
    box, so neither can be named at all without the radius query.
    """
    _page, bundle, _pipeline, _masks = crow_page_0
    groups = sorted(
        bundle.get("symbol_groups") or [],
        key=lambda g: (-int(_field(g, "count", 0) or 0), str(_field(g, "candidate_id", ""))),
    )
    assert len(groups) >= 2, "page 0 must yield at least two symbol clusters"
    for group in groups[:2]:
        texts = [
            t for t in (_field(group, "contained_texts", []) or []) if str(t).strip()
        ]
        assert texts == [], (
            "%s carries contained text %r — the finding this test commits is "
            "that it carries NONE. Re-measure before editing this assertion."
            % (_field(group, "candidate_id", "?"), texts)
        )


def test_every_crow_candidate_carries_one_well_formed_anchor_record(crow_page_0, capsys):
    """Coverage is REPORTED, never required.

    There is deliberately no minimum number of non-None anchors asserted here.
    A floor would create pressure to widen the radius until the floor is met,
    and that is the tuning trap 24-RESEARCH pitfall 1 forbids. How many
    candidates the drawing happens to label is an outcome of the drawing.
    """
    _page, bundle, pipeline, _masks = crow_page_0
    anchors = bundle.get("candidate_anchors")
    assert isinstance(anchors, dict), "the bundle must emit candidate_anchors"
    expected = pipeline._anchor_candidate_map(bundle)
    assert set(anchors) == set(expected), "one record per candidate, no more, no fewer"
    assert anchors, "page 0 carries candidates, so it must carry anchor records"

    split = {}
    for cid, rec in sorted(anchors.items()):
        assert set(rec) == ANCHOR_KEYS, cid
        assert rec["candidate_id"] == cid
        assert rec["anchor_kind"] in (None, "contained", "tag", "nearest_word"), cid
        if rec["anchor_text"] is None:
            assert rec["anchor_kind"] is None, cid
            assert rec["anchor_dist_pt"] is None, cid
            assert rec["anchor_source"] is None, cid
        else:
            assert rec["anchor_source"] in ("page_words", "tag_pairing"), cid
            assert rec["anchor_dist_pt"] >= 0.0, cid
            assert rec["ambiguity_reason"] == "", cid
        split[rec["anchor_kind"]] = split.get(rec["anchor_kind"], 0) + 1
        json.dumps(rec)  # records must survive into takeoff.json unaided

    contested = sum(1 for r in anchors.values() if r["ambiguity_reason"])
    with capsys.disabled():
        print(
            "\n[24-01] Crow page 0 anchor coverage (reported, not required): "
            "%d candidates, split by kind %r, %d withdrawn as contested"
            % (len(anchors), split, contested)
        )


def test_anchors_over_the_real_page_are_byte_identical_on_repeat(crow_page_0):
    """Determinism on a real drawing, not only on a synthetic word list."""
    page, bundle, pipeline, masks = crow_page_0
    candidates = pipeline._anchor_candidate_map(bundle)
    first = anchors_for_candidates(page, candidates, mask_rects=masks)
    second = anchors_for_candidates(page, candidates, mask_rects=masks)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    # And the pipeline's own emitted records are the same computation, so the
    # bundle key is not a second, drifting implementation.
    assert first == bundle["candidate_anchors"]


def test_a_masked_region_supplies_no_anchor_on_the_real_page(crow_page_0):
    """T-24-02 on real geometry: nothing inside a mask is ever an anchor."""
    page, bundle, pipeline, masks = crow_page_0
    if not masks:
        pytest.skip("page 0 carries no schedule or title-block mask to test")
    from bobbytailor.deterministic.tag_pairing import bbox_inside_any  # noqa: PLC0415

    words = page_words(page)
    inside = {w[4] for w in words if bbox_inside_any(w[:4], masks)}
    outside = {w[4] for w in words if not bbox_inside_any(w[:4], masks)}
    mask_only = inside - outside
    if not mask_only:
        pytest.skip("page 0's masks cover no text that is unique to them")

    candidates = pipeline._anchor_candidate_map(bundle)
    anchored = anchors_for_candidates(page, candidates, mask_rects=masks)
    chosen = {
        rec["anchor_text"]
        for rec in anchored.values()
        if rec["anchor_text"] and rec["anchor_kind"] != "tag"
    }
    leaked = chosen & mask_only
    assert not leaked, (
        "these anchors exist ONLY inside a schedule table or title block and "
        "must never have been harvested from the plan body: %r" % sorted(leaked)
    )


# ---------------------------------------------------------------------------
# The module's own boundaries — grep-self, mirroring the phase-23 gate.
# ---------------------------------------------------------------------------


def test_the_module_does_not_reuse_the_drafting_noise_predicate():
    """That predicate returns True for 'B-1' and 'P1' — the tags we need."""
    src = MODULE_PATH.read_text()
    assert "_is_noise_token" not in src
    assert "_is_noise_cluster" not in src
    assert "from bobbytailor.vision" not in src


def test_the_module_runs_free():
    src = MODULE_PATH.read_text()
    for forbidden in (FORBIDDEN_CREDENTIAL, "analyze_drawing", "anthro" + "pic"):
        assert forbidden not in src, forbidden


def test_this_gate_runs_free():
    src = Path(__file__).read_text()
    # Each name appears exactly once — in its own fragment assembly above — so
    # a whole-file grep for the literal returns nothing.
    for forbidden in FORBIDDEN_PAID:
        assert forbidden not in src, forbidden
    # No scored total is asserted against the bollard or column candidates.
    assert re.search(r"==\s*28\b", src) is None
    assert re.search(r"==\s*132\b", src) is None
    assert re.search(r"==\s*136\b", src) is None
    assert re.search(r"==\s*56\b", src) is None
