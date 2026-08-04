"""Unit CLASS — what kind of thing a unit measures.

A quantity and a unit are not independently choosable. 5 tilt-up panels is a
COUNT; publishing it as ``5.0 SF`` does not make it a small area, it makes it a
false one — and Crow shipped exactly that, at ``confidence: high`` and
``needs_review: false``, while the real 106,992 SF sat in the audit trail. The
mirror image shipped on the same run: a 31,104 SF wall-area measurement was
bound to a counted fixture and published as ``LED Wall Pack 34,214 EA``.

Neither number is convertible into the other's unit — there is no factor
between "how many" and "how much". A quantity whose measurement class does not
match its published unit is therefore not a rounding problem or a naming
problem: it is a number that means nothing, and the only honest publication is
a BLANK with a reason (C3b).

Pure data plus two lookups: no I/O, no imports from the pipeline, so both
:mod:`bobbytailor.vision.fusion` (which enforces basis-vs-unit) and
:mod:`bobbytailor.pipeline.aggregator` (which enforces that canonicalising a
name may not silently reclassify its unit) can share ONE definition. Two
definitions of the same rule is how the two halves of this defect drifted
apart in the first place.
"""
from __future__ import annotations

from typing import Optional

#: The measurement classes. Unknown is a first-class answer: an unrecognised
#: unit must never be *guessed* into a class, because a wrong guess here
#: withholds a good quantity.
COUNT = "count"
AREA = "area"
LINEAR = "linear"
VOLUME = "volume"
WEIGHT = "weight"

#: Unit token -> class. Keys are compared case-insensitively with punctuation
#: and whitespace stripped, so "SQ. FT.", "sq_ft" and "SF" all land together.
_UNIT_CLASS = {
    # count
    "ea": COUNT, "each": COUNT, "pc": COUNT, "pcs": COUNT, "piece": COUNT,
    "pr": COUNT, "pair": COUNT, "set": COUNT, "no": COUNT, "nos": COUNT,
    "unit": COUNT, "units": COUNT, "leaf": COUNT, "opening": COUNT,
    "openings": COUNT, "count": COUNT,
    # area
    "sf": AREA, "sqft": AREA, "sqfeet": AREA, "squarefeet": AREA,
    "squarefoot": AREA, "ft2": AREA, "sy": AREA, "sqyd": AREA,
    "squareyard": AREA, "squareyards": AREA, "sq": AREA, "square": AREA,
    "squares": AREA, "sm": AREA, "sqm": AREA, "m2": AREA,
    # linear
    "lf": LINEAR, "linft": LINEAR, "linearfeet": LINEAR, "linearfoot": LINEAR,
    "ft": LINEAR, "feet": LINEAR, "foot": LINEAR, "in": LINEAR,
    "inch": LINEAR, "inches": LINEAR, "ly": LINEAR, "m": LINEAR,
    "lm": LINEAR, "mm": LINEAR,
    # volume
    "cy": VOLUME, "cuyd": VOLUME, "cubicyard": VOLUME, "cubicyards": VOLUME,
    "cf": VOLUME, "cuft": VOLUME, "cubicfeet": VOLUME, "cubicfoot": VOLUME,
    "ft3": VOLUME, "gal": VOLUME, "gallon": VOLUME, "gallons": VOLUME,
    "m3": VOLUME,
    # weight
    "lb": WEIGHT, "lbs": WEIGHT, "pound": WEIGHT, "pounds": WEIGHT,
    "ton": WEIGHT, "tons": WEIGHT, "kg": WEIGHT,
}

#: Measure BASIS (what the engine measured) -> the class its number is in.
#: Absent basis, or a basis not listed here, yields None — unknown, never a
#: guess.
_BASIS_CLASS = {
    "count": COUNT,
    "linear": LINEAR,
    "length": LINEAR,
    "perimeter": LINEAR,
    "wall_area": AREA,
    "floor_area": AREA,
    "roof_area": AREA,
    "ceiling_area": AREA,
    "footprint_area": AREA,
    "facade_area": AREA,
    "area": AREA,
    "volume": VOLUME,
}


def _key(token) -> str:
    """Normalise a unit/basis token for lookup: lowercase, alphanumeric only."""
    out = []
    for ch in str(token or "").lower():
        if ch.isalnum():
            out.append(ch)
    return "".join(out)


def unit_class(unit) -> Optional[str]:
    """The measurement class of *unit*, or ``None`` when it is not recognised.

    ``None`` is deliberate and load-bearing: an unrecognised unit must never be
    guessed into a class, because every consumer here treats a class MISMATCH
    as grounds to withhold a number. Guessing wrong would blank a good
    quantity, which is a worse failure than the one this module prevents.
    """
    return _UNIT_CLASS.get(_key(unit))


def basis_class(basis) -> Optional[str]:
    """The measurement class a *basis* produces, or ``None`` when unknown."""
    return _BASIS_CLASS.get(_key(basis)) or _BASIS_CLASS.get(
        str(basis or "").strip().lower()
    )


def classes_conflict(a, b) -> bool:
    """True only when BOTH classes are known AND they differ.

    Anything unknown on either side is not a conflict. The rule only fires
    where the contradiction is certain.
    """
    return bool(a) and bool(b) and a != b


def unit_conflict(basis, unit) -> bool:
    """True when a quantity measured on *basis* cannot be expressed in *unit*."""
    return classes_conflict(basis_class(basis), unit_class(unit))
