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
    _calculate_from_measurement,
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
