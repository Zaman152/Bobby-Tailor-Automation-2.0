"""Layer-1 tests for generalized deterministic schedule extraction."""
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import fitz
import pytest

from bobbytailor.deterministic.schedule_extraction import extract_door_schedule
from bobbytailor.deterministic.tables import (
    SCHEDULE_KIND_VOCABULARIES,
    ScheduleTable,
    extract_schedules,
)

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"


def _make_table_doc(rows: Sequence[Sequence[str]], col_width: float = 110.0) -> fitz.Document:
    """Build a one-page PDF with a ruled table find_tables can detect."""
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    x0, y0, row_h = 50.0, 50.0, 22.0
    n_cols = max(len(r) for r in rows)
    x1 = x0 + n_cols * col_width
    y1 = y0 + len(rows) * row_h

    for i in range(len(rows) + 1):
        y = y0 + i * row_h
        page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y))
    for c in range(n_cols + 1):
        x = x0 + c * col_width
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y1))

    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            page.insert_text(
                fitz.Point(x0 + ci * col_width + 4, y0 + ri * row_h + 15),
                cell,
                fontsize=9,
            )
    return doc


# ── vocabulary registry ───────────────────────────────────────────────────────


def test_vocabulary_covers_required_kinds():
    for kind in ("door", "window", "finish", "fixture", "equipment", "keynote"):
        assert kind in SCHEDULE_KIND_VOCABULARIES
    assert len(SCHEDULE_KIND_VOCABULARIES) >= 5


# ── synthetic window schedule ─────────────────────────────────────────────────


def test_window_schedule_rows_parse_with_tag_column():
    rows = [
        ["WINDOW MARK", "WIDTH", "HEIGHT", "TYPE", "REMARKS"],
        ["W1", "3'-0\"", "5'-0\"", "FIXED VINYL", ""],
        ["W2", "6'-0\"", "5'-0\"", "FIXED VINYL", "TEMPERED"],
        ["W3", "3'-0\"", "2'-0\"", "CASEMENT", ""],
        ["W4", "4'-0\"", "4'-0\"", "FIXED VINYL", ""],
    ]
    doc = _make_table_doc(rows)
    tables = extract_schedules(doc, kinds=["window"])
    doc.close()

    assert len(tables) == 1
    t = tables[0]
    assert isinstance(t, ScheduleTable)
    assert t.kind == "window"
    assert t.page_index == 0
    assert [r["TAG"] for r in t.rows] == ["W1", "W2", "W3", "W4"]
    assert t.bbox_pt[2] > t.bbox_pt[0] and t.bbox_pt[3] > t.bbox_pt[1]
    # Header-keyed cells survive into structured rows.
    assert any("WIDTH" in r for r in t.rows)


# ── synthetic finish schedule ─────────────────────────────────────────────────


def test_finish_schedule_rows_parse_with_tag_column():
    rows = [
        ["ROOM NO", "ROOM NAME", "FLOOR FINISH", "BASE", "CEILING"],
        ["101", "OFFICE", "VCT", "RB", "ACT"],
        ["102", "STORAGE", "SC", "RB", "GWB"],
        ["103", "CORRIDOR", "CPT", "RB", "ACT"],
        ["104", "TOILET", "CT", "RB", "GWB"],
    ]
    doc = _make_table_doc(rows)
    tables = extract_schedules(doc, kinds=["finish"])
    doc.close()

    assert len(tables) == 1
    t = tables[0]
    assert t.kind == "finish"
    assert [r["TAG"] for r in t.rows] == ["101", "102", "103", "104"]
    assert t.confidence in ("high", "medium")


# ── coverage gate rejects non-schedules ───────────────────────────────────────


def test_non_schedule_table_rejected_by_coverage_gate():
    """A ruled table of prose words carries no kind's tag tokens — the
    door-pattern coverage gate must reject it for every kind."""
    rows = [
        ["GENERAL", "PROJECT", "NOTES", "HERE"],
        ["ALPHA", "BRAVO", "CHARLIE", "DELTA"],
        ["ECHO", "FOXTROT", "GOLF", "HOTEL"],
        ["INDIA", "JULIET", "KILO", "LIMA"],
        ["MIKE", "NOVEMBER", "OSCAR", "PAPA"],
    ]
    doc = _make_table_doc(rows)
    tables = extract_schedules(doc)
    doc.close()
    assert tables == []


# ── door delegation (generalize, don't fork) ─────────────────────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_door_delegation_matches_schedule_extraction_on_crow():
    """kind='door' delegates to schedule_extraction.extract_door_schedule —
    the generalized reader reports exactly the same door records."""
    doc = fitz.open(CROW_PDF)
    door_tables = extract_schedules(doc, kinds=["door"])
    ds = extract_door_schedule(doc)
    doc.close()

    assert ds.found
    total_rows = sum(len(t.rows) for t in door_tables)
    assert total_rows == len(ds.records)
    delegated_tags = sorted(r["TAG"] for t in door_tables for r in t.rows)
    assert delegated_tags == sorted(rec.tag for rec in ds.records)
    for t in door_tables:
        assert t.kind == "door"
        assert t.page_index + 1 in ds.pages
        # Region-masking data: a real located bbox, not the zero default.
        assert t.bbox_pt[2] > t.bbox_pt[0] and t.bbox_pt[3] > t.bbox_pt[1]


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's Discount PDF fixture missing")
def test_extract_schedules_runs_clean_on_bobs_fixture():
    """Full-kind extraction over a real multi-sheet drawing set returns
    structured tables (or none) without raising, each with registry fields."""
    doc = fitz.open(BOBS_PDF)
    tables = extract_schedules(doc)
    doc.close()

    for t in tables:
        assert t.kind in SCHEDULE_KIND_VOCABULARIES
        assert 0 <= t.page_index
        assert t.rows, "claimed tables must carry structured rows"
        assert all("TAG" in r for r in t.rows)
        d = t.to_dict()
        assert d["kind"] == t.kind
        assert tuple(d["bbox_pt"]) == tuple(t.bbox_pt)
