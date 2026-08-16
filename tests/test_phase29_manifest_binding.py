"""Phase 29-02 — a manifest may name what the evidence supports, and nothing else.

The first paid run of the post-29-01 engine (Crow, 2026-08-16, $0.8178) put a
91-entry generic catalog behind `--manifest` and measured three defects, each
pinned here against the run's own recorded strings:

1. ``Stairs = 3.0 EA, MEASURED, needs_review=False`` — manufactured from
   "Stair plan truck court clearance from center line of rail to wall", a
   DIMENSION note. The alias "stair" (one token) was contained in the 9-token
   text and containment scored a flat 0.9. A wrong-and-unflagged count is the
   one output this product exists to never produce.
2. ``Door Frames-GALV = 136 EA`` — a bare "DOOR" detection tied every
   door-family entry at 0.9 and the tie broke on NAME LENGTH. 136 personnel
   doors published as galvanized frames because that string is longest.
3. ``Doors - Steel (door schedule) = 0.0`` with no unit and NOT MEASURED —
   29-01 moved the legend bucket under its canonical name, but the
   duplicate-suppression pre-pass still keyed on the prose label, so
   suppression notes landed on an orphan defaultdict bucket that published
   with the defaultdict's numeric 0.0. A zero and a "not measured" on one row.

Free. No API, no fixtures, no paid marker.
"""
from __future__ import annotations

import json

from bobbytailor.devtools.object_manifest import Manifest, ManifestEntry, load_manifest
from bobbytailor.pipeline.aggregator import aggregate_takeoff

GENERIC_CATALOG = "tests/fixtures/generic_catalog_manifest.json"

#: The exact description the paid run manufactured Stairs = 3 from.
STAIR_DIMENSION_NOTE = (
    "Stair plan truck court clearance from center line of rail to wall"
)


def _catalog() -> Manifest:
    return load_manifest(GENERIC_CATALOG)


# ── 1: single-token alias vs prose ───────────────────────────────────────────


def test_a_dimension_note_containing_stair_does_not_become_stairs():
    assert _catalog().resolve(STAIR_DIMENSION_NOTE, "studs") is None


def test_a_short_label_still_binds_on_one_token():
    """The scale factor must not kill the intended case the tests already pin:
    a LABEL like "Bollard concrete dia." is three tokens, not prose."""
    hit = _catalog().resolve("Bollard concrete fill diameter", "EA")
    assert hit is not None and hit.name == "Bollards"


def test_a_multi_token_alias_still_binds_inside_a_longer_label():
    hit = _catalog().resolve("Tilt-up concrete panel (S.C.C.P.)", "SF")
    assert hit is not None and hit.name == "Tilt Up Wall"


# ── 2: ambiguous ties are refused, not arbitrated by name length ─────────────


def test_a_bare_door_detection_binds_nothing():
    """"DOOR" ties Doors-HM, Doors-STL, Door Frames-*, Overhead Doors...
    The text does not discriminate, so no bind — never the longest name."""
    assert _catalog().resolve("DOOR", "EA") is None


def test_a_discriminating_door_text_still_binds():
    hit = _catalog().resolve("Doors - Steel (door schedule)", "EA")
    assert hit is not None and hit.name == "Doors-STL"


def test_the_unit_may_settle_a_tie_because_a_unit_is_evidence():
    m = Manifest(entries=[
        ManifestEntry("Widget Count", "EA", aliases=["widget"]),
        ManifestEntry("Widget Area", "SF", aliases=["widget"]),
    ])
    hit = m.resolve("widget", "SF")
    assert hit is not None and hit.name == "Widget Area"
    # ...and with no unit evidence the same tie is refused.
    assert m.resolve("widget", "") is None


# ── 3: the orphan 0.0 bucket ─────────────────────────────────────────────────


def _legend_and_duplicate():
    """A canonical-named legend row plus a manifest-bindable duplicate of it."""
    return [
        {
            "description": "Doors - Steel (door schedule)",
            "canonical_item": "Doors-STL",
            "item_type": "schedule_item",
            "calculated_quantity": 70.0,
            "calculated_unit": "EA",
            "qty_source": "plan_schedule_legend",
            "count_corroboration": "schedule",
        },
        {
            "description": "steel door",
            "item_type": "doors",
            "calculated_quantity": 70.0,
            "calculated_unit": "EA",
            "qty_source": "measurement",
        },
    ]


def test_no_row_publishes_a_zero_for_a_suppressed_duplicate():
    """THE defect: the suppression note keyed on the prose label, which no
    longer owns a bucket, so a defaultdict bucket published qty 0.0."""
    out = aggregate_takeoff(_legend_and_duplicate(), manifest=_catalog())
    prose_rows = [r for r in out if r["item"] == "Doors - Steel (door schedule)"]
    assert prose_rows == [], (
        "the prose label must not own a row once the canonical name does: %s"
        % json.dumps(prose_rows, default=str)
    )


def test_the_suppression_note_lands_on_the_canonical_row():
    out = aggregate_takeoff(_legend_and_duplicate(), manifest=_catalog())
    steel = [r for r in out if r["item"] == "Doors-STL"]
    assert steel, [r["item"] for r in out]
    row = steel[0]
    assert float(row["quantity"]) == 70.0, "the duplicate must not SUM"
    reasons = " | ".join(row.get("review_reasons") or [])
    assert "suppressed" in reasons and "duplicate" in reasons


def test_no_aggregated_row_carries_zero_with_not_measured():
    """The invariant behind defect 3, asserted over the whole output: a zero
    quantity and a NOT MEASURED provenance may never share a row. A blank is
    None; 0.0 is a measurement of zero."""
    out = aggregate_takeoff(_legend_and_duplicate(), manifest=_catalog())
    for r in out:
        if r.get("provenance") == "NOT MEASURED":
            assert r.get("quantity") is None, r["item"]
