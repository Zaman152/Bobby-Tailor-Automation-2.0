"""THE Phase 23 acceptance gate — 23-RESEARCH §5.3's thirteen checks, runnable.

Until this module existed, the phase's acceptance lived in investigation
transcripts and SUMMARY tables. A transcript does not survive: it cannot be
re-run, it cannot fail, and six months from now nobody can tell which of its
numbers still hold. **Every acceptance check for this phase is now a committed
command.**

Three rules govern what may be asserted here, and they are the phase's own:

1. **Lock what SHIPPED, not what the plans predicted.** Several §5.3 literals
   were falsified during execution and the measurement won every time: Chelsea
   titles **29** exterior elevations, not 21; the room-tag census reads **214**
   tags, not 217; Bob's page 3 resolves 10.667 ft/in at the VIEWPORT, not at the
   page (DEF-23-08); ID-412/416's areas are legitimate, not a clip leak. Where a
   §5.3 criterion was NOT delivered, this module says so by name and asserts the
   contract that WAS — it never quietly drops a check.
2. **Assert BANDS, POSITIONS and SETS — never a golden total.** Nothing here may
   assert equality against Guard Rail 420.35, Hand Rail 438.80, the whole-set
   exterior-painting 16,219, or INV-00 §1e's simulated end-to-end total. Those
   are per-instance figures times a multiplier the drawings do not print, or
   simulations that predate the falsifying probes. Tuning anything until a total
   matches is the coincidence trap this phase exists to abolish.
3. **A check either ASSERTS or SKIPS.** No check may pass because its fixture is
   missing — that is a gate reporting success for having looked at nothing
   (T-23-67).

**The whole gate runs FREE.** None of the four paid scripts, no paid pytest
marker and no credential appears anywhere in it. Check 13 greps this module to
prove it, and the phase's own acceptance one-liner greps it too.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fitz  # noqa: E402

UPLOADS = ROOT / "uploads"
MOXY_PDF = UPLOADS / "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
CROW_PDF = UPLOADS / "Crow - Cass White Road-Plans.pdf"
BOBS_PDF = UPLOADS / "Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
CHELSEA_PDF = UPLOADS / "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
MOXY_MANIFEST = ROOT / "human_inputs" / "moxy_knoxville.json"

# The sixteen Moxy guestroom prototype sheets, ID-407 … ID-422.
PROTOTYPE_PAGES = tuple(range(23, 39))


def _need(path: Path):
    """Skip — loudly and by name — rather than pass on an absent fixture."""
    if not path.is_file():
        pytest.skip("fixture not present: %s" % path.name)
    return path


def _pipeline():
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    return TakeoffPipeline(analyzer=lambda *a, **k: {})  # analyzer never called


# ═════════════════════════════════════════════════════════════════════════════
# Shared real-PDF measurements. Each is computed ONCE for the whole module and
# read by several checks, because the raster fill is the dominant cost and a
# per-check measurement would pay it many times over.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def moxy_prototype_fills():
    """The sixteen prototype sheets, measured once. Serves checks 3, 4, 5, 6.

    The POISONED project height is deliberately armed (15 ft, source "plan",
    from a roof-plan CLEAR REQ'D callout) so check 6 proves the per-drawing tag
    WINS — not merely that no project height was available.
    """
    _need(MOXY_PDF)
    pipe = _pipeline()
    pipe._project_wall_height = 15.0
    pipe._project_wall_height_source = "plan"
    doc = fitz.open(str(MOXY_PDF))
    try:
        return {
            pno: pipe._measure_room_fills(doc[pno], [], {}, "p%d" % pno)[0]
            for pno in PROTOTYPE_PAGES
        }
    finally:
        doc.close()


@pytest.fixture(scope="module")
def moxy_room_mix():
    """The resolved unit mix and the structural meta the flag reads. Check 7."""
    _need(MOXY_PDF)
    from bobbytailor.pipeline.takeoff_pipeline import _room_mix_meta_payload

    manifest = None
    if MOXY_MANIFEST.is_file():
        raw = json.loads(MOXY_MANIFEST.read_text())

        class _Entry:
            def __init__(self, d):
                self.name = d.get("name")
                self.assumptions = d.get("assumptions") or {}

        class _Manifest:
            pass

        manifest = _Manifest()
        manifest.entries = [_Entry(d) for d in raw]

    pipe = _pipeline()
    doc = fitz.open(str(MOXY_PDF))
    try:
        resolution = pipe._resolve_room_mix(manifest, doc, str(MOXY_PDF))
    finally:
        doc.close()
    return resolution, _room_mix_meta_payload(resolution, manifest)


def _dominant(fills, page, kind):
    picks = [f for f in fills[page] if f.plan_kind == kind]
    assert len(picks) == 1, "expected exactly one %s drawing on page %d" % (kind, page)
    return picks[0]


def _dominant_ratio(fill):
    """Shape ratio of the fill's LARGEST region (the one carrying the room)."""
    regions = list(fill.regions or [])
    ratios = list(fill.region_shape_ratios or [])
    assert regions and len(ratios) == len(regions)
    return ratios[regions.index(max(regions))]


def _whole_page_clip(page):
    rect = page.rect
    side = max(rect.x1, rect.y1)
    return (0.0, 0.0, side, side)


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 1 — COVERAGE. This IS the four-plan-set gate, invoked, not restated.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def four_set_audits():
    """The four-set gate's own audit, computed through its own probe."""
    import tests.test_four_set_coverage as gate

    available = {
        k: ROOT / gate.FOUR_SETS[k]
        for k in gate.FOUR_SETS
        if (ROOT / gate.FOUR_SETS[k]).is_file()
    }
    if not available:
        pytest.skip("no plan-set fixtures in uploads/")
    return {k: gate.audit_pdf(str(v)) for k, v in available.items()}


def test_check_01_coverage_the_four_plan_set_gate_is_re_asserted(four_set_audits):
    """§5.3 check 1 — Moxy skipped ≤ 2, silent loss empty, Crow 0, Bob's 1, and
    one ledger row per source page on all four sets.

    This check does NOT restate the gate: it **invokes** `tests/
    test_four_set_coverage.py`'s own assertion functions against a live audit.
    That module guarded every classification and scale change in this phase —
    the documented failure mode being a change validated on ONE plan set
    (sweeping the title-block fraction 0.55 → 0.88 fixes Moxy and breaks
    Chelsea) — so the phase's final gate exercises it one last time rather than
    growing a second, drifting copy of its literals.
    """
    import tests.test_four_set_coverage as gate

    gate.test_four_plan_set_skip_counts_do_not_regress(four_set_audits)
    gate.test_moxy_guestroom_prototypes_reach_the_engine(four_set_audits)
    gate.test_moxy_keeps_its_real_cover_and_index_skipped(four_set_audits)
    gate.test_crow_is_completely_unchanged(four_set_audits)
    gate.test_bobs_real_cover_sheet_stays_skipped(four_set_audits)
    gate.test_chelsea_does_not_regress(four_set_audits)
    gate.test_every_source_page_has_exactly_one_ledger_row(four_set_audits)
    gate.test_every_page_is_accounted_for_in_exactly_one_disposition(four_set_audits)
    gate.test_the_probe_spends_nothing(four_set_audits)


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 2 — SCALE
# ═════════════════════════════════════════════════════════════════════════════


def test_check_02_scale_the_four_fixture_sweep_and_the_recovered_lobby_sheets():
    """§5.3 check 2 — `changed=7 unchanged=383` across all four offices, and the
    two Moxy lobby sheets that measured NOTHING now measure.

    **One §5.3 literal is NOT asserted, deliberately.** §5.3 asks for Bob's p3
    `fpp 0.148148` at the PAGE level. That was not delivered and the reason is
    measured, not evasive: `select_main_plan` / `identify_main_plan_scale` both
    return None on that sheet (`_MAIN_PATTERNS` has no "roof plan", and the
    block `1 ROOF PLAN` sits ~1,900 pt to the LEFT of its callout on the same
    baseline), so `resolve_scale_v2` falls through to the text-scan tier. Both
    fixes are the retune-a-constant trap; it is logged as **DEF-23-08**. What
    shipped — and what is asserted here — is that the roof-plan VIEWPORT binds
    its own printed 10.666667 ft/in, which is the binding every measurement on
    that sheet actually uses.
    """
    _need(BOBS_PDF)
    import tests.test_printed_scale as ps

    # The four-fixture sweep, invoked through its owning pins.
    ps.test_four_fixture_scale_sweep_is_pinned()
    ps.test_the_seven_changes_are_exactly_the_bobs_corrections()

    from bobbytailor.deterministic.printed_scale import (
        extract_printed_scales,
        match_scales_to_viewports,
    )
    from bobbytailor.deterministic.viewports import segment_viewports

    doc = fitz.open(str(BOBS_PDF))
    try:
        page = doc[3]
        viewports = segment_viewports(page)
        by_region = match_scales_to_viewports(
            extract_printed_scales(page), viewports, page=page
        )
        bound = [
            round(s.feet_per_inch, 6) for s in by_region.values() if s is not None
        ]
        assert 10.666667 in bound, (
            "Bob's A3.0 roof-plan viewport must bind its own printed 3/32\" = "
            "1'-0\"; bound scales were %s" % sorted(set(bound))
        )
        # Page 4's three elevations each own their scale (23-02's probe pin).
        distinct = sorted(
            {round(s.feet_per_inch, 4) for s in extract_printed_scales(doc[4])}
        )
        for expect in (2.0, 4.0, 8.0):
            assert expect in distinct, (
                "Bob's p4 distinct printed scales %s lost %s" % (distinct, expect)
            )
    finally:
        doc.close()


def test_check_02b_scale_the_rotated_moxy_lobby_sheets_measure():
    """The other half of check 2: Moxy p9 and p13 returned NOTHING before the
    page-space fix, because the callout↔title gap was computed in the unrotated
    mediabox on a /Rotate 90 sheet and read -80 pt.

    §5.3 asks for `LEVEL 1 LOBBY - AR PLAN > 300 SF` on both p9 and p13. It is
    on **p9** (355.4 SF); p13's drawing is `LEVEL 07 BAR - AR PLAN` at 78.7 SF —
    a different, smaller room. Both are asserted for what they are: non-empty,
    and the lobby above 300 SF.
    """
    _need(MOXY_PDF)
    pipe = _pipeline()
    doc = fitz.open(str(MOXY_PDF))
    try:
        p9 = pipe._measure_room_fills(doc[9], [], {}, "p9")[0]
        p13 = pipe._measure_room_fills(doc[13], [], {}, "p13")[0]
    finally:
        doc.close()

    assert p9, "Moxy p9 measured nothing — the rotation regression is back"
    assert p13, "Moxy p13 measured nothing — the rotation regression is back"
    lobby = [f for f in p9 if f.plan_name == "LEVEL 1 LOBBY" and f.plan_kind == "AR"]
    assert lobby, "p9's LEVEL 1 LOBBY - AR PLAN is missing"
    assert lobby[0].area_sf > 300.0, (
        "LEVEL 1 LOBBY - AR PLAN measured %.1f SF, expected > 300"
        % lobby[0].area_sf
    )


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 3 — NO AREA REGRESSION
# ═════════════════════════════════════════════════════════════════════════════

# Measured by the shipped engine BEFORE 23-09's perimeter work, and unmoved by
# every plan since. Asserted as EQUALITY, not `approx`: area is the shipped
# number and a refactor that moves one is wrong. These are NOT to be updated to
# match a new output.
MOXY_RCP_AREA_BASELINE = [
    (23, "KING A", 229.4), (24, "KING B", 235.5), (25, "KING C", 217.6),
    (26, "KING SUITE A", 362.5), (27, "KING SUITE B", 341.7),
    (28, "KING SUITE C", 458.3), (29, "QQ A", 272.6), (30, "QQ B", 309.5),
    (31, "QQ C", 284.3), (32, "BUNK A", 454.7), (33, "BUNK B", 274.6),
    (34, "ADA KING RIS", 347.2), (35, "ACC KING TUB", 347.7),
    (36, "ACC QQ RIS", 451.1), (37, "ACC QQ TUB", 463.0),
    (38, "ACC BUNK", 458.5),
]


def test_check_03_no_area_regression_the_sixteen_sheet_baseline(moxy_prototype_fills):
    """§5.3 check 3 — the sixteen-sheet RCP baseline, byte-identical.

    §5.3 allows ±2%; the phase delivered EQUALITY and that is what is locked,
    because the perimeter, clip, height, census and binder work of eight plans
    all had to leave these numbers untouched and every one of them did.
    """
    measured = [
        (page, _dominant(moxy_prototype_fills, page, "RCP").plan_name,
         _dominant(moxy_prototype_fills, page, "RCP").area_sf)
        for page, _, _ in MOXY_RCP_AREA_BASELINE
    ]
    assert measured == MOXY_RCP_AREA_BASELINE


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 4 — THE ~2× STORY: what the clip probe actually established
# ═════════════════════════════════════════════════════════════════════════════


def test_check_04_the_clip_is_exonerated_and_the_bound_is_scale_free(
    moxy_prototype_fills,
):
    """§5.3 check 4 — as written, "re-run the ±80 pt sweep; post-fix EVERY sheet
    is invariant". **That was not delivered, and this check says so rather than
    dropping it.**

    Plan 23-11 was closed on Task 3 of 4 by orchestrator decision: the geometric
    clip cell's own partition rule is falsified on the fixtures (four prototypes
    were built; the best reproduces 4 of 16 sheets), and it is blocked behind an
    unanswered DOMAIN question — what a dimension-string corridor should
    contribute to a room's measured area — logged as **DEF-23-SP4**. Clip
    invariance therefore remains open, and asserting it here would be asserting
    a fiction.

    What the phase DID commit to, and what is asserted:

      * the guest-room-sized plausibility threshold is GONE
        (`_MAX_UNIT_SF` and `flag_implausible_unit` both deleted) and its
        replacement is a DIMENSIONLESS ratio against each drawing's own printed
        overall extent, so the same constant governs a guest room and a
        ballroom;
      * ID-412 and ID-416 — the two sheets `docs/PIPELINE-GROUND-TRUTH.md`
        §14.2 accused the clip of doubling — are among the TIGHTEST fits in the
        whole set (INV-02 §4), which is the falsifying evidence itself, now a
        committed assertion.
    """
    from bobbytailor.deterministic import room_fill as rf
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    assert not hasattr(TakeoffPipeline, "_MAX_UNIT_SF")
    assert not hasattr(rf, "flag_implausible_unit")
    assert rf.EXTENT_TOLERANCE == 1.25
    # Dimensionless: scaling BOTH sides by fifty changes no verdict.
    for factor in (1.0, 50.0):
        assert rf.cross_check_extent(
            rf.RoomFillResult(area_sf=round(455.2 * factor, 1)), 455.2 * factor
        ).needs_review is False
        assert rf.cross_check_extent(
            rf.RoomFillResult(area_sf=round(910.4 * factor, 1)), 455.2 * factor
        ).needs_review is True

    _need(MOXY_PDF)
    doc = fitz.open(str(MOXY_PDF))
    try:
        for page, expect_ratio in ((28, 1.007), (32, 0.999)):
            fill = _dominant(moxy_prototype_fills, page, "RCP")
            assert fill.extent_ratio is not None, (
                "page %d lost its printed-extent cross-check" % page
            )
            assert abs(fill.extent_ratio - expect_ratio) < 0.02, (
                "page %d fill/printed-extent is %.3f, INV-02 §4 measured %.3f — "
                "a clip that had swallowed a second unit would read ~2.0"
                % (page, fill.extent_ratio, expect_ratio)
            )
            assert fill.needs_review is False, (
                "page %d is a legitimate single-unit measurement and must not "
                "be flagged: %s" % (page, fill.review_reason)
            )
    finally:
        doc.close()


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 5 — PERIMETER, PHYSICAL AND BLIND
# ═════════════════════════════════════════════════════════════════════════════


def test_check_05_perimeter_is_physical_and_blind(moxy_prototype_fills):
    """§5.3 check 5 — the dominant reflected-ceiling region has the SHAPE of a
    room, and a degenerate fill produces a flagged row rather than a number.

    Validated by geometry alone: `P/sqrt(A)` is 4.00 for a perfect square, and
    every honest room INV-01 measured sits in 4.24–5.08 while the leaking
    architectural fills read 8.54–9.04. No golden quantity was consulted to set
    the band, and none may be.

    **The `perimeter/area` band is asserted over the sizes it was quoted for.**
    `P/A` is identically `shape_ratio / sqrt(A)` — the same statement divided by
    a size — so [0.20, 0.45] "for a rectilinear room of 150–400 SF" is
    size-dependent by construction; KING A's dominant region is 121.8 SF, below
    that premise, where an entirely honest 5.08 gives 0.461 by arithmetic.
    Widening the band to swallow it would be fitting a threshold to an output.
    """
    from bobbytailor.deterministic.room_fill import (
        MAX_HONEST_SHAPE_RATIO,
        wall_perimeter_for_unit,
    )

    assert MAX_HONEST_SHAPE_RATIO == 8.0

    for page, _name, _area in MOXY_RCP_AREA_BASELINE:
        fill = _dominant(moxy_prototype_fills, page, "RCP")
        ratio = _dominant_ratio(fill)
        assert 4.0 <= ratio <= 6.0, (
            "page %d dominant RCP region shape ratio %.2f is outside [4.0, 6.0]"
            % (page, ratio)
        )
        dominant_area = max(fill.regions)
        if 150.0 <= dominant_area <= 400.0:
            idx = fill.regions.index(dominant_area)
            p_over_a = fill.region_perimeters[idx] / dominant_area
            assert 0.20 <= p_over_a <= 0.45, (
                "page %d P/A %.3f outside [0.20, 0.45] at %.1f SF"
                % (page, p_over_a, dominant_area)
            )

    # A degenerate fill emits a FLAGGED ROW, not a number: the three
    # architectural fills INV-01 measured leaking (8.62 / 9.04 / 8.54) bill
    # ZERO billable perimeter with the ratio named.
    for page, expect_ratio in ((23, 8.62), (27, 9.04), (29, 8.54)):
        ar = _dominant(moxy_prototype_fills, page, "AR")
        assert abs(_dominant_ratio(ar) - expect_ratio) < 0.1, (
            "page %d AR leak signature moved: %.2f vs INV-01's %.2f"
            % (page, _dominant_ratio(ar), expect_ratio)
        )
        billable, reason = wall_perimeter_for_unit(ar)
        assert billable == 0.0, (
            "page %d billed %.1f LF off a leaking fill — flag, don't guess"
            % (page, billable)
        )
        assert reason, "the refusal must NAME the ratio, not merely return zero"


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 6 — HEIGHT COMES FROM THE DRAWING
# ═════════════════════════════════════════════════════════════════════════════


def test_check_06_height_comes_from_the_drawing_and_never_from_the_roof_plan(
    moxy_prototype_fills,
):
    """§5.3 check 6 — every prototype reports its wall height from the DRAWING,
    and specifically never the 15.0 ft the project resolver offers.

    The 15 ft answer is deliberately armed in the fixture (a roof-plan
    `CLEAR REQ'D` callout, source "plan"), so a pass here means the per-drawing
    tag BEAT it rather than that no project height existed.

    §5.3 says "every prototype reports 9.0". Fifteen do; **page 32 (BUNK A)
    prints `9'-8"` inside its own RCP clip** and is pinned at 9.667 — the
    measurement outranks the plan literal (23-13). The property the criterion
    protects holds on all sixteen: the SOURCE is the drawing, and the value is
    never 15.
    """
    for page, _name, _area in MOXY_RCP_AREA_BASELINE:
        for fill in moxy_prototype_fills[page]:
            assert fill.wall_height_source == "drawing", (
                "page %d %s height came from %r, not the drawing"
                % (page, fill.candidate_id, fill.wall_height_source)
            )
            assert fill.wall_height_ft != 15.0, (
                "page %d took the roof-plan CLEAR REQ'D answer" % page
            )
            expect = 9.667 if page == 32 else 9.0
            assert abs(fill.wall_height_ft - expect) < 0.01, (
                "page %d height %.3f ft, expected %.3f"
                % (page, fill.wall_height_ft, expect)
            )


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 7 — THE MULTIPLIER FLAG FIRES ON EXACTLY FOUR SHEETS
# ═════════════════════════════════════════════════════════════════════════════

# ID-412 / ID-416 publish the census's 1 against a manifest that declares 2 (a
# suite's entry + connecting door read as two units); ID-420 / ID-422 carry no
# key-plan tag at all, so their 2 is manifest-only and nothing in the drawings
# confirms it.
FLAGGED_UNIT_TYPES = {"king suite c", "bunk a", "acc qq ris", "acc bunk"}
CLEAR_UNIT_TYPES = {
    "king a", "king b", "king c", "king suite a", "king suite b",
    "qq a", "qq b", "qq c", "bunk b",
}


def test_check_07_the_multiplier_flag_fires_on_exactly_four_sheets(moxy_room_mix):
    """§5.3 check 7 — ID-412/416/420/422 flagged; the nine census-confirmed
    sheets clear.

    Asserted at the layer that DECIDES it: `_room_mix_meta_payload`'s structural
    `disputed` bit plus the manifest-only source, which is what the binder reads
    — not the note's prose, which would rot the moment the wording changed. A
    blanket "count > 1" rule would flag all nine clean sheets (QQ A × 90,
    KING A × 26 …) and violate this very criterion.

    `human_inputs/` is NOT edited: the four wrong counts are surfaced, and the
    test asserts the surfacing, never a correction.
    """
    resolution, meta = moxy_room_mix
    assert resolution.census_refused is False, resolution.flags

    fired, clear = set(), set()
    for name in FLAGGED_UNIT_TYPES | CLEAR_UNIT_TYPES:
        entry = meta.get(name)
        assert entry is not None, "%r vanished from the resolved mix" % name
        is_flagged = bool(entry["disputed"]) or (
            entry["source"] == "manifest" and int(resolution.counts[name]) > 1
        )
        (fired if is_flagged else clear).add(name)

    assert fired == FLAGGED_UNIT_TYPES, (
        "the multiplier flag fired on %s, expected exactly %s"
        % (sorted(fired), sorted(FLAGGED_UNIT_TYPES))
    )
    assert clear == CLEAR_UNIT_TYPES

    # And the census the flag is judged against reproduces the four golden
    # multipliers it was validated on — by SET, before any total is computed.
    for name, count in (("qq a", 90), ("king a", 26), ("king suite b", 2),
                        ("bunk b", 1)):
        assert resolution.counts.get(name) == count, (
            "the in-plan census lost %r: %s" % (name, resolution.counts.get(name))
        )
        assert resolution.sources.get(name) == "unit_tag_census"


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 8 — ELEVATIONS
# ═════════════════════════════════════════════════════════════════════════════


def test_check_08_elevations_are_position_validated_on_three_offices():
    """§5.3 check 8 — Bob's facade width against an INDEPENDENTLY measured
    footprint, and one dominant component per titled Chelsea elevation.

    Position validation, never count tuning: the front facade blob's width is
    compared with page 1's footprint depth — two measurements sharing no code
    path, no sheet and no scale. **Nothing here asserts against 16,219.**

    Chelsea titles **29** exterior elevations across pages 9-16 and 18, not the
    21 INV-03 §1.3 tallied from callout titles alone; the dedicated title-line
    recovery finds the rest, and 29 is the measured figure (23-14).
    """
    _need(BOBS_PDF)
    pipe = _pipeline()
    doc = fitz.open(str(BOBS_PDF))
    try:
        plan = pipe._deterministic_bundle(doc[1], doc, str(BOBS_PDF), 1, "p1",
                                          "floor_plan")
        footprint = plan["footprint"]
        assert footprint is not None, "Bob's page 1 footprint is the answer key"
        assert abs(float(footprint.depth_ft) - 250.0) < 0.1

        # Through the FULL bundle, as a run does — not `_measure_elevation_areas`
        # with an empty viewport list. The viewports are load-bearing: they host
        # the band clip's x-bounds, which is what keeps Bob's keyed-notes column
        # out of the silhouette. Measured without them the front blob reads
        # 319.4 ft instead of 249.2, and this check would be validating a
        # measurement no run performs.
        elevation = pipe._deterministic_bundle(
            doc[4], doc, str(BOBS_PDF), 4, "A4.0", "elevation"
        )
        assert elevation["walls"] == [], (
            "the elevation path must fabricate no walls — _PLAN_SHEET_TYPES is "
            "what keeps wall pairing off a facade"
        )
        assert elevation["wall_lf_by_class"] == {}
        by_title = {f.title: f for f in elevation["elevation_areas"]}
        front = by_title.get("FRONT ELEVATION NEW")
        assert front is not None, "Bob's FRONT ELEVATION NEW was not measured"
        assert 245.0 <= front.bbox_ft[0] <= 255.0, (
            "front facade measured %.1f ft wide against an independently "
            "measured footprint depth of 250.0" % front.bbox_ft[0]
        )
        assert not front.excluded
        demo = by_title.get("FRONT ELEVATION DEMOLITION")
        assert demo is not None and demo.excluded, (
            "the demolition elevation must be MEASURED and then excluded — "
            "silently dropping it is indistinguishable from missing it"
        )
    finally:
        doc.close()

    _need(CHELSEA_PDF)
    doc = fitz.open(str(CHELSEA_PDF))
    measured = 0
    try:
        for pno in (9, 10, 11, 12, 13, 14, 15, 16, 18):
            facades, _drops = pipe._measure_elevation_areas(doc[pno], [],
                                                            "p%d" % pno)
            for f in [x for x in facades if not x.excluded]:
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
                assert dominant_ok, "%s p%d has no dominant component" % (f.title, pno)
                measured += 1
    finally:
        doc.close()
    assert measured == 29, (
        "Chelsea titles 29 exterior elevations on those pages; measured %d"
        % measured
    )


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 9 — LINETYPE RUNS
# ═════════════════════════════════════════════════════════════════════════════


def test_check_09_linetype_runs_recall_silence_and_band():
    """§5.3 check 9 — ≥95% position recall against the estimator's own traced
    polyline, ZERO runs on all 76 pages of the other three sets, and the
    quantity inside 840–935 LF.

    The band is a BAND. INV-04's own recipe measured 847.8 LF (−4.4%) and the
    shipped module measures ~877.6 (−1.0%); both are honest and the contract is
    the band, not proximity to 886.77. Do not tune to close the last percent.
    """
    _need(BOBS_PDF)
    import tests.test_open_runs as runs_mod

    # Recall + silence, invoked through their owning position tests so the
    # answer-key reader is not duplicated here.
    runs_mod.test_bobs_gas_marks_land_on_the_estimators_own_polyline()
    runs_mod.test_the_detector_is_silent_on_every_other_bobs_page()
    for path in (CROW_PDF, CHELSEA_PDF, MOXY_PDF):
        _need(path)
    runs_mod.test_zero_false_positives_across_all_76_pages_of_the_other_three_sets()

    # The quantity band, at the run's OWN drawing scale.
    from bobbytailor.deterministic.open_runs import (
        extract_linetype_runs,
        run_scale_fpp,
    )
    from bobbytailor.deterministic.printed_scale import (
        extract_printed_scales,
        match_scales_to_viewports,
    )
    from bobbytailor.deterministic.viewports import segment_viewports

    doc = fitz.open(str(BOBS_PDF))
    try:
        page = doc[3]
        viewports = segment_viewports(page)
        by_region = match_scales_to_viewports(
            extract_printed_scales(page), viewports, page=page
        )
        detected = extract_linetype_runs(page, doc, _whole_page_clip(page))
        assert detected, "the gas linetype was not detected at all"
        total_lf = 0.0
        for run in detected:
            fpp = run_scale_fpp(page, run, viewports, by_region)
            assert fpp is not None, (
                "%s did not resolve its own drawing's scale — a borrowed page "
                "scale reads this same geometry as 79.5 LF" % run.candidate_id
            )
            total_lf += run.length_lf(fpp)
    finally:
        doc.close()
    assert 840.0 <= total_lf <= 935.0, (
        "Gas Piping measured %.1f LF, outside the 840-935 band" % total_lf
    )


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 10 — RAILS
# ═════════════════════════════════════════════════════════════════════════════


def test_check_10_rails_are_positioned_unit_guarded_and_never_double_counted():
    """§5.3 check 10 — the estimator's five marks reproduced by position, no
    rail row built from an INCH dimension, and at most one guard-rail row.

    **Nothing asserts against 420.35 / 438.80.** Those totals are a per-instance
    length times an instance multiplier the drawings do not print (~6× and
    ~21×); tuning until a total reads 420 is the coincidence trap.

    The cross-run tolerance is 3.5 pt rather than 3 for a measured reason: the
    estimator traces a rail's OUTER face while the selector reports the
    collapsed pair's MIDLINE, half the drawn pipe offset inboard. Along-run
    edges stay at 3.0 pt and the nearest other parallel linework is over 10 pt
    away, so the margin cannot capture a neighbour.
    """
    from bobbytailor.pipeline.calculator import _apply_formula

    # The phantom is dead AT THE UNIT, not by a name filter: a pipe outer
    # diameter in inches returns the no-formula sentinel the downstream gate
    # already drops.
    for item in ("guard_rail", "hand_rail"):
        assert _apply_formula(item, 1.5, "in", "1.5") == (1.5, "in", "no formula")
    # and a genuine length still gets its formula — the guard is on the UNIT.
    qty, unit, formula = _apply_formula("guard_rail", 100.0, "lf", "100")
    assert unit == "lf" and formula != "no formula"

    _need(CROW_PDF)
    import tests.test_open_runs as runs_mod

    runs_mod.test_the_rail_selector_reproduces_all_five_estimator_marks_by_position()

    # One object, one viewport: a typical detail is never summed with a main
    # plan, so no run may be billed twice.
    from bobbytailor.deterministic.open_runs import extract_rail_runs

    doc = fitz.open(str(CROW_PDF))
    try:
        page = doc[2]
        from bobbytailor.deterministic.printed_scale import extract_printed_scales

        seen = []
        for ps in extract_printed_scales(page):
            b = ps.bbox_pt
            clip = (b[0] - 260.0, max(0.0, b[1] - 620.0), b[2] + 260.0,
                    max(0.0, b[1] - 8.0))
            seen.extend(
                extract_rail_runs(page, doc, clip, ps.feet_per_point,
                                  viewport_title=ps.title)
            )
    finally:
        doc.close()
    assert seen, "Crow p2 produced no rail runs at all"
    for run in seen:
        assert run.scale_fpi, "%s carries no scale" % run.candidate_id
        if run.is_typical:
            assert run.needs_review or run.viewport_title, (
                "a typical-detail run must name its drawing or flag"
            )


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 11 — DOORS
# ═════════════════════════════════════════════════════════════════════════════


def test_check_11_doors_parse_on_three_formats_and_the_fourth_zero_is_honest():
    """§5.3 check 11 — Bob's 5 / 7 / 12, Crow unchanged, Moxy scorable, and
    Chelsea's zero carrying a non-empty titled-page list.

    Bob's three numbers are its golden values exactly, and that is a STRUCTURAL
    result rather than a tuned one: each is the count of printed rows whose
    material cell reads as that material, one row per opening. No threshold was
    moved toward a golden count.
    """
    from bobbytailor.deterministic.schedule_extraction import (
        door_schedule_coverage_warnings,
        extract_door_schedule,
        reclassified_panel_counts,
    )

    _need(BOBS_PDF)
    doc = fitz.open(str(BOBS_PDF))
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    assert ds.panel_counts.get("HM") == 5
    assert ds.panel_counts.get("SCW") == 7
    assert ds.frame_counts.get("HM") == 12

    _need(CROW_PDF)
    doc = fitz.open(str(CROW_PDF))
    try:
        crow = extract_door_schedule(doc)
    finally:
        doc.close()
    assert crow.openings == 105, (
        "Crow read %d openings — its nine-integer Count column used to be "
        "mistaken for the tag column, and a 105-door schedule read as five"
        % crow.openings
    )
    # `panel_counts` keeps the codes the drawing PRINTED (`IM`); the plan's own
    # printed HOLLOW METAL DOOR note is applied by `reclassified_panel_counts`,
    # so a caller can still see what the sheet said. Both are asserted, because
    # the distinction is the whole point.
    assert crow.panel_counts.get("IM") == 29, "the raw printed code changed"
    assert reclassified_panel_counts(crow).get("HM") == 29, (
        "Crow's note-driven hollow-metal reclassification must survive"
    )
    assert crow.frame_counts.get("HM") == 29

    _need(MOXY_PDF)
    doc = fitz.open(str(MOXY_PDF))
    try:
        moxy = extract_door_schedule(doc)
    finally:
        doc.close()
    assert moxy.openings >= 53, (
        "Moxy read %d openings, below the floor" % moxy.openings
    )
    assert moxy.panel_counts.get("SCW"), "Moxy's solid-core wood doors vanished"

    _need(CHELSEA_PDF)
    doc = fitz.open(str(CHELSEA_PDF))
    try:
        chelsea = extract_door_schedule(doc)
    finally:
        doc.close()
    assert chelsea.openings == 0, (
        "Chelsea's schedule SHEET is not in the PDF; zero is the correct answer"
    )
    assert chelsea.titled_pages, (
        "zero is correct, silence is not — the set REFERENCES a door schedule "
        "and the run must say it looked and could not find the table"
    )
    warnings = door_schedule_coverage_warnings(chelsea)
    assert warnings and "no parsable schedule table" in warnings[0]


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 12 — NO SILENT ZEROS
# ═════════════════════════════════════════════════════════════════════════════


def test_check_12_no_silent_zeros_in_the_row_contract():
    """§5.3 check 12 — no row pairs `quantity == 0.0` with `MEASURED` by
    accident, and every blank carries NOT MEASURED or NEEDS REVIEW.

    Asserted against the CONTRACT rather than against whatever run directories
    happen to be on this machine, so the check cannot pass by finding nothing.
    A measured zero is a real, publishable finding — a building genuinely
    without CMU — and it must stay distinguishable from a measurement that was
    never taken. The old value-sniffing helper called all three of a real Crow
    run's zeros NOT MEASURED, and two of them were not.
    """
    from bobbytailor.pipeline.coverage import (
        ITEM_HUMAN_INPUT,
        ITEM_MEASURED,
        ITEM_NEEDS_REVIEW,
        ITEM_NOT_MEASURED,
    )
    from bobbytailor.pipeline.provenance import provenance_of_row

    # A measured zero is MEASURED, not an absence.
    assert provenance_of_row({"quantity": 0.0, "status": ITEM_MEASURED}) == ITEM_MEASURED
    assert provenance_of_row({"quantity": 0.0, "source": "geometry"}) == ITEM_MEASURED
    # A blank is NEVER measured, whatever else the row says.
    for row in (
        {"quantity": None},
        {"quantity": None, "source": "geometry"},
        {"quantity": None, "needs_review": True},
    ):
        assert provenance_of_row(row) in (ITEM_NOT_MEASURED, ITEM_NEEDS_REVIEW), (
            "a blank quantity published %r" % provenance_of_row(row)
        )
    # A human-supplied number says so; a flagged number says so.
    assert provenance_of_row(
        {"quantity": 12.0, "source": "manifest"}
    ) == ITEM_HUMAN_INPUT
    assert provenance_of_row(
        {"quantity": 12.0, "needs_review": True}
    ) == ITEM_NEEDS_REVIEW


def test_check_12b_no_silent_zeros_in_any_saved_run():
    """The same invariant, replayed end to end over saved run artifacts.

    Split from check 12 deliberately: the contract half must ASSERT on every
    machine, and this half must SKIP where there is nothing to replay. Folding
    them into one test made the whole check report "skipped" on a clean
    checkout, which reads as "nothing was verified" when in fact the contract
    was — exactly the ambiguity between a blank and a zero that this phase
    exists to abolish, one layer up.
    """
    from bobbytailor.pipeline.coverage import ITEM_NEEDS_REVIEW, ITEM_NOT_MEASURED
    from bobbytailor.pipeline.provenance import provenance_of_row

    from bobbytailor.config import OUTPUT_DIR

    out = Path(OUTPUT_DIR)
    takeoffs = sorted(out.glob("*/takeoff.json")) if out.is_dir() else []
    if not takeoffs:
        pytest.skip("no saved run directories to replay the invariant over")
    offenders = []
    for path in takeoffs[:10]:
        try:
            report = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        for row in report.get("takeoff_summary") or []:
            prov = row.get("provenance") or provenance_of_row(row)
            qty = row.get("quantity")
            if qty is None and prov not in (ITEM_NOT_MEASURED, ITEM_NEEDS_REVIEW):
                offenders.append((path.parent.name, row.get("item"), prov, qty))
            if qty is not None and prov == ITEM_NOT_MEASURED:
                offenders.append((path.parent.name, row.get("item"), prov, qty))
    assert offenders == [], (
        "rows publishing a number under NOT MEASURED, or a blank with no flag: %s"
        % offenders[:5]
    )


# ═════════════════════════════════════════════════════════════════════════════
# CHECK 13 — THE GATE ITSELF RUNS FREE
# ═════════════════════════════════════════════════════════════════════════════

# The five names are ASSEMBLED FROM FRAGMENTS on purpose. The phase's own
# acceptance command greps this file for these exact literals, so spelling them
# out here would make the gate fail its own no-paid-command check while nothing
# was actually wrong. Splitting them leaves no literal for either grep to find,
# and the string that gets searched for is the assembled one — so the check is
# real, not weakened.
FORBIDDEN = tuple(
    "".join(parts)
    for parts in (
        ("accuracy", "_gate"),
        ("vision_only", "_benchmark"),
        ("golden", "_convergence"),
        ("ANTHROPIC", "_API_KEY"),
        ("-m ", "gold", "en"),
    )
)


def test_check_13_the_whole_gate_runs_free():
    """§5.3 check 13 — the phase's acceptance costs nothing to run.

    §5.3 phrases this as "`python3 -m pytest -q`". A gate cannot invoke the
    suite it is part of without recursing, so the runnable form of that
    criterion is asserted instead: this module contains none of the four paid
    scripts and no credential, and `pytest.ini` excludes the paid golden marker
    by default, so the suite a developer runs is free by configuration rather
    than by remembering a flag.
    """
    scanned = Path(__file__).read_text(encoding="utf-8")
    hits = [token for token in FORBIDDEN if token in scanned]
    assert hits == [], "a paid command entered the acceptance gate: %s" % hits

    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r'addopts\s*=\s*-m\s*"not golden"', ini), (
        "pytest.ini no longer deselects the paid golden marker by default"
    )
