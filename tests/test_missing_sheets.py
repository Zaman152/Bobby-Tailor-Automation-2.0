"""A set that CITES a sheet it does not CONTAIN. ZERO API.

Crow's golden take-off lists 10 stairs and the engine will never find them,
because they are not in the file. The uploaded 4-page PDF contains A-101,
A-201, A-401 and A-601, and page 0 defers three times to enlarged plans A-111,
A-112 and A-113 that are absent.

The success condition for Stairs is honest flagging, not a number. These tests
pin that the run SAYS SO — with the sheet ids quoted from the drawing — instead
of publishing a count nobody can defend.

They also correct INV-B on a point of fact. INV-B places the stairs on "A-401
details and the A-111/112/113 enlarged plans, which are not in the uploaded
PDF". A-401 IS in the uploaded PDF: it is page 2, MISC. DETAILS, and it draws a
STAIR PLAN, a STAIR SECTION and a STAIR RAIL. The set shows what a stair looks
like; what it never shows is how many are installed. Only A-111/112/113 (and
A-002, A-501) are genuinely absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.pipeline.coverage import (  # noqa: E402
    NOT_IN_UPLOADED_SET,
    CoverageLedger,
    DrawingCoverage,
    SheetCoverage,
)
from bobbytailor.pipeline.cross_references import (  # noqa: E402
    missing_referenced_sheets,
    sheet_ids_in_text,
)

CROW_PDF = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"


def test_sheet_ids_are_read_out_of_prose():
    got = sheet_ids_in_text("SEE 1/A-111 AND 6/A-401, TYP. ALSO M-101a")
    # A trailing revision letter is part of the sheet id (A-101A is a sheet).
    assert got == ["A-111", "A-401", "M-101A"]
    assert sheet_ids_in_text("") == []
    assert sheet_ids_in_text("no sheets here") == []


def test_a_cited_sheet_that_is_present_is_not_missing():
    assert missing_referenced_sheets(["A-401"], ["SEE 6/A-401"]) == []


def test_a_cited_sheet_that_is_absent_is_reported_with_its_evidence():
    got = missing_referenced_sheets(
        ["A-101"],
        ["SEE 1/A-111", "nothing", "SEE 1/A-111 AND 1/A-112"],
    )
    assert got == [
        {"sheet_id": "A-111", "cited_on_pages": [0, 2], "citations": 2},
        {"sheet_id": "A-112", "cited_on_pages": [2], "citations": 1},
    ]


@pytest.mark.skipif(not CROW_PDF.exists(), reason="Crow fixture PDF not present")
def test_crow_cites_the_enlarged_plans_that_hold_its_stairs_and_does_not_contain_them():
    """The measured statement about the 10 stairs.

    A-401 is PRESENT (page 2). A-111/112/113 are cited from page 0 and absent.
    No detector — deterministic, ML or vision — can count objects that are not
    in the file, so the only correct output for Stairs is this flag.
    """
    import fitz

    doc = fitz.open(CROW_PDF)
    try:
        from scripts.coverage_probe import get_title_block_text

        present = [
            sid
            for i in range(doc.page_count)
            for sid in sheet_ids_in_text(get_title_block_text(doc, i))
        ]
        missing = missing_referenced_sheets(present, [p.get_text() for p in doc])
    finally:
        doc.close()

    assert sorted(present) == ["A-101", "A-201", "A-401", "A-601"]
    ids = [m["sheet_id"] for m in missing]
    assert "A-401" not in ids, "A-401 IS in the uploaded set — it is page 2"
    for enlarged in ("A-111", "A-112", "A-113"):
        assert enlarged in ids, "%s holds the stairs and is absent" % enlarged
        row = next(m for m in missing if m["sheet_id"] == enlarged)
        assert row["cited_on_pages"] == [0]


def test_the_ledger_says_the_input_was_incomplete_not_that_the_engine_failed():
    led = CoverageLedger(pages_in_source=1)
    led.register_page(0)
    led.missing_sheets = [
        {"sheet_id": "A-111", "cited_on_pages": [0], "citations": 2},
    ]
    warning = " ".join(led.warnings())
    assert "A-111" in warning
    assert "UNKNOWN, not zero" in warning
    assert "uploading the missing sheets" in warning
    assert led.summary()["sheets_referenced_but_missing"] == ["A-111"]
    assert led.to_dict()["missing_sheets"][0]["sheet_id"] == "A-111"


def test_a_drawing_absent_from_the_upload_has_its_own_disposition():
    """NOT_IN_UPLOADED_SET is not 'we skipped it' and not 'we measured zero'."""
    led = CoverageLedger(pages_in_source=1)
    row = SheetCoverage(page_index=0)
    row.drawings.append(
        DrawingCoverage(
            region_id="A-111",
            title="ENLARGED PLAN",
            disposition=NOT_IN_UPLOADED_SET,
            reason="cross-referenced from A-101 but not present in the file",
        )
    )
    led.sheets.append(row)
    assert led.summary()["drawings_not_in_uploaded_set"] == 1
    assert led.summary()["drawings_measured"] == 0
    assert "NOT IN THE UPLOADED SET" in " ".join(led.warnings())


def test_a_complete_set_says_nothing_about_missing_sheets():
    led = CoverageLedger(pages_in_source=1)
    led.register_page(0)
    assert led.summary()["sheets_referenced_but_missing"] == []
    assert not any("does not CONTAIN" in w for w in led.warnings())
