"""tests/test_coverage_ledger.py — the coverage ledger and provenance vocabulary.

Pure data tests: no PDF fixture, no fitz, no API key. The ledger module is
deliberately I/O-free so its completeness invariant is provable in milliseconds.

The invariant under test (INV-08 §3.1): every page of the source PDF has exactly
one ledger row, whatever the pipeline decided about it — and a quantity that was
not measured is None, never 0.0.
"""

import pytest

from bobbytailor.pipeline.coverage import (
    ERRORED,
    EXCLUDED_OFF_SCALE,
    ITEM_HUMAN_INPUT,
    ITEM_MEASURED,
    ITEM_NEEDS_REVIEW,
    ITEM_NOT_APPLICABLE,
    ITEM_NOT_MEASURED,
    MEASURED,
    MEASURED_PARTIAL,
    NOT_APPLICABLE,
    SKIPPED_CLASSIFIER,
    SKIPPED_NO_SCALE,
    VISION_ONLY,
    CoverageLedger,
    DrawingCoverage,
    ItemCoverage,
    SheetCoverage,
    _compact_ranges,
)
from bobbytailor.pipeline.provenance import provenance_of_row

pytestmark = pytest.mark.generalization


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_item_status_strings_are_the_client_vocabulary_verbatim():
    """The four-value vocabulary from export_takeoff_excel.py:7-10, unchanged.

    These strings are printed on a workbook a client bids from; renaming one is
    a client-visible change, not a refactor.
    """
    assert ITEM_MEASURED == "MEASURED"
    assert ITEM_HUMAN_INPUT == "HUMAN INPUT"
    assert ITEM_NEEDS_REVIEW == "NEEDS REVIEW"
    assert ITEM_NOT_MEASURED == "NOT MEASURED"
    assert ITEM_NOT_APPLICABLE == "NOT APPLICABLE"


def test_seven_sheet_dispositions_are_distinct():
    values = [
        MEASURED, MEASURED_PARTIAL, VISION_ONLY, SKIPPED_CLASSIFIER,
        SKIPPED_NO_SCALE, NOT_APPLICABLE, ERRORED,
    ]
    assert len(set(values)) == 7


# ---------------------------------------------------------------------------
# "None is not zero"
# ---------------------------------------------------------------------------


def test_unmeasured_quantities_default_to_none_never_zero():
    """A blank must never render as a zero — enforced at the dataclass default."""
    assert ItemCoverage(name="Gyp Ceiling").quantity is None
    assert DrawingCoverage().area_sf is None


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_dataclass_round_trip_through_to_dict():
    drawing = DrawingCoverage(
        region_id="FILL-2",
        title="KING SUITE B - RCP PLAN",
        plan_kind="RCP",
        disposition=MEASURED,
        printed_scale_fpi=4.0,
        area_sf=341.7,
    )
    sheet = SheetCoverage(
        page_index=27,
        sheet_name="ID-411",
        sheet_type="title_sheet",
        type_source="title_block",
        classifier_keyword="COVER",
        classifier_context="ABEL ON THE LIGHT SWITCH COVER PLATE INDICATING",
        disposition=SKIPPED_CLASSIFIER,
        reason="classified title_sheet",
        measurable_signal={"plan_titles": 5, "printed_scales": 13, "viewports": 9},
        drawings=[drawing],
        items_emitted=0,
    )
    item = ItemCoverage(
        name="Gyp Ceiling", unit="SF", status=ITEM_NOT_MEASURED,
        basis="ceiling_area", expected_from="vocabulary",
        reason="sheet skipped by classifier",
    )
    ledger = CoverageLedger(pages_in_source=40, sheets=[sheet], items=[item])

    payload = ledger.to_dict()
    assert payload["pages_in_source"] == 40
    assert len(payload["sheets"]) == 1

    row = payload["sheets"][0]
    assert row["page_index"] == 27
    assert row["sheet_name"] == "ID-411"
    assert row["classifier_keyword"] == "COVER"
    assert "PLATE" in row["classifier_context"]
    assert row["disposition"] == SKIPPED_CLASSIFIER
    assert row["measurable_signal"] == {
        "plan_titles": 5, "printed_scales": 13, "viewports": 9,
    }
    assert row["is_silent_loss"] is True
    assert row["drawings"][0]["area_sf"] == pytest.approx(341.7)
    assert row["drawings"][0]["title"] == "KING SUITE B - RCP PLAN"

    assert payload["items"][0]["quantity"] is None
    assert payload["items"][0]["status"] == ITEM_NOT_MEASURED
    assert payload["summary"]["pages_in_source"] == 40
    assert isinstance(payload["warnings"], list)


# ---------------------------------------------------------------------------
# The completeness invariant
# ---------------------------------------------------------------------------


def _ledger_of(pages: int, registered) -> CoverageLedger:
    ledger = CoverageLedger(pages_in_source=pages)
    for i in registered:
        ledger.register_page(i, disposition=MEASURED)
    return ledger


def test_assert_accounted_reports_the_missing_page():
    """39 rows for a 40-page source: the ledger names the page it lost."""
    missing_index = 23
    present = [i for i in range(40) if i != missing_index]
    ledger = _ledger_of(40, present)
    assert ledger.assert_accounted() == [missing_index]


def test_assert_accounted_is_empty_when_every_page_has_a_row():
    ledger = _ledger_of(40, range(40))
    assert ledger.assert_accounted() == []
    assert len(ledger.sheets) == 40


def test_unaccounted_pages_raise_a_warning_string():
    ledger = _ledger_of(40, [i for i in range(40) if i != 7])
    joined = " ".join(ledger.warnings())
    assert "no ledger row" in joined
    assert "7" in joined


def test_register_page_is_idempotent():
    """A second registration updates the row; it never appends a duplicate."""
    ledger = CoverageLedger(pages_in_source=3)
    first = ledger.register_page(1, sheet_name="A2.1", disposition=SKIPPED_CLASSIFIER)
    second = ledger.register_page(1, disposition=MEASURED_PARTIAL, items_emitted=4)

    assert len(ledger.sheets) == 1
    assert first is second
    assert ledger.sheet(1).sheet_name == "A2.1"          # preserved
    assert ledger.sheet(1).disposition == MEASURED_PARTIAL  # updated
    assert ledger.sheet(1).items_emitted == 4


def test_register_page_rejects_an_unknown_field():
    """A typo must fail loudly rather than silently record nothing."""
    ledger = CoverageLedger(pages_in_source=1)
    with pytest.raises(TypeError):
        ledger.register_page(0, dispositon="measured")  # noqa: SC200 — typo on purpose


def test_sheet_returns_none_for_an_unregistered_page():
    assert CoverageLedger(pages_in_source=5).sheet(2) is None


# ---------------------------------------------------------------------------
# is_silent_loss — the Gap 8 alarm
# ---------------------------------------------------------------------------


def test_is_silent_loss_true_when_skipped_despite_measurable_signal():
    """Moxy pages 23-38: called a title sheet while holding 5-6 plan drawings."""
    row = SheetCoverage(
        page_index=23,
        disposition=SKIPPED_CLASSIFIER,
        measurable_signal={"plan_titles": 6, "printed_scales": 10},
    )
    assert row.is_silent_loss is True


def test_is_silent_loss_false_for_a_genuine_cover_sheet():
    """Same disposition, all-zero signal: Bob's page 0 is a real cover sheet."""
    row = SheetCoverage(
        page_index=0,
        disposition=SKIPPED_CLASSIFIER,
        measurable_signal={"plan_titles": 0, "printed_scales": 0, "viewports": 0},
    )
    assert row.is_silent_loss is False


def test_is_silent_loss_false_when_the_page_was_measured():
    row = SheetCoverage(
        page_index=9,
        disposition=MEASURED,
        measurable_signal={"plan_titles": 2, "printed_scales": 2},
    )
    assert row.is_silent_loss is False


@pytest.mark.parametrize(
    "disposition", [SKIPPED_CLASSIFIER, SKIPPED_NO_SCALE, NOT_APPLICABLE]
)
def test_every_not_measured_disposition_can_be_a_silent_loss(disposition):
    row = SheetCoverage(
        page_index=1, disposition=disposition,
        measurable_signal={"plan_titles": 1},
    )
    assert row.is_silent_loss is True


# ---------------------------------------------------------------------------
# summary() / warnings()
# ---------------------------------------------------------------------------


def _moxy_shaped_ledger() -> CoverageLedger:
    """A ledger shaped like the pre-veto Moxy audit in INV-08 §1.1."""
    ledger = CoverageLedger(pages_in_source=40)
    for i in range(40):
        if i in (0, 1):
            ledger.register_page(
                i, disposition=NOT_APPLICABLE, sheet_type="title_sheet",
                classifier_keyword="COVER SHEET",
                measurable_signal={"plan_titles": 0, "printed_scales": 0},
            )
        elif 23 <= i <= 38:
            ledger.register_page(
                i, disposition=SKIPPED_CLASSIFIER, sheet_type="title_sheet",
                classifier_keyword="COVER",
                classifier_context="LIGHT SWITCH COVER PLATE INDICATING",
                measurable_signal={"plan_titles": 5, "printed_scales": 9},
            )
        elif i in (3, 4, 5, 15, 16, 17, 18, 19, 20):
            ledger.register_page(i, disposition=VISION_ONLY, sheet_type="elevation")
        else:
            ledger.register_page(i, disposition=MEASURED, sheet_type="floor_plan")
    return ledger


def test_summary_counts_every_disposition():
    summary = _moxy_shaped_ledger().summary()
    assert summary["pages_in_source"] == 40
    assert summary["sheets_not_applicable"] == 2
    assert summary["sheets_skipped"] == 16
    assert summary["sheets_vision_only"] == 9
    assert summary["sheets_measured"] == 13
    assert summary["sheets_errored"] == 0
    assert summary["sheets_measured"] + summary["sheets_vision_only"] \
        + summary["sheets_skipped"] + summary["sheets_not_applicable"] \
        + summary["sheets_errored"] == 40
    assert summary["silent_loss_pages"] == list(range(23, 39))
    assert summary["coverage_pct_pages"] == pytest.approx(32.5)


def test_warnings_name_the_pages_and_the_deciding_keyword():
    joined = " ".join(_moxy_shaped_ledger().warnings())
    assert "23-38" in joined
    assert "COVER" in joined
    assert "blank" in joined.lower()


def test_summary_is_all_zero_on_an_empty_ledger():
    summary = CoverageLedger().summary()
    assert summary["pages_in_source"] == 0
    assert summary["coverage_pct_pages"] == 0.0
    assert summary["coverage_pct_items"] == 0.0
    assert summary["silent_loss_pages"] == []
    assert CoverageLedger().warnings() == []


def test_drawing_counts_separate_off_scale_from_no_scale():
    """Excluded-as-off-scale and dropped-for-no-scale are different facts."""
    ledger = CoverageLedger(pages_in_source=1)
    row = ledger.register_page(0, disposition=MEASURED_PARTIAL)
    row.drawings = [
        DrawingCoverage(region_id="FILL-1", disposition=MEASURED, area_sf=229.4),
        DrawingCoverage(
            region_id="FILL-2", disposition=SKIPPED_NO_SCALE,
            reason="no printed scale beneath the title",
        ),
        DrawingCoverage(
            region_id="R3", disposition=EXCLUDED_OFF_SCALE,
            reason="printed scale differs from the resolved page scale",
        ),
    ]
    summary = ledger.summary()
    assert summary["drawings_measured"] == 1
    assert summary["drawings_dropped_no_scale"] == 1
    assert summary["drawings_excluded_off_scale"] == 1
    assert "squared error" in " ".join(ledger.warnings())


def test_item_summary_counts_and_percentage():
    ledger = CoverageLedger(pages_in_source=1)
    ledger.add_item(ItemCoverage(name="a", status=ITEM_MEASURED, quantity=10.0))
    ledger.add_item(ItemCoverage(name="b", status=ITEM_NEEDS_REVIEW, quantity=5.0))
    ledger.add_item(ItemCoverage(name="c", status=ITEM_NOT_MEASURED))
    ledger.add_item(ItemCoverage(name="d", status=ITEM_HUMAN_INPUT, quantity=2.0))
    summary = ledger.summary()
    assert summary["items_measured"] == 1
    assert summary["items_needs_review"] == 1
    assert summary["items_not_measured"] == 1
    assert summary["items_human_input"] == 1
    assert summary["coverage_pct_items"] == pytest.approx(25.0)
    assert "do NOT read" in " ".join(ledger.warnings())


def test_errored_pages_are_warned_about():
    ledger = CoverageLedger(pages_in_source=2)
    ledger.register_page(0, disposition=MEASURED)
    ledger.register_page(1, disposition=ERRORED, reason="boom")
    assert ledger.summary()["sheets_errored"] == 1
    assert "errored" in " ".join(ledger.warnings())


def test_overruled_pages_are_warned_about():
    ledger = CoverageLedger(pages_in_source=1)
    ledger.register_page(
        0, disposition=MEASURED_PARTIAL, classifier_overruled=True,
        reason="classifier overruled; deterministic geometry only",
    )
    joined = " ".join(ledger.warnings())
    assert "overruled" in joined
    assert "zero API" in joined


@pytest.mark.parametrize(
    "indices,expected",
    [
        ([], ""),
        ([5], "5"),
        ([0, 1], "0-1"),
        ([23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38], "23-38"),
        ([0, 1, 5, 6, 7, 9], "0-1, 5-7, 9"),
    ],
)
def test_compact_ranges(indices, expected):
    assert _compact_ranges(indices) == expected


# ---------------------------------------------------------------------------
# provenance_of_row
# ---------------------------------------------------------------------------


def test_provenance_none_quantity_is_not_measured():
    assert provenance_of_row({"quantity": None}) == ITEM_NOT_MEASURED
    assert provenance_of_row({}) == ITEM_NOT_MEASURED
    assert provenance_of_row({"quantity": ""}) == ITEM_NOT_MEASURED


def test_provenance_a_measured_zero_stays_measured():
    """The S12 fix: a real zero and a never-attempted measurement differ.

    The old exporter logic said `float(qty or 0) <= 0 -> NOT MEASURED`, which
    made a building with genuinely no CMU indistinguishable from one whose CMU
    was never measured.
    """
    assert provenance_of_row({"quantity": 0.0, "source": "geometry"}) == ITEM_MEASURED


def test_provenance_flagged_row_is_needs_review():
    assert provenance_of_row(
        {"quantity": 12.0, "needs_review": True}
    ) == ITEM_NEEDS_REVIEW


@pytest.mark.parametrize(
    "source", ["manifest", "human", "learned", "manifest_missing", "MANIFEST"]
)
def test_provenance_human_sources(source):
    assert provenance_of_row({"quantity": 3.0, "source": source}) == ITEM_HUMAN_INPUT


def test_provenance_recorded_status_wins_over_inference():
    """The ledger knows what happened; nothing should second-guess it."""
    row = {"status": ITEM_NOT_MEASURED, "quantity": 99.0, "source": "geometry"}
    assert provenance_of_row(row) == ITEM_NOT_MEASURED


def test_provenance_plain_measured_row():
    assert provenance_of_row({"quantity": 4500.0, "source": "geometry"}) == ITEM_MEASURED


def test_provenance_needs_review_outranks_human_source():
    row = {"quantity": 1.0, "needs_review": True, "source": "manifest"}
    assert provenance_of_row(row) == ITEM_NEEDS_REVIEW
