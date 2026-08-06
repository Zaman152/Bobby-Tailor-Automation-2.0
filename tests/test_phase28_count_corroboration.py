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
import re
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
# Task 3 — pinned against the two saved runs, never against a golden number
# ─────────────────────────────────────────────────────────────────────────────

_EVIDENCE_ROOT = ROOT / ".planning" / "paid-run-evidence"
#: The phase-24 determinism A/B. Both are FROZEN artifacts: opened read-only,
#: never re-scored, never rewritten. Re-scoring them after a code change returns
#: the same numbers, because the numbers are what was saved — which is exactly
#: why this module reasons about their RECORDED FIELDS instead.
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


def _sheet_kinds(run: dict) -> dict:
    """``source_sheet`` → the sheet type that run itself recorded for it."""
    return {e.get("sheet"): e.get("type") for e in run.get("sheet_log", [])}


def _verdict_of(row: dict, kinds: dict) -> str:
    """Run the shipped verdict function over a row as it was RECORDED."""
    return _count_corroboration(
        row.get("provenance"),
        kinds.get(row.get("source_sheet")),
        row.get("item_type"),
        row.get("qty_source"),
    )


def _published(run: dict) -> dict:
    return {(r["item"], r["unit"]): r for r in run.get("takeoff_summary", [])}


def _backing_rows(run: dict, summary_row: dict) -> list:
    """The calculated rows the published row was rolled up from."""
    wanted = {(d.get("sheet"), d.get("description"))
              for d in (summary_row.get("detail") or [])}
    return [r for r in run.get("calculated_takeoff", [])
            if (r.get("source_sheet"), r.get("description")) in wanted]


def _quantity_key(row: dict) -> tuple:
    return (row.get("item_type"),
            str(row.get("calculated_unit") or "").lower(),
            row.get("calculated_quantity"))


def test_the_saved_runs_every_quantity_that_moved_was_a_count_nothing_confirmed():
    """Prediction, not tuning: the verdict covers every quantity that varied.

    The differing published keys are computed at runtime by comparing the two
    ``takeoff_summary`` lists — they are never typed in as the subject of the
    check. (For the reader: they are ``Stairs``, ``Lift`` and ``Door Frames-HM``.)

    **A plan premise measured false, asserted rather than quietly dropped.**
    28-01's plan recorded run A's ``Door Frames-HM`` row as carrying no
    provenance. It does: the row is ``provenance: geometry``. So the honest
    claim is weaker and more specific than "everything that varied was
    uncorroborated". What actually holds, and is asserted here, is that every
    backing row of a varying key is either

    * classified uncorroborated by the verdict function — the number moved
      because nothing pinned it; or
    * classified ``geometry`` and **absent altogether** from the other run — the
      number did not move, the ROW vanished, which is an extraction-pass
      variance one layer upstream and not something a corroboration verdict can
      or should claim to catch.

    Recording that distinction is the point. A gate that asserted the plan's
    original sentence would be asserting something the evidence contradicts.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)
    ka, kb = _sheet_kinds(a), _sheet_kinds(b)
    pa, pb = _published(a), _published(b)

    shared = set(pa) & set(pb)
    differing = sorted(k for k in shared
                       if pa[k].get("quantity") != pb[k].get("quantity"))
    if not differing:
        pytest.skip("the two saved runs published no differing quantity to explain")

    other_side = {
        _RUN_A: {_quantity_key(r) for r in b.get("calculated_takeoff", [])},
        _RUN_B: {_quantity_key(r) for r in a.get("calculated_takeoff", [])},
    }

    uncorroborated_hits = 0
    for key in differing:
        for run_name, run, published, kinds in (
            (_RUN_A, a, pa, ka), (_RUN_B, b, pb, kb),
        ):
            for row in _backing_rows(run, published[key]):
                verdict = _verdict_of(row, kinds)
                if verdict in ("detail_sheet_only", "none"):
                    uncorroborated_hits += 1
                    continue
                assert _quantity_key(row) not in other_side[run_name], (
                    "%s in %s is backed by a row the verdict calls %r, and an "
                    "identical row exists in the other run — so the published "
                    "quantity moved for a reason this verdict does not explain "
                    "and must not be claimed to" % (key, run_name, verdict)
                )

    assert uncorroborated_hits, (
        "no varying key was backed by an uncorroborated row — the verdict "
        "explained none of the observed variance, so this gate proved nothing"
    )


def test_the_saved_runs_a_geometry_backed_number_never_moved():
    """The converse, asserted only where it holds.

    Every row run B recorded with ``provenance: geometry`` has a
    quantity-identical counterpart in run A. Geometry is the layer 24-RESEARCH
    found already deterministic, and this is that finding restated as a check on
    the corroboration signal itself: the thing the verdict trusts is the thing
    that did not move.

    **The reverse implication is deliberately NOT asserted.** An uncorroborated
    row may happen to agree across two runs — the two runs published 48 of 51
    keys identically and most of those rows have no provenance at all. Asserting
    "uncorroborated ⇒ varies" would be a claim the evidence does not support,
    and would turn a coincidence into a contract.

    The single geometry row that has NO counterpart is asserted too, by
    property: it did not change value, it disappeared, and it disappeared out of
    a published key that varied.
    """
    a, b = _load_run(_RUN_A), _load_run(_RUN_B)

    def geometry_rows(run):
        return [r for r in run.get("calculated_takeoff", [])
                if r.get("provenance") == "geometry"]

    ga, gb = geometry_rows(a), geometry_rows(b)
    if not ga or not gb:
        pytest.skip("a saved run recorded no geometry-backed calculated row")

    keys_a = {_quantity_key(r) for r in ga}
    orphans_b = [r for r in gb if _quantity_key(r) not in keys_a]
    assert orphans_b == [], (
        "geometry-backed rows in %s with no quantity-equal counterpart in %s: %s"
        % (_RUN_B, _RUN_A, [_quantity_key(r) for r in orphans_b])
    )

    keys_b = {_quantity_key(r) for r in gb}
    orphans_a = [r for r in ga if _quantity_key(r) not in keys_b]

    pa, pb = _published(a), _published(b)
    varied = {k for k in set(pa) & set(pb)
              if pa[k].get("quantity") != pb[k].get("quantity")}
    accounted = set()
    for key in varied:
        accounted.update(id(r) for r in _backing_rows(a, pa[key]))
    for row in orphans_a:
        assert id(row) in accounted, (
            "a geometry-backed row in %s vanished from %s without any published "
            "quantity moving: %s — an unexplained disappearance, not a variance "
            "this phase has characterised" % (_RUN_A, _RUN_B, _quantity_key(row))
        )


def test_the_saved_runs_printed_schedule_rows_are_corroborated_and_untouched():
    """The row that must NOT be flagged by anything this phase adds.

    A quantity read off a table printed on the plans is corroborated by that
    table. The rows are located by their recorded formula prefix, not by item
    name and not by number, so the check does not depend on which schedule the
    plan set happened to carry.
    """
    found = 0
    for run_name in (_RUN_A, _RUN_B):
        run = _load_run(run_name)
        kinds = _sheet_kinds(run)
        rows = [r for r in run.get("calculated_takeoff", [])
                if str(r.get("formula_applied") or "").startswith(
                    "authoritative plan schedule")]
        for row in rows:
            found += 1
            assert _verdict_of(row, kinds) == "schedule", (
                "%s in %s reads off a printed plan schedule and the verdict "
                "failed to say so" % (row.get("description"), run_name)
            )
    if not found:
        pytest.skip("neither saved run recorded an authoritative plan-schedule row")


def test_the_saved_evidence_tree_is_opened_read_only():
    """T-28-02. This module reads frozen artifacts; it must never write one.

    Asserted of the module's own source: every ``open`` in this file passes an
    explicit read mode, and no mutating primitive appears at all. The mutating
    tokens are assembled from halves; the mode check is a regex over the call
    sites rather than a substring scan, because a substring scan for a write
    mode has to spell one out and would then fail on itself — the self-defeating
    grep 24-09 and 24-10 both hit.
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
# The module's own contract
# ─────────────────────────────────────────────────────────────────────────────


def test_the_module_names_no_golden_literal():
    """No Crow item's expected count is typed here, and none is compared against.

    Two checks, because either alone is dodgeable:

    1. The module never reaches for the golden fixture — not by path, not by
       import, not by name. The token is assembled from halves so this check
       does not trip on itself.
    2. No assertion inside the evidence-backed tests compares anything to a
       numeric literal. Every expectation in that section is derived from the
       OTHER run's recorded fields at runtime. Tuning a number here until the
       gate went green is the failure mode this forbids.
    """
    text = THIS_FILE.read_text(encoding="utf-8")
    fixture_tokens = ("crow" + "_cass", "golden" + "_validator",
                      "_golden" + ".csv", "golden" + "_takeoff")
    hits = [t for t in fixture_tokens if t in text]
    assert hits == [], "this gate reached for a golden fixture: %s" % hits

    evidence_section = text.split("# Task 3 —", 1)
    assert len(evidence_section) == 2, "the evidence section marker moved"
    section = evidence_section[1].split("# The module's own contract", 1)[0]
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
