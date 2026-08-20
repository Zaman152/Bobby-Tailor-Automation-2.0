"""31-02 — `region_ref` and `name_source` survive the reporter whitelist.

28-05 built `_withhold_region_sharing_hypotheses` to stop ONE measured region
publishing as several priced line items: on Crow the 397,600 SF footprint went
out three times — Exposed Structure, Sealed Concrete, and a Concrete Pad whose
name came from a vocabulary object's measure basis with nothing on the sheet
naming it. An estimator summing that SF column priced the building three times.

The rule shipped, its unit tests passed, and IT HAS NEVER FIRED IN PRODUCTION.
`_normalize_calculated` is a whitelist and neither field was on it, so
`region_ref` was permanently "" for every row, the grouping never had two
members, and the whole rule was unreachable. `_name_is_a_hypothesis`'s
vocabulary-basis disjunct was dormant for exactly the same reason. The unit
tests pass both fields in BY HAND, which is why the seam stayed invisible for
two phases.

Measured: the saved paid run of 2026-08-17 carries `region_ref` on 0 of its 45
calculated rows — not because no row had one, but because the key could not
cross the seam.

Free. No API, no fixtures.
"""
from __future__ import annotations

from bobbytailor.pipeline.aggregator import aggregate_takeoff
from bobbytailor.pipeline.reporter import _normalize_calculated

#: Crow's real shape: three SF readings backed by ONE measured region, of which
#: one is named by a vocabulary basis rather than by anything printed.
CROW_REGION_ROWS = [
    {"description": "Exposed Structure", "quantity": 397600.0, "unit": "SF",
     "item_type": "exposed_structure", "provenance": "geometry",
     "region_ref": "fill:FILL-1", "name_source": "text_anchor"},
    {"description": "Sealed Concrete", "quantity": 397600.0, "unit": "SF",
     "item_type": "sealed_concrete", "provenance": "geometry",
     "region_ref": "fill:FILL-1", "name_source": "text_anchor"},
    {"description": "Concrete Pad", "quantity": 397600.0, "unit": "SF",
     "item_type": "concrete_slab", "provenance": "geometry",
     "region_ref": "fill:FILL-1", "name_source": "vocabulary_basis"},
]


def _sf_rows(rows):
    out = _normalize_calculated(rows)
    return {str(r.get("item")): r for r in aggregate_takeoff(out)
            if str(r.get("unit") or "").upper() == "SF"}


def test_the_whitelist_carries_both_fields():
    """The seam itself, asserted directly."""
    row = _normalize_calculated([{
        "description": "CMU Wall", "quantity": 1.0, "unit": "SF",
        "region_ref": "wallclass:WALL-TC1", "name_source": "naming_library",
    }])[0]
    assert row["region_ref"] == "wallclass:WALL-TC1"
    assert row["name_source"] == "naming_library"


def test_a_hypothesis_sharing_a_region_is_withheld():
    """28-05's rule, firing through the real reporter seam for the first time."""
    rows = _sf_rows(CROW_REGION_ROWS)
    held = [r for r in rows.values() if r.get("quantity") is None]
    assert held, "no row was withheld — the region rule is still unreachable"
    assert all(r.get("needs_review") for r in held), "a withheld row must be flagged"
    assert any("region_shared" in str(r.get("source") or "") for r in held), (
        "the withholding did not come from the region-sharing rule: %r"
        % [r.get("source") for r in held])


def test_the_evidence_named_layers_still_publish():
    """The fence. D1's real layer sharing must survive — this rule removes a
    DUPLICATE, and removing a real layer instead would be a worse defect than
    the one it fixes."""
    rows = _sf_rows(CROW_REGION_ROWS)
    for name in ("Exposed Structure", "Sealed Concrete"):
        assert name in rows, "%s vanished" % name
        assert rows[name].get("quantity") == 397600.0, (
            "%s lost its measured area" % name)


def test_without_the_fields_the_rule_cannot_fire():
    """NON-VACUITY, and a record of what production did until now.

    Strip the two keys — exactly what the old whitelist did — and all three
    rows publish the same 397,600 SF. This is the bug, reproduced.
    """
    stripped = [{k: v for k, v in r.items()
                 if k not in ("region_ref", "name_source")}
                for r in CROW_REGION_ROWS]
    rows = _sf_rows(stripped)
    priced = [r for r in rows.values() if r.get("quantity") == 397600.0]
    assert len(priced) >= 3, (
        "expected the un-deduplicated triple-publish, got %d" % len(priced))


def test_a_row_with_no_region_is_untouched():
    """A row that never had a region must not be withheld for lacking one."""
    rows = _sf_rows([{
        "description": "Sealed Concrete", "quantity": 1000.0, "unit": "SF",
        "item_type": "sealed_concrete", "provenance": "geometry",
    }])
    assert rows["Sealed Concrete"]["quantity"] == 1000.0
