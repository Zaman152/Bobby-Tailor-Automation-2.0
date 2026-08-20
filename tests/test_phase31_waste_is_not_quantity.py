"""31-01 — a take-off quantity is what is on the drawing, not what to order.

Bob's Gas Piping published 921.48 LF against a golden of 886.77 — 3.91% error,
scored FAIL. The row's own formula read `count × 1.05`: the raw geometry is
877.60 LF and a 5% waste factor was multiplied into the PUBLISHED quantity. The
estimator's take-off measured 886.77 and carried no waste at all, so the gap was
one point of real measurement difference and five points of a factor the app
invented.

Sixteen tables did this. The error is small enough per-row to read as
measurement noise, which is why it survived — but it meant the app could never
match ANY estimator's take-off on those item types.

The factor is not deleted. It stays on the row (`waste_factor_applied`, already
whitelisted by reporter.py) and is named in the formula text, so whoever prices
the job still has it.

WHERE WASTE STAYS: a formula that converts to a PURCHASE unit — drywall sheets,
studs — bakes waste into the conversion, because you cannot order 0.4 of a
sheet. The rule is therefore: waste stops multiplying wherever the output unit
equals the measured unit, and stays wherever the formula changes units.

Free. No API, no fixtures.
"""
from __future__ import annotations

import pytest

from bobbytailor.pipeline.calculator import ESTIMATION_TABLES, _apply_formula


def test_gas_piping_publishes_the_measured_length():
    """THE case, with Bob's real numbers."""
    qty, unit, formula = _apply_formula("gas_pipe", 877.60, "lf", "877.60")
    assert qty == pytest.approx(877.60), "the measured length was altered"
    assert unit == "lf"
    assert "1.05" in formula and "not applied" in formula, (
        "the factor must still be NAMED on the row: %r" % formula)


def test_that_takes_gas_piping_from_a_fail_to_a_near_miss():
    """Measured against the golden this row is scored on."""
    golden = 886.77
    before = 877.60 * 1.05          # what the app used to publish
    after, _, _ = _apply_formula("gas_pipe", 877.60, "lf", "877.60")
    assert abs(before - golden) / golden > 0.03, "the old error was not ~3.9%"
    assert abs(after - golden) / golden < 0.02, (
        "removing the invented factor should leave ~1% of real measurement "
        "difference, not more")


@pytest.mark.parametrize("item_type,value,unit", [
    ("lintel", 179.0, "lf"),
    ("eifs", 3053.0, "sq_ft"),
    ("conduit_lf", 100.0, "lf"),
    ("duct_lf", 100.0, "lf"),
    ("insulation", 1000.0, "sq_ft"),
    ("flooring", 1000.0, "sq_ft"),
    ("storm_pipe", 50.0, "lf"),
    ("asphalt", 5000.0, "sq_ft"),
])
def test_every_same_unit_table_publishes_its_measurement(item_type, value, unit):
    qty, _, _ = _apply_formula(item_type, value, unit, str(value))
    assert qty == pytest.approx(value), (
        "%s still multiplies the quantity by its waste factor" % item_type)


@pytest.mark.parametrize("item_type,value", [("drywall", 1000.0), ("wall_framing", 100.0)])
def test_a_purchase_unit_conversion_keeps_its_waste(item_type, value):
    """Sheets and studs are ORDER units — you cannot buy 0.4 of a sheet.

    This is the fence. Without it the change would read as "waste is always
    wrong", and a drywall take-off would under-order on every job.
    """
    unit = "sq_ft" if item_type == "drywall" else "lf"
    qty, out_unit, _ = _apply_formula(item_type, value, unit, str(value))
    assert out_unit != unit, "this table is supposed to convert units"
    assert qty > 0


def test_a_table_with_no_waste_factor_is_untouched():
    """The rows already scoring 0.5-1.3% carry no factor, and must not move."""
    for item_type, value in (("tilt_up_wall", 106992.0), ("sealed_concrete", 397600.0),
                             ("exposed_structure", 397600.0)):
        # Either absent or an explicit 1.0 — `sealed_concrete` states 1.0, which
        # is a declaration that this material has no waste rather than an
        # oversight. What matters is that the row does not MOVE.
        assert ESTIMATION_TABLES.get(item_type, {}).get("waste_factor", 1.0) == 1.0, (
            "%s gained a real waste factor; the accurate rows would move" % item_type)
        qty, _, _ = _apply_formula(item_type, value, "sq_ft", str(value))
        assert qty == pytest.approx(value)


def test_the_factor_is_still_recorded_on_the_table():
    """Not deleted — pricing still needs it."""
    assert ESTIMATION_TABLES["gas_pipe"]["waste_factor"] == 1.05
    assert ESTIMATION_TABLES["eifs"]["waste_factor"] == 1.05

# ─── the branch 31-01 missed ────────────────────────────────────────────────

def test_the_component_producer_publishes_the_measurement():
    """31-01 fixed `_apply_formula` and reported Gas Piping as fixed. It was not.

    The paid run of 2026-08-21 returned Gas Piping at 921.48 LF against a golden
    of 886.77 — raw_value 877.6, `formula: count x 1.05` — byte-identical to the
    run BEFORE that fix, because this producer publishes the row and
    `_apply_formula` never sees it. A fix proved on a function is not a fix
    proved on a row.

    Asserted through the real producer with the shape Bob's gas piping actually
    arrives as, so the next person to change a waste rule finds out here.
    """
    from bobbytailor.pipeline.calculator import _calculate_from_component

    out = _calculate_from_component(
        {"name": "Gas Piping", "quantity": 877.6, "unit": "LF",
         "provenance": "geometry", "confidence": "high"},
        "page_0004.png", "roof_plan",
    )
    assert out is not None, "the producer refused a row it publishes in production"
    assert out["quantity"] == 877.6, (
        "the measured length was multiplied by a waste factor: %r" % out["quantity"])
    assert out["waste_factor_applied"] == 1.05, (
        "the factor must be RECORDED for pricing, not discarded")
    assert "not applied" in out["formula"], (
        "the row must say the factor was withheld: %r" % out["formula"])


def test_no_producer_multiplies_a_published_quantity_by_waste():
    """The rule, asserted against the SOURCE so a third branch cannot reappear.

    Two branches carried this defect and the second survived a fix that claimed
    both. A grep-level guard costs nothing and closes the class.
    """
    import re
    from pathlib import Path as _P

    src = _P("src/bobbytailor/pipeline/calculator.py").read_text()
    offenders = [ln.strip() for ln in src.splitlines()
                 if re.search(r"(?<![\w.])(numeric|value)\s*\*\s*wf\b", ln)
                 and "sheets" not in ln and "studs" not in ln]
    assert offenders == [], (
        "a producer multiplies a published quantity by the waste factor: %r\n"
        "Waste belongs to ordering, not to a take-off quantity." % offenders)
