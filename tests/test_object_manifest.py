"""Tests for the optional Object Manifest (runtime flexible naming + completeness)."""
import json

import pytest

from object_manifest import (
    Manifest,
    ManifestEntry,
    discover_manifest_path,
    load_manifest,
    load_manifest_safe,
    measure_from_unit,
    resolve_project_manifest,
    template_csv,
)
from aggregator import aggregate_takeoff


# ── Loading ──────────────────────────────────────────────────────────────────

def test_load_json_list(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps([
        {"name": "CMU Wall", "unit": "SF", "aliases": ["cmu", "concrete masonry"]},
        {"name": "Bollards", "unit": "EA"},
    ]))
    m = load_manifest(str(p))
    assert len(m) == 2
    assert m.entries[0].name == "CMU Wall"
    assert m.entries[0].unit == "SF"
    assert m.entries[0].measure == "area"
    assert m.entries[1].measure == "count"


def test_numeric_suffix_items_are_distinct(tmp_path):
    """Items differing only by a numeric suffix (WC-1..WC-10) must NOT collapse.

    Regression: digit-stripping tokenization merged these into one entry, silently
    losing components — the opposite of the manifest's completeness guarantee.
    """
    p = tmp_path / "m.json"
    p.write_text(json.dumps([
        {"name": f"WC-{i}", "unit": "SF"} for i in (1, 2, 4, 6, 10)
    ]))
    m = load_manifest(str(p))
    assert len(m) == 5
    assert {e.name for e in m.entries} == {"WC-1", "WC-2", "WC-4", "WC-6", "WC-10"}
    # And they resolve to themselves, not to a sibling.
    assert m.resolve("WC-2", "SF").name == "WC-2"
    assert m.resolve("WC-10", "SF").name == "WC-10"
    # A produced "WC-2" should not mark WC-10 as found (completeness intact).
    missing = {e.name for e in m.missing(["WC-2"])}
    assert "WC-10" in missing and "WC-2" not in missing


def test_load_json_objects_wrapper(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"objects": [{"name": "Lift", "unit": "EA"}]}))
    m = load_manifest(str(p))
    assert len(m) == 1 and m.entries[0].name == "Lift"


def test_load_csv(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        "name,unit,aliases,measure,height_ft\n"
        "CMU Wall,SF,cmu;concrete masonry,area,35\n"
        "Bollards,EA,bollard;pipe bollard,count,\n"
    )
    m = load_manifest(str(p))
    assert len(m) == 2
    cmu = m.entries[0]
    assert cmu.name == "CMU Wall"
    assert "cmu" in cmu.aliases
    assert cmu.assumptions.get("height_ft") == 35.0


def test_load_safe_missing_returns_none():
    assert load_manifest_safe(None) is None
    assert load_manifest_safe("/no/such/file.json") is None


def test_measure_from_unit():
    assert measure_from_unit("SF") == "area"
    assert measure_from_unit("LF") == "length"
    assert measure_from_unit("EA") == "count"
    assert measure_from_unit("") == "count"


# ── Resolution ────────────────────────────────────────────────────────────────

def _m():
    return Manifest([
        ManifestEntry("CMU Wall", "SF", aliases=["cmu", "concrete masonry"]),
        ManifestEntry("Bollards", "EA", aliases=["bollard", "pipe bollard"]),
        ManifestEntry("Columns-H-35'", "EA", aliases=["column", "structural column"]),
        ManifestEntry("Fiber Cement Panel", "SF", aliases=["fiber cement", "cement panel"]),
    ])


def test_resolve_alias_match():
    m = _m()
    e = m.resolve("8\" CMU block wall", "SF")
    assert e is not None and e.name == "CMU Wall"


def test_resolve_singular_plural():
    m = _m()
    assert m.resolve("Bollard concrete dia.", "EA").name == "Bollards"


def test_resolve_column_with_height():
    m = _m()
    assert m.resolve("Steel column", "EA").name == "Columns-H-35'"


def test_resolve_does_not_misfire_on_unrelated():
    m = _m()
    # "Electrical Panels" must NOT bind to "Fiber Cement Panel" just because of "panel".
    assert m.resolve("Electrical Panels", "EA") is None


def test_resolve_below_cutoff_returns_none():
    m = _m()
    assert m.resolve("random unrelated widget", "EA") is None


# ── Aggregation with manifest ──────────────────────────────────────────────────

def test_aggregate_uses_manifest_name_and_unit_verbatim():
    m = _m()
    items = [
        {"description": "Bollard concrete dia.", "item_type": "concrete_slab",
         "calculated_quantity": 0.15, "calculated_unit": "CY", "qty_source": "measurement"},
    ]
    summary = aggregate_takeoff(items, manifest=m)
    bollards = [r for r in summary if r["item"] == "Bollards"]
    assert bollards, summary
    # Unit comes from manifest (EA), not the vision-derived CY.
    assert bollards[0]["unit"] == "EA"
    assert bollards[0]["source"] == "manifest"


def test_aggregate_injects_missing_manifest_items_as_needs_review():
    m = _m()
    items = [
        {"description": "8in CMU wall", "item_type": "cmu_wall",
         "calculated_quantity": 1000, "calculated_unit": "SF", "qty_source": "measurement"},
    ]
    summary = aggregate_takeoff(items, manifest=m)
    names = {r["item"]: r for r in summary}
    # CMU Wall found; the other manifest objects must still appear, flagged.
    assert "CMU Wall" in names
    for missing in ("Bollards", "Columns-H-35'", "Fiber Cement Panel"):
        assert missing in names, f"{missing} should be injected for completeness"
        assert names[missing]["needs_review"] is True
        assert names[missing]["quantity_fmt"] == "—"
        assert "not found" in " ".join(names[missing]["review_reasons"]).lower()


def test_aggregate_without_manifest_is_unchanged_shape():
    items = [
        {"description": "bollard", "item_type": "bollard",
         "calculated_quantity": 3, "calculated_unit": "EA", "qty_source": "component"},
    ]
    summary = aggregate_takeoff(items)
    assert any(r["item"] == "Bollards" for r in summary)
    # New fields exist but default to safe values.
    row = next(r for r in summary if r["item"] == "Bollards")
    assert row["needs_review"] is False
    assert "confidence" in row


def test_confidence_rolls_up_to_worst():
    items = [
        {"description": "bollard", "item_type": "bollard", "calculated_quantity": 2,
         "calculated_unit": "EA", "qty_source": "component", "confidence": "high"},
        {"description": "bollard", "item_type": "bollard", "calculated_quantity": 1,
         "calculated_unit": "EA", "qty_source": "component", "confidence": "low"},
    ]
    summary = aggregate_takeoff(items)
    row = next(r for r in summary if r["item"] == "Bollards")
    assert row["confidence"] == "low"


# ── Auto-discovery (StackCT runs have no manifest upload control) ──────────────

def _write_manifest(d, stem, names):
    p = d / f"{stem}.json"
    p.write_text(json.dumps([{"name": n, "unit": "EA"} for n in names]))
    return p


def test_discover_fuzzy_matches_project_name(tmp_path):
    _write_manifest(tmp_path, "crow_cass", ["Bollards"])
    # "Crow - Cass White Road" slug contains "crowcass" → match.
    found = discover_manifest_path("Crow - Cass White Road", search_dirs=[str(tmp_path)])
    assert found and found.endswith("crow_cass.json")


def test_discover_prefers_exact_then_specific(tmp_path):
    _write_manifest(tmp_path, "crow", ["A"])
    _write_manifest(tmp_path, "crow_cass_white_road", ["B"])
    # Exact slug match wins over a shorter partial match.
    found = discover_manifest_path("Crow Cass White Road", search_dirs=[str(tmp_path)])
    assert found.endswith("crow_cass_white_road.json")


def test_discover_default_fallback_only_when_no_match(tmp_path):
    _write_manifest(tmp_path, "default", ["X"])
    found = discover_manifest_path("Totally Unrelated", search_dirs=[str(tmp_path)])
    assert found.endswith("default.json")


def test_discover_returns_none_without_match(tmp_path):
    _write_manifest(tmp_path, "moxy", ["X"])
    assert discover_manifest_path("Crow Cass", search_dirs=[str(tmp_path)]) is None


def test_resolve_explicit_path_wins_over_discovery(tmp_path):
    explicit = _write_manifest(tmp_path, "explicit_one", ["Bollards"])
    _write_manifest(tmp_path, "crow_cass", ["Columns"])
    m = resolve_project_manifest(
        "Crow Cass", explicit_path=str(explicit), search_dirs=[str(tmp_path)]
    )
    assert [e.name for e in m.entries] == ["Bollards"]


def test_resolve_falls_back_to_discovery(tmp_path):
    _write_manifest(tmp_path, "crow_cass", ["Columns", "Bollards"])
    m = resolve_project_manifest("Crow Cass White Road", search_dirs=[str(tmp_path)])
    assert m and {e.name for e in m.entries} == {"Columns", "Bollards"}


def test_resolve_returns_none_when_nothing_found(tmp_path):
    assert resolve_project_manifest("Unknown", search_dirs=[str(tmp_path)]) is None


def test_template_csv_has_header():
    t = template_csv()
    assert t.splitlines()[0].startswith("name,unit")
