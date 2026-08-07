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

Everything here is FREE: no paid marker, no credential, no golden comparison, no
network, no write to the frozen evidence tree.
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
# The module's own contract
# ─────────────────────────────────────────────────────────────────────────────


def test_the_module_names_no_golden_literal():
    """No Crow item's expected quantity is typed here, and none is compared to.

    The module never reaches for the golden fixture — not by path, not by
    import, not by name. The tokens are assembled from halves so this check
    cannot trip on itself. Tuning a number until the gate went green is the
    failure mode this forbids.
    """
    text = THIS_FILE.read_text(encoding="utf-8")
    fixture_tokens = ("crow" + "_cass", "golden" + "_validator",
                      "_golden" + ".csv", "golden" + "_takeoff")
    hits = [t for t in fixture_tokens if t in text]
    assert hits == [], "this gate reached for a golden fixture: %s" % hits


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
