"""A bollard is a POST, not a cell of a tile field (29-13). ZERO API.

The `perimeter_jamb_symbol` hint had a MINIMUM count and no maximum, and it
names the LARGEST cluster that survives its gates. On a dense sheet the largest
cluster is the drafting fill, so on the paid Bob's run of 2026-08-17 the hint
handed a finish plan's floor-tile field the name of a bollard and published 505
of them — flagged, and still the largest single error in either plan set.

What is asserted here is one claim about the object, and its consequences:

* **A BOLLARD STANDS CLEAR OF ITS NEIGHBOURS.** The gap beside it staying open
  is the whole function of the thing. Marks pitched closer together than their
  own footprint are not discrete posts; they tessellate, which is what a tile
  pattern, a hatch and a repeated fill do. Measured on the real drawing: the
  505-mark field's 1.51 ft marks sit 2.06 ft apart — 1.37 of their own width.
* **THE RULE IS A RATIO, SO IT CARRIES NO PLAN'S DIMENSIONS.** Both terms are
  lengths in the same coordinate system. A test multiplies every coordinate on
  a sheet by a constant and asserts the verdict does not move — the same proof
  `_MASONRY_MAX_LF_SHARE` was given in 28-04.
* **IT REFUSES A FILL, NOT EVERYTHING.** A ring built at realistic post spacing
  still binds, and the rule reads the MEDIAN neighbour so one coincidentally
  close pair inside a genuine array does not condemn it.
* **CROW'S 56-MARK LATTICE STAYS UNBOUND, AND THIS RULE IS NOT WHY.** Its marks
  are pitched 62 of their own widths apart — far above anything this rule
  excludes. Phase 28's ring test is what refuses it, and this module asserts
  that so the new rule is not credited with a refusal it did not make.
* **A REFUSED CLUSTER IS NOT DELETED.** It reaches the unnamed-geometry ledger
  carrying its count. A deletion and a zero read identically to a client.

Free by construction: vector geometry and hand-built groups only — no analyzer,
no credential, no network. The module states no take-off quantity and compares
no count against one; 505 is our own published number, not anyone's ground
truth, and the fix is not measured against a target.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fitz  # noqa: E402

from bobbytailor.deterministic.symbols import cluster_symbols  # noqa: E402
from bobbytailor.vision import fusion as F  # noqa: E402
from bobbytailor.vision.fusion import fuse_sheet  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"

# Crow's floor plan is page 0 at 1" = 40'-0"; Bob's finish plan is page 1 at
# 1" = 10'-8" (PIPELINE-GROUND-TRUTH §11). Both are drawing scales read off the
# sheets, not quantities.
CROW_PLAN_PAGE, CROW_FPP = 0, 40.0 / 72.0
BOBS_FINISH_PAGE, BOBS_FPP = 1, 0.148148

#: The naming library reduced to the one hint under test.
_PERIM_LIB = {"perimeter_jamb_symbol": {"name": "Perimeter Post", "basis": "count"}}

_CACHE: dict = {}


def _groups(pdf, page_index, fpp, key):
    """Symbol clusters for one real page — clustered once per session."""
    if key not in _CACHE:
        doc = fitz.open(pdf)
        _CACHE[key + "_doc"] = doc          # keep alive; page borrows from it
        _CACHE[key] = cluster_symbols(
            doc[page_index], fpp, doc=doc, page_index=page_index
        )
    return _CACHE[key]


def _crow():
    return _groups(CROW_PDF, CROW_PLAN_PAGE, CROW_FPP, "crow")


def _bobs():
    return _groups(BOBS_PDF, BOBS_FINISH_PAGE, BOBS_FPP, "bobs")


def _judged(groups, expect_count):
    """The cluster the perimeter hint reaches for on this page.

    Every filter the hint applies EXCEPT the ring test and the pitch test — the
    two predicates under scrutiny — then the strictly largest count, which is
    how the hint itself chooses. Identifying the subject this way rather than by
    a candidate id keeps it stable across a re-clustering, and identifying it
    independently of the rule being tested is what stops the test from selecting
    whichever cluster happens to give the answer it wants. Counts are not
    unique on either page, so *expect_count* is a check, not the search key.
    """
    shortlist = [
        g for g in groups
        if int(F._field(g, "count", 0) or 0) >= F._PERIMETER_MIN_COUNT
        and F._size_uniform(g) and F._is_small_marker(g) and F._is_2d_distributed(g)
    ]
    assert shortlist, "no cluster on this page reaches the perimeter hint at all"
    top = max(int(F._field(g, "count", 0) or 0) for g in shortlist)
    winners = [g for g in shortlist if int(F._field(g, "count", 0) or 0) == top]
    assert len(winners) == 1, (
        "the shortlist's maximum is not unique (%s), so the subject under test "
        "would depend on list order" % [g.candidate_id for g in winners]
    )
    assert top == expect_count, (
        "the hint now reaches for a %d-mark cluster, not the %d-mark one this "
        "module was measured against — re-measure before trusting it"
        % (top, expect_count)
    )
    return winners[0]


def _pitch_here(group):
    """The neighbour pitch, recomputed in this module rather than imported.

    An assertion that calls the implementation to decide what the implementation
    should produce proves only that the implementation equals itself.
    """
    cents = F._instance_centroids(group)
    widths, heights = F._instance_dims(group)
    marker = F._median([max(w, h) for w, h in zip(widths, heights)])
    nearest = [
        min(
            math.hypot(px - qx, py - qy)
            for j, (qx, qy) in enumerate(cents)
            if j != i
        )
        for i, (px, py) in enumerate(cents)
    ]
    return F._median(nearest) / marker


def _scaled(group, k):
    """The same cluster with every COORDINATE multiplied by *k*.

    Only the point geometry moves. ``bbox_size_ft`` is a real-world measurement,
    not a coordinate, and re-scaling it would be re-drawing the building.
    """
    return {
        "candidate_id": F._field(group, "candidate_id", ""),
        "count": F._field(group, "count", 0),
        "bbox_size_ft": F._field(group, "bbox_size_ft", None),
        "contained_texts": list(F._field(group, "contained_texts", []) or []),
        "representative_bbox_pt": tuple(
            v * k for v in (F._field(group, "representative_bbox_pt", ()) or ())
        ),
        "instance_bboxes_pt": [
            tuple(v * k for v in box)
            for box in (F._field(group, "instance_bboxes_pt", None) or [])
        ],
    }


def _ring(n_per_side, pitch_pt, marker_pt, origin=(200.0, 200.0)):
    """A hollow rectangular ring of *n_per_side* posts a side, hand-built.

    ``pitch_pt / marker_pt`` is the only thing the rule reads, so the ring is
    parameterised on exactly that: a caller asks for posts standing five of
    their own widths apart, or for marks packed at one.
    """
    ox, oy = origin
    span = (n_per_side - 1) * pitch_pt
    centres = []
    for i in range(n_per_side):
        centres.append((ox + i * pitch_pt, oy))
        centres.append((ox + i * pitch_pt, oy + span))
    for i in range(1, n_per_side - 1):
        centres.append((ox, oy + i * pitch_pt))
        centres.append((ox + span, oy + i * pitch_pt))
    half = marker_pt / 2.0
    boxes = [(x - half, y - half, x + half, y + half) for x, y in centres]
    return {
        "candidate_id": "SYM-RING",
        "count": len(boxes),
        "instance_bboxes_pt": boxes,
        "representative_bbox_pt": boxes[0],
        # A post drawn a foot across, at whatever pitch the caller asked for.
        "bbox_size_ft": (1.0, 1.0),
        "contained_texts": [],
    }


# ═════════════════════════════════════════════════════════════════════════════
# THE MEASUREMENT — WHAT THE REAL TILE FIELD IS
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's plan fixture absent")
def test_the_field_that_took_the_name_is_pitched_tighter_than_its_own_marks():
    """The 505-mark cluster, measured — and measured to clear every OTHER gate.

    The second half matters more than the first. If the cluster failed the size,
    uniformity or ring gate as well, this module could report a refusal that
    some pre-existing rule was already making, and the new one would be
    untested. It clears all of them; the pitch is the only thing that stops it.
    """
    field = _judged(_bobs(), 505)

    assert F._size_uniform(field)
    assert F._is_small_marker(field)
    assert F._is_perimeter_ring(field), (
        "the tile field no longer reads as a hollow ring, so the pitch rule is "
        "not what refuses it and this module is asserting nothing. Re-measure "
        "before trusting any result below."
    )

    pitch = _pitch_here(field)
    assert pitch < F._MARKER_MIN_NEIGHBOUR_PITCH, (
        "the tile field measures %.3f of its own marks' width between "
        "neighbours, at or above the threshold of %.1f — the drawing, the "
        "clusterer or the threshold has moved" % (pitch, F._MARKER_MIN_NEIGHBOUR_PITCH)
    )
    assert not F._is_discrete_object_array(field)


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's plan fixture absent")
def test_the_tile_field_no_longer_takes_the_perimeter_name():
    """The defect itself: the 505-mark cluster is not bound by the hint."""
    field = _judged(_bobs(), 505)
    bindings = F._library_symbol_bindings(_bobs(), {}, _PERIM_LIB)
    assert field.candidate_id not in bindings, (
        "the tile field still takes the perimeter object's name: %r" % bindings
    )


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's plan fixture absent")
def test_the_hint_did_not_simply_stop_binding_on_this_sheet():
    """What the hint names on Bob's INSTEAD, stated rather than buried.

    The rule removes one candidate; it does not close the channel. The next
    cluster down takes the name, and this sheet has no ground truth that can say
    whether THAT one is right either — so the binding is asserted to exist and
    to be a different, far smaller cluster, and nothing here claims it is
    correct. A rule that had silently emptied the hint would fail this.
    """
    bindings = F._library_symbol_bindings(_bobs(), {}, _PERIM_LIB)
    assert len(bindings) == 1, (
        "the perimeter hint binds %r on Bob's finish plan — 29-13 measured "
        "exactly one survivor. A change here is a change to what the sheet "
        "publishes and must be re-measured, not re-fitted." % bindings
    )
    cid = next(iter(bindings))
    bound = next(g for g in _bobs() if g.candidate_id == cid)
    refused = _judged(_bobs(), 505)
    assert bound.candidate_id != refused.candidate_id
    assert bound.count < refused.count


# ═════════════════════════════════════════════════════════════════════════════
# THE GENERALISATION BAR
# ═════════════════════════════════════════════════════════════════════════════


def test_a_ring_of_posts_at_realistic_spacing_still_binds():
    """A rule that refuses everything is not a discriminator.

    Posts a foot across standing five feet apart, laid out as a hollow ring —
    the shape and the spacing of a real bollard run. It binds.
    """
    ring = _ring(n_per_side=6, pitch_pt=50.0, marker_pt=10.0)
    assert F._is_discrete_object_array(ring)
    bindings = F._library_symbol_bindings([ring], {}, _PERIM_LIB)
    assert bindings == {"SYM-RING": ("Perimeter Post", "perimeter_jamb_symbol")}, (
        "a hollow ring of posts at five widths' spacing was refused: %r" % bindings
    )


def test_the_same_ring_packed_to_a_tile_pitch_is_refused():
    """The SAME shape, the same count, the same marks — only the pitch differs.

    Every other gate sees an identical cluster, so this isolates the new rule
    from all of them.
    """
    packed = _ring(n_per_side=6, pitch_pt=13.7, marker_pt=10.0)
    assert not F._is_discrete_object_array(packed)
    assert F._library_symbol_bindings([packed], {}, _PERIM_LIB) == {}


def test_the_verdict_does_not_move_when_every_coordinate_is_scaled():
    """Scale-independence, the proof 28-04 gave the masonry share guard.

    Multiply every point on the sheet by a constant — a different paper size, a
    different drawing scale, a different unit — and both verdicts are identical.
    The rule reads a ratio of two lengths, so nothing in it can be traced to a
    particular drawing's dimensions.
    """
    ring = _ring(n_per_side=6, pitch_pt=50.0, marker_pt=10.0)
    packed = _ring(n_per_side=6, pitch_pt=13.7, marker_pt=10.0)
    for k in (0.013, 0.37, 7.0, 137.0):
        assert F._is_discrete_object_array(_scaled(ring, k)) is True, k
        assert F._is_discrete_object_array(_scaled(packed, k)) is False, k

    # The WHOLE bind is scale-free only where the gates it runs behind are.
    # `_min_2d_span_pt` carries an absolute floor in points, so shrinking a
    # sheet far enough makes the 2-D test — not this one — refuse everything.
    # That is pre-existing and out of this change's scope; naming it here is
    # what stops the range below from looking arbitrarily chosen.
    for k in (0.37, 7.0, 137.0):
        assert F._library_symbol_bindings(
            [_scaled(ring, k), _scaled(packed, k)], {}, _PERIM_LIB
        ) == F._library_symbol_bindings([ring, packed], {}, _PERIM_LIB), k


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's plan fixture absent")
def test_the_real_sheets_verdict_is_scale_free_too():
    """The same proof on the real cluster, not only on a constructed one."""
    field = _judged(_bobs(), 505)
    before = F._is_discrete_object_array(field)
    for k in (0.013, 7.0, 137.0):
        assert F._is_discrete_object_array(_scaled(field, k)) is before, k


def test_the_threshold_is_a_dimensionless_ratio():
    """It is a multiple of the marks' own size — no length, no unit, no plan."""
    assert isinstance(F._MARKER_MIN_NEIGHBOUR_PITCH, float)
    assert 0.0 < F._MARKER_MIN_NEIGHBOUR_PITCH < 100.0


def test_the_rule_reads_the_median_neighbour_not_the_closest_pair():
    """One coincidentally close pair inside a genuine array is not a fill.

    A ring of well-spaced posts with a single extra mark dropped beside one of
    them: the minimum neighbour distance collapses, the median does not, and the
    array still binds. Reading the minimum would have refused it.
    """
    ring = _ring(n_per_side=6, pitch_pt=50.0, marker_pt=10.0)
    x0, y0, x1, y1 = ring["instance_bboxes_pt"][0]
    ring["instance_bboxes_pt"].append((x0 + 3.0, y0, x1 + 3.0, y1))
    ring["count"] += 1
    cents = F._instance_centroids(ring)
    closest = min(
        math.hypot(a[0] - b[0], a[1] - b[1])
        for i, a in enumerate(cents)
        for j, b in enumerate(cents)
        if i != j
    )
    assert closest < 10.0 * F._MARKER_MIN_NEIGHBOUR_PITCH, (
        "the coincidental pair is not actually close, so this asserts nothing"
    )
    assert F._is_discrete_object_array(ring)


def test_an_unmeasurable_pitch_names_nothing():
    """Absence of evidence must not be what supplies an object's name."""
    assert F._neighbour_pitch({"instance_bboxes_pt": []}) is None
    assert F._neighbour_pitch(
        {"instance_bboxes_pt": [(0.0, 0.0, 10.0, 10.0)]}
    ) is None
    # Degenerate marks: centres known, size zero — the ratio has no denominator.
    assert F._neighbour_pitch(
        {"instance_bboxes_pt": [(0.0, 0.0, 0.0, 0.0), (5.0, 0.0, 5.0, 0.0)]}
    ) is None
    assert not F._is_discrete_object_array({"instance_bboxes_pt": []})


# ═════════════════════════════════════════════════════════════════════════════
# CROW — REFUSED BEFORE, REFUSED AFTER, AND NOT BY THIS RULE
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow plan fixture absent")
def test_crows_lattice_stays_unbound_and_this_rule_is_not_what_refuses_it():
    """Phase 28 established the 56-mark cluster is an interior lattice.

    It must stay unbound — and the credit must stay with the ring test. Its
    marks are pitched tens of their own widths apart, so the pitch rule would
    have let it straight through. Asserting both is what stops a later reader
    from believing this rule closed a hole it never touched.
    """
    lattice = _judged(_crow(), 56)
    assert F._is_discrete_object_array(lattice), (
        "Crow's lattice now fails the pitch rule, which would mean this rule is "
        "being credited with phase 28's refusal"
    )
    assert not F._is_perimeter_ring(lattice)
    assert F._library_symbol_bindings(_crow(), {}, _PERIM_LIB) == {}, (
        "Crow's plan page emitted a perimeter binding again"
    )


# ═════════════════════════════════════════════════════════════════════════════
# A REFUSAL IS NOT A DELETION
# ═════════════════════════════════════════════════════════════════════════════


def test_a_refused_cluster_reaches_the_ledger_carrying_its_whole_count():
    """A deletion and a zero read identically to a client; neither is what
    happens. The marks were measured, they are real, and they are unidentified —
    so they surface as the absence of a NAME, with the count intact."""
    packed = _ring(n_per_side=8, pitch_pt=13.7, marker_pt=10.0)
    count = packed["count"]
    fused = fuse_sheet(
        {"sheet_name": "A-1.1", "symbol_groups": [packed]},
        {},
        vocabulary=[
            {
                "name": "Perimeter Post",
                "basis": "count",
                "binding_hint": "perimeter_jamb_symbol",
            }
        ],
    )
    assert not [
        c for c in fused["components"] if c.get("candidate_id") == "SYM-RING"
    ], "the refused cluster was published as a named component anyway"

    ledger = fused[F.UNNAMED_GEOMETRY_KEY]
    rows = [r for r in ledger if r.get("candidate_id") == "SYM-RING"]
    assert len(rows) == 1, (
        "the refused cluster left %d ledger rows, not one — its %d marks are "
        "either lost or double-reported: %r" % (len(rows), count, ledger)
    )
    assert rows[0]["quantity"] == count, (
        "the ledger row carries %r, not the %d marks that were measured"
        % (rows[0]["quantity"], count)
    )
    assert rows[0]["unit"] == "EA"
    assert rows[0].get("reason")
