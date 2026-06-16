"""Tests for companion take-off PDF discovery and table parsing (no API)."""
from pathlib import Path

from companion_takeoff import (
    _parse_legend_from_text,
    _table_to_rows,
    extract_legend_schedules,
    find_companion_takeoff_pdf,
)


def test_table_to_rows_parses_item_qty_unit():
    table = [
        ["Item", "Qty", "Unit"],
        ["Bollards", "28", "EA"],
        ["Sealed Concrete", "395673.42", "SF"],
    ]
    rows = _table_to_rows(table)
    assert len(rows) == 2
    assert rows[0]["ITEM"] == "Bollards"
    assert rows[0]["QTY"] == "28"
    assert rows[1]["UNIT"] == "SF"


def test_find_companion_takeoff_pdf(tmp_path):
    plans = tmp_path / "warehouse_plans.pdf"
    plans.write_bytes(b"%PDF-1.4")
    companion = tmp_path / "warehouse_takeoff.pdf"
    companion.write_bytes(b"%PDF-1.4")

    found = find_companion_takeoff_pdf(str(plans))
    assert found == str(companion.resolve())


def test_extract_legend_schedules_missing_file():
    assert extract_legend_schedules("/nonexistent/path/takeoff.pdf") == []


def test_parse_legend_from_text_borderless_pairs():
    """Borderless legend: icon-prefixed item line, then '<qty> <unit>' line."""
    text = (
        "Legend\n"
        "\uf114Bollards\n28 EA\n"
        "\ue92bCMU Wall\n2,204.33 SF\n"
        "\uf114Columns-H-35'\n132 EA\n"
        "Internal Tilt up walls\n108,442.66 SF\n"
    )
    rows = _parse_legend_from_text(text)
    by_item = {r["ITEM"]: r for r in rows}
    assert by_item["Bollards"]["QTY"] == "28"
    assert by_item["Bollards"]["UNIT"] == "EA"
    assert by_item["CMU Wall"]["QTY"] == "2,204.33"
    assert by_item["CMU Wall"]["UNIT"] == "SF"
    assert by_item["Columns-H-35'"]["QTY"] == "132"
    assert by_item["Internal Tilt up walls"]["UNIT"] == "SF"


def test_parse_legend_from_text_inline():
    rows = _parse_legend_from_text("Gas Piping 886.77 LF\nLintels 179.24 LF\n")
    assert {r["ITEM"]: r["UNIT"] for r in rows} == {
        "Gas Piping": "LF", "Lintels": "LF",
    }


def test_parse_legend_rejects_noise():
    """Pure-number 'items', dimension strings, and unknown units are ignored."""
    text = (
        "8\n001A EA\n"          # door-mark noise: item would be pure number
        "54' - 0\"\n"            # dimension callout
        "STEEL PIPE 80 SCH\n"   # 'SCH' is not a known unit
        "Bollards\n11 EA\n"     # valid
    )
    rows = _parse_legend_from_text(text)
    items = {r["ITEM"] for r in rows}
    assert items == {"Bollards"}
