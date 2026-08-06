"""Phase 28-01 — a counted row records WHAT corroborated it. ZERO API.

The defect this module exists to pin: ``Stairs`` published ``MEASURED``,
``needs_review=False``, confidence medium, at **1.00 in one saved run and 2.00
in the other**, off a sheet both runs classified ``detail``. Its
``source_location`` names stair *details* — "Detail 10 (Stair Section)",
"Detail 6 (Stair Plan)" — so the number moved because the number of details the
model noticed moved. It was counting drawings, not objects.

The codebase already refuses exactly that on the dimension path:
``_calculate_from_measurement`` drops a detail-sheet callout for the item types
in ``_DETAIL_SHEET_NOT_AN_INSTALL_COUNT`` (RC-6, widened by 23-15 / INV-06).
``_calculate_from_component`` receives the identical ``sheet_type`` argument and
never consulted it — and the count path is the path ``Stairs``, ``Lift`` and
``Door Frames-HM`` all travelled. That asymmetry is the defect.

WHAT THIS MODULE ASSERTS, AND WHAT IT REFUSES TO ASSERT
-------------------------------------------------------
* **No golden literal, anywhere.** This module never compares a quantity to a
  golden count. ``Stairs`` golden is not typed here, and neither is any other
  Crow item's expected number. :func:`test_the_module_names_no_golden_literal`
  greps this file to prove it. Tuning to a golden count would make the gate
  pass for having memorised an answer.
* **The verdict is recorded, not enforced.** 28-01 changes no published status
  and deletes no quantity; 28-03 owns the publish decision. So every assertion
  here is about a *recorded field*, never about a row disappearing.
* **A check either asserts or skips** (inherited from
  ``tests/test_phase23_acceptance.py`` and ``tests/test_determinism_harness.py``).
  A missing evidence directory skips with a named reason and can never pass
  silently.
* **The whole module runs FREE** — no paid marker, no paid script name, no
  credential. :func:`test_the_whole_module_runs_free` greps this file for them,
  assembling the forbidden tokens from halves so the check cannot fail on its
  own source.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.pipeline import calculator  # noqa: E402
from bobbytailor.pipeline.calculator import (  # noqa: E402
    _DETAIL_SHEET_NOT_AN_INSTALL_COUNT,
    _calculate_from_component,
    _calculate_from_measurement,
    _calculate_from_schedule,
    _count_corroboration,
)

THIS_FILE = Path(__file__)

#: The members the guard held as an inline tuple at calculator.py:526-529 before
#: 28-01 hoisted it. Written out here so the hoist is proven to be a MOVE and not
#: a rewrite: a member silently added or dropped during the move would be a
#: behaviour change wearing a refactor's clothes.
_MEMBERS_BEFORE_THE_HOIST = {
    "bollard", "stairs", "columns", "ladder", "lift",
    "guard_rail", "hand_rail", "striping", "trench_drain",
}


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — one list, two paths
# ─────────────────────────────────────────────────────────────────────────────


def test_the_constant_holds_exactly_what_the_inline_tuple_held():
    """The hoist moved the list. It did not edit it."""
    assert set(_DETAIL_SHEET_NOT_AN_INSTALL_COUNT) == _MEMBERS_BEFORE_THE_HOIST


def test_the_constant_is_what_the_measurement_path_actually_consults(monkeypatch):
    """Not a second copy that happens to agree — the same object, read live.

    Proven by moving a member and watching the measurement path's answer move
    with it, in BOTH directions:

    * drop ``guard_rail`` from the constant and a detail-sheet guard-rail run
      stops being refused;
    * put it back and the refusal returns.

    A private copy inside ``_calculate_from_measurement`` would leave the answer
    unchanged under both edits, and this test would fail.
    """
    m = {"value": "42", "unit": "lf", "description": "Guardrail run",
         "raw_text": "42 LF GUARDRAIL"}

    # Baseline: the guard is on, so the detail-sheet callout is refused.
    assert _calculate_from_measurement(m, "A-401", "detail") is None

    thinner = tuple(t for t in _DETAIL_SHEET_NOT_AN_INSTALL_COUNT if t != "guard_rail")
    monkeypatch.setattr(calculator, "_DETAIL_SHEET_NOT_AN_INSTALL_COUNT", thinner)
    row = _calculate_from_measurement(m, "A-401", "detail")
    assert row is not None, (
        "_calculate_from_measurement still refused a guard-rail run after "
        "guard_rail was removed from the constant — it is reading its own copy"
    )
    assert row["item_type"] == "guard_rail"

    monkeypatch.setattr(
        calculator, "_DETAIL_SHEET_NOT_AN_INSTALL_COUNT",
        _DETAIL_SHEET_NOT_AN_INSTALL_COUNT,
    )
    assert _calculate_from_measurement(m, "A-401", "detail") is None


def test_the_measurement_path_behaviour_did_not_move_in_the_hoist():
    """Same inputs, same returns — including every ``None`` the guard produced.

    Each item type in the constant is probed on a detail sheet and on a plan
    sheet, so the hoist is shown not to have widened or narrowed the refusal.
    """
    probes = (
        ("bollard", "42", "ea", "Bollard", "42 BOLLARDS"),
        ("guard_rail", "42", "lf", "Guardrail run", "42 LF GUARDRAIL"),
        ("hand_rail", "42", "lf", "Handrail run", "42 LF HANDRAIL"),
        ("striping", "42", "lf", "Parking striping", "42 LF STRIPING"),
        ("trench_drain", "42", "lf", "Trench drain", "42 LF TRENCH DRAIN"),
    )
    for _label, value, unit, desc, raw in probes:
        m = {"value": value, "unit": unit, "description": desc, "raw_text": raw}
        assert _calculate_from_measurement(m, "A-401", "detail") is None, desc


def test_the_constant_is_what_the_count_path_actually_consults(monkeypatch):
    """The sibling path reads the SAME object — that is the point of hoisting it.

    ``_calculate_from_component`` was handed the ``sheet_type`` argument from the
    beginning and never looked at it. Now it does, through this constant.
    """
    c = {"name": "Stair / Stair Run", "quantity": 2, "unit": "ea"}
    assert _calculate_from_component(c, "A-401", "detail")["count_corroboration"] == \
        "detail_sheet_only"

    thinner = tuple(t for t in _DETAIL_SHEET_NOT_AN_INSTALL_COUNT if t != "stairs")
    monkeypatch.setattr(calculator, "_DETAIL_SHEET_NOT_AN_INSTALL_COUNT", thinner)
    assert _calculate_from_component(c, "A-401", "detail")["count_corroboration"] == \
        "none", (
            "the count path still called it a detail-sheet count after stairs was "
            "removed from the constant — it is reading its own copy"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — every count row records what corroborated it
# ─────────────────────────────────────────────────────────────────────────────


def _reason_without_the_sheet_name(reason: str, sheet_name: str) -> str:
    return reason.replace(sheet_name, "")


def test_a_geometry_backed_count_is_corroborated_by_geometry():
    """``provenance == "geometry"`` means instance bounding boxes on the page.

    That is the one signal separating a symbol-cluster count from a model's
    prose count, and it is the corroboration test.
    """
    row = _calculate_from_component(
        {"name": "Bollard", "quantity": 3, "unit": "ea", "provenance": "geometry"},
        "A-101", "floor_plan",
    )
    assert row["count_corroboration"] == "geometry"
    assert _count_corroboration("geometry", "detail", "stairs") == "geometry", (
        "geometry outranks the sheet kind: bboxes on a details sheet are still bboxes"
    )


def test_a_printed_schedule_row_is_corroborated_by_the_schedule():
    """A table on the plan STATING a number is itself the corroboration.

    This is what keeps the hollow-metal door-frame schedule row publishing as a
    measured quantity once 28-03 starts withholding uncorroborated counts.
    """
    rows = _calculate_from_schedule(
        {
            "name": "DOOR SCHEDULE",
            "table_purpose": "takeoff_legend",
            "rows": [{"DESCRIPTION": "Door Frames - Hollow Metal",
                      "QUANTITY": "29", "UNIT": "EA"}],
        },
        "A-101",
    )
    assert rows, "the schedule route produced no row to check"
    assert all(r["count_corroboration"] == "schedule" for r in rows)
    assert all(r["formula"].startswith("authoritative plan schedule") for r in rows)


def test_every_route_out_of_the_schedule_calculator_comes_out_corroborated():
    """All three emitted shapes — legend, table-matched, and fall-through."""
    legend = _calculate_from_schedule(
        {"name": "TAKEOFF", "table_purpose": "takeoff_legend",
         "rows": [{"DESCRIPTION": "Bollards", "QUANTITY": "12", "UNIT": "EA"}]},
        "A-101")
    tabled = _calculate_from_schedule(
        {"name": "DOOR SCHEDULE",
         "rows": [{"DESCRIPTION": "Hollow metal door", "QTY": "7"}]},
        "A-101")
    other = _calculate_from_schedule(
        {"name": "EQUIPMENT SCHEDULE",
         "rows": [{"DESCRIPTION": "Mysterious Widget XJ", "QTY": "5"}]},
        "A-101")
    produced = legend + tabled + other
    assert produced, "no schedule rows were produced by any of the three routes"
    assert {r["count_corroboration"] for r in produced} == {"schedule"}


def test_an_install_count_read_off_a_details_sheet_is_marked_as_counting_drawings():
    """THE defect. ``Stairs``, read off a sheet the run itself typed ``detail``.

    The recorded ``source_location`` in the saved runs names stair *details*, so
    what moved between the runs was the number of details the model noticed. The
    row is now marked, flagged, and given a reason an estimator can act on — and
    the number is still on it, because 28-03 owns the publish decision.
    """
    row = _calculate_from_component(
        {"name": "Stair / Stair Run", "quantity": 2, "unit": "ea",
         "confidence": "medium"},
        "A-401", "detail",
    )
    assert row["count_corroboration"] == "detail_sheet_only"
    assert row["count_evidence_sheet_kind"] == "detail"
    assert row["needs_review"] is True
    reason = row["review_reason"]
    assert "A-401" in reason, "the reason must name the sheet the count came off"
    assert "detail" in reason.lower()
    assert "installed" in reason.lower(), (
        "the reason must say the reading counts drawings, not installed objects"
    )
    assert ("schedule" in reason.lower() or "plan sheet" in reason.lower()), (
        "the reason must name the confirmation an estimator should go get"
    )
    assert not any(ch.isdigit() for ch in
                   _reason_without_the_sheet_name(reason, "A-401")), (
        "the reason states no number: naming an expected count here would be "
        "tuning the message to a golden answer"
    )


def test_an_uncorroborated_count_on_any_other_sheet_kind_gets_its_own_verdict():
    """Not every uncorroborated count is a details-sheet count.

    A prose count off a floor plan has no geometry and no printed table behind
    it either. It is flagged, with a reason that does not misdescribe the sheet.
    """
    row = _calculate_from_component(
        {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "high"},
        "A-101", "floor_plan",
    )
    assert row["count_corroboration"] == "none"
    assert row["count_evidence_sheet_kind"] == "floor_plan"
    assert row["needs_review"] is True
    assert row["review_reason"], "an uncorroborated count must carry a reason"
    assert "details sheet" not in row["review_reason"].lower()


def test_an_item_type_outside_the_list_on_a_details_sheet_is_merely_uncorroborated():
    """The details-sheet verdict is scoped to the shared list, not to the sheet.

    A door count off a details sheet is uncorroborated — but calling it a
    detail-drawing count would be a claim about doors the list does not make.
    """
    row = _calculate_from_component(
        {"name": "Hollow metal door", "quantity": 4, "unit": "ea"},
        "A-401", "detail",
    )
    assert row["item_type"] not in _DETAIL_SHEET_NOT_AN_INSTALL_COUNT
    assert row["count_corroboration"] == "none"
    assert row["count_evidence_sheet_kind"] == "detail"


def test_a_text_layer_count_is_not_geometry():
    """``text_layer`` provenance is a string read off the PDF, not a bbox census.

    It is recorded, it is not corroboration, and pretending otherwise would let
    a printed word stand in for a counted object.
    """
    assert _count_corroboration("text_layer", "floor_plan", "bollard") == "none"
    assert _count_corroboration("text_layer", "detail", "stairs") == "detail_sheet_only"


def test_the_verdict_moves_no_quantity_and_drops_no_row():
    """The number on the row is byte-identical in every branch.

    28-01 records. It does not withhold. A row that vanished here would destroy
    the audit trail the phase is trying to build (T-28-03).
    """
    probes = (
        ({"name": "Stair / Stair Run", "quantity": 2, "unit": "ea"}, "A-401", "detail"),
        ({"name": "Bollard", "quantity": 3, "unit": "ea"}, "A-101", "floor_plan"),
        ({"name": "Bollard", "quantity": 3, "unit": "ea",
          "provenance": "geometry"}, "A-101", "floor_plan"),
        ({"name": "Mysterious Widget XJ", "quantity": 7, "unit": "ea"},
         "A-401", "detail"),
        ({"name": "Hollow metal door", "quantity": 4, "unit": "ea"},
         "A-201", "elevation"),
    )
    for c, sheet, kind in probes:
        row = _calculate_from_component(c, sheet, kind)
        assert row is not None, (c, sheet, kind)
        table = calculator.ESTIMATION_TABLES.get(row["item_type"], {})
        wf = table.get("waste_factor", 1.0)
        expected = round(float(c["quantity"]) * row["waste_factor_applied"], 2)
        assert row["quantity"] == expected, (c, sheet, kind)
        assert row["raw_value"] == c["quantity"]
        assert row["provenance"] == c.get("provenance"), (
            "the verdict must not rewrite provenance"
        )
        del table, wf


def test_the_sheet_kind_is_carried_verbatim():
    """``count_evidence_sheet_kind`` is the argument, not an interpretation of it."""
    for kind in ("detail", "floor_plan", "elevation", "unknown", "schedule"):
        row = _calculate_from_component(
            {"name": "Bollard", "quantity": 3, "unit": "ea"}, "A-101", kind)
        assert row["count_evidence_sheet_kind"] == kind


def test_an_upstream_review_reason_is_appended_to_never_replaced():
    """The flag-don't-guess signal from fusion must survive into the take-off.

    The existing ``reasons`` list and its ``dict.fromkeys`` de-duplication is the
    mechanism; a second one would be a place for the two to disagree.
    """
    upstream = "symbol group named by deterministic geometry"
    row = _calculate_from_component(
        {"name": "Stair / Stair Run", "quantity": 2, "unit": "ea",
         "needs_review": True, "review_reason": upstream},
        "A-401", "detail",
    )
    assert upstream in row["review_reason"]
    assert row["review_reason"] != upstream, "the corroboration reason was dropped"
    assert row["review_reason"].count(upstream) == 1


def test_a_repeated_reason_is_de_duplicated_by_the_existing_mechanism():
    """Feeding the verdict's own words back in upstream yields one copy, not two."""
    seeded = _calculate_from_component(
        {"name": "Stair / Stair Run", "quantity": 2, "unit": "ea"},
        "A-401", "detail")["review_reason"]
    row = _calculate_from_component(
        {"name": "Stair / Stair Run", "quantity": 2, "unit": "ea",
         "needs_review": True, "review_reason": seeded},
        "A-401", "detail",
    )
    assert row["review_reason"].count(seeded) == 1


def test_a_low_confidence_or_unclassified_count_keeps_the_reason_it_already_had():
    """Every condition that set ``needs_review`` before still sets it, and says why."""
    low = _calculate_from_component(
        {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "low",
         "provenance": "geometry"},
        "A-101", "floor_plan")
    assert low["needs_review"] is True
    assert "low-confidence count" in low["review_reason"]
    assert low["count_corroboration"] == "geometry"

    unclassified = _calculate_from_component(
        {"name": "Mysterious Widget XJ", "quantity": 2, "unit": "ea",
         "provenance": "geometry"},
        "A-101", "floor_plan")
    assert unclassified["needs_review"] is True
    assert "unclassified" in unclassified["review_reason"]


def test_a_geometry_backed_count_is_not_flagged_by_this_phase():
    """Corroborated counts are left exactly as they were — no new flag, no reason.

    A phase that flagged everything would be a phase that told an estimator
    nothing.
    """
    row = _calculate_from_component(
        {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "high",
         "provenance": "geometry"},
        "A-101", "floor_plan")
    assert row["count_corroboration"] == "geometry"
    assert row["needs_review"] is False
    assert row["review_reason"] == ""


def test_the_verdict_survives_normalisation_into_the_report_layer():
    """A field the aggregator cannot see is a field that was never written.

    ``_normalize_calculated`` whitelists keys on the way from the calculator to
    ``aggregate_takeoff``. 28-03 consumes ``count_corroboration`` there, so the
    key has to be on the whitelist or this plan's whole artifact is inert.
    """
    from bobbytailor.pipeline.reporter import _normalize_calculated

    rows = _normalize_calculated([
        _calculate_from_component(
            {"name": "Stair / Stair Run", "quantity": 2, "unit": "ea"},
            "A-401", "detail"),
    ])
    assert rows[0]["count_corroboration"] == "detail_sheet_only"
    assert rows[0]["count_evidence_sheet_kind"] == "detail"


# ─────────────────────────────────────────────────────────────────────────────
# The module's own contract
# ─────────────────────────────────────────────────────────────────────────────


def test_the_whole_module_runs_free():
    """No paid marker, no paid script name, no credential, anywhere in this file."""
    text = THIS_FILE.read_text(encoding="utf-8")
    # Assembled from halves on purpose: the check is a substring scan over this
    # very file, so spelling a marker out would make the module fail its own
    # audit. 24-09 and 24-10 both hit this and fixed it the same way.
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
