"""Row provenance — where each published number came from.

**A blank must never render as a zero.** Every take-off row a client bids from
must say where its number came from:

  MEASURED       — geometry measured it off the drawing (the app earned it)
  HUMAN INPUT    — an estimator supplied it (room mix, scale, wall height)
  NEEDS REVIEW   — measured but flagged; a human must confirm before use
  NOT MEASURED   — the app has no measurement path for this item yet

This vocabulary originated in ``scripts/export_takeoff_excel.py`` and lives in
``src`` now for two reasons (INV-08 §5):

1. **It was inferred from the value, not recorded.** The old
   ``_provenance`` said ``float(qty or 0) <= 0 -> NOT MEASURED``, which makes a
   genuinely measured zero (a building with no CMU) indistinguishable from a
   measurement that was never attempted. ``provenance_of_row`` reads the
   recorded status first, and treats ``quantity is None`` — not ``quantity ==
   0`` — as "never measured".
2. **Only Excel users saw it.** ``takeoff.json``, ``takeoff_summary.csv``, the
   web results view and the API all shipped the bare number.

The exporter keeps ownership of layout, colours and the About sheet; that is
genuinely presentation.
"""
from __future__ import annotations

from typing import Any, Dict

from bobbytailor.pipeline.coverage import (
    ITEM_HUMAN_INPUT,
    ITEM_MEASURED,
    ITEM_NEEDS_REVIEW,
    ITEM_NOT_MEASURED,
)

# Row ``source`` values that mean a human supplied the number IN A HUMAN INPUT
# FILE, rather than the app measuring it off the drawing.
#
# ``plan_schedule_legend`` is deliberately NOT here and never was: a legend the
# app parsed off the plans is a machine reading. The aggregator's ``_row_status``
# is the authority for a legend row and only calls it HUMAN INPUT when the
# legend's own ``legend_origin`` is ``human_input`` — an estimator's companion
# take-off, ingested from a human input file (C4).
#
# ``learned`` is a NAMING marker (a stored human correction to what an object is
# CALLED); it is retained here only for pre-23 rows that carry no recorded
# status, because for those the naming correction is the only human signal on
# the row. Any row this run produced carries an explicit ``status`` and never
# reaches this branch.
_HUMAN_SOURCES = frozenset(
    {"manifest", "human", "learned", "manifest_missing", "human_input", "estimator"}
)


def provenance_of_row(row: Dict[str, Any]) -> str:
    """Classify one take-off row into the four-value client vocabulary.

    Order matters, and it is deliberately record-first:

    1. An explicit recorded ``status`` (an ``ItemCoverage``-backed row) wins —
       the ledger knows what happened; nothing should second-guess it.
    2. ``quantity is None`` means the measurement was never made. This is the
       S12 fix: the aggregator used to ship a defaultdict ``0.0`` for a
       never-measured item, and every numeric consumer read the blank as a zero.
    3. Otherwise a flagged row is NEEDS REVIEW, a human-sourced row is HUMAN
       INPUT, and everything left is MEASURED.

    A quantity of ``0.0`` is NEVER treated as "not measured": a measured zero is
    a real, publishable finding and must stay distinguishable from an absence.

    Args:
        row: A take-off summary row (or any mapping with the same keys).

    Returns:
        One of MEASURED / HUMAN INPUT / NEEDS REVIEW / NOT MEASURED.
    """
    status = row.get("status")
    if status:
        return str(status)

    quantity = row.get("quantity")
    # `is None` and the empty string only — never a comparison against zero.
    if quantity is None or quantity == "":
        return ITEM_NOT_MEASURED

    if row.get("needs_review"):
        return ITEM_NEEDS_REVIEW

    if str(row.get("source") or "").strip().lower() in _HUMAN_SOURCES:
        return ITEM_HUMAN_INPUT

    return ITEM_MEASURED
