"""The grid-lattice column detector — position-first, four-plan-set gated. ZERO API.

Read this before changing a constant in ``grid_lattice.py``.

Every assertion here is about POSITION, SHAPE or the drawing's own printed text.
Not one of them is a golden take-off number, and none may ever be adjusted to
make a total match one. Crow's golden Columns count is 132; this file asserts
the detector measures **120**, because 120 is what the sheet draws. Closing that
gap by filtering is the documented coincidence trap that has already cost this
project days, twice.

The gate that matters most is :func:`test_no_lattice_anywhere_else_in_four_sets`.
A detector that fires on a second plan set is rejected outright — that is the
four-plan-set discipline, and it is why the roof-pitch false positive on Chelsea
page 17 was fixed at the root (a gridline axis must be uniquely and sequentially
labelled) rather than filtered away.
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

from bobbytailor.deterministic.grid_lattice import (  # noqa: E402
    MIN_MARKERS,
    GridAxis,
    _is_grid_axis_labelling,
    closed_rects,
    detect_grid_lattices,
    grid_axes,
    lattice_groups,
    lattice_shadowed_symbol_ids,
)
from bobbytailor.deterministic.symbols import (  # noqa: E402
    _harvest_primitives,
    cluster_symbols,
)
from bobbytailor.deterministic.dimensions import _visible_drawings  # noqa: E402

CROW_PDF = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
# A-101 OVERALL FLOOR PLAN prints 1" = 40'.
CROW_P0_FPP = 40.0 / 72.0

_CACHE: dict = {}


def _crow_page0():
    if "doc" not in _CACHE:
        _CACHE["doc"] = fitz.open(CROW_PDF)
    return _CACHE["doc"], _CACHE["doc"][0]


def _crow_lattices():
    if "lat" not in _CACHE:
        doc, page = _crow_page0()
        _CACHE["lat"] = detect_grid_lattices(page, CROW_P0_FPP, doc=doc, page_index=0)
    return _CACHE["lat"]


crow_only = pytest.mark.skipif(
    not CROW_PDF.exists(), reason="Crow fixture PDF not present"
)


# ─────────────────────────────────────────────────────────────────────────────
# Pure-function unit tests — no PDF, no fixtures.
# ─────────────────────────────────────────────────────────────────────────────


class _Prim:
    def __init__(self, e1, e2, kind="l"):
        self.kind = kind
        self.e1 = e1
        self.e2 = e2


def _box(x, y, w, h):
    return [
        _Prim((x, y), (x + w, y)),
        _Prim((x + w, y), (x + w, y + h)),
        _Prim((x + w, y + h), (x, y + h)),
        _Prim((x, y + h), (x, y)),
    ]


def test_closed_rects_needs_all_four_edges():
    """Three edges are not a rectangle — this is what makes the gridline dash
    harmless. The dash is one segment on one side and can never close a box."""
    assert closed_rects(_box(10, 10, 2, 2), 8.0) == [(10.0, 10.0, 12.0, 12.0)]
    assert closed_rects(_box(10, 10, 2, 2)[:3], 8.0) == []


def test_closed_rects_respects_the_size_ceiling():
    assert closed_rects(_box(0, 0, 20, 20), 8.0) == []


def test_a_gridline_axis_must_be_uniquely_and_sequentially_labelled():
    """The three structural properties of a printed grid.

    The middle case is Chelsea page 17 verbatim: roof-pitch callouts read
    ``3 2 4 3 2 4 ...`` across the sheet and, before this rule existed, twelve
    pitch triangles snapped to them as a 6x2 lattice at 100% occupancy — a
    false positive on a second plan set.
    """
    assert _is_grid_axis_labelling(["1", "2", "3", "4"])
    assert _is_grid_axis_labelling(["A", "B", "C", "D"])
    assert _is_grid_axis_labelling(["D", "C", "B", "A"])  # right-to-left is a grid
    assert not _is_grid_axis_labelling(["3", "2", "4", "3", "2", "4"])  # repeats
    assert not _is_grid_axis_labelling(["1", "3", "2", "4"])  # out of sequence
    assert not _is_grid_axis_labelling(["1", "2", "A", "B"])  # mixed alphabet


def _synthetic_lattice(n_cols, n_rows, dx=50.0, dy=40.0):
    prims = []
    for i in range(n_cols):
        for j in range(n_rows):
            prims += _box(100 + i * dx, 100 + j * dy, 2.0, 2.0)
    ax = GridAxis("x", [101.0 + i * dx for i in range(n_cols)],
                  [str(i + 1) for i in range(n_cols)])
    ay = GridAxis("y", [101.0 + j * dy for j in range(n_rows)],
                  [chr(ord("A") + j) for j in range(n_rows)])
    return prims, ax, ay


def test_a_collinear_tick_row_is_rejected_by_construction():
    """Ground truth section 10's trap, encoded permanently.

    A 136-mark row of dimension ticks has ``yspan = 0`` -> ONE distinct Y. The
    ``>= 2 distinct Y`` rule rejects it structurally. It is not a threshold that
    happens to exclude it, and no count filter is involved: make the row 1000
    marks long and it is still rejected.
    """
    prims, ax, ay = _synthetic_lattice(40, 1)
    rects = closed_rects(prims, 8.0)
    assert len(rects) == 40
    assert lattice_groups(rects, [ax], [ay], 0.5) == []


def test_a_full_two_dimensional_lattice_is_accepted():
    prims, ax, ay = _synthetic_lattice(5, 4)
    groups = lattice_groups(closed_rects(prims, 8.0), [ax], [ay], 0.5)
    assert len(groups) == 1
    assert groups[0].count == 20
    assert (groups[0].n_cols, groups[0].n_rows) == (5, 4)
    assert groups[0].occupancy == 1.0
    assert groups[0].cell_ids[0] == "A-1"


def test_a_sparse_lattice_is_rejected_for_occupancy():
    """A grid with holes in it is not a bay grid, however many marks it has.

    Four scattered cells removed from a 6 x 4 block still spans all 6 columns
    and all 4 rows, so the ONLY thing that rejects it is occupancy: 20/24 =
    0.833.
    """
    prims, ax, ay = _synthetic_lattice(6, 4)
    rects = closed_rects(prims, 8.0)
    assert len(rects) == 24
    holed = [r for i, r in enumerate(rects) if i not in (1, 8, 15, 22)]
    assert len(holed) == 20
    assert lattice_groups(holed, [ax], [ay], 0.5) == []


def test_fewer_than_the_minimum_markers_is_not_a_bay_grid():
    prims, ax, ay = _synthetic_lattice(3, 3)  # 9 < MIN_MARKERS
    assert MIN_MARKERS > 9
    assert lattice_groups(closed_rects(prims, 8.0), [ax], [ay], 0.5) == []


def test_one_extendable_axis_yields_a_single_flagged_completion():
    """When only ONE axis is missing its end positions, the drawing itself picks
    the extension, so a completion candidate is published — still flagged, still
    unconfirmed, never summed into the count."""
    prims, ax, ay = _synthetic_lattice(5, 4)
    ax_wide = GridAxis("x", [50.0] + list(ax.coords) + [500.0],
                       ["0"] + list(ax.labels) + ["9"])
    g = lattice_groups(closed_rects(prims, 8.0), [ax_wide], [ay], 0.5)[0]
    assert g.count == 20                     # measured stays measured
    assert g.completion_candidate == 4 * 7   # 4 rows x the full 7-line axis
    assert g.needs_review is True
    assert [h.axis for h in g.completion_hypotheses] == ["x"]
    assert all(h.confirmed is False for h in g.completion_hypotheses)


def test_two_extendable_axes_publish_no_completion_at_all():
    """When BOTH axes are missing only their ends, the drawing does not say
    which — so nothing is published. This is the whole product contract: flag,
    do not guess."""
    prims, ax, ay = _synthetic_lattice(5, 4)
    ax_wide = GridAxis("x", [50.0] + list(ax.coords) + [500.0],
                       ["0"] + list(ax.labels) + ["9"])
    ay_wide = GridAxis("y", [50.0] + list(ay.coords) + [500.0],
                       ["Z"] + list(ay.labels) + ["Z2"])
    ay_wide.labels = ["W"] + list(ay.labels) + ["Y"]
    g = lattice_groups(closed_rects(prims, 8.0), [ax_wide], [ay_wide], 0.5)[0]
    assert g.count == 20
    assert g.completion_candidate is None
    assert sorted(h.axis for h in g.completion_hypotheses) == ["both", "x", "y"]
    assert "does NOT determine" in g.review_reason


# ─────────────────────────────────────────────────────────────────────────────
# Crow page 0 — the measured recipe, on the real drawing.
# ─────────────────────────────────────────────────────────────────────────────


@crow_only
def test_crow_page0_grid_axes_come_from_the_printed_bubbles():
    """The lattice is validated against text the DRAWING prints, not a constant.

    Both axes reconcile to the sheet's own printed overall dimensions:
    21 x ~97.5 pt @ 0.5556 ft/pt = 1136'-0", and 7 bands = 350'-0".
    """
    _, page = _crow_page0()
    x_axes, y_axes = grid_axes(page)
    nums = [a for a in x_axes if a.labels == [str(i) for i in range(1, 23)]]
    lets = [a for a in y_axes if a.labels == list("ABCDEFGH")]
    assert nums, "the printed 1..22 gridline row was not recovered"
    assert lets, "the printed A..H gridline column was not recovered"
    printed = page.get_text()
    assert round(nums[0].span_pt * CROW_P0_FPP) == 1136
    assert "1136'" in printed.replace(" ", "") or "1136" in printed
    assert round(lets[0].span_pt * CROW_P0_FPP) == 350
    assert "350" in printed


@crow_only
def test_crow_page0_finds_exactly_one_lattice_of_120_at_full_occupancy():
    """120 markers, one per cell of a 20 x 6 sub-grid, no cell empty, no stray.

    A shape whose positions were predicted by the printed grid and then found.
    NOT 132. The sheet draws 120 and this test exists to keep it that way.
    """
    groups = _crow_lattices()
    assert len(groups) == 1
    g = groups[0]
    assert g.count == 120
    assert (g.n_cols, g.n_rows) == (20, 6)
    assert g.occupancy == 1.0
    assert g.marker_size_pt == (1.44, 1.56)
    assert g.marker_size_in == (9.6, 10.4)          # a 10"-square HSS column
    assert g.evidence["occupied_rows"] == list("BCDEFG")
    assert g.evidence["occupied_cols"] == [str(i) for i in range(2, 22)]
    assert len(set(g.cell_ids)) == 120               # no duplicate cell
    assert g.cell_ids[0] == "B-2" and g.cell_ids[-1] == "G-21"


@crow_only
def test_crow_page0_publishes_no_completion_because_the_drawing_does_not_say():
    """The 120 -> 132 gap stays OPEN, and visibly so.

    INV-B proposed extending the six detected rows across the full 22-line
    number axis (6 x 22 = 132) and was candid that the rule was chosen after
    seeing golden = 132. Re-measured: the occupied block is rows B..G of A..H
    AND columns 2..21 of 1..22 — both axes are missing exactly their two end
    positions, and all four footprint edges carry the same continuous panel
    geometry. Extending numbers gives 132, letters 160, both 176. The drawing
    does not choose, so neither does the engine.
    """
    g = _crow_lattices()[0]
    assert g.completion_candidate is None
    assert g.needs_review is True
    counts = sorted(h.count for h in g.completion_hypotheses)
    assert counts == [132, 160, 176]
    assert all(h.confirmed is False for h in g.completion_hypotheses)
    assert g.count == 120 and g.count not in counts


@crow_only
def test_crow_page0_tick_rows_exist_and_are_rejected():
    """Section 10's 136-mark tick row is really there, and really rejected.

    This is the permanent encoding of the trap: the rejection must come from
    the rows having ONE distinct Y, not from any count filter.
    """
    doc, page = _crow_page0()
    prims = _harvest_primitives(_visible_drawings(page, doc))
    rects = closed_rects(prims, (36.0 / 12.0) / CROW_P0_FPP)
    by_size: dict = {}
    for r in rects:
        by_size.setdefault(
            (round(r[2] - r[0], 2), round(r[3] - r[1], 2)), []
        ).append(r)

    ticks = by_size.get((1.8, 0.72), [])
    joints = by_size.get((1.32, 1.32), [])
    assert len(ticks) >= 100, "the section-10 tick row should still be present"
    for name, marks in (("tick row", ticks), ("panel joints", joints)):
        if not marks:
            continue
        y_span = max(r[1] for r in marks) - min(r[1] for r in marks)
        assert y_span < 1.0, "%s is collinear (yspan %.2f)" % (name, y_span)

    # And the accepted lattice is none of them.
    assert _crow_lattices()[0].marker_size_pt == (1.44, 1.56)


@crow_only
def test_the_lattice_shadows_the_symbol_group_that_was_mislabelled_bollards():
    """The reported "Bollards 56 vs 28" defect is these same columns.

    ``cluster_symbols`` shatters the lattice (a gridline dash unions into the
    marker at 0.805 pt, and the dash phase differs per intersection). The
    largest fragment, SYM-2 with 56 instances, was named Bollards by the
    semantic pass. Those 56 are column markers, so publishing both the lattice
    and the fragment double-counts the drawing.
    """
    doc, page = _crow_page0()
    groups = cluster_symbols(page, CROW_P0_FPP, doc=doc, page_index=0)
    shadowed = lattice_shadowed_symbol_ids(groups, _crow_lattices())
    assert shadowed, "no symbol fragment was recognised as lattice markers"
    by_id = {g.candidate_id: g for g in groups}
    covered = sum(by_id[cid].count for cid in shadowed)
    assert covered >= 50
    assert covered <= 120, "a shadow must never exceed the lattice it duplicates"


@crow_only
def test_shadowing_is_inert_without_a_lattice():
    doc, page = _crow_page0()
    groups = cluster_symbols(page, CROW_P0_FPP, doc=doc, page_index=0)
    assert lattice_shadowed_symbol_ids(groups, []) == []


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline wiring — the lattice has to reach the candidate registry.
# ─────────────────────────────────────────────────────────────────────────────


def _crow_bundle():
    if "bundle" not in _CACHE:
        from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

        doc, _page = _crow_page0()
        pipeline = TakeoffPipeline.__new__(TakeoffPipeline)
        pipeline._project_footprint = None
        pipeline._project_vocab_labels = []
        pipeline._schedules_cache = {}
        _CACHE["bundle"] = pipeline._deterministic_bundle(
            doc[0], doc, str(CROW_PDF), 0, "A-101", "floor_plan"
        )
    return _CACHE["bundle"]


@crow_only
def test_the_lattice_reaches_the_candidate_registry_as_a_counted_candidate():
    bundle = _crow_bundle()
    groups = {g.candidate_id: g for g in bundle["symbol_groups"]}
    assert "LAT-1" in groups, "the lattice never became a candidate"
    lat = groups["LAT-1"]
    assert lat.count == 120
    assert len(lat.instance_bboxes_pt) == 120
    assert lat.needs_review is True, "an undetermined grid end must stay flagged"
    # Its name is NOT invented from the grid labels — an unnamed candidate with
    # 120 positions is a flagged measurement, which is the honest outcome.
    assert lat.contained_texts == []


@crow_only
def test_the_bundle_carries_the_lattice_evidence_and_no_completed_number():
    lattices = _crow_bundle()["grid_lattices"]
    assert len(lattices) == 1
    lat = lattices[0]
    assert lat["count"] == 120
    assert lat["occupancy"] == 1.0
    assert lat["completion_candidate"] is None
    assert sorted(h["count"] for h in lat["completion_hypotheses"]) == [132, 160, 176]
    assert lat["evidence"]["axis_x_labels"] == "1..22"
    assert lat["evidence"]["axis_y_labels"] == "A..H"
    assert len(lat["cell_ids"]) == 120


@crow_only
def test_the_false_56_bollards_fragment_no_longer_reaches_the_report():
    """SYM-2's 56 instances are column markers the semantic pass named Bollards.

    Once the lattice counts them properly the fragment must not ALSO be
    published, or the same 56 drawn objects appear twice under two names.
    """
    ids = {g.candidate_id for g in _crow_bundle()["symbol_groups"]}
    assert "SYM-2" not in ids
    assert "LAT-1" in ids
    # The 136-mark tick row is NOT suppressed — it is not a lattice marker and
    # removing it would be a different (wrong) claim about the drawing.
    assert "SYM-1" in ids


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE — four plan sets, every page. A second fire is a rejection.
# ─────────────────────────────────────────────────────────────────────────────

_FOUR_SET_SCALES = (
    ("crow", "uploads/Crow - Cass White Road-Plans.pdf", 40.0 / 72.0),
    ("bobs", "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf", 8.0 / 72.0),
    (
        "chelsea",
        "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf",
        8.0 / 72.0,
    ),
    (
        "moxy",
        "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
        8.0 / 72.0,
    ),
)


@pytest.mark.generalization
def test_no_lattice_anywhere_else_in_four_sets():
    """One fire, on the right page, with the right answer. Everything else clean.

    Measured over all 83 pages of Moxy, Crow, Bob's and Chelsea — four drafting
    offices, four gridline conventions. The ONLY page that produces a lattice is
    Crow page 0, and it produces 120.

    A change that makes this test report a second fire has broken the detector,
    however much it may improve Crow. That is the rule that killed the Chelsea
    roof-pitch false positive at its root.
    """
    present = [(n, ROOT / p, f) for n, p, f in _FOUR_SET_SCALES if (ROOT / p).exists()]
    if not present:
        pytest.skip("none of the four plan sets are present")

    fires = []
    pages = 0
    for name, path, fpp in present:
        doc = fitz.open(path)
        try:
            for pi in range(doc.page_count):
                pages += 1
                for g in detect_grid_lattices(doc[pi], fpp, doc=doc, page_index=pi):
                    fires.append((name, pi, g.count, g.n_cols, g.n_rows))
        finally:
            doc.close()

    assert pages >= 4
    crow_fires = [f for f in fires if f[0] == "crow"]
    other_fires = [f for f in fires if f[0] != "crow"]
    assert other_fires == [], (
        "the detector fired on a second plan set — REJECTED, do not filter it "
        "away, find the structural reason: %r" % (other_fires,)
    )
    if any(n == "crow" for n, _, _ in present):
        assert crow_fires == [("crow", 0, 120, 20, 6)]
