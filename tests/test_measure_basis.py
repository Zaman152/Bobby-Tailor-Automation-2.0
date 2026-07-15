"""Offline tests for the deterministic measure-basis classifier (Part A).

No API calls — ``classify_basis`` is pure text classification and
``merge_with_vocabulary`` runs it as the AUTHORITATIVE basis over whatever the
LLM vocabulary pass guessed. This is the structural fix for run-to-run FOUND/
MISSING flipping on area-bound items (Exposed Structure → roof_area binds the
footprint every run instead of drifting to count/unclassified).
"""
import pytest

from bobbytailor.deterministic.component_library import (
    classify_basis,
    merge_with_vocabulary,
)


# ── classify_basis: standard construction vocabulary → deterministic basis ────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Sealed Concrete", "floor_area"),
        ("Polished Concrete", "floor_area"),
        ("Slab On Grade", "floor_area"),
        ("Flooring", "floor_area"),
        ("Exposed Structure", "roof_area"),
        ("Exposed Deck", "roof_area"),
        ("Open Web Joist", "roof_area"),
        ("CMU Wall", "wall_area"),
        ("Exterior Tilt Up Wall", "wall_area"),
        ("S.C.C.P.", "wall_area"),
        ("Masonry Wall", "wall_area"),
        ("Columns", "count"),
        ("Bollards", "count"),
        ("Ladder", "count"),
        ("Door Frames-HM", "count"),
        ("Dock Leveler", "count"),
        ("Guard Rail", "linear"),
        ("Curb & Gutter", "linear"),
        ("Handrail", "linear"),
        ("Lintels", "linear"),
    ],
)
def test_classify_basis_known_vocabulary(name, expected):
    assert classify_basis(name) == expected


@pytest.mark.parametrize(
    "gibberish",
    ["Zorplex Widget", "Fizzbuzz", "qwerty asdf", "", "   "],
)
def test_classify_basis_unknown_returns_none(gibberish):
    assert classify_basis(gibberish) is None


def test_classify_basis_matches_on_aliases():
    # The name is opaque but an alias carries the standard vocabulary.
    assert classify_basis("Type-A Panel", aliases=["Tilt Up Wall"]) == "wall_area"


# ── merge authority: deterministic basis overrides the LLM basis ──────────────


def test_merge_deterministic_basis_overrides_llm():
    """LLM mis-classifies Exposed Structure as count → merged basis is roof_area."""
    llm_objects = [{"name": "Exposed Structure", "basis": "count", "aliases": []}]
    merged = merge_with_vocabulary([], llm_objects)
    entry = next(e for e in merged if e["name"] == "Exposed Structure")
    assert entry["basis"] == "roof_area"


def test_merge_llm_basis_survives_when_classifier_unknown():
    """classify_basis(None) → the LLM basis fills (authority only where it knows)."""
    llm_objects = [{"name": "Mezzanine Guard Panel", "basis": "count", "aliases": []}]
    merged = merge_with_vocabulary([], llm_objects)
    entry = next(e for e in merged if e["name"] == "Mezzanine Guard Panel")
    assert classify_basis("Mezzanine Guard Panel") is None
    assert entry["basis"] == "count"


def test_merge_corrects_deterministic_entry_basis():
    """A deterministic library entry with a wrong basis is also corrected."""
    deterministic = [{"name": "Sealed Concrete", "aliases": [], "basis": "count"}]
    merged = merge_with_vocabulary(deterministic, [])
    entry = next(e for e in merged if e["name"] == "Sealed Concrete")
    assert entry["basis"] == "floor_area"
