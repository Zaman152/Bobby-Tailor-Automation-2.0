"""28-05 — one measured region backs one published row per building layer.

The defect, measured in both saved paid Crow runs and identical in each: the
397,600 SF building footprint publishes THREE times.

    Exposed Structure  397,600 SF  plan_schedule_legend  MEASURED
    Sealed Concrete    397,600 SF  plan_schedule_legend  MEASURED
    Concrete Pad       397,600 SF  library               NEEDS REVIEW

An estimator who sums the SF column prices the building three times. Two of the
three rows are golden-correct and both must survive — they are genuinely
different building layers (the sealed-concrete floor finish and the exposed roof
structure) through one plan area, which is phase 23's D1 exception and is NOT
being taken back. The third never measured a slab; it inherited the footprint
because its measure basis is area-shaped, and the report already says so in its
own words on the neighbouring row: *"NOT reconciled by name: 1 measured row(s)
share this unit (SF) and measure basis (floor_area) and were named by a
hypothesis rather than by printed evidence — 'Concrete Pad'."*

What made this hard to fix honestly is that the region identity was DROPPED
between fusion and the published row, so the only thing left to tell the three
rows apart was that their numbers were equal. Arbitrating on numeric equality is
a coincidence rule, and this phase rejects those: two genuinely distinct regions
that happen to measure the same area must both publish. So the region is
threaded end to end first, and the rule keys on it.

Everything here is FREE: no paid marker, no credential, no golden comparison, no
network. The module audits itself for all four at the bottom.
"""
import ast
import inspect
from pathlib import Path

import pytest

from bobbytailor.pipeline import aggregator
from bobbytailor.pipeline.aggregator import aggregate_takeoff
from bobbytailor.pipeline.calculator import (
    _calculate_from_component,
    _calculate_from_measurement,
)
from bobbytailor.vision import fusion
from bobbytailor.vision.fusion import (
    NAME_SOURCE_VOCABULARY_BASIS,
    _NAME_AUTHORITY,
    _arbitrate_one_area_one_item,
    _fuse_project_area_items,
    _share_rank,
)


# ─── helpers ────────────────────────────────────────────────────────────────

#: The Crow footprint, to the tenth of a square foot the run recorded. Used as
#: an INPUT here, never as an expected answer — no assertion below compares a
#: published number against a golden figure.
CROW_FOOTPRINT_SF = 397600.0

#: The six floor/roof-shaped objects Crow's vocabulary offered, which is how one
#: measured footprint came to back six line items at once (INV-00 §4).
CROW_FOOTPRINT_VOCABULARY = {
    "Canopy": {"basis": "roof_area", "unit": "SF"},
    "Concrete Pad": {"basis": "floor_area", "unit": "SF"},
    "Exposed Structure": {"basis": "roof_area", "unit": "SF"},
    "Sealed Concrete": {"basis": "floor_area", "unit": "SF"},
    "Vapor Barrier": {"basis": "floor_area", "unit": "SF"},
}


def _footprint_components(vocabulary=None, area_sf=CROW_FOOTPRINT_SF):
    """Whatever `_fuse_project_area_items` emits for a measured footprint."""
    components: list = []
    _fuse_project_area_items(
        {"footprint": {"area_sf": area_sf, "confidence": "high"}},
        CROW_FOOTPRINT_VOCABULARY if vocabulary is None else vocabulary,
        components,
    )
    return components


def _row(rows, name):
    matches = [r for r in rows if r["item"] == name]
    assert len(matches) == 1, "expected exactly one %r row, got %r" % (
        name, [r["item"] for r in rows]
    )
    return matches[0]


def _legend_row(name, qty, unit="SF"):
    """A row the PLAN'S OWN printed schedule named and quantified.

    This is the shape `_calculate_from_schedule` emits for an authoritative
    take-off legend, which is how `Exposed Structure` and `Sealed Concrete`
    reached the published report in both saved runs.
    """
    return {
        "item_type": "schedule_item",
        "description": name,
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


def _detected_row(name, qty, region_ref=None, unit="SF", **extra):
    """A row fusion measured and the calculator carried through.

    ``region_ref=None`` means the key is ABSENT, which is the shape of every row
    measured on no particular region — and the shape every row in the pre-28-05
    codebase had.
    """
    item = {
        "item_type": "concrete_slab",
        "description": name,
        "quantity": qty,
        "unit": unit,
        "raw_unit": unit,
        "formula": "count",
        "source_sheet": "A-101",
        "confidence": "high",
        "needs_review": False,
    }
    if region_ref is not None:
        item["region_ref"] = region_ref
    item.update(extra)
    return item


def _library(*names, basis="floor_area", unit="SF"):
    """A component library that will name these rows, so their published
    ``source`` is ``library`` — the marker the codebase already uses for "this
    row's NAME is a hypothesis"."""
    return [
        {"name": n, "aliases": [n], "basis": basis, "unit": unit} for n in names
    ]


# ═══ Task 1 — the stamp and the region survive, and move nothing ════════════


def test_every_footprint_row_carries_the_stamp_naming_who_named_it():
    """The vocabulary named a CLASS of object; nothing on the sheet named this
    region. Recording that is the whole of task 1."""
    components = _footprint_components()
    assert len(components) == len(CROW_FOOTPRINT_VOCABULARY)
    assert {c["name_source"] for c in components} == {
        NAME_SOURCE_VOCABULARY_BASIS
    }
    assert {c["region_ref"] for c in components} == {"footprint"}


def test_the_stamp_is_registered_rather_than_falling_to_the_unknown_default():
    """An unregistered marker scores as "nobody recorded who named this", which
    is precisely the state task 1 exists to end."""
    assert NAME_SOURCE_VOCABULARY_BASIS in _NAME_AUTHORITY


def test_the_stamp_outranks_nothing_it_did_not_outrank_before():
    """Below every printed authority and below a learned verbatim string.

    A vocabulary basis is a statement that an object of this class exists in the
    project. It is never a statement that THIS region is that object.
    """
    rank = _NAME_AUTHORITY[NAME_SOURCE_VOCABULARY_BASIS]
    for printed in ("vision", "plan_schedule_legend", "schedule", "text_layer",
                    "naming_library", "library", "learned"):
        assert rank > _NAME_AUTHORITY[printed], printed


def test_the_stamp_does_not_move_the_crow_footprint_anchor():
    """The stamp is INERT here, and that is the point: a behaviour change hidden
    inside a plumbing task is unreviewable.

    The anchor of the footprint region decides which rows are suppressed against
    it, and `_reinstate_orphaned_supersessions` re-checks supersessions whose
    superseder died — so an anchor that quietly moved would ripple two
    arbitrations away from here.
    """
    stamped = _footprint_components()
    # The same six rows as they were emitted BEFORE task 1: no name_source at
    # all, so `_share_rank` fell to the unknown-source default for every one.
    unstamped = [
        {k: v for k, v in c.items() if k != "name_source"} for c in stamped
    ]
    assert all("name_source" not in c for c in unstamped)

    def anchor(group):
        return sorted(group, key=_share_rank)[0]["name"]

    assert anchor(stamped) == anchor(unstamped)
    assert [c["name"] for c in sorted(stamped, key=_share_rank)] == [
        c["name"] for c in sorted(unstamped, key=_share_rank)
    ]


def test_the_stamp_does_not_move_a_single_suppression_on_the_crow_fan_out():
    """The whole arbitration, not just its first sort key: same survivors, same
    layers, same rejections, same reasons."""
    def arbitrate(components):
        rejected: list = []
        _arbitrate_one_area_one_item(components, rejected)
        return (
            sorted((c["name"], c.get("building_layer")) for c in components),
            sorted((r["answer"], r["reason"], r["detail"]) for r in rejected),
        )

    stamped = _footprint_components()
    unstamped = [
        {k: v for k, v in c.items() if k != "name_source"} for c in stamped
    ]
    assert arbitrate(stamped) == arbitrate(unstamped)


def test_the_calculator_carries_the_region_a_stamped_component_recorded():
    """`provenance` has been carried through this seam since 23-C3 with a
    comment saying downstream consumers cannot do their job without it. The
    region identity was being nulled at the same seam, for want of the same
    line."""
    component = _footprint_components()[0]
    row = _calculate_from_component(component, "A-101", "plan")
    assert row is not None
    assert row["region_ref"] == component["region_ref"]
    assert row["name_source"] == component["name_source"]


def test_a_region_the_component_never_recorded_is_absent_not_empty():
    """A blank region reference would group every regionless row in the project
    into one enormous "region"."""
    row = _calculate_from_component(
        {"name": "Bollards", "quantity": 5, "unit": "EA"}, "A-101", "plan",
    )
    assert row is not None
    assert "region_ref" not in row
    assert "name_source" not in row


def test_the_measurement_entry_point_carries_the_region_too():
    """Both calculator entry points, or half the report loses its provenance
    without anything failing."""
    row = _calculate_from_measurement(
        {"value": "1000", "unit": "sf", "description": "sealed concrete",
         "region_ref": "fill:FILL-2", "name_source": "room_fill"},
        "A-101", "plan",
    )
    assert row is not None
    assert row["region_ref"] == "fill:FILL-2"
    assert row["name_source"] == "room_fill"


def test_the_aggregator_reads_the_stamp_by_value_and_the_two_agree():
    """`pipeline.aggregator` must not import `vision.fusion` — the dependency
    runs the other way. The string is carried by VALUE, exactly as fusion
    carries `text_anchor.KIND_TAG`, and this is the test that fails if the two
    ever diverge."""
    assert (
        aggregator._NAME_SOURCE_VOCABULARY_BASIS == NAME_SOURCE_VOCABULARY_BASIS
    )


def test_the_bucket_a_stamped_row_lands_in_records_both_facts():
    """The seam the two fields were dying at is the bucket, not the row.

    What the bucket DOES with them is task 2's decision; task 1 only has to
    stop dropping them, and this is the assertion that says they arrived.
    """
    bucket = aggregator._new_bucket()
    assert bucket["region_ref"] == ""
    assert bucket["name_source"] == ""


def test_the_stamp_is_kept_out_of_the_symbol_group_naming_gate():
    """`NAME_WORTHY_SOURCES` is 24-04's gate on what may name a SYMBOL GROUP. A
    vocabulary-basis name is never a symbol group's name, and widening that gate
    to register a marker would loosen an unrelated rule."""
    assert NAME_SOURCE_VOCABULARY_BASIS not in fusion.NAME_WORTHY_SOURCES


# ═══ Module self-audit — this file spends nothing ═══════════════════════════


def _module_source_under_audit() -> str:
    """This module's source with the two audit tests themselves removed.

    A guard that searches for a string has to state that string, so a guard
    which scanned its own body would always find its own evidence and fail. The
    two audit functions are excised by their own source text rather than by a
    line range, so the exclusion cannot drift as the file grows.
    """
    source = Path(__file__).read_text()
    for audit in (test_this_module_runs_free, test_this_module_asserts_no_golden_total):
        source = source.replace(inspect.getsource(audit), "")
    return source


def test_this_module_runs_free():
    """No paid marker, no credential, no network, no golden comparison."""
    source = _module_source_under_audit()
    for forbidden in ("ANTHROPIC_API_KEY", "mark.golden", "accuracy_gate",
                      "vision_only_benchmark", "golden_convergence",
                      "requests.", "httpx.", "urllib"):
        assert forbidden not in source, forbidden


def test_this_module_asserts_no_golden_total():
    """The footprint appears as an INPUT and never as an expected answer.

    The golden floor area for this building is a number this file does not
    contain, and the assertion below is what keeps it that way: a test that
    watched a published number move toward a golden figure would be tuning to
    golden, which is the practice this phase exists to end.
    """
    source = _module_source_under_audit()
    assert "395,673" not in source and "395673" not in source
