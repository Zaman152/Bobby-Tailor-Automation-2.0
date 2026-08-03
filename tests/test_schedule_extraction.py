"""Regression tests for deterministic door-schedule extraction.

Door panel/frame materials are printed exactly in the schedule table; these tests
lock in (a) tag tokenisation, (b) phrase-based material reading, (c) column roles
with a content fallback, (d) the two-part legend guard, and (e) precise per-sheet
recovery on the real plan PDFs without false positives from floor-plan door
callouts or from a drawing grid PyMuPDF happens to read as a table.

Every real-PDF number below is the drawing's OWN printed structure — one printed
row is one opening, one printed material cell is that opening's material. No
threshold is tuned toward a golden count (23-CONTEXT: "Never tune to golden").
"""
import os

import pytest

from bobbytailor.deterministic.schedule_extraction import (
    _column_roles,
    _count_column,
    _door_title_bands,
    _is_door_title_line,
    _material_code,
    _material_columns,
    _normalise_material_text,
    _tag_column,
    _tag_tokens,
    accepted_door_tables,
    canonical_material_code,
    door_schedule_coverage,
    door_schedule_coverage_warnings,
    door_schedule_to_legend,
    extract_door_schedule,
    reclassified_panel_counts,
)

UPLOADS = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
MOXY = os.path.join(UPLOADS, "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf")
CROW = os.path.join(UPLOADS, "Crow - Cass White Road-Plans.pdf")
BOBS = os.path.join(UPLOADS, "Bob's Discount Furniture - Kennesaw, GA-plans.pdf")
CHELSEA = os.path.join(
    UPLOADS, "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
)


# ── Tag tokenisation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell,expected", [
    ("003", ["003"]),
    ("006A", ["006A"]),
    ("113A 113B", ["113A", "113B"]),   # merged cell -> two doors
    ("T2 T6", ["T2", "T6"]),
    ("T1", ["T1"]),
    ("DSF", ["DSF"]),                   # a type+count schedule's TYPE code
    ("OD1", ["OD1"]),
    ("SF", ["SF"]),
    ("WORK AREA", []),                  # room name, not a tag (4 letters)
    ("DATA", []),
    ("SCW", []),                        # material, not a tag
    ("HM", []),
    ("A", []),                          # an elevation grid letter is not a tag
    ("", []),
])
def test_tag_tokens(cell, expected):
    assert _tag_tokens(cell) == expected


def test_tag_column_is_leftmost_not_most_hits():
    """A type+count schedule's Count column is itself tag-shaped.

    Nine small integers beat seven type codes on a "most hits" rule, which hands
    the tag role to the COUNT column and turns Crow's 105 doors into 5. The rule
    is LEFT-MOST of columns 0-3 with >=3 tag-shaped cells (INV-07 §4.1).
    """
    rows = [
        ["DSF", "2", "", "6' - 0\"", "AL"],
        ["OD1", "68", "-", "9' - 0\"", "STL"],
        ["P1", "24", "-", "3' - 0\"", "IM"],
        ["P2", "2", "-", "3' - 0\"", "IM"],
        ["SF", "4", "-", "3' - 0\"", "AL"],
    ]
    assert _tag_column(rows) == 0


# ── Material normalisation + phrase resolution (INV-07 §4.1) ──────────────────

@pytest.mark.parametrize("raw,normalised,code", [
    ("--- H. M. 6A", "HM 6A", "HM"),                       # split frame pair
    ("HM-STL.", "HM STL", "HM"),                            # hyphenated steel form
    ("S.C. WOOD & GLASS", "SC WOOD GLASS", "SCW"),          # leaf beats the lite
    ("ALUM. & 1\" INSULATED GLASS", "ALUM 1 INSULATED GLASS", "ALUM"),
    ("*", "", ""),                                          # "see manufacturer"
])
def test_material_normalisation_and_code(raw, normalised, code):
    assert _normalise_material_text(raw) == normalised
    assert _material_code(raw) == code


def test_split_frame_cell_pair_resolves_to_hollow_metal():
    """PyMuPDF splits Bob's frame material across two cells; joined they read."""
    assert _material_code("--- H." + " " + "M. 6A") == "HM"
    assert _material_code("--- AL" + " " + "UM. **") == "ALUM"


@pytest.mark.parametrize("text", ["FLOORING LEGEND", "PAINT COLORS"])
def test_material_code_rejects_unrelated_legend_titles(text):
    """The widened reader must not turn an unrelated legend into a material."""
    assert _material_code(text) == ""


def test_material_code_is_leftmost_then_longest():
    # Leftmost: the leaf material is printed before the glazing.
    assert _material_code("SOLID CORE WOOD W/ GLASS LITE") == "SCW"
    # Longest at the same offset: SCW is preferred over a bare token inside it.
    assert _material_code("SC WOOD") == "SCW"


# ── Column roles + the count column ───────────────────────────────────────────

def test_material_columns_are_order_independent():
    # tag | room | panel-type | PANEL MAT | fire | FRAME MAT
    rows = [
        ["TAG", "ROOM", "TYPE", "PANEL", "FIRE", "FRAME"],
        ["001", "OFFICE", "A", "SCW", "-", "HM"],
        ["002", "LOBBY", "B", "GLASS", "-", "ALUM"],
        ["003", "MECH", "C", "HM", "45", "GALV"],
    ]
    tag_col = _tag_column(rows)
    assert tag_col == 0
    panel_col, frame_col = _material_columns(rows, tag_col)
    # leftmost readable material column is the panel; rightmost is the frame
    assert panel_col == 3
    assert frame_col == 5


def test_column_roles_read_a_three_row_stacked_header():
    """Schedules stack 2-3 header rows — the role must survive the split."""
    rows = [
        ["DOOR SCHEDULE", "", "", "", ""],
        ["DOOR", "ROOM", "LEAF", "FRAME", "FRAME"],
        ["NO.", "NAME", "QTY.", "TYPE", "MATERIAL"],
        ["001", "OFFICE", "1", "1", "HM"],
        ["002", "LOBBY", "1", "1", "HM"],
        ["003", "MECH", "1", "1", "HM"],
    ]
    roles = _column_roles(rows)
    assert roles.get(4) == "frame_mat"
    assert roles.get(2) == "count"
    assert roles.get(0) == "tag"


def test_count_column_found_on_a_crow_shaped_table():
    rows = [
        ["DSF", "2", "", "6' - 0\"", "AL"],
        ["OD1", "68", "-", "9' - 0\"", "STL"],
        ["P1", "24", "-", "3' - 0\"", "IM"],
        ["P2", "2", "-", "3' - 0\"", "IM"],
        ["SF", "4", "-", "3' - 0\"", "AL"],
    ]
    assert _count_column(rows, 0, {}) == 1


def test_count_column_absent_on_a_bobs_shaped_table_means_one_door_per_row():
    """No count column is a VALID answer — it is what makes Bob's readable."""
    rows = [
        ["", "NO.", "TYPICAL LOCATION", "", "", "MATERIAL"],
        ["", "001A", "VESTIBULE", "", "", "ALUM. & GLASS"],
        ["", "002", "DINING", "", "", "HM-STL."],
        ["", "010", "DATA", "", "", "S.C. WOOD"],
        ["", "013", "UNISEX", "", "", "S.C. WOOD"],
    ]
    assert _count_column(rows, 1, {}) is None


# ── The legend guard, part 1: standalone title bands ──────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("DOOR SCHEDULE", True),
    ("DOOR SCHEDULE - GUESTROOMS", True),
    ("ARCHITECTURAL DOOR SCHEDULE", True),
    ("DOOR & FRAME TYPES", True),
    # An in-note reference is prose, not a title — this is the phantom's doorway.
    ("REFER TO ARCHITECTURAL DOOR SCHEDULE WC 01 FOR ADDITIONAL INFORMATION",
     False),
    ("REF: DOOR SCHEDULE (ABOVE)", False),      # a callout points, it does not title
    ("SEE DOOR SCHEDULE", False),
    ("DOOR HARDWARE SCHEDULE", False),          # deny word, DOOR not adjacent
    ("FLOORING LEGEND", False),
    ("PAINT COLORS", False),
    ("REFLECTED CEILING PLAN", False),
])
def test_is_door_title_line(line, expected):
    assert _is_door_title_line(line) is expected


# ── PDF regression fixtures (skip if PDFs absent) ─────────────────────────────

def _open(path):
    import fitz
    return fitz.open(path)


@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_moxy_elevation_grid_page_contributes_zero_door_rows():
    """T-23-13: page index 15 DOES produce a title band and still yields nothing.

    Its interior-elevation drawing grid is read as a table by PyMuPDF; the column
    of grid letters looks like a tag column and the word WOOD inside prose supplies
    a pseudo material. This is the anti-regression assertion for the widened
    material reader — without part 2 of the guard it reports a phantom WD 4.
    """
    doc = _open(MOXY)
    try:
        page = doc[15]
        bands = _door_title_bands(page, [])
        assert bands, "page 15 is expected to produce a door-schedule title band"
        assert accepted_door_tables(page) == []
    finally:
        doc.close()


@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_moxy_all_five_schedule_fragments_are_accepted():
    """All five genuine fragments, including the header-less continuations."""
    doc = _open(MOXY)
    try:
        accepted = accepted_door_tables(doc[6])
    finally:
        doc.close()
    assert len(accepted) == 5, f"expected 5 accepted fragments, got {len(accepted)}"
    # The continuation fragments carry no header of their own and qualify purely
    # because their parent's band was extended over them.
    headerless = [t for t in accepted if not t["own_roles"]]
    assert len(headerless) >= 3, (
        f"expected >=3 header-less continuation fragments, got {len(headerless)}"
    )
    # Every fragment reads its materials from the same column indices.
    assert {t["panel_col"] for t in accepted} == {7}


@pytest.mark.skipif(not os.path.exists(BOBS), reason="Bob's plans PDF not present")
def test_bobs_schedule_table_is_accepted_and_read():
    """Today this table is FOUND and thrown away by the material-coverage gate."""
    doc = _open(BOBS)
    try:
        accepted = accepted_door_tables(doc[5])
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    assert len(accepted) == 1
    table = accepted[0]
    # Tag in column 1 (column 0 is the blank EXIST DOOR column), no count column,
    # panel from the MATERIAL header, frame from CONTENT (its header is split).
    assert (table["tag_col"], table["count_col"]) == (1, None)
    assert (table["panel_col"], table["frame_col"]) == (10, 12)

    # The drawing's own printed rows: one row is one opening.
    assert ds.pages == [6], f"unexpected schedule pages {ds.pages}"
    assert ds.panel_counts.get("HM") == 5
    assert ds.panel_counts.get("SCW") == 7
    assert ds.panel_counts.get("ALUM") == 2
    assert ds.frame_counts.get("HM") == 12


@pytest.mark.skipif(not os.path.exists(BOBS), reason="Bob's plans PDF not present")
def test_bobs_legend_item_names_are_canonical_not_prose():
    """The ITEM field must be what the aggregator and the scorer match on."""
    doc = _open(BOBS)
    try:
        legend = door_schedule_to_legend(extract_door_schedule(doc))
    finally:
        doc.close()
    items = {r["ITEM"] for r in legend["rows"]}
    assert {"Doors-HM", "Doors-WD", "Door Frames-HM"}.issubset(items)
    for item in items:
        assert "(door schedule)" not in item, f"prose suffix leaked into ITEM: {item}"
        assert "Solid Core" not in item and "Hollow Metal" not in item, item
    # The prose survives where a human reads it.
    descriptions = {r["DESCRIPTION"] for r in legend["rows"]}
    assert any("Solid Core Wood" in d for d in descriptions)
    # Quantities pass through verbatim — a counted door is never re-wasted.
    by_item = {r["ITEM"]: int(r["QTY"]) for r in legend["rows"]}
    assert by_item["Doors-HM"] == 5
    assert by_item["Doors-WD"] == 7
    assert by_item["Door Frames-HM"] == 12


@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_moxy_door_schedule_is_read_from_its_own_sheet():
    doc = _open(MOXY)
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    # The genuine door schedule lives on a single sheet — floor-plan door tags on
    # other pages must NOT be counted as schedule rows.
    assert ds.pages == [7], f"unexpected schedule pages {ds.pages}"
    assert ds.openings >= 53, f"expected >=53 scheduled openings, got {ds.openings}"
    # Material breakdown read from the table (raw codes, pre-canonicalisation).
    assert ds.panel_counts.get("SCW") == 40
    assert ds.panel_counts.get("GLASS") == 6
    assert ds.frame_counts.get("HM") == 40
    assert ds.frame_counts.get("GALV") == 6


@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_moxy_emits_canonical_names_instead_of_prose():
    """Moxy's 42 doors parsed correctly and scored MISSING purely on the NAME.

    ``Doors - Solid Core Wood (door schedule)`` shares no useful tokens with the
    golden's ``Doors-WD``, so no matcher could bridge it (INV-07 §3). Nothing
    about the parse changes here — only what the row is called.
    """
    doc = _open(MOXY)
    try:
        legend = door_schedule_to_legend(extract_door_schedule(doc))
    finally:
        doc.close()
    items = {r["ITEM"] for r in legend["rows"]}
    assert "Doors-WD" in items
    assert "Door Frames-HM" in items
    assert not any("(door schedule)" in i for i in items)


@pytest.mark.skipif(not os.path.exists(CROW), reason="Crow plans PDF not present")
def test_crow_type_schedule_is_read_by_the_same_parser():
    """The type+count format is now read by ONE parser, tag column included."""
    doc = _open(CROW)
    try:
        accepted = accepted_door_tables(doc[3])
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    assert len(accepted) == 1
    table = accepted[0]
    # Type code in column 0, Count in column 1 — not the other way round.
    assert (table["tag_col"], table["count_col"]) == (0, 1)
    assert ds.found
    assert ds.pages == [4]
    # The Count column is honoured: 2+68+2+24+2+1+1+1+4.
    assert ds.openings == 105, f"expected 105 openings, got {ds.openings}"
    assert ds.panel_counts.get("IM") == 29     # as PRINTED, before the note
    assert ds.panel_counts.get("STL") == 70
    assert ds.panel_counts.get("ALUM") == 6
    assert ds.frame_counts.get("HM") == 29


@pytest.mark.skipif(not os.path.exists(CROW), reason="Crow plans PDF not present")
def test_crow_note_driven_hm_reclassification_survives_the_parser_merge():
    """Crow's golden fixture has NO door rows, so the saved-run scorer cannot
    catch a door regression here — these assertions are the only guard.

    The 29 P-series doors print ``IM`` and are named hollow metal because the
    plan's own NOTE 1 / NOTE 2 bodies say *16 GA. HOLLOW METAL DOORS*. Deleting
    the type+count parser without moving that reclassification would silently
    emit ``Doors-IM``, which matches none of the aggregator's door patterns.
    """
    doc = _open(CROW)
    try:
        ds = extract_door_schedule(doc)
        legend = door_schedule_to_legend(ds)
    finally:
        doc.close()
    assert dict(reclassified_panel_counts(ds)) == {"HM": 29, "ALUM": 6, "STL": 70}
    by_item = {r["ITEM"]: int(r["QTY"]) for r in legend["rows"]}
    assert by_item["Doors-HM"] == 29
    assert by_item["Door Frames-HM"] == 29
    assert "Doors-IM" not in by_item


def test_solid_core_wood_canonicalises_to_the_wood_code():
    """SCW -> WD, not SC: aggregator.py has ``door.*\\bwd\\b`` and no ``\\bsc\\b``."""
    assert canonical_material_code("SCW") == "WD"
    assert canonical_material_code("ALUM") == "AL"
    assert canonical_material_code("GLASS") == "GL"
    assert canonical_material_code("HM") == "HM"


def test_the_type_plus_count_parser_is_gone():
    """One parser, not two — the count column absorbed its only distinct logic."""
    from bobbytailor.deterministic import component_library

    assert not hasattr(component_library, "_parse_count_door_rows")


# ── Honest zero: an input gap is reported as an input gap ─────────────────────

@pytest.mark.skipif(not os.path.exists(CHELSEA), reason="Chelsea plans PDF not present")
def test_chelsea_reports_zero_with_a_stated_reason():
    """Chelsea's schedule SHEET is not in the PDF. Zero is correct; silence is not.

    Its golden asks for 236 / 2,378 / 2,687 doors — per-unit-type multifamily
    numbers unreachable from this input. The difference this test pins is between
    reporting nothing and reporting that we looked, found the reference, and
    could not find the table.
    """
    doc = _open(CHELSEA)
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    assert ds.openings == 0
    assert ds.titled_pages, "Chelsea references a door schedule and must say so"
    warnings = door_schedule_coverage_warnings(ds)
    assert len(warnings) == 1
    for page in ds.titled_pages:
        assert str(page) in warnings[0]
    assert "no parsable schedule table" in warnings[0]


@pytest.mark.parametrize("pdf", [BOBS, CROW, MOXY])
def test_a_parsable_schedule_produces_no_coverage_warning(pdf):
    if not os.path.exists(pdf):
        pytest.skip(f"{pdf} not present")
    doc = _open(pdf)
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    assert ds.openings > 0
    assert door_schedule_coverage_warnings(ds) == []


def test_coverage_records_use_the_shared_item_status_vocabulary():
    """The status must be IMPORTED from the coverage module, not redefined.

    A second flag shape for the same fact is how a report ends up carrying two
    disagreeing accounts of one gap (D-03).
    """
    from bobbytailor.deterministic.schedule_extraction import DoorSchedule
    from bobbytailor.pipeline import coverage

    ds = DoorSchedule(openings=0, titled_pages=[1, 18])
    records = door_schedule_coverage(ds)
    assert len(records) == 1
    assert records[0]["status"] == coverage.ITEM_NOT_MEASURED
    assert records[0]["status"] in coverage.ITEM_STATUSES
    # None is not zero — the whole point of the 23-03 contract.
    assert records[0]["quantity"] is None
    assert "1, 18" in records[0]["reason"]


def test_an_absent_referenced_sheet_is_stated_never_reconstructed():
    """A schedule that parses but references a sheet the PDF lacks says so.

    The scheduled count stands as a LOWER BOUND. Scaling it by a multiplier that
    is not in the input would be a fabrication, so no multiplier is invented.
    """
    from bobbytailor.deterministic.schedule_extraction import DoorSchedule
    from bobbytailor.pipeline import coverage

    ds = DoorSchedule(openings=40, titled_pages=[7])
    records = door_schedule_coverage(ds, absent_references=["CS-04 UNIT MATRIX"])
    assert len(records) == 1
    assert records[0]["status"] == coverage.ITEM_NEEDS_REVIEW
    assert records[0]["quantity"] == 40.0
    assert "CS-04 UNIT MATRIX" in records[0]["reason"]
    assert "NOT reconstructed" in records[0]["reason"]
