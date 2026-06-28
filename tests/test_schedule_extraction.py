"""Regression tests for deterministic door-schedule extraction.

Door panel/frame materials are printed exactly in the schedule table; these tests
lock in (a) tag tokenisation, (b) order-independent material-column detection, and
(c) precise per-sheet recovery on the real plan PDFs without false positives from
floor-plan door callouts.
"""
import os

import pytest

from schedule_extraction import (
    _tag_tokens,
    _tag_column,
    _material_columns,
    extract_door_schedule,
)

UPLOADS = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
MOXY = os.path.join(UPLOADS, "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf")
CROW = os.path.join(UPLOADS, "Crow - Cass White Road-Plans.pdf")


# ── Tag tokenisation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell,expected", [
    ("003", ["003"]),
    ("006A", ["006A"]),
    ("113A 113B", ["113A", "113B"]),   # merged cell -> two doors
    ("T2 T6", ["T2", "T6"]),
    ("T1", ["T1"]),
    ("WORK AREA", []),                  # room name, not a tag
    ("SCW", []),                        # material, not a tag
    ("", []),
])
def test_tag_tokens(cell, expected):
    assert _tag_tokens(cell) == expected


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
    # panel column carries leaf-only tokens (SCW/GLASS); frame carries GALV
    assert panel_col == 3
    assert frame_col == 5


# ── PDF regression fixtures (skip if PDFs absent) ─────────────────────────────

@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_moxy_door_schedule_is_exact():
    import fitz
    doc = fitz.open(MOXY)
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    # The genuine door schedule lives on a single sheet — floor-plan door tags on
    # other pages must NOT be counted as schedule rows.
    assert ds.pages == [7], f"unexpected schedule pages {ds.pages}"
    assert ds.openings == 60, f"expected 60 scheduled openings, got {ds.openings}"
    # Exact material breakdown read from the table.
    assert ds.panel_counts.get("SCW") == 42
    assert ds.panel_counts.get("GLASS") == 6
    assert ds.frame_counts.get("HM") == 42
    assert ds.frame_counts.get("GALV") == 6


@pytest.mark.skipif(not os.path.exists(CROW), reason="Crow plans PDF not present")
def test_crow_door_schedule_recovers_openings():
    import fitz
    doc = fitz.open(CROW)
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    assert ds.found
    assert ds.openings == 5, f"expected 5 openings, got {ds.openings}"
    assert ds.frame_counts.get("HM") == 2
