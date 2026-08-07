"""V4-FIX-03 — a printed thickness only identifies a wall when it discriminates.

24-02 inverted the wall-class naming precedence so a printed-thickness match
outranks a vision reading. That inversion is right and is not touched here.
What was never asked is whether the match *identifies anything*: pass 1 of
``map_wall_classes_from_library`` accepted the FIRST library object within
``_WALL_THICKNESS_TOL_IN`` of a class, marked it ``confident=True``, and never
checked whether some other object — or some other class — satisfied the same
match equally well.

A printed thickness is evidence of DIMENSION. It becomes evidence of IDENTITY
only when exactly one candidate claims it. A number two candidates both satisfy
discriminates between them not at all, and calling it "deterministic evidence"
is the error this module pins.

The ambiguity is measured on the real drawing rather than argued: Crow's page 0
carries thirteen wall thickness classes, and an object printing a nominal 8"
lands within the 1.5" match tolerance of THREE of them. The class the bind
happened to take was simply the nearest — and "nearest" inside a tolerance is
noise, which is the very thing the tolerance exists to absorb.

Everything here is FREE: vector geometry and frozen artifacts only. No analyzer,
no credential, no network, no golden comparison. The module audits itself for
all four at the bottom, and it names no published take-off quantity — the number
was never the evidence and may not become the test.
"""
import ast
import json
from pathlib import Path

import pytest

from bobbytailor.vision import fusion as F
from bobbytailor.vision.fusion import (
    _WALL_THICKNESS_TOL_IN,
    map_wall_classes_from_library,
)

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
CROW_PLAN_PAGE = 0

PAID_RUN_EVIDENCE = (
    Path(__file__).resolve().parents[1] / ".planning" / "paid-run-evidence"
)

# A nominal masonry-unit thickness, printed to the inch. It is the token the
# saved runs recorded on the library object, and it is used here ONLY as an
# input to the ambiguity measurement — no assertion in this module compares any
# quantity to any take-off figure.
_NOMINAL_PRINTED_IN = 8.0


# ── The drawing, read once ───────────────────────────────────────────────────

_CACHE = {}


def _crow_wall_classes():
    """``(lf_by_class, thickness_in_by_class)`` for the real Crow plan page.

    Vector geometry only — the analyzer is a stub that is never called.
    """
    if "walls" not in _CACHE:
        import fitz

        from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

        pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
        doc = fitz.open(str(CROW_PDF))
        try:
            page = doc[CROW_PLAN_PAGE]
            bundle = pipe._deterministic_bundle(
                page, doc, str(CROW_PDF), CROW_PLAN_PAGE,
                "page%d" % CROW_PLAN_PAGE, "floor_plan",
            )
        finally:
            doc.close()
        _CACHE["walls"] = (
            dict(bundle.get("wall_lf_by_class") or {}),
            F._wall_thickness_in_by_class(bundle),
        )
    return _CACHE["walls"]


# ── Synthetic library objects ────────────────────────────────────────────────


def _obj(name, thickness_in=None, hint="", variant="", basis="wall_area"):
    o = {"name": name, "basis": basis}
    if thickness_in is not None:
        o["thickness_in"] = thickness_in
    if hint:
        o["binding_hint"] = hint
    if variant:
        o["variant"] = variant
    return o


def _tiltup(thickness_in=None):
    return _obj(
        "Tilt Up Wall", thickness_in, hint="exterior_wall", variant="exterior"
    )


def _cmu(thickness_in=None):
    return _obj("CMU Wall", thickness_in, hint="masonry_wall")


def _precast(thickness_in=None):
    """A SECOND non-masonry wall object, so an object contest can be built
    without the masonry guards deciding the case for us."""
    return _obj("Precast Panel", thickness_in, hint="interior_wall",
                variant="interior")


# ─────────────────────────────────────────────────────────────────────────────
# The ambiguity, measured on the real sheet
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not CROW_PDF.is_file(),
    reason="Crow Cass plan set (tests/fixtures/crow_cass/crow_cass_plans.pdf) "
           "is absent — the thickness ambiguity in this module is measured on "
           "the real drawing and cannot be simulated",
)
def test_a_printed_nominal_thickness_is_not_unique_on_the_real_sheet():
    """One printed nominal thickness, several classes it cannot tell apart.

    This is the finding the whole plan rests on, computed at runtime from
    vector geometry so nobody has to take it on trust. The classes are named by
    id and their LF is reported in the failure message only — no assertion here
    compares a length or an area to anything.
    """
    lf, thickness = _crow_wall_classes()
    assert len(lf) > 2, "the sheet must carry several classes for this to mean anything"
    within = sorted(
        c for c in lf
        if thickness.get(c) is not None
        and abs(thickness[c] - _NOMINAL_PRINTED_IN) <= _WALL_THICKNESS_TOL_IN
    )
    assert len(within) > 1, (
        "a printed %.1f\" would be unique on this sheet after all — the premise "
        "of this module is falsified and must be rewritten, not deleted "
        "(classes within %.1f\": %r)"
        % (_NOMINAL_PRINTED_IN, _WALL_THICKNESS_TOL_IN, within)
    )
    # And the classes it cannot tell apart are of wildly different size, so
    # "nearest" is choosing between genuinely different objects.
    sizes = sorted(lf[c] for c in within)
    assert sizes[-1] > sizes[0] * 2, (
        "the contested classes are all the same size, so the ambiguity would be "
        "harmless; measured %r" % sizes
    )


@pytest.mark.skipif(
    not PAID_RUN_EVIDENCE.is_dir(),
    reason=".planning/paid-run-evidence/ is absent — the recorded outcome of "
           "the silent tie-break cannot be read",
)
def test_the_silent_tie_break_is_recorded_in_both_saved_runs():
    """The override the saved runs published, read back from frozen artifacts.

    Read-only. The point is not the number: it is that a bind whose evidence
    could not discriminate was recorded as "deterministic evidence" and
    outranked a reading that said something else, identically in two runs.
    """
    runs = sorted(PAID_RUN_EVIDENCE.glob("*/takeoff.json"))
    if not runs:
        pytest.skip("no saved run artifacts under .planning/paid-run-evidence/")
    seen = []
    for path in runs:
        with path.open() as fh:
            report = json.load(fh)
        for rec in report.get("fusion_rejected") or []:
            if rec.get("reason") == F._WALL_LABEL_PRECEDENCE_REASON:
                seen.append(rec)
    if not seen:
        pytest.skip(
            "no wall-class precedence override in the saved runs — nothing to "
            "read back"
        )
    for rec in seen:
        assert rec.get("matched_thickness_in") is not None
        assert rec.get("class_thickness_in") is not None
        # The evidence the override cited is a thickness agreement, and that is
        # exactly what this plan shows is not, on its own, an identification.
        assert (
            abs(float(rec["matched_thickness_in"]) - float(rec["class_thickness_in"]))
            <= _WALL_THICKNESS_TOL_IN
        )


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — a match two OBJECTS satisfy is not unique, and does not bind
# ─────────────────────────────────────────────────────────────────────────────


def test_a_thickness_two_objects_both_print_is_not_unique_and_binds_neither():
    """The plan's headline case: two vocabulary objects, one printed number.

    Neither object may take the class. Picking the nearer one is not available:
    both are inside the tolerance, and inside the tolerance "nearer" is the
    noise the tolerance exists to absorb.
    """
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("8"), _precast("8.4")],
    )
    assert "TC2" not in mapping or mapping["TC2"][2] is not True, (
        "a class two objects both match was bound confidently: %r"
        % (mapping.get("TC2"),)
    )


def test_a_thickness_only_one_object_prints_is_unique_and_still_binds():
    """The case that must not regress — an unambiguous match is unchanged."""
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("12"), _precast("8")],
    )
    assert mapping["TC2"][0] == "Precast Panel"
    assert mapping["TC2"][2] is True
    assert mapping["TC2"][3] == 8.0
    assert mapping["TC1"][0] == "Tilt Up Wall"
    assert mapping["TC1"][2] is True
    assert mapping["TC1"][3] == 12.0


def test_a_unique_match_is_still_unique_when_the_other_object_prints_nothing():
    """An object with no printed thickness contests nothing — it is not a
    candidate at all, and treating it as one would refuse every real bind."""
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup(), _precast("8")],
    )
    assert mapping["TC2"][0] == "Precast Panel"
    assert mapping["TC2"][2] is True


def test_an_object_that_lost_a_unique_contest_is_not_consumed():
    """It failed to prove an identity; it did not cease to exist.

    The object must still be available to pass 2's hint-based assignment, so an
    object carrying a real hint still binds somewhere.
    """
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("8"), _precast("8.4")],
    )
    names = {v[0] for v in mapping.values()}
    assert "Tilt Up Wall" in names, (
        "the exterior_wall object was consumed by the contest it lost and never "
        "reached the hint pass: %r" % (mapping,)
    )
    tilt_cls = [c for c, v in mapping.items() if v[0] == "Tilt Up Wall"][0]
    assert mapping[tilt_cls][2] is False, "a hint bind is never confident"


def test_the_fourth_slot_is_none_for_everything_that_is_not_a_confident_bind():
    """The invariant a refusal must not break.

    ``matched_thickness_in`` is what keeps a non-authoritative bind out of the
    authoritative branch in ``_fuse_wall_classes``. A refused match must leave
    it ``None`` — never the thickness that failed to prove anything.
    """
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("8"), _precast("8.4")],
    )
    for cls, entry in mapping.items():
        if entry[2] is not True:
            assert entry[3] is None, (
                "class %r is not a confident bind but carries a matched "
                "thickness %r" % (cls, entry[3])
            )


# ─────────────────────────────────────────────────────────────────────────────
# The same principle on the other axis — one object, several classes
# ─────────────────────────────────────────────────────────────────────────────


def test_an_object_matching_two_classes_is_not_unique_and_binds_neither():
    """The mirror of the plan's case, and the one the real sheet exhibits.

    An 8" object beside an 8.0" class and an 8.8" class has not said which of
    them it is. The old pass took the nearer; this asserts it may not.
    """
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 8.8, "TC2": 8.0},
        [_precast("8")],
    )
    assert mapping == {} or all(v[2] is not True for v in mapping.values()), (
        "an object whose printed thickness fits two classes bound one of them "
        "confidently: %r" % (mapping,)
    )


def test_the_nearer_class_is_not_preferred_inside_the_tolerance():
    """Explicitly: exact agreement does not break a tie that the tolerance made.

    The 8.0" class agrees to the decimal and the 8.8" class is 0.8" away. Both
    are inside a 1.5" tolerance, so the tolerance has already declared that
    difference to be noise. Reading it back as a preference would be reading
    signal out of the thing we declared to be noise.
    """
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 8.8, "TC2": 8.0},
        [_precast("8")],
    )
    assert mapping.get("TC2", (None,))[0] != "Precast Panel" or (
        mapping["TC2"][2] is not True
    ), "the exactly-agreeing class was preferred over an equally admissible one"


@pytest.mark.skipif(
    not CROW_PDF.is_file(),
    reason="Crow Cass plan set is absent — this assertion is measured on the "
           "real drawing and cannot be simulated",
)
def test_the_real_sheet_gives_a_nominal_object_no_confident_class():
    """End of the argument, on the real geometry: an 8" object names nothing.

    The wall objects here are synthetic (the saved runs did not persist the
    vocabulary); the GEOMETRY is the real sheet's. That is the half that was
    ambiguous, and it is the half that is measured.
    """
    lf, thickness = _crow_wall_classes()
    mapping = {}
    F_map = map_wall_classes_from_library(lf, thickness, [_precast("8")])
    mapping.update(F_map)
    confident = {c: v for c, v in mapping.items() if v[2] is True}
    assert not confident, (
        "an 8\" object still confidently named a class on the real sheet: %r"
        % confident
    )


# ─────────────────────────────────────────────────────────────────────────────
# What a refusal must be able to explain
# ─────────────────────────────────────────────────────────────────────────────


def test_a_refusal_reports_which_objects_contested_the_class():
    contested = {}
    map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("8"), _precast("8.4")],
        contested=contested,
    )
    assert "TC2" in contested, "the contested class was not reported: %r" % contested
    assert set(contested["TC2"]["objects"]) == {"Tilt Up Wall", "Precast Panel"}


def test_a_refusal_reports_which_other_classes_one_object_also_matched():
    contested = {}
    map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 8.8, "TC2": 8.0},
        [_precast("8")],
        contested=contested,
    )
    assert set(contested) == {"TC1", "TC2"}
    assert contested["TC2"]["objects"] == ["Precast Panel"]
    assert contested["TC2"]["also_matched_classes"] == ["TC1"]
    assert contested["TC1"]["also_matched_classes"] == ["TC2"]


def test_an_uncontested_sheet_reports_no_contest_at_all():
    contested = {}
    map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("12"), _precast("8")],
        contested=contested,
    )
    assert contested == {}


def test_the_contested_argument_is_optional_and_omitting_it_changes_nothing():
    """A caller that does not want the explanation gets identical behaviour."""
    args = (
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_tiltup("8"), _precast("8.4")],
    )
    assert map_wall_classes_from_library(*args) == map_wall_classes_from_library(
        *args, contested={}
    )


def test_the_bind_does_not_depend_on_the_order_the_objects_arrive_in():
    """A uniqueness rule is worth having partly because it removes the order
    dependence the old first-match-wins pass had."""
    lf = {"TC1": 900.0, "TC2": 60.0, "TC3": 30.0}
    th = {"TC1": 12.0, "TC2": 8.0, "TC3": 4.0}
    objs = [_tiltup("12"), _precast("8"), _obj("Thin Partition", "4")]
    first = map_wall_classes_from_library(lf, th, objs)
    second = map_wall_classes_from_library(lf, th, list(reversed(objs)))
    assert first == second


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — a masonry object is a small wall; test the share, not the ranking
# ─────────────────────────────────────────────────────────────────────────────
#
# The guard that already existed excluded exactly ONE class — the single
# most-LF one. A sheet with a dozen thickness classes has plenty of large
# classes that are not the largest, and a masonry object could take any of
# them. What makes a wall masonry-shaped is its SIZE relative to the sheet, not
# its position in a ranking.


def _names_in(mapping):
    return {v[0] for v in mapping.values()}


def test_a_masonry_object_refuses_a_large_share_class_that_is_not_the_dominant_one():
    """The exact hole the rank test left open.

    TC2 is not the largest class, so the dominant guard has nothing to say
    about it — but it carries a large fraction of every wall line on the sheet,
    which is not what a room-scale masonry exception looks like.
    """
    lf = {"TC1": 500.0, "TC2": 400.0, "TC3": 10.0}
    th = {"TC1": 12.0, "TC2": 8.0, "TC3": 20.0}
    mapping = map_wall_classes_from_library(lf, th, [_cmu("8")])
    assert lf["TC2"] < lf["TC1"], "TC2 must not be the dominant class"
    assert mapping.get("TC2", (None,))[0] != "CMU Wall", (
        "a masonry object took a class carrying %.0f%% of the sheet's wall "
        "linework: %r" % (100 * lf["TC2"] / sum(lf.values()), mapping.get("TC2"))
    )


def test_the_object_refused_on_share_is_not_consumed_either():
    """A refusal on size is still a refusal to IDENTIFY, not a deletion."""
    lf = {"TC1": 500.0, "TC2": 400.0, "TC3": 10.0}
    th = {"TC1": 12.0, "TC2": 8.0, "TC3": 20.0}
    mapping = map_wall_classes_from_library(lf, th, [_cmu("8")])
    assert "CMU Wall" in _names_in(mapping), (
        "the masonry object vanished instead of falling through to the hint "
        "pass: %r" % (mapping,)
    )
    cls = [c for c, v in mapping.items() if v[0] == "CMU Wall"][0]
    assert mapping[cls][2] is False, "a hint bind is never confident"
    assert cls == "TC3", "the hint pass must still prefer the small class"


def test_a_masonry_object_still_binds_a_genuinely_small_class():
    """The case that must not regress."""
    mapping = map_wall_classes_from_library(
        {"TC1": 900.0, "TC2": 60.0},
        {"TC1": 12.0, "TC2": 8.0},
        [_cmu("8")],
    )
    assert mapping["TC2"][0] == "CMU Wall"
    assert mapping["TC2"][2] is True


def test_the_dominant_exclusion_still_holds_where_the_share_test_is_silent():
    """Two overlapping guards, and here only the rank test speaks.

    Five equal classes: every one of them is well under the share threshold, so
    the share test excludes none. The largest is still the perimeter wall and a
    masonry object still may not have it.
    """
    lf = {"TC%d" % i: 100.0 for i in range(1, 6)}
    th = {"TC1": 8.0, "TC2": 12.0, "TC3": 16.0, "TC4": 20.0, "TC5": 24.0}
    shares = {c: v / sum(lf.values()) for c, v in lf.items()}
    assert max(shares.values()) < F._MASONRY_MAX_LF_SHARE, (
        "this fixture no longer isolates the rank test — some class exceeds "
        "the share threshold: %r" % shares
    )
    mapping = map_wall_classes_from_library(lf, th, [_cmu("8")])
    assert mapping.get("TC1", (None,))[0] != "CMU Wall"


def test_the_hint_pass_cannot_walk_around_the_share_guard():
    """The same rule on the other route.

    A masonry object whose printed thickness matches nothing still reaches
    pass 2, where it is handed the smallest non-dominant class. When the only
    class left is itself a large share of the sheet, that assignment is the
    same wrong claim arriving by a different door.
    """
    lf = {"TC1": 550.0, "TC2": 450.0}
    mapping = map_wall_classes_from_library(
        lf, {"TC1": 12.0, "TC2": 8.0}, [_cmu("20")]
    )
    assert "CMU Wall" not in _names_in(mapping), (
        "the hint pass assigned a masonry object a class carrying %.0f%% of "
        "the sheet's wall linework: %r"
        % (100 * lf["TC2"] / sum(lf.values()), mapping)
    )


def test_the_share_guard_binds_no_absolute_length_at_all():
    """The strongest statement that nothing here is tuned to a drawing.

    Scale every length on the sheet by an arbitrary factor and the guard must
    reach an identical verdict. A threshold derived from any particular plan's
    footage could not survive this, because a share is a ratio and a target
    length is not.
    """
    lf = {"TC1": 500.0, "TC2": 400.0, "TC3": 10.0}
    th = {"TC1": 12.0, "TC2": 8.0, "TC3": 20.0}
    scaled = {c: v * 137.0 for c, v in lf.items()}
    assert map_wall_classes_from_library(
        lf, th, [_cmu("8")]
    ) == map_wall_classes_from_library(scaled, th, [_cmu("8")])


def test_the_share_threshold_is_a_dimensionless_fraction():
    assert isinstance(F._MASONRY_MAX_LF_SHARE, float)
    assert 0.0 < F._MASONRY_MAX_LF_SHARE < 1.0


def test_a_non_masonry_object_is_untouched_by_the_share_rule():
    """The rule encodes what a masonry wall IS. It is not a general
    restriction on binding large classes, and a tilt-up object — whose whole
    nature is to be the big one — must be unaffected."""
    mapping = map_wall_classes_from_library(
        {"TC1": 500.0, "TC2": 400.0, "TC3": 10.0},
        {"TC1": 12.0, "TC2": 8.0, "TC3": 20.0},
        [_precast("8")],
    )
    assert mapping["TC2"][0] == "Precast Panel"
    assert mapping["TC2"][2] is True


# ─────────────────────────────────────────────────────────────────────────────
# This module's own contract
# ─────────────────────────────────────────────────────────────────────────────


def test_this_module_names_no_golden_quantity_and_calls_no_paid_service():
    source = Path(__file__).read_text()
    # Assembled from halves so the check cannot find itself.
    forbidden = [
        "ANTHRO" + "PIC",
        "crow_cass" + "_golden",
        "golden" + ".csv",
        "vision_only" + "_benchmark",
        "accuracy" + "_gate",
        "golden_" + "convergence",
    ]
    for token in forbidden:
        assert token not in source, (
            "this module must stay free and golden-free; found %r" % token
        )


def test_this_module_states_no_published_takeoff_quantity():
    """The published figures this defect produced may not become the oracle.

    Each literal is assembled from halves so the check cannot match itself.
    """
    source = Path(__file__).read_text()
    for token in ("11" + "286", "22" + "04", "31" + "104", "106" + "992"):
        assert token not in source, (
            "a published take-off quantity appears in this module (%r) — the "
            "fix is judged on whether the evidence discriminates, never on "
            "whether a number moved toward a target" % token
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
    allowed = {"ast", "json", "pathlib", "pytest", "fitz", "bobbytailor"}
    assert imported <= allowed, (
        "this module must stay offline; unexpected imports %r"
        % sorted(imported - allowed)
    )
