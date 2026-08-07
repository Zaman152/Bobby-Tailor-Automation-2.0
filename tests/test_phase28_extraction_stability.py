"""28-06 — every published number says which route produced it.

Phase 24 stabilised the NAMING layer and proved it: across the two saved paid
Crow runs the published ``(item, unit)`` key sets are identical and the 34
unnamed-geometry candidates are bit-identical. The residual variance sits one
layer upstream, in the per-sheet vision EXTRACTION pass — 113 raw line items in
one run against 124 in the other, and 3 of 51 published quantities moved.

This module pins the DISCLOSURE half of V4-FIX-05. Stabilising the extraction
pass would mean sampling a paid pass repeatedly, which this phase may not do;
what it can do is make the instability impossible to mistake for a settled
number. So every published row records a ``quantity_route`` saying how its
number was produced and, by implication, whether a re-run reproduces it:

  measured_from_drawing — geometry measured off the page, or a dimension read
                          verbatim out of the PDF text layer. Reproducible.
  printed_schedule      — copied out of a table or legend printed on the plans.
                          Reproducible, and stated by the designer rather than
                          measured by this app.
  sheet_reading         — a model read the number off a sheet image. A re-run
                          MAY answer differently. This is not a claim that the
                          number is wrong.

**One-directional, and asserted as such.** An unstable route predicts "this
number MAY move", never "this number DID move" — and agreement across two
samples is not evidence that a number cannot move.
:func:`test_the_saved_runs_a_reading_route_row_can_still_agree` exists so nobody
later upgrades the claim by deleting the caveat: if the caveat ever stops being
true, that assertion is what fails.

**A plan premise falsified, and asserted in its weaker true form.** 28-06's plan
predicted that every quantity that moved between the two saved runs would
classify as the reading route. It does not. ``Door Frames-HM`` published
``4.0 EA`` in run A off a row recorded ``provenance: geometry`` — the MEASURED
route — and published nothing at all in run B, because the backing row was never
extracted. The number did not move; the ROW vanished. That is a second axis, row
PRESENCE, which no per-run route classification can see, and
:func:`test_the_saved_runs_every_quantity_that_moved_is_explained` asserts the
honest disjunction instead of the plan's false stronger one. 28-01 measured the
same falsification from the corroboration side and warned this plan about it.

Everything here is FREE: no paid marker, no credential, no golden comparison, no
network, no write to the frozen evidence tree. The module audits itself for all
of that at the bottom.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bobbytailor.pipeline import aggregator  # noqa: E402
from bobbytailor.pipeline.aggregator import (  # noqa: E402
    QUANTITY_ROUTE_MEASURED,
    QUANTITY_ROUTE_PRINTED_SCHEDULE,
    QUANTITY_ROUTE_SHEET_READING,
    aggregate_takeoff,
)

THIS_FILE = Path(__file__)


# ─── helpers ────────────────────────────────────────────────────────────────


def _row(rows, name):
    matches = [r for r in rows if r["item"] == name]
    assert len(matches) == 1, "expected exactly one %r row, got %r" % (
        name, [r["item"] for r in rows]
    )
    return matches[0]


def _item(description, qty=3.0, unit="ea", **extra):
    """One calculated row shaped as ``_normalize_calculated`` hands it over.

    ``provenance`` and ``qty_source`` are absent unless a caller supplies them,
    which is the shape a per-sheet vision reading actually has — the 12 rows in
    run A and 23 in run B that carry no provenance at all.
    """
    item = {
        "description": description,
        "item_type": "component",
        "calculated_quantity": qty,
        "calculated_unit": unit,
        "source_sheet": "A-101",
        "formula": "count",
        "confidence": "medium",
        "auto_verified": True,
    }
    item.update(extra)
    return item


_EVIDENCE_ROOT = ROOT / ".planning" / "paid-run-evidence"
#: The phase-24 determinism A/B. FROZEN artifacts: opened read-only, never
#: re-scored, never rewritten. Re-scoring them after a code change returns the
#: same numbers because the numbers are what was saved — which is exactly why
#: this module reasons about their RECORDED FIELDS instead.
_RUN_A = "VisionOnly_P24DET_Crow_20260806_194607"
_RUN_B = "VisionOnly_P24DET_Crow_20260806_195704"


def _load_run(dir_name: str) -> dict:
    path = _EVIDENCE_ROOT / dir_name / "takeoff.json"
    if not path.exists():
        pytest.skip(
            "saved run %s is absent from .planning/paid-run-evidence — this gate "
            "asserts against recorded runs and will not pass without them"
            % dir_name
        )
    with open(path, "r", encoding="utf-8") as fh:  # read mode, always
        return json.load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — the route, and the one place its precedence lives
# ─────────────────────────────────────────────────────────────────────────────


def test_route_three_values_and_no_more():
    """Exactly three routes exist, and they are distinct strings.

    A fourth value appearing without a docstring saying what produced it and
    whether a re-run reproduces it is the drift this pins.
    """
    routes = {
        QUANTITY_ROUTE_MEASURED,
        QUANTITY_ROUTE_PRINTED_SCHEDULE,
        QUANTITY_ROUTE_SHEET_READING,
    }
    assert len(routes) == 3
    assert set(aggregator._QUANTITY_ROUTE_RANK) == routes


def test_route_geometry_is_the_measured_route():
    assert aggregator._quantity_route("geometry", "") == QUANTITY_ROUTE_MEASURED


def test_route_a_printed_dimension_is_the_measured_route():
    """``text_layer`` is a string read verbatim out of the PDF, not a reading of
    an image — a re-run over the same file returns the same characters."""
    assert aggregator._quantity_route("text_layer", "") == QUANTITY_ROUTE_MEASURED


def test_route_a_parsed_schedule_table_is_the_measured_route():
    assert aggregator._quantity_route("schedule_table", "") == QUANTITY_ROUTE_MEASURED


def test_route_a_plan_schedule_legend_takes_its_own_route():
    """The six ``plan_schedule_legend`` rows in each saved Crow run.

    Folding them into either neighbour would misstate them: a table the
    DESIGNER printed is reproducible, but it is a quantity stated on the plans
    rather than one this app measured.
    """
    assert aggregator._quantity_route(
        None, "plan_schedule_legend"
    ) == QUANTITY_ROUTE_PRINTED_SCHEDULE


def test_route_a_schedule_qty_source_takes_the_printed_schedule_route():
    assert aggregator._quantity_route(
        None, "schedule"
    ) == QUANTITY_ROUTE_PRINTED_SCHEDULE


def test_route_a_printed_schedule_outranks_a_geometry_provenance():
    """Precedence is stated once and tested where the two inputs disagree."""
    assert aggregator._quantity_route(
        "geometry", "plan_schedule_legend"
    ) == QUANTITY_ROUTE_PRINTED_SCHEDULE


def test_route_no_provenance_is_the_reading_route():
    """The shape of every row whose number a re-run may answer differently."""
    assert aggregator._quantity_route(None, "") == QUANTITY_ROUTE_SHEET_READING
    assert aggregator._quantity_route("", "") == QUANTITY_ROUTE_SHEET_READING


def test_route_vision_ensemble_is_the_reading_route():
    assert aggregator._quantity_route(
        "vision_ensemble", ""
    ) == QUANTITY_ROUTE_SHEET_READING


def test_route_an_unrecognised_provenance_falls_to_the_reading_route():
    """A string this function has never seen may never be read as reproducible.

    Same safe-floor reasoning as ``fusion.DEFAULT_PROVENANCE``: an unknown
    source is treated as the least reproducible one, so a typo in a future
    provenance value cannot silently promote a model reading.
    """
    assert aggregator._quantity_route(
        "geometrie", ""
    ) == QUANTITY_ROUTE_SHEET_READING


def test_route_the_deterministic_provenance_set_has_not_drifted():
    """The set this module keys on IS the one fusion and the reporter use.

    Carried by value rather than imported, because ``pipeline`` must keep taking
    no dependency on ``vision``. That indirection is only safe with a check that
    fails the moment the copies disagree — so this asserts all three at once.
    """
    from bobbytailor.pipeline import reporter
    from bobbytailor.vision import fusion

    assert set(aggregator._DETERMINISTIC_QUANTITY_PROVENANCES) == set(
        fusion.DETERMINISTIC_PROVENANCES
    )
    assert set(aggregator._DETERMINISTIC_QUANTITY_PROVENANCES) == set(
        reporter._DETERMINISTIC_PROVENANCES
    )


def test_route_the_schedule_qty_sources_are_the_calculators_own():
    """The printed-table markers are IMPORTED from the calculator, not restated.

    Both modules live in ``pipeline``, so there is no dependency-direction
    reason for a second copy here — and a second copy is how the calculator
    starts stamping a marker this layer no longer recognises.
    """
    from bobbytailor.pipeline import calculator

    assert (aggregator._SCHEDULE_QTY_SOURCES
            is calculator._SCHEDULE_QTY_SOURCES)


def test_route_precedence_the_least_reproducible_contributor_wins():
    """A quantity is only as reproducible as its least reproducible contributor.

    Deliberately the mirror of :func:`aggregator._stronger_corroboration`, which
    takes the BEST verdict: corroboration is evidence, and one good witness
    vouches for the whole; reproducibility is a property of the weakest link.
    Asserted in both argument orders so the answer cannot depend on row order.
    """
    worse = aggregator._less_reproducible_route
    for a, b in (
        (QUANTITY_ROUTE_MEASURED, QUANTITY_ROUTE_SHEET_READING),
        (QUANTITY_ROUTE_PRINTED_SCHEDULE, QUANTITY_ROUTE_SHEET_READING),
    ):
        assert worse(a, b) == QUANTITY_ROUTE_SHEET_READING
        assert worse(b, a) == QUANTITY_ROUTE_SHEET_READING
    assert worse(
        QUANTITY_ROUTE_MEASURED, QUANTITY_ROUTE_PRINTED_SCHEDULE
    ) == QUANTITY_ROUTE_PRINTED_SCHEDULE
    assert worse(
        QUANTITY_ROUTE_PRINTED_SCHEDULE, QUANTITY_ROUTE_MEASURED
    ) == QUANTITY_ROUTE_PRINTED_SCHEDULE


def test_route_precedence_none_means_nothing_has_contributed_yet():
    """``None`` is not a route and never wins over one, in either order."""
    worse = aggregator._less_reproducible_route
    assert worse(None, QUANTITY_ROUTE_MEASURED) == QUANTITY_ROUTE_MEASURED
    assert worse(QUANTITY_ROUTE_MEASURED, None) == QUANTITY_ROUTE_MEASURED
    assert worse(None, None) is None
    assert worse("", QUANTITY_ROUTE_MEASURED) == QUANTITY_ROUTE_MEASURED


def test_route_precedence_lives_in_exactly_one_place(monkeypatch):
    """The rank table is the object the combiner actually consults.

    A liveness proof rather than a reading of the source: reverse the table and
    the combiner's answer must move with it. If it does not, a second copy of
    the precedence is deciding, which is the drift this guards.
    """
    reversed_rank = {
        QUANTITY_ROUTE_SHEET_READING: 2,
        QUANTITY_ROUTE_PRINTED_SCHEDULE: 1,
        QUANTITY_ROUTE_MEASURED: 0,
    }
    monkeypatch.setattr(aggregator, "_QUANTITY_ROUTE_RANK", reversed_rank)
    assert aggregator._less_reproducible_route(
        QUANTITY_ROUTE_MEASURED, QUANTITY_ROUTE_SHEET_READING
    ) == QUANTITY_ROUTE_MEASURED


def test_route_an_unknown_route_string_is_ranked_least_reproducible():
    assert aggregator._less_reproducible_route(
        QUANTITY_ROUTE_MEASURED, "invented_route"
    ) == "invented_route"


# ─── the route on a PUBLISHED row ───────────────────────────────────────────


def test_route_a_published_geometry_row_carries_the_measured_route():
    rows = aggregate_takeoff([
        _item("hollow metal frame", qty=4.0, provenance="geometry"),
    ])
    assert _row(rows, "Frame-HM")["quantity_route"] == QUANTITY_ROUTE_MEASURED


def test_route_a_published_reading_row_carries_the_reading_route():
    rows = aggregate_takeoff([_item("aluminum window unit", qty=6.0)])
    assert _row(rows, "Windows")["quantity_route"] == QUANTITY_ROUTE_SHEET_READING


def test_route_a_mixed_bucket_takes_the_less_reproducible_route():
    """One reading in the bucket makes the whole published number a reading.

    Asserted in BOTH insertion orders: the deterministic row first, then the
    reading first. A roll-up that answered differently depending on which sheet
    was processed first would be exactly the silent variance this field exists
    to expose.
    """
    deterministic = _item("Bollard at dock", qty=8.0, provenance="geometry")
    reading = _item("bollards along drive", qty=3.0)
    for items in ([deterministic, reading], [reading, deterministic]):
        rows = aggregate_takeoff([dict(i) for i in items])
        row = _row(rows, "Bollards")
        assert row["quantity_route"] == QUANTITY_ROUTE_SHEET_READING
        assert row["quantity"] == 11.0


def test_route_a_bucket_of_only_deterministic_rows_stays_measured():
    rows = aggregate_takeoff([
        _item("Bollard at dock", qty=8.0, provenance="geometry"),
        _item("bollard row north", qty=3.0, provenance="text_layer"),
    ])
    assert _row(rows, "Bollards")["quantity_route"] == QUANTITY_ROUTE_MEASURED


def test_route_a_blank_row_carries_no_route():
    """There is no number to characterise, so no route is invented for one.

    A blank that acquired a route would read as a quantity with a pedigree —
    the "blank rendered as a value" failure this codebase keeps closing, in a
    new column.
    """
    class _Manifest:
        """The smallest manifest the aggregator will accept: it names nothing on
        the sheet and reports one object it never found."""

        def resolve(self, description, unit):
            return None

        def missing(self, present):
            from types import SimpleNamespace
            return [SimpleNamespace(name="Ladder", unit="EA", measure="count")]

    rows = aggregate_takeoff([_item("aluminum window unit", qty=6.0)],
                             manifest=_Manifest())
    blank = _row(rows, "Ladder")
    assert blank["quantity"] is None
    assert blank["quantity_route"] is None
    assert "quantity_route" in blank, (
        "the column must still exist on a blank row — an absent key and an "
        "empty cell are different facts to a spreadsheet reader"
    )


def test_route_a_withheld_number_carries_no_route():
    """A detail-sheet count is WITHHELD, so it publishes no route either.

    The row had a contributing calculated row and a real reading behind it, and
    the number was still refused — so the honest answer is no route at all,
    not the route the refused reading came by.
    """
    rows = aggregate_takeoff([
        _item("Stair / Stair Run", qty=1.0,
              count_corroboration="detail_sheet_only",
              count_evidence_sheet_kind="detail"),
    ])
    withheld = _row(rows, "Stairs")
    assert withheld["quantity"] is None
    assert withheld["quantity_route"] is None


def test_route_an_injected_standard_line_item_carries_no_route():
    """Mobilization is a convention the APP injects; no row produced its number.

    Nobody read it, measured it or printed it on a plan, so none of the three
    routes describes it and it takes none of them.
    """
    rows = aggregate_takeoff([_item("aluminum window unit", qty=6.0)])
    mobilization = [r for r in rows if r["item_type"] == "standard_line_item"]
    assert mobilization, "no standard line item was injected"
    for row in mobilization:
        assert row["quantity_route"] is None


def test_route_nothing_else_about_the_published_row_shape_moved():
    """The ONLY new key is the route, checked against the frozen runs' shape.

    The saved paid runs are the record of what a published row looked like
    before this plan. Comparing the emitted key set against theirs is a
    stronger check than an inline list, because the expectation cannot be
    edited to match a regression.
    """
    saved = _load_run(_RUN_A)
    recorded_keys = set().union(*(set(r) for r in saved["takeoff_summary"]))
    rows = aggregate_takeoff([
        _item("Bollard at dock", qty=8.0, provenance="geometry"),
        _item("aluminum window unit", qty=6.0),
    ])
    for row in rows:
        assert set(row) == recorded_keys | {"quantity_route"}, (
            "the published row shape changed by more than the route: %s"
            % sorted(set(row) ^ (recorded_keys | {"quantity_route"}))
        )


def test_route_no_status_quantity_or_flag_moved_when_the_route_was_added():
    """The route describes a number; it must not change one, or any verdict.

    Same three rows through the aggregator, asserted against values computed by
    hand from the inputs rather than from a golden take-off.
    """
    rows = aggregate_takeoff([
        _item("Bollard at dock", qty=8.0, provenance="geometry"),
        _item("bollards along drive", qty=3.0),
        _item("aluminum window unit", qty=6.0),
    ])
    bollards = _row(rows, "Bollards")
    assert bollards["quantity"] == 11.0
    assert bollards["unit"] == "EA"
    assert bollards["needs_review"] is False
    windows = _row(rows, "Windows")
    assert windows["quantity"] == 6.0
    assert windows["provenance"] == "MEASURED"


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — pinned against the two saved runs, never against a golden number


def _published(run: dict) -> dict:
    return {(r["item"], r["unit"]): r for r in run.get("takeoff_summary", [])}


def _backing_rows(run: dict, summary_row: dict) -> list:
    """The calculated rows the published row was rolled up from."""
    wanted = {(d.get("sheet"), d.get("description"))
              for d in (summary_row.get("detail") or [])}
    return [r for r in run.get("calculated_takeoff", [])
            if (r.get("source_sheet"), r.get("description")) in wanted]


def _route_of_published(run: dict, summary_row: dict):
    """Run the SHIPPED classifier over a published row's own recorded rows.

    Returns ``None`` when the row published no number — the blank case, which
    carries no route by construction.
    """
    if summary_row.get("quantity") is None:
        return None
    route = None
    for row in _backing_rows(run, summary_row):
        route = aggregator._less_reproducible_route(
            route,
            aggregator._quantity_route(row.get("provenance"), row.get("qty_source")),
        )
    return route


def _quantity_key(row: dict) -> tuple:
    return (row.get("item_type"),
            str(row.get("calculated_unit") or "").lower(),
            row.get("calculated_quantity"))


def _differing_keys(a: dict, b: dict) -> list:
    pa, pb = _published(a), _published(b)
    return sorted(k for k in set(pa) & set(pb)
                  if pa[k].get("quantity") != pb[k].get("quantity"))


def test_the_saved_runs_are_comparable_and_did_disagree():
    """NON-VACUITY. Without this the prediction below proves nothing.

    Two conditions, both required:

    * the published ``(item, unit)`` key sets are EQUAL, so "differs" is a
      comparison of the same rows and not an artifact of one run publishing
      something the other never did; and
    * at least one quantity actually differs, so the prediction test iterates
      over a non-empty set.

    This is the trap 24-09 and 24-10 each had to close in their own gates: a
    for-loop over an empty set passes and asserts nothing. Demonstrated once by
    running the prediction against two copies of the SAME directory, where this
    check fails on its second assertion and the prediction still passed.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)
    pa, pb = _published(a), _published(b)
    assert set(pa) == set(pb), (
        "the two runs published different key sets, so a quantity comparison "
        "between them is not like-for-like: only-in-A %s, only-in-B %s"
        % (sorted(set(pa) - set(pb)), sorted(set(pb) - set(pa)))
    )
    assert _differing_keys(a, b), (
        "the two saved runs published no differing quantity — the prediction "
        "below would iterate over an empty set and assert nothing"
    )


def test_the_saved_runs_every_quantity_that_moved_is_explained():
    """The prediction, in the strongest form the evidence actually supports.

    The differing keys are computed at runtime by comparing the two published
    lists; they are never typed in as the subject of the assertion. (For the
    reader they are ``Stairs``, ``Lift`` and ``Door Frames-HM``.)

    **The plan's stronger claim is false and is not asserted here.** 28-06's
    plan predicted every quantity that moved would classify as the reading
    route. ``Door Frames-HM`` does not: run A published ``4.0 EA`` off a row
    recorded ``provenance: geometry``, which is the MEASURED route, and run B
    published no number at all because that row was never extracted. The number
    did not move — the ROW vanished.

    So for each differing key, in each run, exactly one of three things is true
    and one of them is asserted:

    1. the route is the READING route — the number came by a route a re-run may
       answer differently, which is what this plan discloses; or
    2. there is NO route, because that run published a blank — an absence is
       already visible as an absence and needs no route to say so; or
    3. the route is deterministic AND the backing row is absent from the other
       run entirely — the extraction pass did not produce the row at all. That
       is a second axis, row PRESENCE, which no per-run route classification can
       see and which this plan does not claim to catch.

    Disjunct 3 is the falsification, kept in the assertion rather than scoped
    around it. 28-01 measured the same fact from the corroboration side.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)
    pa, pb = _published(a), _published(b)
    differing = _differing_keys(a, b)
    if not differing:
        pytest.skip("the two saved runs published no differing quantity to explain")

    other_side = {
        _RUN_A: {_quantity_key(r) for r in b.get("calculated_takeoff", [])},
        _RUN_B: {_quantity_key(r) for r in a.get("calculated_takeoff", [])},
    }

    reading_route_hits = 0
    vanished_row_hits = 0
    for key in differing:
        for run_name, run, published in ((_RUN_A, a, pa), (_RUN_B, b, pb)):
            summary_row = published[key]
            route = _route_of_published(run, summary_row)
            if route is None:
                assert summary_row.get("quantity") is None, (
                    "%s in %s published a number and no route — every published "
                    "quantity must state how it was produced" % (key, run_name)
                )
                continue
            if route == QUANTITY_ROUTE_SHEET_READING:
                reading_route_hits += 1
                continue
            missing = [r for r in _backing_rows(run, summary_row)
                       if _quantity_key(r) not in other_side[run_name]]
            assert missing, (
                "%s in %s is backed only by rows the classifier calls %r, and "
                "every one of them also exists in the other run — so the "
                "published quantity moved for a reason neither the route nor "
                "row presence explains, and neither may be claimed to"
                % (key, run_name, route)
            )
            vanished_row_hits += 1

    assert reading_route_hits, (
        "no differing quantity was explained by the reading route — the "
        "classification would then be carried entirely by its escape hatches "
        "and would be disclosing nothing"
    )
    assert vanished_row_hits, (
        "no differing quantity needed the vanished-row disjunct — if that ever "
        "becomes true the plan's stronger claim has become sayable and this "
        "docstring's falsification must be revisited rather than left standing"
    )


def test_the_saved_runs_the_measured_route_partition_held_its_numbers():
    """Every deterministically-recorded row in A has a quantity-equal twin in B.

    Asserted over QUANTITIES only, and deliberately so: the descriptions in
    that partition DID move. The same 136-count cluster is described as
    ``personnel door`` in one run and ``DOOR`` in the other, at an identical
    count. The quantity held; the text did not — which is exactly why the route
    keys on the recorded provenance and never on the description.

    The one row this cannot find a twin for is proven to belong to a published
    key whose quantity differed, i.e. the vanished-row case the test above
    isolates, rather than being scoped out of the assertion.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)
    deterministic_a = [
        r for r in a.get("calculated_takeoff", [])
        if aggregator._quantity_route(r.get("provenance"), r.get("qty_source"))
        != QUANTITY_ROUTE_SHEET_READING
    ]
    if not deterministic_a:
        pytest.skip("run A recorded no deterministic calculated row")
    twins_b = {_quantity_key(r) for r in b.get("calculated_takeoff", [])}

    differing = set(_differing_keys(a, b))
    backing_a_differing = {
        (r.get("source_sheet"), r.get("description"))
        for key in differing
        for r in _backing_rows(a, _published(a)[key])
    }

    for row in deterministic_a:
        if _quantity_key(row) in twins_b:
            continue
        assert (row.get("source_sheet"), row.get("description")) in backing_a_differing, (
            "a deterministically-recorded row in run A has no quantity-equal "
            "counterpart in run B and does not back any published key whose "
            "quantity differed: %r" % (row.get("description"),)
        )


def test_the_saved_runs_a_reading_route_row_can_still_agree():
    """THE LIMIT, as a runnable assertion rather than a comment.

    At least one published row whose number came by the READING route holds the
    same quantity across both runs. That is why the claim this plan makes is
    one-directional: an unstable route says the number MAY be answered
    differently by a re-run, never that it WILL be, and agreement across two
    samples is not evidence that a number cannot move.

    This test exists so that nobody later upgrades the claim by deleting the
    caveat: if the caveat stopped being true, this assertion is what fails.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)
    pa, pb = _published(a), _published(b)

    agreed = []
    for key in sorted(set(pa) & set(pb)):
        if pa[key].get("quantity") != pb[key].get("quantity"):
            continue
        if pa[key].get("quantity") is None:
            continue
        if (_route_of_published(a, pa[key]) == QUANTITY_ROUTE_SHEET_READING
                and _route_of_published(b, pb[key]) == QUANTITY_ROUTE_SHEET_READING):
            agreed.append(key)

    assert agreed, (
        "no reading-route row agreed across the two runs — if that is really "
        "so, the one-directional caveat this module pins is no longer "
        "supported by the evidence and must be re-derived, not deleted"
    )


def test_the_saved_runs_the_printed_schedule_partition_is_named_and_stable():
    """The printed-table route is a real partition of the evidence, not a stub.

    Both saved runs recorded rows whose ``qty_source`` says the number came off
    a table printed on the plans. If that partition were empty, giving it its
    own route value would be an untested branch dressed as a distinction.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)
    for name, run in ((_RUN_A, a), (_RUN_B, b)):
        printed = [
            r for r in run.get("calculated_takeoff", [])
            if aggregator._quantity_route(r.get("provenance"), r.get("qty_source"))
            == QUANTITY_ROUTE_PRINTED_SCHEDULE
        ]
        assert printed, (
            "%s recorded no printed-schedule row, so the route's own value is "
            "unexercised by the evidence" % name
        )


def test_the_saved_runs_were_opened_read_only():
    """The frozen evidence tree is READ, never touched.

    Asserted of this module's own source: every ``open`` here is
    ``with``-managed and passes an explicit read mode, and no mutating
    primitive appears at all. The mutating tokens are assembled from halves and
    the mode check is a regex over the call sites, because a substring scan for
    a write mode has to spell one out and would then fail on itself — the
    self-defeating grep 24-09, 24-10 and 28-01 each hit.
    """
    text = THIS_FILE.read_text(encoding="utf-8")

    sites = [m.start() for m in re.finditer(r"\bopen\(", text)]
    assert sites, "no open call site in this file — the read-only check is vacuous"
    for offset in sites:
        assert text[max(0, offset - 5):offset] == "with ", (
            "an unmanaged open call in a read-only gate, at offset %d" % offset
        )
    for args in re.findall(r"\bopen\(([^)]*)\)", text):
        assert re.search(r"""['"]r['"]""", args), (
            "an open call in a read-only gate states no read mode: %s" % args
        )

    forbidden = (
        "json." + "dump",
        ".unlink" + "(",
        ".write" + "_text(",
        ".mkdir" + "(",
        "shutil." + "rmtree",
    )
    hits = [token for token in forbidden if token in text]
    assert hits == [], "mutating primitives in a read-only gate: %s" % hits


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 — the artifact a human actually reads
# ─────────────────────────────────────────────────────────────────────────────


def test_the_summary_section_names_exactly_what_a_real_aggregation_routed():
    """The section's membership is DERIVED from the aggregator's own output.

    No item name is typed in as the expectation and no count is asserted as a
    literal: the aggregator is run over a mixed set of rows, and the section is
    then required to name every published row it routed to the reading route and
    no other published row. A section that named one row too many or one too few
    would be describing a take-off the run did not produce.
    """
    from bobbytailor.pipeline.reporter import _reproducibility_lines

    rows = aggregate_takeoff([
        _item("hollow metal frame", qty=4.0, provenance="geometry"),
        _item("Bollard at dock", qty=8.0, provenance="text_layer"),
        _item("aluminum window unit", qty=6.0),
        _item("Sprinkler head", qty=12.0),
        _item("door schedule count", qty=29.0, qty_source="plan_schedule_legend"),
    ])
    text = "\n".join(_reproducibility_lines({"takeoff_summary": rows}))

    reading = {r["item"] for r in rows
               if r.get("quantity_route") == QUANTITY_ROUTE_SHEET_READING}
    assert reading, "the fixture routed nothing to the reading route"
    for name in reading:
        assert name in text, "%r took the reading route and is not named" % name
    for row in rows:
        if row["item"] in reading:
            continue
        assert row["item"] not in text, (
            "%r did not take the reading route and must not be named: route %r"
            % (row["item"], row.get("quantity_route"))
        )


def test_the_summary_section_never_names_a_row_that_published_no_number():
    """A blank has no route, so it cannot appear among the unreproducible.

    The failure this forbids is specific: listing a never-measured row under a
    heading about numbers a re-run may answer differently would tell a reader
    there IS a number and that it is shaky, when there is no number at all.
    """
    from bobbytailor.pipeline.reporter import _reproducibility_lines

    rows = aggregate_takeoff([
        _item("Stair / Stair Run", qty=1.0,
              count_corroboration="detail_sheet_only",
              count_evidence_sheet_kind="detail"),
        _item("Sprinkler head", qty=12.0),
    ])
    withheld = [r for r in rows if r["quantity"] is None]
    assert withheld, "the fixture withheld nothing"
    text = "\n".join(_reproducibility_lines({"takeoff_summary": rows}))
    for row in withheld:
        assert row["item"] not in text


# ─────────────────────────────────────────────────────────────────────────────
# The module's own contract
# ─────────────────────────────────────────────────────────────────────────────


def test_the_module_names_no_golden_literal():
    """No Crow item's expected quantity is typed here, and none is compared to.

    Two checks, because either alone is dodgeable:

    1. The module never reaches for the golden fixture — not by path, not by
       import, not by name. The tokens are assembled from halves so this check
       cannot trip on itself.
    2. No assertion inside the evidence-backed section compares against a
       numeric literal. Every expectation there is derived from the OTHER run's
       recorded fields at runtime. Tuning a number until the gate went green is
       the failure mode this forbids.
    """
    text = THIS_FILE.read_text(encoding="utf-8")
    fixture_tokens = ("crow" + "_cass", "golden" + "_validator",
                      "_golden" + ".csv", "golden" + "_takeoff")
    hits = [t for t in fixture_tokens if t in text]
    assert hits == [], "this gate reached for a golden fixture: %s" % hits

    parts = text.split("# Task 2 —", 1)
    assert len(parts) == 2, "the evidence section marker moved"
    section = parts[1].split("# The module's own contract", 1)[0]
    offenders = [
        line.strip() for line in section.splitlines()
        if "assert" in line
        and re.search(r"[=!<>]=?\s*-?\d+(\.\d+)?\s*(,|\)|$)", line)
    ]
    assert offenders == [], (
        "an evidence assertion compares against a numeric literal: %s" % offenders
    )


def test_the_whole_module_runs_free():
    """No paid marker, no paid script name, no credential, anywhere in this file."""
    text = THIS_FILE.read_text(encoding="utf-8")
    # Assembled from halves on purpose: the check is a substring scan over this
    # very file, so spelling a marker out would make the module fail its own
    # audit.
    forbidden = (
        "pytest.mark." + "golden",
        "accuracy" + "_gate",
        "vision_only" + "_benchmark",
        "golden" + "_convergence",
        "ANTHROPIC" + "_API_KEY",
        "REPLAY" + "_RECORD",
    )
    hits = [token for token in forbidden if token in text]
    assert hits == [], "paid-gate markers in a free module: %s" % hits
