"""Phase 29-01 — the canonical estimator name survives to the aggregator.

`door_schedule_to_legend` emits ITEM="Doors-STL" beside
DESCRIPTION="Doors - Steel (door schedule)", and its own docstring says the ITEM
field exists *because that is what the aggregator and the scorer match on*. It
shipped 2026-08-03. The saved Crow paid run of 2026-08-06 nevertheless published

    MEASURED      Doors - Steel (door schedule) = 70 EA
    NOT MEASURED  Doors-STL                     = (blank)

in the same report — the largest single bucket of lost coverage in that run (16
of 31 blanks are "NOT reconciled by name"). The name was produced correctly and
then discarded twice over: by a first-match-wins field tuple in
`_calculate_from_schedule`, and by the legend branch of `aggregate_takeoff`
publishing `_clean_legend_label(desc)`.

These tests pin the whole seam and, just as importantly, pin what must NOT move:
a schedule whose ITEM column holds marks rather than estimator names must never
publish a mark as an item name.

Free. No API, no fixtures, no paid marker.
"""
from __future__ import annotations

from bobbytailor.pipeline.aggregator import aggregate_takeoff
from bobbytailor.pipeline.calculator import _calculate_from_schedule
from bobbytailor.pipeline.reporter import _normalize_calculated

DOOR_ROWS = [
    {"ITEM": "Doors-STL", "DESCRIPTION": "Doors - Steel (door schedule)",
     "QTY": "70", "QUANTITY": "70", "UNIT": "EA"},
    {"ITEM": "Door Frames-HM",
     "DESCRIPTION": "Door Frames - Hollow Metal (door schedule)",
     "QTY": "29", "QUANTITY": "29", "UNIT": "EA"},
]


def _door_legend(rows=None):
    """The shape `door_schedule_to_legend` returns, including its marker."""
    return {
        "name": "Door Schedule (extracted from plans)",
        "table_purpose": "takeoff_legend",
        "legend_origin": "plan_parsed",
        "schedule_type": "door",
        "use_for_takeoff": True,
        "item_field_is_canonical": True,
        "columns": ["ITEM", "QTY", "UNIT"],
        "rows": list(DOOR_ROWS if rows is None else rows),
    }


def _published(sched, sheet="A-601"):
    """Drive the real seam: calculator -> whitelist -> aggregator."""
    calculated = _calculate_from_schedule(sched, sheet)
    return aggregate_takeoff(_normalize_calculated(calculated))


def _names(published):
    return {str(r.get("item") or r.get("name") or "") for r in published}


# ── the defect ───────────────────────────────────────────────────────────────


def test_the_canonical_name_reaches_the_calculated_row():
    rows = _calculate_from_schedule(_door_legend(), "A-601")
    assert {r["canonical_item"] for r in rows} == {"Doors-STL", "Door Frames-HM"}


def test_the_whitelist_does_not_swallow_it():
    """`_normalize_calculated` is a whitelist; a key left off it is invisible."""
    normalized = _normalize_calculated(_calculate_from_schedule(_door_legend(), "A-601"))
    assert {n["canonical_item"] for n in normalized} == {"Doors-STL", "Door Frames-HM"}


def test_the_published_row_carries_the_estimator_name_not_the_prose():
    """THE defect: Crow published the prose name and a blank under the real one."""
    names = _names(_published(_door_legend()))
    assert "Doors-STL" in names
    assert "Door Frames-HM" in names
    assert "Doors - Steel (door schedule)" not in names


def test_the_quantity_and_unit_are_untouched():
    """This plan moves a NAME. Nothing else may move with it."""
    by_name = {
        str(r.get("item") or r.get("name")): r for r in _published(_door_legend())
    }
    steel = by_name["Doors-STL"]
    assert float(steel.get("quantity")) == 70.0
    assert str(steel.get("unit")).upper() == "EA"


# ── what must NOT move ───────────────────────────────────────────────────────


def test_a_schedule_printing_one_label_is_unchanged():
    """No ITEM column => nothing to carry => the description names the row."""
    sched = _door_legend(rows=[
        {"DESCRIPTION": "Sealed Concrete", "QTY": "397600", "UNIT": "SF"},
    ])
    rows = _calculate_from_schedule(sched, "A-101")
    assert rows[0]["canonical_item"] == ""
    assert "Sealed Concrete" in _names(aggregate_takeoff(_normalize_calculated(rows)))


def test_a_mark_is_never_published_as_an_item_name():
    """The guard against the naive fix.

    Reordering the field tuple so ITEM wins would publish "A-1" — a drawing tag
    — as an item name on every generic schedule in the corpus. The canonical
    read is gated on the PRODUCER's declaration instead, so a schedule that did
    not declare its ITEM column to hold estimator names is never read that way.
    This assertion failed against the first draft of the fix.
    """
    sched = {
        "name": "Storefront Schedule",
        "table_purpose": "takeoff_legend",
        "rows": [{"ITEM": "A-1", "DESCRIPTION": "Storefront Assembly",
                  "QTY": "4", "UNIT": "EA"}],
    }
    rows = _calculate_from_schedule(sched, "A-201")
    assert rows[0]["canonical_item"] == ""
    assert "A-1" not in _names(aggregate_takeoff(_normalize_calculated(rows)))


def test_the_producer_marker_is_what_gates_it():
    """Same rows, marker removed => canonical name is not read.

    Pins the gate itself, so a later edit that starts inferring canonicality
    from the string's shape fails here rather than in a customer's report.
    """
    sched = _door_legend()
    sched.pop("item_field_is_canonical")
    rows = _calculate_from_schedule(sched, "A-601")
    assert {r["canonical_item"] for r in rows} == {""}


def test_the_real_producer_declares_the_marker():
    """The marker is not a test fiction — the shipped producer emits it."""
    import inspect

    from bobbytailor.deterministic import schedule_extraction

    src = inspect.getsource(schedule_extraction.door_schedule_to_legend)
    assert '"item_field_is_canonical": True' in src
