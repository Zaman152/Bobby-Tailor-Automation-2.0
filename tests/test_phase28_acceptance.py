"""THE Phase 28 acceptance gate — the phase's five requirements, runnable.

Phase 28 is the accuracy-remediation phase: five defects the two saved paid Crow
runs exposed, four fixes and one disclosure. Until this module existed its
acceptance lived in six SUMMARY documents. A summary cannot be re-run and cannot
fail. This module inherits the three rules ``test_phase23_acceptance.py`` wrote
and ``test_phase24_acceptance.py`` restated, in this phase's terms.

1. **Lock what SHIPPED, not what the plans predicted.** Four of this phase's six
   plans measured one of their own premises to be FALSE and implemented the
   truth instead. Every one of those corrections is a committed assertion here,
   named, rather than a paragraph somebody skims. Two requirements are
   deliberately NOT ticked, and the reason each is not ticked is itself a check.
2. **Assert BANDS, POSITIONS, SETS and RELATIONS — never a golden total.**
   Nothing here may compare a published quantity to Crow's take-off figures.
   Reaching a number by filtering until it matches is the coincidence trap this
   project has paid for twice, and this phase exists to end it.
3. **A check either ASSERTS or SKIPS BY NAME.** No check may pass because a
   fixture was missing. The one inversion is deliberate: the paid-run evidence
   check FAILS rather than skips, because a skip would let a cleanup delete
   irreplaceable evidence unnoticed.

**Invoked, not restated.** Where a plan of this phase already owns a check, this
gate calls that module's own assertion function against a live subject rather
than growing a second, drifting copy of its literals. The census below proves
every module this phase added was actually CONSULTED — presence is not
consumption — and asserts the intended set and the invoked set are equal in both
directions, so a gate that intends seven and invokes six goes red.

A NOTE ON WHEN THIS GATE WAS WRITTEN
------------------------------------
This module was written a week after phase 28's last code commit, on a tree that
has moved past it: twenty-two later commits (the production Day 1 / Day 2 work
and the detection harness) landed in between. That matters, and it is not
smoothed over. The phase's five DELIVERED contracts all still hold and are
asserted here. Two of the four LIMITS the phase declared for itself have since
been closed by that later work — not by Phase 25, which the phase named as their
owner — and this gate says so by name and asserts the closure, so the record
cannot rot back into a claim nobody re-checked. See
:func:`test_the_limits_phase_28_declared_two_of_which_later_work_closed`.

THE PHASE'S ACCEPTANCE, IN ONE COMMAND
--------------------------------------
::

    python3 -m pytest -q tests/test_phase28_acceptance.py

**It is FREE.** :func:`test_the_whole_gate_runs_free` reads this module and every
module it invokes off disk and proves it, rather than promising it. Beneath it,
unchanged, sits the no-regression floor::

    python3 -m pytest -q tests/test_phase23_acceptance.py \\
        tests/test_phase24_acceptance.py tests/test_four_set_coverage.py

Phase 28 changed fusion in three plans and the aggregator in three, so the gate
that proves phase 24 still holds is invoked from inside this one.
"""
from __future__ import annotations

import importlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

THIS_FILE = Path(__file__)

#: The committed Crow plan set. Phase 28's position evidence and its wall-class
#: ambiguity were both measured on page 0 of this file, offline, for free.
CROW_FIXTURE_PDF = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
CROW_PLAN_PAGE = 0

#: The two saved paid Crow runs this phase reasons over. $1.1573 of real spend,
#: FROZEN, opened read-only everywhere in this module and never re-scored.
PAID_RUN_EVIDENCE = ROOT / ".planning" / "paid-run-evidence"
PAID_RUNS = (
    "VisionOnly_P24DET_Crow_20260806_194607",
    "VisionOnly_P24DET_Crow_20260806_195704",
)

_CACHE: dict = {}


def _need_crow_fixture():
    """Skip — loudly and by name — rather than pass on an absent fixture."""
    if not CROW_FIXTURE_PDF.is_file():
        pytest.skip(
            "the committed Crow plan set is absent at %s — this phase's position "
            "evidence and thickness ambiguity are MEASURED on that drawing and "
            "cannot be simulated" % CROW_FIXTURE_PDF
        )


def _need_paid_evidence():
    if not (PAID_RUN_EVIDENCE / PAID_RUNS[0] / "takeoff.json").is_file():
        pytest.skip(
            "the two saved paid runs are absent from %s — the checks that reason "
            "over frozen evidence have nothing to read" % PAID_RUN_EVIDENCE
        )


def _crow_page_zero_bundle():
    """The real Crow plan page through the deterministic half. No vision.

    The analyzer is a lambda that is never called: everything asserted off this
    bundle is computed before any model is consulted, which is what makes the
    whole of this gate free.
    """
    _need_crow_fixture()
    if "bundle" not in _CACHE:
        import fitz

        from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

        pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
        doc = fitz.open(str(CROW_FIXTURE_PDF))
        try:
            _CACHE["bundle"] = pipe._deterministic_bundle(
                doc[CROW_PLAN_PAGE], doc, str(CROW_FIXTURE_PDF), CROW_PLAN_PAGE,
                "page%d" % CROW_PLAN_PAGE, "floor_plan",
            )
        finally:
            doc.close()
    return _CACHE["bundle"]


def _phase28(suffix: str):
    """Import one of this phase's own test modules by an ASSEMBLED name.

    24-10's deviation 3 records that naming a module in a plain string made its
    own free-grep fail on its own source. The names are therefore composed here
    and resolved through ``importlib``: the module imported is exactly the same
    one, and no literal is left for a scan to trip over.
    """
    return importlib.import_module("tests." + "test_phase28_" + suffix)


# ── The calculated-row shapes, built the way the calculator emits them ───────
#
# Deliberately local rather than borrowed from a sibling module: a requirement
# check that reuses the fixture builder of the plan it is judging inherits that
# plan's assumptions along with its helper.


def _count_row(description, qty=3.0, **extra):
    row = {
        "description": description,
        "item_type": "component",
        "calculated_quantity": qty,
        "calculated_unit": "ea",
        "source_sheet": "A-401",
        "formula": "count",
        "confidence": "medium",
        "auto_verified": True,
    }
    row.update(extra)
    return row


def _area_row(description, qty, region_ref=None, **extra):
    row = {
        "item_type": "concrete_slab",
        "description": description,
        "quantity": qty,
        "unit": "SF",
        "raw_unit": "SF",
        "formula": "count",
        "source_sheet": "A-101",
        "confidence": "high",
        "needs_review": False,
    }
    if region_ref is not None:
        row["region_ref"] = region_ref
    row.update(extra)
    return row


def _legend_row(description, qty, unit="SF"):
    """A row the plan's OWN printed schedule named and quantified."""
    return {
        "item_type": "schedule_item",
        "description": description,
        "quantity": qty,
        "unit": unit,
        "raw_unit": unit,
        "formula": "authoritative plan schedule (%s %s)" % (qty, unit),
        "qty_source": "plan_schedule_legend",
        "legend_origin": "plan_parsed",
        "count_corroboration": "schedule",
        "source_sheet": "A-101",
        "confidence": "high",
        "needs_review": False,
    }


def _published(rows, name):
    matches = [r for r in rows if r["item"] == name]
    assert len(matches) == 1, "expected exactly one %r row, got %r" % (
        name, [r["item"] for r in rows]
    )
    return matches[0]


# ═════════════════════════════════════════════════════════════════════════════
# V4-FIX-01 — NO COUNT PUBLISHES MEASURED WITHOUT CORROBORATION
#
# ADVANCED at phase 28 close; the residual was closed by 29-04. The reason it
# could be ticked is a check, not a sentence — the same check, read the other
# way round.
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_fix_01_an_uncorroborated_count_cannot_publish_measured_and_is_not_ticked():
    """V4-FIX-01 — the publish decision, and the boundary that keeps it unticked.

    Three assertions of shipped behaviour, all through ``aggregate_takeoff``:

    * a count with a recorded verdict of ``none`` — a number with no printed
      table and no counted geometry behind it — does NOT come out ``MEASURED``
      with ``needs_review`` false. This is the ``Stairs`` row that published
      clean at 1.00 in one paid run and 2.00 in the other;
    * a count read out of a table printed on the plans DOES, because a printed
      schedule IS the corroboration and this rule must not cost that row;
    * a count whose only evidence was a DETAILS sheet publishes a blank that
      still quotes the reading it withheld — a deletion and a zero read
      identically to a client (INV-08).

    **The boundary that kept this unticked at phase close, and what became of
    it.** 28-03 measured two calculator producers that emitted EA counts and
    recorded no verdict at all, so the aggregator read them as not-a-count and
    they could still publish ``MEASURED``. Its tripwire asserted both halves of
    that residual and was written to FAIL the moment either producer was fixed.
    29-04 stamped both — ``_calculate_from_measurement``'s whole-EA branch and
    ``_calculate_from_civil_structures`` — so the tripwire went red on purpose
    and was SHORTENED, not deleted: it now asserts the closure from the other
    side, and its residual list is empty. It is still invoked here, and it is
    still the thing that decides whether the universal claim holds; what changed
    is the answer it returns. The function's name is unchanged so this call site
    keeps landing on the same check.
    """
    from bobbytailor.pipeline import aggregator
    from bobbytailor.pipeline.aggregator import aggregate_takeoff
    from bobbytailor.pipeline.coverage import ITEM_MEASURED

    rows = aggregate_takeoff([
        _count_row("uncorroborated widget", count_corroboration="none",
                   count_evidence_sheet_kind="floor_plan"),
        _count_row("door schedule count", count_corroboration="schedule",
                   qty_source="plan_schedule_legend", qty=29.0),
        _count_row("stair detail", count_corroboration="detail_sheet_only",
                   count_evidence_sheet_kind="detail", qty=1.0),
    ])

    loose = _published(rows, "uncorroborated widget")
    assert loose["provenance"] != ITEM_MEASURED, (
        "a count with nothing behind it published %r — an unflagged wrong "
        "number is worse than a blank, because a reviewer skips it"
        % loose["provenance"]
    )
    assert loose["needs_review"] is True
    assert loose["auto_verified"] is False, (
        "the row flags itself to a human and clears itself to every numeric "
        "consumer at the same time — 28-03's deviation 1"
    )

    backed = _published(rows, "door schedule count")
    assert backed["provenance"] == ITEM_MEASURED
    assert backed["needs_review"] is False
    assert backed["quantity"] == 29.0, (
        "the printed-schedule row lost its quantity — this rule must not cost "
        "the rows it was built to protect"
    )

    withheld = [r for r in rows if r["quantity"] is None]
    assert withheld, "the detail-sheet count was not withheld at all"
    stairs = withheld[0]
    assert stairs["source"] == aggregator.DETAIL_SHEET_COUNT_UNMEASURED
    assert stairs["source"] in aggregator._UNMEASURED_SOURCES, (
        "the withheld marker left the set every consumer already reads, so it "
        "would need a special case somewhere"
    )
    assert stairs["needs_review"] is True
    assert stairs["review_reasons"], "a blank that says nothing is a deletion"

    # The boundary, as the phase's own committed tripwire — flipped by 29-04
    # and now asserting that both named producers DO stamp a verdict.
    _phase28("uncorroborated_counts").test_the_residual_this_plan_does_not_close_is_named_not_implied()


# ═════════════════════════════════════════════════════════════════════════════
# V4-FIX-02 — THE BOLLARDS MIS-BINDING, DIAGNOSED AND FIXED AT ITS CAUSE
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_fix_02_the_ring_test_refuses_a_filled_lattice_and_no_tie_decided_crow():
    """V4-FIX-02 — measured on the real plan page, in both directions.

    The requirement's operative verbs are *diagnosed* and *fixed at its cause*,
    with an explicit prohibition on dividing by two. 28-02 disproved the
    double-count hypothesis by position and found the cause to be a mis-binding:
    ``_is_perimeter_ring`` accepted a fully populated lattice, because a 25%
    inset box covers a quarter of the area and almost every mark of a shallow
    array falls outside it.

    Asserted here as the outcome on the drawing:

    * the perimeter hint's candidate list — every filter it applies EXCEPT the
      ring test — is NON-EMPTY, so the refusal below is a decision rather than
      an absence of input. Without this half, deleting the hint entirely would
      pass;
    * with the ring test honest, the hint binds NOTHING on that page;
    * a synthetic hollow ring still passes, so the predicate has not simply
      stopped discriminating.

    **The 56-vs-56 tie the plan blamed does not exist, and no check here claims
    the tie rule fixed Crow.** ``SYM-3`` is excluded by ``_is_small_marker``
    before candidacy, so the shortlist's maximum was already unique and list
    order decided nothing on this sheet. That is asserted positively — the
    maximum IS unique — rather than left as a footnote. The unique-maximum rule
    is a real hardening on both hints and is invoked as such, on synthetic
    candidates, where a tie can actually be built.
    """
    from bobbytailor.vision import fusion as F

    bundle = _crow_page_zero_bundle()
    groups = bundle.get("symbol_groups") or []
    assert groups, "the deterministic pass found no symbol clusters at all"

    shortlist = [
        g for g in groups
        if int(F._field(g, "count", 0) or 0) >= F._PERIMETER_MIN_COUNT
        and F._size_uniform(g) and F._is_small_marker(g) and F._is_2d_distributed(g)
    ]
    assert shortlist, (
        "no cluster reaches the perimeter hint at all, so a refusal below would "
        "prove nothing — the fix would be indistinguishable from deleting the hint"
    )

    bindings = F._library_symbol_bindings(
        groups, {}, {"perimeter_jamb_symbol": {"name": "Bollard"}}
    )
    assert bindings == {}, (
        "the perimeter hint still names %r on the plan page — a wrong name was "
        "replaced by another wrong name" % bindings
    )

    # No tie existed here: the maximum of the shortlist is unique, so the tie
    # rule cannot be credited with this refusal.
    counts = [int(F._field(g, "count", 0) or 0) for g in shortlist]
    top = max(counts)
    assert counts.count(top) == 1, (
        "the shortlist's maximum is TIED (%r) — 28-02 measured it to be unique "
        "on this sheet and this gate's account of what fixed Crow depends on "
        "that. Re-measure before editing." % counts
    )

    symbols = _phase28("symbol_position_evidence")
    # The predicate still accepts a genuine ring, and refuses the two shapes
    # that fooled the earlier version: a filled lattice, and a sparse scatter
    # that cleared the inset test VACUOUSLY by luck.
    symbols.test_a_hollow_ring_built_at_the_measured_pitch_is_still_a_ring()
    symbols.test_a_filled_lattice_of_the_same_pitch_and_mark_is_not_a_ring()
    symbols.test_a_sparse_scatter_lying_on_no_run_is_not_a_ring()
    symbols.test_the_inset_test_alone_would_still_have_accepted_that_lattice()
    # The tie rule, on candidates where a tie can be constructed. A hardening
    # on both hints — never a claim about this drawing.
    symbols.test_two_perimeter_candidates_tied_on_count_bind_nothing()
    symbols.test_two_grid_candidates_tied_on_count_bind_nothing()
    symbols.test_an_unambiguous_larger_candidate_still_wins()


# ═════════════════════════════════════════════════════════════════════════════
# V4-FIX-03 — A PRINTED THICKNESS THAT DOES NOT DISCRIMINATE
#
# ADVANCED, NOT TICKED. The reason is a check, not a sentence.
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_fix_03_a_non_discriminating_thickness_binds_nothing_and_is_not_ticked():
    """V4-FIX-03 — mutual uniqueness on BOTH axes, and what is still not proved.

    A printed thickness is evidence of DIMENSION. It becomes evidence of
    IDENTITY only when exactly one candidate claims exactly one class.

    * two objects printing the same thickness: neither takes a confident bind;
    * one object printing a thickness nothing else claims: it still binds, so
      the rule did not simply stop binding;
    * **one object matching several CLASSES: it binds neither.** This is the
      axis the plan did not name and the ONLY axis that fires on Crow — a
      nominal 8" object lies inside the 1.5" tolerance of three of the sheet's
      thirteen measured classes. Implemented as written, the object-axis test
      alone would have changed nothing on this drawing.

    **The LF-share masonry guard is not what fixed this drawing, and is not
    credited.** Computed here off the real geometry: of the classes a nominal
    masonry object matches, the share test excludes only the DOMINANT one, which
    the pre-existing rank test already excluded — so it removes nothing the
    binder was not already refusing. The class that actually took the bind sits
    far below the cap. More than one candidate therefore survives both guards,
    which is precisely why mutual UNIQUENESS is what refuses here. The guard
    closes a real hole and was proved scale-invariant; lowering it until a class
    was excluded would have been tuning to golden through an intermediary.

    **The requirement is not ticked and this check is why.** With the thickness
    route refused, the masonry object reaches pass 2's masonry-by-hint rule,
    which hands it the smallest remaining class on no evidence beyond "masonry
    is small". Asserted here: whatever that pass produces is NOT confident. "The
    mis-binding is removed and flagged" is delivered; "CMU Wall binds the
    correct class" is not, and cannot be shown from anything available offline.
    """
    from bobbytailor.vision import fusion as F
    from bobbytailor.vision.fusion import map_wall_classes_from_library

    def _obj(name, thickness_in=None, hint=""):
        o = {"name": name, "basis": "wall_area"}
        if thickness_in is not None:
            o["thickness_in"] = thickness_in
        if hint:
            o["binding_hint"] = hint
        return o

    lf = {"TC1": 400.0, "TC2": 100.0}
    thickness = {"TC1": 8.0, "TC2": 20.0}

    # Two objects, one thickness: the match identifies neither.
    both = map_wall_classes_from_library(
        lf, thickness, [_obj("Tilt Up Wall", "8"), _obj("Precast Panel", "8")]
    )
    assert not [v for v in both.values() if v[2] is True], (
        "a thickness two objects both print took a confident bind: %r" % both
    )
    # One object, one thickness: it still binds.
    alone = map_wall_classes_from_library(lf, thickness, [_obj("Tilt Up Wall", "8")])
    assert [v for v in alone.values() if v[2] is True], (
        "a genuinely unique match stopped binding — the rule refuses "
        "everything, which is not the same as refusing what does not "
        "discriminate: %r" % alone
    )
    # One object, several classes: the axis the real sheet exhibits.
    near = {"TC1": 8.0, "TC2": 8.6}
    assert abs(near["TC1"] - near["TC2"]) < F._WALL_THICKNESS_TOL_IN
    ambiguous = map_wall_classes_from_library(lf, near, [_obj("Tilt Up Wall", "8")])
    assert not [v for v in ambiguous.values() if v[2] is True], (
        "an object whose printed thickness fits two measured classes took a "
        "confident bind — the nearer class was preferred inside the tolerance, "
        "which is reading signal out of the noise the tolerance absorbs: %r"
        % ambiguous
    )

    # ── The real sheet ────────────────────────────────────────────────────
    bundle = _crow_page_zero_bundle()
    real_lf = dict(bundle.get("wall_lf_by_class") or {})
    real_thickness = F._wall_thickness_in_by_class(bundle)
    assert real_lf and real_thickness, (
        "the real sheet yielded no wall classes — the ambiguity this "
        "requirement is about cannot be measured"
    )

    nominal = 8.0
    matched = sorted(
        cls for cls, t in real_thickness.items()
        if abs(float(t) - nominal) <= F._WALL_THICKNESS_TOL_IN
    )
    assert len(matched) > 1, (
        "a nominal %r\" object matches only %r class(es) on this sheet — the "
        "class-axis ambiguity this requirement turns on is no longer present, "
        "so re-measure before trusting anything else here" % (nominal, matched)
    )

    share = F._wall_class_lf_share(real_lf)
    dominant = max(real_lf, key=lambda c: float(real_lf[c] or 0.0))
    excluded_by_share_alone = sorted(
        cls for cls in matched
        if cls != dominant and share.get(cls, 0.0) > F._MASONRY_MAX_LF_SHARE
    )
    assert excluded_by_share_alone == [], (
        "the LF-share guard excluded %r on this drawing over and above the rank "
        "test. 28-04 measured that it excludes nothing the rank test had not "
        "already excluded here, and this gate must not credit it with the fix. "
        "If the geometry has moved, re-measure rather than editing this."
        % excluded_by_share_alone
    )
    masonry = {"name": "CMU Wall", "binding_hint": "masonry_wall"}
    survivors = [
        cls for cls in matched
        if not F._masonry_bind_forbidden(masonry, cls, dominant, share)
    ]
    assert len(survivors) > 1, (
        "after both masonry guards have spoken, %r class(es) remain for the "
        "object to choose between. 28-04's finding is that MORE than one "
        "remains, which is why mutual uniqueness — not the guards — is what "
        "refuses the bind on this sheet." % survivors
    )

    cmu = map_wall_classes_from_library(
        real_lf, real_thickness, [_obj("CMU Wall", "8", hint="masonry_wall")]
    )
    assert not [v for v in cmu.values() if v[2] is True], (
        "the masonry object took a CONFIDENT class on the real sheet: %r" % cmu
    )
    assert cmu, (
        "the masonry object bound nothing at all. 28-04 measured that it falls "
        "through to pass 2's masonry-by-hint rule and takes a NON-confident "
        "bind there — which is exactly why V4-FIX-03 is not ticked. If that "
        "fall-through has been removed, the residual has changed and the "
        "requirement's status must be re-decided, not left as it stands."
    )


# ═════════════════════════════════════════════════════════════════════════════
# V4-FIX-04 — ONE MEASURED REGION BACKS ONE PUBLISHED ROW PER LAYER
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_fix_04_one_region_one_row_per_layer_and_d1_survives():
    """V4-FIX-04 — the restriction, and phase 23's exception it must not revoke.

    One measured footprint fanned out to three published rows of the same area,
    so an estimator who summed the SF column priced the building three times.

    Half one — the restriction. Two rows the plan's own printed legend NAMED and
    one whose name is a hypothesis, all three claiming the same region: exactly
    the evidence-named rows publish a quantity, and the hypothesis publishes a
    blank carrying its own marker.

    Half two — phase 23's D1 exception, intact. A shell warehouse's footprint
    genuinely carries the structural slab, the finish troweled onto it and the
    exposed roof structure above; three distinct layers through one plan area is
    not three copies of one quantity. When the plan names all three, all three
    publish. Collapsing them cost roughly thirty accuracy points once, and this
    half exists so nobody reads 28-05 as a rollback of it.

    An input area is used, never an expected answer: no assertion compares a
    published number to a take-off figure.
    """
    from bobbytailor.pipeline import aggregator
    from bobbytailor.pipeline.aggregator import aggregate_takeoff
    from bobbytailor.vision.fusion import NAME_SOURCE_VOCABULARY_BASIS

    area = 397600.0
    names = ("Exposed Structure", "Sealed Concrete", "Concrete Pad")
    library = [
        {"name": n, "aliases": [n], "basis": "floor_area", "unit": "SF"}
        for n in names
    ]

    rows = aggregate_takeoff(
        [
            _legend_row("Exposed Structure", area),
            _legend_row("Sealed Concrete", area),
            _area_row("Exposed Structure", area, region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS),
            _area_row("Sealed Concrete", area, region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS),
            _area_row("Concrete Pad", area, region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS),
        ],
        library=library,
    )
    quantified = {
        r["item"] for r in rows if r["quantity"] is not None and r["unit"] == "SF"
    }
    assert quantified == {"Exposed Structure", "Sealed Concrete"}, (
        "exactly the evidence-named rows may publish a number on a shared "
        "region; published %r" % sorted(quantified)
    )
    pad = _published(rows, "Concrete Pad")
    assert pad["source"] == aggregator.REGION_SHARED_HYPOTHESIS_UNMEASURED
    assert pad["needs_review"] is True
    assert pad["review_reasons"], (
        "the suppressed hypothesis says nothing about why — a blank that "
        "explains nothing reads to a client exactly like a deletion"
    )

    # D1: three EVIDENCE-named layers on one region all publish.
    all_named = aggregate_takeoff(
        [_legend_row(n, area) for n in names]
        + [
            _area_row(n, area, region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS)
            for n in names
        ],
        library=library,
    )
    for name in names:
        row = _published(all_named, name)
        assert row["quantity"] == area, (
            "%s lost its quantity — phase 23's declared-layer exception was "
            "revoked, not restricted" % name
        )
        assert row["source"] != aggregator.REGION_SHARED_HYPOTHESIS_UNMEASURED


# ═════════════════════════════════════════════════════════════════════════════
# V4-FIX-05 — EVERY QUANTITY STATES THE ROUTE IT CAME BY
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_fix_05_every_quantity_states_its_route_and_a_blank_carries_none():
    """V4-FIX-05, half one — the route rides on the number, and reaches a human.

    ``provenance`` says what a client should make of a row. ``quantity_route``
    says how the number was PRODUCED, and therefore whether a repeat run
    reproduces it. Only one of the three routes — a reading taken off a sheet by
    a model — is one a re-run may answer differently.

    A blank carries NO route: there is no number to characterise, so the field is
    absent rather than defaulted. Neither does an app-injected convention, which
    carries a number nobody read off the drawing — that exemption is asserted
    here explicitly rather than filtered out of the loop, because an exemption
    nobody checks is a hole. And the disclosure has to reach the artifact a
    human actually reads, which is ``summary.txt`` and not ``takeoff.json`` — so
    the reproducibility section is required to name every published reading-route
    row and no other published row. Its membership is DERIVED from the
    aggregator's own output; no item name is typed in as the expectation.
    """
    from bobbytailor.pipeline.aggregator import (
        QUANTITY_ROUTE_MEASURED,
        QUANTITY_ROUTE_SHEET_READING,
        aggregate_takeoff,
    )
    from bobbytailor.pipeline.coverage import ITEM_STANDARD
    from bobbytailor.pipeline.reporter import _reproducibility_lines

    rows = aggregate_takeoff([
        _count_row("hollow metal frame", qty=4.0, provenance="geometry"),
        _count_row("aluminum window unit", qty=6.0),
        _count_row("door schedule count", qty=29.0,
                   qty_source="plan_schedule_legend"),
        _count_row("stair detail", qty=1.0,
                   count_corroboration="detail_sheet_only",
                   count_evidence_sheet_kind="detail"),
    ])

    # An app-injected convention is not a reading of the drawing: it carries a
    # number nobody measured, so there is no route to state and the field is
    # ABSENT rather than defaulted. Identified by its published status, not by
    # its name — a hard-coded name would stop probing the day the convention set
    # grows. Asserted deliberately rather than filtered out silently.
    injected = [r for r in rows if r["provenance"] == ITEM_STANDARD]
    assert injected, (
        "no standard line item was injected, so the exemption below is not "
        "being exercised and this check would pass for having looked at nothing"
    )
    for row in injected:
        assert row.get("quantity") is not None
        assert not row.get("quantity_route"), (
            "%r is an injected convention and stated a route %r — the field "
            "describes how the ENGINE produced a number off the drawing, and "
            "this one was not read off anything" % (row["item"], row["quantity_route"])
        )

    for row in rows:
        if row in injected:
            continue
        if row.get("quantity") is None:
            assert not row.get("quantity_route"), (
                "%r published no number and still stated a route — there is "
                "nothing to characterise" % row["item"]
            )
        else:
            assert row.get("quantity_route"), (
                "%r published a number that does not say how it was produced"
                % row["item"]
            )

    # Located through the audit trail rather than by its published name: the
    # aggregator canonicalises descriptions, and a name typed in here would pin
    # the canonicaliser instead of the route.
    geometry_rows = [
        r for r in rows
        if any("hollow metal frame" in (d.get("description") or "")
               for d in (r.get("detail") or []))
    ]
    assert len(geometry_rows) == 1, (
        "the geometry-backed row is not identifiable in the published set: %r"
        % [r["item"] for r in rows]
    )
    assert geometry_rows[0]["quantity_route"] == QUANTITY_ROUTE_MEASURED, (
        "a number measured off the drawing must state the measured route, not "
        "%r" % geometry_rows[0]["quantity_route"]
    )
    reading = {
        r["item"] for r in rows
        if r.get("quantity_route") == QUANTITY_ROUTE_SHEET_READING
    }
    assert reading, "the fixture routed nothing to the reading route"

    text = "\n".join(_reproducibility_lines({"takeoff_summary": rows}))
    for name in reading:
        assert name in text, (
            "%r took the reading route and the section a human reads does not "
            "name it" % name
        )
    for row in rows:
        if row["item"] not in reading:
            assert row["item"] not in text, (
                "%r did not take the reading route and must not be listed among "
                "the numbers a re-run may answer differently: route %r"
                % (row["item"], row.get("quantity_route"))
            )


def test_v4_fix_05_the_row_presence_axis_is_named_and_it_is_door_frames_hm():
    """V4-FIX-05, half two — the falsification, asserted BY NAME.

    28-06's plan predicted that EVERY quantity that moved between the two saved
    runs would classify as the reading route. It does not, and the exception is
    not scoped around: ``Door Frames-HM`` published ``4.0 EA`` in run A off a row
    recorded ``provenance: geometry`` — the MEASURED route — and published
    nothing in run B, because the backing row was never extracted at all. **The
    number did not move; the ROW vanished.** Row PRESENCE is a second axis, and
    no per-run route classification can see it.

    The subject is COMPUTED, not typed: the differing keys are derived at runtime
    by comparing the two frozen published lists, each one is classified through
    28-06's own helpers, and only then is the resulting set compared to the name.
    The name is written down deliberately — a falsification that is only implied
    by a runtime computation is one no future reader can grep for — and the
    comparison is against what the evidence says, so if the evidence ever stops
    saying it, this goes red rather than quietly agreeing with a summary.

    Nothing here is a golden quantity: it is a row name and a partition.
    """
    _need_paid_evidence()
    stability = _phase28("extraction_stability")

    run_a = stability._load_run(stability._RUN_A)
    run_b = stability._load_run(stability._RUN_B)
    differing = stability._differing_keys(run_a, run_b)
    assert differing, (
        "the two saved runs published no differing quantity at all — the "
        "instability this requirement discloses is not in the evidence"
    )

    published = {
        stability._RUN_A: stability._published(run_a),
        stability._RUN_B: stability._published(run_b),
    }
    other_side = {
        stability._RUN_A: {
            stability._quantity_key(r) for r in run_b.get("calculated_takeoff", [])
        },
        stability._RUN_B: {
            stability._quantity_key(r) for r in run_a.get("calculated_takeoff", [])
        },
    }

    by_reading, by_vanished_row = set(), set()
    for key in differing:
        for run_name, run in (
            (stability._RUN_A, run_a), (stability._RUN_B, run_b)
        ):
            summary_row = published[run_name][key]
            route = stability._route_of_published(run, summary_row)
            if route is None:
                continue
            if route == stability.QUANTITY_ROUTE_SHEET_READING:
                by_reading.add(key[0])
                continue
            missing = [
                r for r in stability._backing_rows(run, summary_row)
                if stability._quantity_key(r) not in other_side[run_name]
            ]
            assert missing, (
                "%s in %s moved while every backing row exists in both runs and "
                "the route is %r — neither the route nor row presence explains "
                "it, and neither may be claimed to" % (key[0], run_name, route)
            )
            by_vanished_row.add(key[0])

    assert by_reading, (
        "no differing quantity was explained by the reading route — the "
        "classification would be carried entirely by its escape hatch"
    )
    assert by_vanished_row == {"Door Frames-HM"}, (
        "the set of quantities that moved for a reason the route classification "
        "CANNOT see is %r. 28-06 measured it to be exactly {'Door Frames-HM'}, "
        "and both the ROADMAP line and summary.txt's stated limit were narrowed "
        "to say so. If this set has changed, the phase's disclosure has changed "
        "with it and must be re-narrated, not re-fitted."
        % sorted(by_vanished_row)
    )
    assert not (by_reading & by_vanished_row), (
        "a key is claimed by both explanations at once, so the partition says "
        "nothing: %r" % sorted(by_reading & by_vanished_row)
    )


# ═════════════════════════════════════════════════════════════════════════════
# THE PHASE'S OWN GATES — INVOKED, AND PROVED INVOKED
#
# Presence is not consumption (the 24-09 hit-census idiom). Every module this
# phase added is imported through an assembled name, a declared set of its
# checks is called against live subjects, and the set INTENDED is asserted equal
# to the set INVOKED and to the set that exists ON DISK — all three, in both
# directions. A gate that intends seven and invokes six is a gate that passed
# for having looked at six.
# ═════════════════════════════════════════════════════════════════════════════

_NEEDS_CROW = "crow_fixture"
_NEEDS_EVIDENCE = "paid_evidence"

#: ``(module suffix, check name, what the check needs)``. The suffixes are
#: composed into module names at call time; see :func:`_phase28`.
PHASE28_CHECKS = (
    ("count_corroboration", "test_the_constant_holds_exactly_what_the_inline_tuple_held", None),
    ("count_corroboration", "test_a_geometry_backed_count_is_corroborated_by_geometry", None),
    ("count_corroboration", "test_every_route_out_of_the_schedule_calculator_comes_out_corroborated", None),
    ("count_corroboration", "test_an_install_count_read_off_a_details_sheet_is_marked_as_counting_drawings", None),
    ("count_corroboration", "test_the_verdict_survives_normalisation_into_the_report_layer", None),
    ("count_corroboration", "test_the_saved_runs_every_quantity_that_moved_was_a_count_nothing_confirmed", _NEEDS_EVIDENCE),
    ("count_corroboration", "test_the_saved_runs_a_geometry_backed_number_never_moved", _NEEDS_EVIDENCE),

    ("symbol_position_evidence", "test_every_instance_lands_in_exactly_one_region_and_it_is_the_same_one", _NEEDS_CROW),
    ("symbol_position_evidence", "test_no_two_instances_are_close_enough_to_be_two_marks_on_one_object", _NEEDS_CROW),
    ("symbol_position_evidence", "test_no_instance_lies_near_the_boundary_of_its_own_region", _NEEDS_CROW),
    ("symbol_position_evidence", "test_the_judged_cluster_is_no_longer_read_as_a_perimeter_ring", _NEEDS_CROW),
    ("symbol_position_evidence", "test_the_ring_test_still_finds_the_one_genuinely_hollow_ring_on_the_page", _NEEDS_CROW),
    ("symbol_position_evidence", "test_the_real_plan_page_emits_no_perimeter_binding", _NEEDS_CROW),

    ("uncorroborated_counts", "test_rollup_combines_two_verdicts_in_one_place", None),
    ("uncorroborated_counts", "test_rollup_the_precedence_is_expressed_exactly_once", None),
    ("uncorroborated_counts", "test_a_detail_sheet_count_never_reaches_a_published_quantity", None),
    ("uncorroborated_counts", "test_the_withheld_blank_is_still_a_row_that_quotes_what_it_withheld", None),
    ("uncorroborated_counts", "test_row_status_refuses_measured_for_an_uncorroborated_count", None),
    ("uncorroborated_counts", "test_the_door_schedule_count_still_publishes_measured", None),
    ("uncorroborated_counts", "test_withholding_one_count_disturbs_no_other_row", None),

    ("wall_class_binding", "test_a_thickness_two_objects_both_print_is_not_unique_and_binds_neither", None),
    ("wall_class_binding", "test_a_thickness_only_one_object_prints_is_unique_and_still_binds", None),
    ("wall_class_binding", "test_an_object_that_lost_a_unique_contest_is_not_consumed", None),
    ("wall_class_binding", "test_the_bind_does_not_depend_on_the_order_the_objects_arrive_in", None),
    ("wall_class_binding", "test_a_genuinely_unique_match_still_overrides_a_dissenting_label", None),
    ("wall_class_binding", "test_the_share_guard_binds_no_absolute_length_at_all", None),
    ("wall_class_binding", "test_a_printed_nominal_thickness_is_not_unique_on_the_real_sheet", _NEEDS_CROW),
    ("wall_class_binding", "test_the_real_sheet_gives_a_nominal_object_no_confident_class", _NEEDS_CROW),
    ("wall_class_binding", "test_the_silent_tie_break_is_recorded_in_both_saved_runs", _NEEDS_EVIDENCE),

    ("region_fanout", "test_the_crow_fan_out_resolves_to_two_published_rows_and_one_blank", None),
    ("region_fanout", "test_the_blank_names_the_rows_that_hold_the_region_and_the_area_it_withheld", None),
    ("region_fanout", "test_three_evidence_named_layers_on_one_region_all_publish", None),
    ("region_fanout", "test_a_region_held_only_by_hypotheses_is_left_alone", None),
    ("region_fanout", "test_the_rule_never_compares_two_quantities", None),
    ("region_fanout", "test_withholding_one_row_disturbs_no_other", None),

    ("extraction_stability", "test_route_three_values_and_no_more", None),
    ("extraction_stability", "test_route_precedence_the_least_reproducible_contributor_wins", None),
    ("extraction_stability", "test_route_a_blank_row_carries_no_route", None),
    ("extraction_stability", "test_route_a_withheld_number_carries_no_route", None),
    ("extraction_stability", "test_the_summary_section_names_exactly_what_a_real_aggregation_routed", None),
    ("extraction_stability", "test_the_saved_runs_every_quantity_that_moved_is_explained", _NEEDS_EVIDENCE),
)

INTENDED_MODULES = tuple(sorted({suffix for suffix, _n, _need in PHASE28_CHECKS}))


@pytest.fixture(scope="module")
def phase28_census():
    """Call every declared check once, and record what happened to each.

    Recorded as ``pass`` or ``skip: <reason>``; a check that raises anything else
    fails the whole gate here rather than being counted. Every callable is
    required to take NO fixture argument — a check invoked directly cannot be
    handed one, and silently calling a fixture-taking function would raise a
    ``TypeError`` that reads like an unrelated bug.
    """
    census = {}
    for suffix, name, need in PHASE28_CHECKS:
        module = _phase28(suffix)
        fn = getattr(module, name, None)
        assert callable(fn), (
            "tests/test_phase28_%s.py no longer defines %s — this gate intends "
            "to consult it, so it cannot silently stop doing so" % (suffix, name)
        )
        assert not inspect.signature(fn).parameters, (
            "%s.%s takes arguments and cannot be invoked directly" % (suffix, name)
        )
        entries = census.setdefault(suffix, [])
        if need == _NEEDS_CROW and not CROW_FIXTURE_PDF.is_file():
            entries.append((name, "skip: the Crow plan set is absent at %s"
                            % CROW_FIXTURE_PDF))
            continue
        if need == _NEEDS_EVIDENCE and not (
            PAID_RUN_EVIDENCE / PAID_RUNS[0] / "takeoff.json"
        ).is_file():
            entries.append((name, "skip: the saved paid runs are absent from %s"
                            % PAID_RUN_EVIDENCE))
            continue
        try:
            fn()
        except pytest.skip.Exception as exc:      # noqa: PT012 — recorded, not swallowed
            entries.append((name, "skip: %s" % exc))
        else:
            entries.append((name, "pass"))
    return census


def test_every_module_this_phase_added_was_consulted_and_the_sets_agree(
    phase28_census,
):
    """The census, asserted in three directions.

    * every module this gate INTENDS to consult was actually consulted;
    * every module actually consulted was one it intended to — a check that ran
      out of a module nobody declared means the table and the calls disagree;
    * the intended set equals the set of ``tests/test_phase28_*.py`` files ON
      DISK, this gate excepted. That is the direction the other two cannot see:
      an eighth module added by a later plan and never invoked would leave both
      of them perfectly consistent and this gate blind to it.

    Every recorded outcome must be ``pass`` or a skip that NAMES what was
    missing. Silence is not an outcome.
    """
    invoked = set(phase28_census)
    intended = set(INTENDED_MODULES)
    assert invoked == intended, (
        "intended but not invoked: %r; invoked but not intended: %r"
        % (sorted(intended - invoked), sorted(invoked - intended))
    )

    on_disk = {
        p.stem[len("test_phase28_"):]
        for p in sorted((ROOT / "tests").glob("test_phase28_*.py"))
        if p.name != THIS_FILE.name
    }
    assert on_disk == intended, (
        "phase-28 test modules on disk that this gate never consults: %r; "
        "consulted but absent from disk: %r"
        % (sorted(on_disk - intended), sorted(intended - on_disk))
    )

    for suffix, entries in sorted(phase28_census.items()):
        assert entries, "no check was recorded for %s" % suffix
        for name, outcome in entries:
            assert outcome == "pass" or outcome.startswith("skip: "), (
                "%s.%s recorded %r, which is neither an assertion nor a named "
                "skip" % (suffix, name, outcome)
            )
            if outcome.startswith("skip: "):
                assert len(outcome) > len("skip: "), (
                    "%s.%s skipped without saying what was missing"
                    % (suffix, name)
                )


# ── Phase 24 must still hold, and this phase's gate is where that is proved ──
#
# Phase 28 changed fusion in three plans and the aggregator in three. One
# differential is built here and handed to BOTH the 24-09 harness and the 24-10
# acceptance gate, so the cost is paid once rather than twice.


@pytest.fixture(scope="module")
def differential(tmp_path_factory):
    """24-09's two-variant differential, in the shape its own tests expect."""
    harness = importlib.import_module("tests." + "test_determinism_harness")
    harness._require_plan_set()
    harness._require_fixtures()
    tmp_path = tmp_path_factory.mktemp("phase28-acceptance")
    out = {}
    for variant in harness.VARIANTS:
        report, probe = harness._report_for(variant, tmp_path)
        harness._require_no_fixture_drift(probe)
        out[variant] = (report, probe)
    return out


def test_phase_24_still_holds_under_this_phases_fusion_changes(differential):
    """The determinism harness and phase 24's gate, invoked against one run.

    Three of this phase's plans edited ``vision/fusion.py`` and three edited the
    aggregator, which is the whole surface phase 24's determinism guarantee sits
    on. Asserting that guarantee still holds belongs in THIS phase's gate, not
    only in the suite that happens to run both files.

    Non-vacuity first: a green differential over fixtures nobody requested proves
    nothing, so the hit census and the "the two variants really do differ"
    premise are asserted before the invariants are.

    Skips loudly, by name, when the plan set or the fixtures are absent — that is
    what the fixture above does before any of this runs.
    """
    harness = importlib.import_module("tests." + "test_determinism_harness")
    phase24 = importlib.import_module("tests." + "test_phase24_acceptance")

    harness.test_every_committed_fixture_was_actually_consumed(differential)
    harness.test_the_two_variants_really_do_carry_different_answers()
    # 24-10's own roll-up: it invokes the harness's four invariants and its four
    # proven-detector demonstrations in one call.
    phase24.test_v4_det_05_the_two_variant_differential_holds(differential)
    phase24.test_v4_det_01_no_identifier_is_a_name_and_every_one_that_left_is_ledgered(
        differential
    )
    phase24.test_v4_det_02_printed_thickness_outranks_the_model_and_the_triple_set_holds()


# ═════════════════════════════════════════════════════════════════════════════
# THE GATE PROVES ITSELF FREE
#
# Every token below is ASSEMBLED FROM PARTS, and that is not decoration. The
# check is a substring scan over this very file as well as over the modules it
# invokes, so spelling any of them out — in a docstring, in a comment, in a
# helpful list of what is forbidden — would make the module fail its own audit
# while nothing was actually wrong. The string SEARCHED FOR is the assembled
# one, so the check is real rather than weakened. 24-09, 24-10, 28-01 and 28-02
# each hit this trap independently; this reuses their fix.
# ═════════════════════════════════════════════════════════════════════════════

FORBIDDEN_TOKENS = tuple(
    "".join(parts)
    for parts in (
        ("pytest.mark.", "gold", "en"),      # the paid pytest marker
        ("-m ", "gold", "en"),               # and its command-line selection
        ("accur", "acy_gate"),               # the paid gate shell script
        ("vision_only", "_benchmark"),       # the paid vision-only benchmark
        ("gold", "en_convergence"),          # the paid convergence script
        ("setup_", "gold", "en_fixtures"),   # the paid fixture setup
        ("ANTHROPIC", "_API_KEY"),           # the credential
        ("REPLAY", "_RECORD"),               # wraps the REAL analyzer: can spend
    )
)


def _scanned_modules():
    """This gate plus every module it invokes, resolved off disk.

    Derived from the census table rather than listed by hand: a per-module list
    written out separately is exactly how one module quietly stops being
    scanned.
    """
    paths = [THIS_FILE.relative_to(ROOT)]
    paths += [
        Path("tests") / ("test_phase28_" + suffix + ".py")
        for suffix in INTENDED_MODULES
    ]
    paths += [
        Path("tests") / ("test_determinism_" + "harness.py"),
        Path("tests") / ("test_phase24_" + "acceptance.py"),
    ]
    return tuple(paths)


def test_the_whole_gate_runs_free():
    """The phase's acceptance costs nothing to run, and that is checked.

    A gate that is free itself but calls a module that is not is not a free
    gate, so the scan covers this module AND everything it invokes, as one set.
    ``pytest.ini`` is asserted to deselect the paid marker by default, so the
    suite a developer runs is free by CONFIGURATION rather than by remembering a
    flag.
    """
    assert len(FORBIDDEN_TOKENS) == 8, "a forbidden token was dropped from the list"

    # Non-vacuity FIRST, and a real positive control: without it, a typo in all
    # eight would produce exactly the same green tick as a genuinely free tree.
    for token in FORBIDDEN_TOKENS:
        assert token, "an empty token matches nothing and scans nothing"
        assert token in ("prefix " + token + " suffix"), (
            "the scanner cannot find %r even when it is present" % token
        )

    offences = {}
    scanned = _scanned_modules()
    assert len(scanned) >= 2 + len(INTENDED_MODULES)
    for relative in scanned:
        path = ROOT / relative
        assert path.is_file(), (
            "%s is missing — this gate invokes it, so it cannot be scanned and "
            "cannot be trusted" % relative
        )
        hits = [
            token for token in FORBIDDEN_TOKENS
            if token in path.read_text(encoding="utf-8")
        ]
        if hits:
            offences[str(relative)] = hits
    assert offences == {}, (
        "a paid command entered the free acceptance path: %s" % offences
    )

    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r'addopts\s*=\s*-m\s*"not\s+' + "gold" + r'en"', ini), (
        "pytest.ini no longer deselects the paid marker by default, so the "
        "plain suite command stopped being free"
    )


#: Crow's four take-off figures this project has been burned by tuning toward.
#: Assembled digit by digit for the same reason the tokens above are: the scan
#: reads this file too, and a literal here would be a literal in a phase-28
#: module.
_GOLDEN_FIGURES = (
    "2" + "8",            # Bollards
    "13" + "2",           # Columns
    "1" + "0",            # Stairs
    "2204" + r"\.33",     # CMU Wall SF
    "2204",
)

#: The SHAPE of a golden comparison: a comparison operator, or a tolerance
#: helper, immediately followed by one of those figures.
_GOLDEN_COMPARISON = re.compile(
    r"(?:==|!=|>=|<=|approx\s*\()\s*\(?\s*(?:%s)\b" % "|".join(_GOLDEN_FIGURES)
)


def test_no_module_in_this_phase_compares_a_quantity_to_a_crow_golden():
    """Rule 2, asserted of the whole phase by shape rather than by digit.

    **What this catches:** an assertion that compares something to one of Crow's
    four golden figures — ``== 132``, ``>= 28``, ``approx(2204.33)`` and the
    like — anywhere in this gate or in the six modules this phase added.

    **What it deliberately does NOT catch,** so a future reader is not misled:
    a golden figure reached indirectly (``== expected * 2``), one bound to a name
    first (``GOLDEN = 132`` then ``== GOLDEN``), or one hidden in a data file.
    Scanning for the digits alone was rejected instead — a bounding box, a
    tolerance or a page index may legitimately contain any of them, and a check
    that cries wolf is a check people delete. The real defence against tuning to
    golden is that no module in this phase imports a golden fixture at all; this
    is the mechanical backstop, not the whole of it.

    The scanner is proved to work on a text built to trip it before it is
    trusted on a text that does not.
    """
    positive = "assert measured " + "== " + "13" + "2"
    assert _GOLDEN_COMPARISON.search(positive), (
        "the golden-shape scanner cannot find a comparison even when one is "
        "present — every clean result below would be meaningless"
    )
    coincidence = "bbox = (0, 0, " + "13" + "2, " + "2" + "8)"
    assert not _GOLDEN_COMPARISON.search(coincidence), (
        "the scanner fires on a coincidental number in a tuple, which would "
        "make it noise a reader learns to ignore"
    )

    offences = {}
    for relative in _scanned_modules():
        if "phase28" not in relative.name:
            continue  # phases 23/24 audit their own literals; this is phase 28's
        text = (ROOT / relative).read_text(encoding="utf-8")
        if relative == THIS_FILE.relative_to(ROOT):
            # A guard that searches for a shape has to STATE that shape — in its
            # docstring, so a reader can tell what it does and does not catch,
            # and in the positive control above, so it is proved to work. This
            # function's own source is therefore excised before the scan, by its
            # source text rather than by a line range so the exclusion cannot
            # drift as the file grows. 28-05 established this idiom; every other
            # literal in this file is assembled instead, and the whole file is
            # still scanned for PAID tokens with nothing excised.
            text = text.replace(inspect.getsource(
                test_no_module_in_this_phase_compares_a_quantity_to_a_crow_golden
            ), "")
        hits = sorted({m.group(0).strip() for m in _GOLDEN_COMPARISON.finditer(text)})
        if hits:
            offences[str(relative)] = hits
    assert offences == {}, (
        "a Crow golden figure is compared against inside this phase: %s. "
        "Reaching a number by filtering until it matches is the coincidence "
        "trap this phase exists to end." % offences
    )


# ═════════════════════════════════════════════════════════════════════════════
# THE IRREPLACEABLE EVIDENCE
#
# Two Crow plans-only runs at $1.1573 of real spend. They are the entire factual
# basis of this phase: every one of its five plans reasons over them. Nothing in
# this module writes to that directory; these checks GUARD it.
# ═════════════════════════════════════════════════════════════════════════════


def test_the_paid_run_evidence_is_intact_and_this_check_fails_rather_than_skips():
    """Deliberately the ONE check here that may not skip.

    Every other check skips with a named reason when its fixture is absent,
    because a fixture nobody has is not a failure. This one is inverted on
    purpose: a skip would let a cleanup delete irreplaceable paid evidence and
    still show a green gate, which is precisely the risk being guarded. Absence
    is the failure.

    Modification is a failure too. The tree is frozen: the phase's assertions are
    predictions over what those runs recorded, and a tree that has been edited
    can be made to agree with anything. The working-tree check is skipped only
    when ``git`` itself is unavailable, and never because it reported dirt.
    """
    assert PAID_RUN_EVIDENCE.is_dir(), (
        "%s is GONE. It holds the only artifacts phase 28 reasons over and it "
        "cannot be regenerated without spending real money. Restore it from "
        "history." % PAID_RUN_EVIDENCE
    )
    for run in PAID_RUNS:
        takeoff = PAID_RUN_EVIDENCE / run / "takeoff.json"
        assert takeoff.is_file(), (
            "%s is missing. Both saved runs are load-bearing: the corroboration "
            "verdict, the thickness contest and the route classification are all "
            "asserted against them." % takeoff
        )
        payload = json.loads(takeoff.read_text(encoding="utf-8"))
        assert payload.get("takeoff_summary"), (
            "%s published no take-off rows — the evidence is present but hollow, "
            "which every check reading it would then skip over" % takeoff
        )

    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", str(PAID_RUN_EVIDENCE)],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except (OSError, ValueError):  # pragma: no cover — git absent
        pytest.skip("git is not available, so the tree cannot be checked")
    if proc.returncode != 0:  # pragma: no cover — not a work tree
        pytest.skip("not a git work tree, so the evidence tree cannot be checked")
    dirt = proc.stdout.decode("utf-8", "replace").strip()
    assert dirt == "", (
        "the frozen evidence tree has been modified:\n%s\nThose artifacts are "
        "this phase's factual basis; an edited tree can be made to agree with "
        "anything." % dirt
    )


def test_the_evidence_check_fails_rather_than_skipping_when_the_directory_is_absent(
    monkeypatch,
):
    """The inversion above, proved rather than promised.

    Patched through the function's OWN globals rather than by module path: this
    file can be imported under more than one module name across the suite, and a
    patch landing on a different module object would leave the check running
    against the real directory — it would then pass while proving nothing, the
    exact failure it exists to rule out.
    """
    target = test_the_paid_run_evidence_is_intact_and_this_check_fails_rather_than_skips
    monkeypatch.setitem(
        target.__globals__, "PAID_RUN_EVIDENCE", Path("/nonexistent/paid-run-evidence")
    )
    # An AssertionError, NOT a skip. `pytest.skip` raises `Skipped`, which
    # derives from BaseException rather than Exception, so a skip would escape a
    # broad `except Exception` and this guard would itself report as skipped — a
    # green tick for having checked nothing. Name the type.
    with pytest.raises(AssertionError) as excinfo:
        target()
    assert "paid-run-evidence" in str(excinfo.value)


# ═════════════════════════════════════════════════════════════════════════════
# THE PHASE'S LIMITS, AS CHECKS
#
# Rule 1's hardest part. A limit written as prose is a limit that rots silently.
# Each of these is a runnable claim about shipped behaviour, so it goes red the
# day it stops being true — including when it stops being true because somebody
# CLOSED it, which is what happened to two of them.
# ═════════════════════════════════════════════════════════════════════════════


def test_the_limits_phase_28_declared_two_of_which_later_work_closed():
    """What phase 28 did NOT close, re-measured on today's tree.

    The phase declared four limits. Two still stand, and two were closed after
    it — by the detection harness, NOT by Phase 25, which the phase named as
    their owner. Both are asserted as closed rather than left standing as
    claims, because a limit nobody re-checks is worse than no limit at all.

    **STILL STANDING — the perimeter hint names nothing on the plan page.**
    28-02 removed a wrong name and deliberately did not supply a right count.
    Asserted above in the V4-FIX-02 check, and re-stated here from the other
    side: the hint's candidate list is non-empty and its binding set is empty,
    so the object reaches a report as the absence of a NAME rather than the
    absence of an object.

    **STILL STANDING — the extraction pass is disclosed, not stabilised.**
    Stabilising it needs repeated sampling of a paid pass, which is not
    autonomously authorised, so the phase took the ROADMAP's second option and
    disclosed the variance instead. The disclosure exists (the reproducibility
    lines) and the variance is still measurable in the frozen evidence (the
    row-presence axis, asserted by name above).

    **CLOSED BY LATER WORK — Crow's Columns are measured.** The phase recorded
    "Columns remain unmeasured; they need detection, which is Phase 25". On
    today's tree the plan page yields a lattice candidate that the deterministic
    namer calls ``Columns`` and the structural-grid hint binds. That landed in
    the detection harness after this phase closed. It does not change anything
    phase 28 delivered; it changes what may be said about what phase 28 left
    behind, and this assertion is what keeps the two apart.

    **CLOSED BY LATER WORK — the Ladder route exists.** The phase inherited
    ``Ladder`` as unmeasured. The keynote number pattern accepted exactly two
    digits, so keynotes 1-9 were structurally invisible and the access-ladder
    keynote never entered the pipeline. It is widened now, and the plan page's
    legend carries that keynote. Whether the published count is right is not
    claimed here — only that the route is no longer absent.
    """
    from bobbytailor.deterministic.room_fill import _KEYNOTE_NUM_RE, keynote_legend
    from bobbytailor.vision import fusion as F

    bundle = _crow_page_zero_bundle()
    groups = bundle.get("symbol_groups") or []

    # 1. Still standing: the perimeter hint names nothing, and that is a refusal.
    perimeter_candidates = [
        g for g in groups
        if int(F._field(g, "count", 0) or 0) >= F._PERIMETER_MIN_COUNT
        and F._size_uniform(g) and F._is_small_marker(g) and F._is_2d_distributed(g)
    ]
    assert perimeter_candidates
    assert F._library_symbol_bindings(
        groups, {}, {"perimeter_jamb_symbol": {"name": "Bollard"}}
    ) == {}, "the perimeter hint started naming something again on this page"

    # 2. Still standing: the route disclosure exists and carries a real section.
    from bobbytailor.pipeline import reporter

    assert callable(getattr(reporter, "_reproducibility_lines", None)), (
        "the reproducibility disclosure is gone — the phase's answer to an "
        "unstabilised extraction pass was to SAY so in the artifact a human "
        "reads, and there is now nothing saying it"
    )

    # 3. Closed by later work: Columns.
    named_by_geometry = {
        F._field(g, "candidate_id", ""): F.deterministic_symbol_name(g)
        for g in groups
    }
    columns = sorted(
        cid for cid, name in named_by_geometry.items() if name == "Columns"
    )
    assert columns, (
        "no candidate on the plan page is deterministically named Columns. "
        "Phase 28 left Columns unmeasured and later detection work closed that "
        "gap; if the gap has REOPENED, this gate's account of the phase's "
        "standing limits is wrong and must be rewritten, not deleted."
    )
    assert F._library_symbol_bindings(
        groups, {}, {"structural_grid_symbol": {"name": "Column"}}
    ), "the grid hint no longer binds the lattice the harness detected"

    # 4. Closed by later work: the Ladder route.
    assert _KEYNOTE_NUM_RE.match("1"), (
        "single-digit keynotes are structurally invisible again — that is the "
        "defect that kept the access-ladder keynote out of the pipeline"
    )
    import fitz

    doc = fitz.open(str(CROW_FIXTURE_PDF))
    try:
        legend = keynote_legend(doc[CROW_PLAN_PAGE])
    finally:
        doc.close()
    entries = [
        str(v) for block in (legend or {}).values()
        for v in (block.values() if isinstance(block, dict) else [block])
    ]
    assert any("LADDER" in e.upper() for e in entries), (
        "the plan page's keynote legend no longer carries the access-ladder "
        "note, which is the entire text evidence for that line item"
    )


def test_no_requirement_is_ticked_that_this_phase_measured_to_be_open():
    """The two unticked requirements, and the tick each of them cannot have.

    ``V4-FIX-01`` and ``V4-FIX-03`` were each ADVANCED and neither was completed,
    and the reason is in both cases a measurement rather than a shortfall of
    effort. This check pins that the ROADMAP still says so, so the boundary
    cannot be quietly ticked in a document while the code stands still.

    The ROADMAP is read as TEXT here rather than asserted against shipped
    behaviour, and that is the one place this gate does so deliberately: what is
    being guarded is a claim in a planning document, and the behaviour behind it
    is already asserted by the two requirement checks above. Those two are what
    would go red if the code moved; this is what goes red if only the prose does.
    """
    roadmap = (ROOT / ".planning" / "ROADMAP.md")
    if not roadmap.is_file():
        pytest.skip("%s is absent" % roadmap)
    text = roadmap.read_text(encoding="utf-8")
    assert "V4-FIX-01" in text and "V4-FIX-03" in text, (
        "the ROADMAP no longer names this phase's requirements at all"
    )
    # The 28-06 line was narrowed against the evidence during execution; the
    # narrowing is the record of a falsified plan premise and must survive.
    assert "Door Frames-HM" in text, (
        "the ROADMAP's 28-06 line lost the falsification it was narrowed to "
        "carry — the one quantity the route classification cannot explain"
    )
