"""V4-FIX-02 — position evidence against the "it is a double-count" hypothesis.

The `perimeter_jamb_symbol` naming hint bound a Crow page-0 marker cluster, and
the published count came out at exactly twice the take-off's figure. A clean
factor of two, one detail line, one formula, identical across two paid runs:
the textbook reading is that every object is being marked twice and the cure is
to halve.

This module refuses that reading and makes the refusal runnable. It measures the
cluster the hint would name, on the real plan set, for free, and asserts three
properties that a double-count cannot have:

1. **One region.** Every instance resolves to exactly one segmented viewport,
   and it is the same viewport for all of them. A plan-plus-detail double-marking
   would put half the instances in a detail region.
2. **No coincident pairs.** The closest two instances are many symbol widths
   apart. A second mark on an already-marked object sits *on* it.
3. **Nowhere near an edge.** No instance is within a small fraction of the
   region's short side of that region's boundary. A perimeter object hugs the
   boundary; these sit deep in the interior.

What the cluster positively is, also asserted here: a fully populated lattice.
Every band it occupies along both axes is as full as every other — the signature
of rows and columns, not of a hollow ring, whose interior bands hold one mark
per side. That is the property `_is_perimeter_ring` could not see, and the
reason a lattice on the structural bay grid acquired a perimeter object's name.

Free by construction: vector geometry only, no analyzer, no credential, no
network. The module states no take-off quantity and compares no count against
one — the whole point is that the count was never the evidence.
"""
import ast
import math
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.symbols import cluster_symbols
from bobbytailor.deterministic.viewports import segment_viewports
from bobbytailor.vision import fusion as F

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"

# Crow's floor plan is page 0 at 1" = 40'-0" (PIPELINE-GROUND-TRUTH §11.0).
CROW_PLAN_PAGE = 0
CROW_P0_FPP = 40.0 / 72.0

pytestmark = pytest.mark.skipif(
    not CROW_PDF.is_file(),
    reason="Crow Cass plan set (tests/fixtures/crow_cass/crow_cass_plans.pdf) "
           "is absent — the position evidence in this module is measured on the "
           "real drawing and cannot be simulated",
)

# ── Geometric facts these assertions are written against ─────────────────────
#
# None of these is derived from any published take-off figure. Each states a
# property of a shape.

# A hollow ring's interior band holds one mark per side — two. A band holding
# more than that is a populated ROW, not the two flanks of a ring.
_RING_INTERIOR_BAND = 2
# A ring is assembled from two runs per axis: its two opposite sides.
_RING_MAX_DENSE_BANDS = 2
# Two marks drawn on ONE object (a pipe and its cap) sit within a symbol width
# of each other. Anything separated by several widths is two objects.
_DOUBLE_MARK_WIDTHS = 5.0
# An object AT a perimeter sits against the boundary. Expressed as a fraction of
# the region's short side so it carries no unit and no plan's dimensions.
_EDGE_HUG_FRACTION = 0.05


# ── The drawing, read once ───────────────────────────────────────────────────

_CACHE = {}


def _page_symbols():
    """(page, [SymbolGroup]) for Crow's plan page — clustered once per session."""
    if "page" not in _CACHE:
        doc = fitz.open(CROW_PDF)
        page = doc[CROW_PLAN_PAGE]
        _CACHE["doc"] = doc  # keep the document alive; page borrows from it
        _CACHE["page"] = page
        _CACHE["groups"] = cluster_symbols(
            page, CROW_P0_FPP, doc=doc, page_index=CROW_PLAN_PAGE
        )
        _CACHE["viewports"] = segment_viewports(page)
    return _CACHE["page"], _CACHE["groups"]


def _viewports():
    _page_symbols()
    return _CACHE["viewports"]


# ── Identifying the judged cluster the way the binder does ───────────────────


def _hint_shortlist(groups):
    """Clusters the `perimeter_jamb_symbol` hint will consider.

    Every filter `_library_symbol_bindings` applies to that hint EXCEPT the ring
    test itself, which is the predicate under scrutiny. Excluding it is what
    makes this shortlist stable across the fix: the same cluster is judged
    before and after, so the position evidence keeps describing the cluster that
    actually received the name.
    """
    return [
        g for g in groups
        if int(F._field(g, "count", 0) or 0) >= F._PERIMETER_MIN_COUNT
        and F._size_uniform(g)
        and F._is_small_marker(g)
        and F._is_2d_distributed(g)
    ]


def _judged_cluster():
    """The shortlisted cluster with the strictly largest count — the one the
    hint names when the ring test lets it through."""
    shortlist = _hint_shortlist(_page_symbols()[1])
    assert shortlist, "no cluster on the plan page reaches the perimeter hint at all"
    top = max(int(F._field(g, "count", 0) or 0) for g in shortlist)
    winners = [g for g in shortlist if int(F._field(g, "count", 0) or 0) == top]
    assert len(winners) == 1, (
        "the shortlist's maximum is not unique (%s) — the cluster under test "
        "would depend on list order" % [F._field(g, "candidate_id", "") for g in winners]
    )
    return winners[0]


def _cid(group):
    return F._field(group, "candidate_id", "")


# ── Band occupancy, computed here independently of the implementation ────────


def _bands(values, tol):
    """Indices of *values*, greedily grouped into bands no more than *tol* apart.

    An oracle written for this module: the fix under test adds its own band
    computation to `fusion`, and a test that borrowed it could not catch it
    being wrong.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    bands, bucket = [], []
    for i in order:
        if bucket and values[i] - values[bucket[-1]] > tol:
            bands.append(bucket)
            bucket = []
        bucket.append(i)
    if bucket:
        bands.append(bucket)
    return bands


def _axis_bands(centroids, tol):
    return (
        _bands([c[0] for c in centroids], tol),
        _bands([c[1] for c in centroids], tol),
    )


def _band_tolerance(centroids):
    """Half the closest approach between any two marks.

    Self-evidently a valid band tolerance for this data: no two marks are
    within it, so two marks share a band only when they genuinely share a
    coordinate. Derived from the cluster's own measurements, nothing else.
    """
    return _min_separation(centroids) / 2.0


def _min_separation(centroids):
    return min(
        math.hypot(a[0] - b[0], a[1] - b[1])
        for i, a in enumerate(centroids)
        for b in centroids[i + 1:]
    )


def _median_mark_size(group):
    widths, heights = F._instance_dims(group)
    return F._median([max(w, h) for w, h in zip(widths, heights)])


# ── Synthetic shapes, built from the real cluster's own measurements ─────────


def _measured_pitch(group):
    """The real cluster's smallest gap between adjacent occupied coordinates."""
    centroids = F._instance_centroids(group)
    gaps = []
    for axis in (0, 1):
        coords = sorted(set(round(c[axis], 3) for c in centroids))
        gaps += [b - a for a, b in zip(coords, coords[1:]) if b - a > 0]
    return min(gaps)


def _ring_boxes(n_per_side, step, size, origin=(1000.0, 1000.0)):
    """A HOLLOW rectangular ring: marks on the boundary, interior empty."""
    ox, oy = origin
    span = n_per_side * step
    boxes = []
    for i in range(n_per_side):
        d = i * step
        boxes += [
            (ox + d, oy, ox + d + size, oy + size),
            (ox + d, oy + span, ox + d + size, oy + span + size),
            (ox, oy + d, ox + size, oy + d + size),
            (ox + span, oy + d, ox + size + span, oy + d + size),
        ]
    return boxes


def _lattice_boxes(cols, rows, step, size, origin=(1000.0, 1000.0)):
    """A FULLY POPULATED lattice of the same pitch and mark size."""
    ox, oy = origin
    return [
        (ox + c * step, oy + r * step, ox + c * step + size, oy + r * step + size)
        for r in range(rows)
        for c in range(cols)
    ]


def _group_of(boxes):
    return {
        "candidate_id": "SYNTH",
        "count": len(boxes),
        "instance_bboxes_pt": boxes,
        "representative_bbox_pt": boxes[0],
        "contained_texts": [],
        "confidence": "medium",
    }


# ── 1. The cluster under test is identified, not assumed ─────────────────────


def test_the_perimeter_hint_resolves_to_exactly_one_cluster_on_the_plan_page():
    group = _judged_cluster()
    counts = {
        _cid(g): int(F._field(g, "count", 0) or 0)
        for g in _hint_shortlist(_page_symbols()[1])
    }
    assert _cid(group) in counts, "the judged cluster fell out of its own shortlist"
    assert counts[_cid(group)] == max(counts.values()), (
        "the cluster judged below (%s) is not the one the hint would name; "
        "shortlist was %r" % (_cid(group), counts)
    )


# ── 2. Falsification: it is not a plan-plus-detail double-marking ────────────


def test_every_instance_lands_in_exactly_one_region_and_it_is_the_same_one():
    group = _judged_cluster()
    centroids = F._instance_centroids(group)
    regions = []
    for px, py in centroids:
        hits = [
            v.region_id for v in _viewports()
            if v.bbox_pt[0] <= px <= v.bbox_pt[2] and v.bbox_pt[1] <= py <= v.bbox_pt[3]
        ]
        assert len(hits) == 1, (
            "%s: an instance at (%.1f, %.1f) resolves to %d regions (%r) — "
            "region membership is not decidable" % (_cid(group), px, py, len(hits), hits)
        )
        regions.append(hits[0])
    assert len(set(regions)) == 1, (
        "%s: instances are spread across regions %r. A cluster drawn once on "
        "the plan and again in a detail would look exactly like this; this one "
        "does not." % (_cid(group), sorted(set(regions)))
    )


# ── 3. Falsification: no object carries two marks ────────────────────────────


def test_no_two_instances_are_close_enough_to_be_two_marks_on_one_object():
    group = _judged_cluster()
    centroids = F._instance_centroids(group)
    closest = _min_separation(centroids)
    mark = _median_mark_size(group)
    assert mark > 0, "%s: instance sizes are unreadable" % _cid(group)
    assert closest > _DOUBLE_MARK_WIDTHS * mark, (
        "%s: the two closest instances are %.1f pt apart against a %.2f pt "
        "symbol — close enough to be one object marked twice" % (_cid(group), closest, mark)
    )


# ── 4. Falsification: nothing is at a perimeter ──────────────────────────────


def test_no_instance_lies_near_the_boundary_of_its_own_region():
    group = _judged_cluster()
    centroids = F._instance_centroids(group)
    region = None
    for v in _viewports():
        if all(
            v.bbox_pt[0] <= px <= v.bbox_pt[2] and v.bbox_pt[1] <= py <= v.bbox_pt[3]
            for px, py in centroids
        ):
            region = v
            break
    assert region is not None, "%s: no single region contains the cluster" % _cid(group)
    x0, y0, x1, y1 = region.bbox_pt
    short_side = min(x1 - x0, y1 - y0)
    nearest = min(
        min(px - x0, x1 - px, py - y0, y1 - py) for px, py in centroids
    )
    assert nearest > _EDGE_HUG_FRACTION * short_side, (
        "%s: an instance sits %.3f of the short side from the boundary of %s — "
        "close enough to be a perimeter object" % (_cid(group), nearest / short_side, region.region_id)
    )


# ── 5. What it positively is: a filled lattice, not a hollow ring ────────────


def test_every_band_the_cluster_occupies_is_as_full_as_every_other():
    group = _judged_cluster()
    centroids = F._instance_centroids(group)
    tol = _band_tolerance(centroids)
    xb, yb = _axis_bands(centroids, tol)
    for axis, occ in (("column", [len(b) for b in xb]), ("row", [len(b) for b in yb])):
        assert min(occ) > _RING_INTERIOR_BAND, (
            "%s: its emptiest %s holds %d marks; a hollow ring's interior %s "
            "holds one per side. Occupancies: %r"
            % (_cid(group), axis, min(occ), axis, occ)
        )
    assert len([b for b in xb if len(b) > _RING_INTERIOR_BAND]) > _RING_MAX_DENSE_BANDS
    assert len([b for b in yb if len(b) > _RING_INTERIOR_BAND]) > _RING_MAX_DENSE_BANDS


# ── 6. The discriminator itself, on shapes built from the real measurements ──


def test_a_hollow_ring_has_two_dense_bands_per_axis_and_a_lattice_has_more():
    group = _judged_cluster()
    step = _measured_pitch(group)
    size = _median_mark_size(group)
    n = len({round(c[0], 3) for c in F._instance_centroids(group)})

    ring = F._instance_centroids(_group_of(_ring_boxes(n, step, size)))
    lattice = F._instance_centroids(_group_of(_lattice_boxes(n, n, step, size)))

    for name, centroids, expected in (("ring", ring, True), ("lattice", lattice, False)):
        tol = step / 2.0
        xb, yb = _axis_bands(centroids, tol)
        dense_x = len([b for b in xb if len(b) > _RING_INTERIOR_BAND])
        dense_y = len([b for b in yb if len(b) > _RING_INTERIOR_BAND])
        is_ringlike = dense_x <= _RING_MAX_DENSE_BANDS and dense_y <= _RING_MAX_DENSE_BANDS
        assert is_ringlike is expected, (
            "synthetic %s built at the measured pitch %.1f pt reads dense bands "
            "(%d, %d); a ring has at most %d per axis"
            % (name, step, dense_x, dense_y, _RING_MAX_DENSE_BANDS)
        )


def test_the_ring_and_the_lattice_are_indistinguishable_by_count():
    """Both synthetic shapes are built from the same pitch; the ring's marks and
    the lattice's marks are told apart by WHERE they sit, never by how many."""
    group = _judged_cluster()
    step = _measured_pitch(group)
    size = _median_mark_size(group)
    ring = _ring_boxes(14, step, size)
    lattice = _lattice_boxes(14, 4, step, size)
    assert len(ring) == len(lattice), (
        "the two shapes were built to carry identical mark counts so that no "
        "assertion in this module can be satisfied by a count alone"
    )


# ── 7. `_is_perimeter_ring` tells the two shapes apart ───────────────────────


def _jamb_run_boxes(n_pairs, step, size, gap):
    """A bollard pair at each overhead-door jamb along ONE wall: two parallel
    runs, no interior at all. The layout the hint is named for."""
    ox, oy = 1000.0, 1000.0
    boxes = []
    for i in range(n_pairs):
        x = ox + i * step
        boxes += [
            (x, oy, x + size, oy + size),
            (x, oy + gap, x + size, oy + gap + size),
        ]
    return boxes


def test_the_judged_cluster_is_no_longer_read_as_a_perimeter_ring():
    group = _judged_cluster()
    assert F._is_perimeter_ring(group) is False, (
        "%s is a fully populated lattice (asserted band-by-band above) and must "
        "not satisfy a predicate named for a hollow ring" % _cid(group)
    )


def test_the_inset_test_alone_would_still_have_accepted_that_lattice():
    """Why the 25% inset was not enough, measured rather than argued: with only
    a few rows, almost every mark of a lattice falls OUTSIDE the inset box, so
    the cluster reads as hollow."""
    group = _judged_cluster()
    centroids = F._instance_centroids(group)
    xs = [c[0] for c in centroids]
    ys = [c[1] for c in centroids]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    ix0, ix1 = x0 + 0.25 * (x1 - x0), x1 - 0.25 * (x1 - x0)
    iy0, iy1 = y0 + 0.25 * (y1 - y0), y1 - 0.25 * (y1 - y0)
    inner = sum(1 for px, py in centroids if ix0 < px < ix1 and iy0 < py < iy1)
    assert inner / float(len(centroids)) <= F._PERIMETER_INNER_MAX_FILL, (
        "%s no longer reads as hollow against the inset box, so this test no "
        "longer explains anything" % _cid(group)
    )


def test_a_hollow_ring_built_at_the_measured_pitch_is_still_a_ring():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    ring = _group_of(_ring_boxes(14, step, size))
    assert F._is_perimeter_ring(ring) is True


def test_a_filled_lattice_of_the_same_pitch_and_mark_is_not_a_ring():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    lattice = _group_of(_lattice_boxes(14, 4, step, size))
    assert F._is_perimeter_ring(lattice) is False


def test_a_run_of_jamb_pairs_along_one_wall_is_still_a_ring():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    jamb = _group_of(_jamb_run_boxes(10, step, size, gap=step / 4.0))
    assert F._is_perimeter_ring(jamb) is True, (
        "the door-jamb layout the hint is named for was rejected"
    )


def test_a_sparse_scatter_lying_on_no_run_is_not_a_ring():
    """Nine marks in general position clear a 25% inset box by luck — that box
    covers a quarter of the area, so a random scatter puts about a quarter of
    its marks inside. Lying on no RUN is the positive evidence that is missing."""
    scatter = [
        (1000.0, 1000.0), (1041.0, 1233.0), (1187.0, 1074.0), (1302.0, 1411.0),
        (1466.0, 1121.0), (1523.0, 1355.0), (1198.0, 1502.0), (1610.0, 1046.0),
        (1372.0, 1198.0),
    ]
    group = _group_of([(x, y, x + 2.0, y + 2.0) for x, y in scatter])
    assert F._is_2d_distributed(group) is True, "fixture must clear the 2-D gate"
    assert F._is_perimeter_ring(group) is False


def test_a_collinear_strip_is_still_rejected_and_the_two_d_gate_still_decides_it():
    """The pre-existing gate is not weakened: a strip fails on 2-D spread, before
    any occupancy is counted."""
    strips = [
        g for g in _page_symbols()[1]
        if len(F._instance_centroids(g)) >= F._PERIMETER_MIN_COUNT
        and not F._is_2d_distributed(g)
    ]
    assert strips, "the plan page carries no collinear strip to check against"
    for g in strips:
        assert F._is_perimeter_ring(g) is False, (
            "%s is collinear and must never read as a ring" % _cid(g)
        )


def test_too_few_marks_is_not_evidence_of_a_ring():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    boxes = _ring_boxes(14, step, size)[: F._PERIMETER_MIN_COUNT - 1]
    assert F._is_perimeter_ring(_group_of(boxes)) is False


# ── 8. The real outcome on the plan page ─────────────────────────────────────


def test_no_small_marker_cluster_on_the_plan_page_reads_as_a_perimeter_ring():
    """The honest consequence: the hint finds nothing to name on this sheet.

    The count does not get closer to the take-off's figure; the WRONG NAME goes
    away. Detecting the real objects is symbol detection's job, not naming's.
    """
    bound = [
        _cid(g) for g in _page_symbols()[1]
        if int(F._field(g, "count", 0) or 0) >= F._PERIMETER_MIN_COUNT
        and F._size_uniform(g)
        and F._is_small_marker(g)
        and F._is_perimeter_ring(g)
    ]
    assert bound == [], (
        "the perimeter hint still names %r on this sheet — the fix replaced one "
        "unevidenced name with another" % bound
    )


def test_the_ring_test_still_finds_the_one_genuinely_hollow_ring_on_the_page():
    """Non-vacuity, on real geometry: the sheet DOES carry a hollow ring, the
    predicate still recognises it, and it is kept away from the marker hint by
    the pre-existing size filter rather than by the ring test."""
    rings = [g for g in _page_symbols()[1] if F._is_perimeter_ring(g)]
    assert rings, (
        "the predicate now accepts nothing at all on this sheet — it has stopped "
        "discriminating and started refusing"
    )
    survivors = {
        _cid(g): ("too large to be a marker" if not F._is_small_marker(g)
                  else "instance sizes are not uniform")
        for g in rings
    }
    assert all(
        not (F._is_small_marker(g) and F._size_uniform(g)) for g in rings
    ), (
        "a uniform small-marker ring survived the ring test but not the "
        "binder's filter, so the two disagree: %r" % survivors
    )


# ── 9. A tie is not a decision ───────────────────────────────────────────────
#
# `_library_symbol_bindings` filtered candidates and then took `max(..., key=
# count)`. `max` returns the FIRST maximum, so when two surviving clusters carry
# the same count the winner is whichever the clusterer happened to emit first.
# An ambiguity resolved by list order is a guess wearing a decision's clothes.


def _marker_group(cid, boxes, size_ft=(0.8, 0.9)):
    g = _group_of(boxes)
    g["candidate_id"] = cid
    g["bbox_size_ft"] = size_ft
    return g


def _two_rings(step, size):
    return [
        _marker_group("SYM-A", _ring_boxes(14, step, size)),
        _marker_group(
            "SYM-B", _ring_boxes(14, step, size, origin=(9000.0, 9000.0))
        ),
    ]


def _two_grids(step, size):
    return [
        _marker_group("SYM-C", _lattice_boxes(6, 6, step, size)),
        _marker_group(
            "SYM-D", _lattice_boxes(6, 6, step, size, origin=(9000.0, 9000.0))
        ),
    ]


_PERIM_LIB = {"perimeter_jamb_symbol": {"name": "Perimeter Object", "basis": "count"}}
_GRID_LIB = {"structural_grid_symbol": {"name": "Grid Object", "basis": "count"}}


def test_two_perimeter_candidates_tied_on_count_bind_nothing():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    rings = _two_rings(step, size)
    assert all(F._is_perimeter_ring(g) for g in rings), "both fixtures must survive the filters"
    assert rings[0]["count"] == rings[1]["count"], "the fixtures must tie"

    bindings = F._library_symbol_bindings(rings, {}, _PERIM_LIB)
    assert bindings == {}, (
        "a tie was resolved into a name: %r. Whichever cluster the clusterer "
        "emitted first would have been named." % bindings
    )


def test_two_grid_candidates_tied_on_count_bind_nothing():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    grids = _two_grids(step, size)
    assert all(
        int(g["count"]) >= F._GRID_MIN_COUNT and F._is_2d_distributed(g)
        and F._is_small_marker(g) and F._size_uniform(g)
        for g in grids
    ), "both fixtures must survive the grid filters"

    bindings = F._library_symbol_bindings(grids, {}, _GRID_LIB)
    assert bindings == {}, (
        "the columns hint inherited the defect being fixed on the bollards "
        "hint: %r" % bindings
    )


def test_a_refused_tie_says_which_candidates_tied(caplog):
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    with caplog.at_level("INFO", logger=F.logger.name):
        F._library_symbol_bindings(_two_rings(step, size), {}, _PERIM_LIB)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "SYM-A" in logged and "SYM-B" in logged, (
        "a refusal nobody can see is indistinguishable from a cluster that was "
        "never a candidate; log was %r" % logged
    )


def test_a_single_surviving_candidate_still_binds():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    only = [_marker_group("SYM-A", _ring_boxes(14, step, size))]
    bindings = F._library_symbol_bindings(only, {}, _PERIM_LIB)
    assert bindings == {"SYM-A": ("Perimeter Object", "perimeter_jamb_symbol")}


def test_an_unambiguous_larger_candidate_still_wins():
    """A strictly larger count is a discriminator; only a TIE is refused."""
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    cands = [
        _marker_group("SYM-A", _ring_boxes(10, step, size)),
        _marker_group("SYM-B", _ring_boxes(14, step, size, origin=(9000.0, 9000.0))),
    ]
    bindings = F._library_symbol_bindings(cands, {}, _PERIM_LIB)
    assert list(bindings) == ["SYM-B"]


def test_no_surviving_candidate_binds_nothing():
    group = _judged_cluster()
    step, size = _measured_pitch(group), _median_mark_size(group)
    lattice = [_marker_group("SYM-A", _lattice_boxes(14, 4, step, size))]
    assert F._library_symbol_bindings(lattice, {}, _PERIM_LIB) == {}


def test_the_real_plan_page_emits_no_perimeter_binding():
    """End to end on the drawing: with the ring test honest and the tie rule in
    place, the hint names nothing here. The object reaches the report as an
    absence of a NAME, not an absence of an object — its count and position are
    still measured, they are simply not published under a name nothing earned.
    """
    bindings = F._library_symbol_bindings(_page_symbols()[1], {}, _PERIM_LIB)
    assert bindings == {}, "the hint still names %r on the plan page" % bindings


# ── 10. The module's own contract ────────────────────────────────────────────


def test_this_module_names_no_published_quantity_and_calls_no_paid_service():
    source = Path(__file__).read_text()
    # Assembled from halves so the check cannot find itself.
    forbidden = [
        "ANTHRO" + "PIC",
        "crow_cass" + "_golden",
        "golden" + ".csv",
        "vision_only" + "_benchmark",
        "accuracy" + "_gate",
    ]
    for token in forbidden:
        assert token not in source, (
            "this module must stay free and golden-free; found %r" % token
        )

def test_this_module_imports_nothing_that_could_reach_a_network():
    """Checked over the module's own import statements rather than by scanning
    its text — a substring scan for a networking library finds itself."""
    tree = ast.parse(Path(__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"ast", "math", "pathlib", "fitz", "pytest", "bobbytailor"}
    assert imported <= allowed, (
        "this module must stay offline; unexpected imports %r" % sorted(imported - allowed)
    )
