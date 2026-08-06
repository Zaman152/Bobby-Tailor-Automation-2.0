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


# ── 7. The module's own contract ─────────────────────────────────────────────


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
