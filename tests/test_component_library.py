"""Tests for the deterministic component-library harvester.

The harvester reads the plan's own printed vocabulary — ABBREVIATION key,
schedules, keynotes / general notes — into a ``{name, aliases, basis, unit}``
library, and counts doors / frames by material from a type+count door schedule.
All tests are OFFLINE (synthetic text blocks + the real Crow PDF text layer);
never a paid API call, never a golden run.
"""
import os

import pytest

from bobbytailor.deterministic.component_library import (
    abbreviations_to_library,
    count_doors_by_material,
    extract_door_component_counts,
    harvest_component_library,
    harvest_from_notes,
    library_labels,
    merge_with_vocabulary,
    parse_abbreviations,
    resolve_library_name,
)

UPLOADS = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
CROW = os.path.join(UPLOADS, "Crow - Cass White Road-Plans.pdf")


# ── Abbreviation parsing ──────────────────────────────────────────────────────


def test_parse_abbreviations_same_line():
    text = "HM = HOLLOW METAL\nAL = ALUMINUM & GLASS\nSC = SOLID CORE"
    abbr = parse_abbreviations(text)
    assert abbr["HM"] == "Hollow Metal"
    assert abbr["AL"] == "Aluminum & Glass"
    assert abbr["SC"] == "Solid Core"


def test_parse_abbreviations_split_cell_lines():
    # PyMuPDF often splits "HM =" from its "HOLLOW METAL" body onto two lines.
    text = "HC = \nHOLLOW CORE\nHM = \nHOLLOW METAL"
    abbr = parse_abbreviations(text)
    assert abbr["HC"] == "Hollow Core"
    assert abbr["HM"] == "Hollow Metal"


def test_parse_abbreviations_drops_junk():
    # "(X) =" / "PF =" with no real body must not become an abbreviation.
    text = "(X) = \nPF = \nHM = HOLLOW METAL"
    abbr = parse_abbreviations(text)
    assert "HM" in abbr
    assert abbr.get("X") in (None, "")  # no alpha body on the next line


def test_abbreviations_compose_door_and_frame_names():
    abbr = parse_abbreviations("HM = HOLLOW METAL")
    lib = abbreviations_to_library(abbr)
    names = {e["name"] for e in lib}
    assert "Doors-HM" in names
    assert "Door Frames-HM" in names
    # The expansion is carried as an alias so detected text resolves to the name.
    door = next(e for e in lib if e["name"] == "Doors-HM")
    assert any("Hollow Metal" in a for a in door["aliases"])
    assert door["basis"] == "count"
    assert door["unit"] == "EA"


# ── Keynote / general-note object nouns ───────────────────────────────────────


def test_harvest_from_notes_finds_objects():
    text = (
        "KEYNOTES:\n"
        "1. PROVIDE ACCESS LADDER TO ROOF.\n"
        "2. RAMP GUARDRAIL PAINTED SAFETY YELLOW.\n"
        "3. 5' X 5' CONCRETE PAD FOR TRANSFORMER.\n"
        "4. STEEL PIPE BOLLARD AT EACH COLUMN."
    )
    lib = harvest_from_notes(text)
    names = {e["name"] for e in lib}
    assert "Ladder" in names
    assert "Guard Rail" in names
    assert "Concrete Pad" in names
    assert "Bollards" in names
    assert "Columns" in names
    # basis classification is carried
    guard = next(e for e in lib if e["name"] == "Guard Rail")
    assert guard["basis"] == "linear"
    pad = next(e for e in lib if e["name"] == "Concrete Pad")
    assert pad["basis"] == "floor_area"


def test_harvest_from_notes_dedups():
    text = "LADDER ... ACCESS LADDER ... ladder again"
    lib = harvest_from_notes(text)
    assert sum(1 for e in lib if e["name"] == "Ladder") == 1


# ── harvest_component_library orchestration ───────────────────────────────────


def test_harvest_component_library_synthetic_pages():
    pages = [
        "ABBREVIATIONS:\nHM = HOLLOW METAL\nAL = ALUMINUM & GLASS",
        "KEYNOTES:\n1. ACCESS LADDER.\n2. RAMP GUARDRAIL.\n3. PIPE BOLLARD.",
    ]
    lib = harvest_component_library(pages)
    names = {e["name"] for e in lib}
    # abbreviation-composed door/frame names
    assert "Doors-HM" in names
    assert "Door Frames-HM" in names
    assert "Doors-AL" in names
    # keynote object nouns
    assert "Ladder" in names
    assert "Guard Rail" in names
    assert "Bollards" in names
    # every entry carries the library shape
    for e in lib:
        assert set(("name", "aliases", "basis", "unit", "source")).issubset(e)


def test_harvest_component_library_empty_input_is_noop():
    assert harvest_component_library([]) == []
    assert harvest_component_library([""]) == []


# ── Door counting by material (type + count schedule) ─────────────────────────


def test_count_doors_by_material_uses_count_column():
    # A synthetic type schedule: 5 HM doors of one type, 3 of another.
    rows = [
        {"type": "P1", "count": 5, "door_material": "HM", "frame_material": "HM"},
        {"type": "P2", "count": 3, "door_material": "HM", "frame_material": "HM"},
        {"type": "W1", "count": 2, "door_material": "WD", "frame_material": ""},
    ]
    out = count_doors_by_material(rows)
    by_name = {d["name"]: d["quantity"] for d in out}
    assert by_name["Doors-HM"] == 8
    assert by_name["Doors-WD"] == 2
    assert by_name["Door Frames-HM"] == 8
    assert all(d["unit"] == "EA" for d in out)


def test_count_doors_five_hm_doors():
    # Plan spec: a synthetic door schedule with 5 HM doors → Doors-HM qty 5.
    rows = [{"type": "P1", "count": 5, "door_material": "HM", "frame_material": "HM"}]
    out = count_doors_by_material(rows)
    by_name = {d["name"]: d["quantity"] for d in out}
    assert by_name["Doors-HM"] == 5
    assert by_name["Door Frames-HM"] == 5


def test_count_doors_note_aware_hm_reclassification():
    # Door material printed IM, but the referenced NOTE classifies it as a
    # HOLLOW METAL DOOR → reclassify to HM (reads the plan's own note text).
    rows = [{"type": "P1", "count": 4, "door_material": "IM",
             "frame_material": "HM", "comment": "NOTE 1"}]
    notes = "NOTE 1 - (EXTERIOR DOORS) 16 GA. HOLLOW METAL DOORS IN WELDED FRAMES."
    out = count_doors_by_material(rows, notes_text=notes)
    by_name = {d["name"]: d["quantity"] for d in out}
    assert by_name["Doors-HM"] == 4
    assert by_name["Door Frames-HM"] == 4
    assert "Doors-IM" not in by_name


def test_count_doors_no_note_keeps_printed_material():
    rows = [{"type": "OD1", "count": 6, "door_material": "STL",
             "frame_material": "", "comment": "NOTE 3"}]
    notes = "NOTE 3 - 24 GAUGE SECTIONAL VERTICAL LIFT OVERHEAD DOORS."
    out = count_doors_by_material(rows, notes_text=notes)
    by_name = {d["name"]: d["quantity"] for d in out}
    assert by_name["Doors-STL"] == 6
    assert "Doors-HM" not in by_name


# ── Merge with the LLM vocabulary ─────────────────────────────────────────────


def test_merge_deterministic_name_wins_and_llm_basis_fills():
    deterministic = [
        {"name": "Doors-HM", "aliases": ["Hollow Metal Door"], "basis": None,
         "unit": "EA", "source": "abbreviation"},
    ]
    llm = [
        {"name": "Hollow Metal Door", "aliases": [], "basis": "count", "unit": "EA"},
    ]
    merged = merge_with_vocabulary(deterministic, llm)
    # deterministic entry is not duplicated; its name wins
    names = [e["name"] for e in merged]
    assert names.count("Doors-HM") == 1
    assert "Hollow Metal Door" not in names  # matched as an alias, not a new type
    det = next(e for e in merged if e["name"] == "Doors-HM")
    assert det["basis"] == "count"  # LLM filled the missing basis


def test_merge_adds_object_text_missed():
    deterministic = [
        {"name": "Doors-HM", "aliases": [], "basis": "count", "unit": "EA",
         "source": "abbreviation"},
    ]
    llm = [{"name": "Roof Deck", "aliases": [], "basis": "roof_area", "unit": "SF"}]
    merged = merge_with_vocabulary(deterministic, llm)
    names = {e["name"] for e in merged}
    assert "Doors-HM" in names
    assert "Roof Deck" in names


def test_merge_empty_library_returns_llm():
    llm = [{"name": "Ladder", "aliases": [], "basis": "count", "unit": "EA"}]
    merged = merge_with_vocabulary([], llm)
    assert {e["name"] for e in merged} == {"Ladder"}


# ── Consumers: labels + alias resolution ──────────────────────────────────────


def test_library_labels_flattens_names_and_aliases():
    lib = [
        {"name": "Doors-HM", "aliases": ["Hollow Metal Door"], "basis": "count"},
        {"name": "Ladder", "aliases": [], "basis": "count"},
    ]
    labels = library_labels(lib)
    assert "Doors-HM" in labels
    assert "Hollow Metal Door" in labels
    assert "Ladder" in labels


def test_resolve_library_name_via_alias():
    lib = [
        {"name": "Doors-HM", "aliases": ["Hollow Metal Door"], "unit": "EA"},
    ]
    hit = resolve_library_name("Exterior hollow metal door at egress", lib)
    assert hit is not None
    assert hit[0] == "Doors-HM"
    assert hit[1] == "EA"


def test_resolve_library_name_prefers_longest_match():
    lib = [
        {"name": "Doors", "aliases": ["door"], "unit": "EA"},
        {"name": "Doors-HM", "aliases": ["hollow metal door"], "unit": "EA"},
    ]
    hit = resolve_library_name("new hollow metal door", lib)
    assert hit[0] == "Doors-HM"


def test_resolve_library_name_miss_returns_none():
    lib = [{"name": "Ladder", "aliases": [], "unit": "EA"}]
    assert resolve_library_name("concrete slab on grade", lib) is None


# ── Real Crow PDF regression (skip if absent) ─────────────────────────────────


@pytest.mark.skipif(not os.path.exists(CROW), reason="Crow plans PDF not present")
def test_crow_door_counts_by_material():
    import fitz
    doc = fitz.open(CROW)
    try:
        notes = "\n".join(doc[i].get_text() for i in range(doc.page_count))
        counts = extract_door_component_counts(doc, notes_text=notes)
    finally:
        doc.close()
    by_name = {c["name"]: c["quantity"] for c in counts}
    # Golden naming: P-series personnel doors (24+2+1+1+1) in HM frames.
    assert by_name["Doors-HM"] == 29
    assert by_name["Door Frames-HM"] == 29
    # Overhead sectional (STL) and storefront (AL) doors are read too.
    assert by_name["Doors-STL"] == 70
    assert by_name["Doors-AL"] == 6


@pytest.mark.skipif(not os.path.exists(CROW), reason="Crow plans PDF not present")
def test_crow_abbreviation_key_decodes_materials():
    import fitz
    doc = fitz.open(CROW)
    try:
        text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()
    abbr = parse_abbreviations(text)
    assert abbr["HM"] == "Hollow Metal"
    assert abbr["IM"] == "Insulated Metal"
    assert abbr["STL"] == "Steel"
    assert abbr["SC"] == "Solid Core"
