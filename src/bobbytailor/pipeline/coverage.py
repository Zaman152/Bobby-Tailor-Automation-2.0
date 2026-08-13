"""Per-run coverage ledger — every page, drawing and expected item accounted for.

**A blank must never render as a zero.** This module holds the record of what the
run did NOT measure, so the report can state it explicitly instead of shipping a
defaultdict's ``0.0`` that every numeric consumer reads as "the building has none
of this".

The invariant (INV-08 §3.1):

    Every page of the source PDF, every drawing on a measured page, and every
    expected line item is accounted for as exactly one of
    measured / flagged / explicitly-not-applicable. A quantity that was not
    measured is ``None``, never ``0.0``, and always carries a reason.

One-line acceptance, for every PDF, always::

    len(report["coverage_ledger"]) == report["coverage"]["pages_in_source"] \\
        == fitz.open(pdf).page_count

If a page is not in the ledger, the run is a bug.

Pure data plus formatting: no I/O, no ``fitz`` import, no PDF dependency, so the
whole module is unit-testable with zero fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Sheet dispositions (INV-08 §3.2)
# ---------------------------------------------------------------------------
MEASURED = "measured"                    # deterministic geometry produced numbers
MEASURED_PARTIAL = "measured_partial"    # some drawings measured, some dropped
VISION_ONLY = "vision_only"              # reached vision passes, no geometry engine
SKIPPED_CLASSIFIER = "skipped_classifier"  # title_sheet / empty pass list
SKIPPED_NO_SCALE = "skipped_no_scale"    # fpp <= 0, nothing measurable
NOT_APPLICABLE = "not_applicable"        # genuine cover/index — no take-off content
ERRORED = "errored"                      # exception; degraded per-sheet

# The wallet stopped the work, not the drawing. A sheet whose remaining passes
# were skipped because the run BudgetGuard refused a charge is NOT measured —
# and it is a different fact from MEASURED_PARTIAL, whose gap is explained by
# something on the page (an off-scale viewport, a drawing with no printed
# scale). This gap is explained by the cap, and it closes by raising the cap
# and re-running. Crow's A-401 and A-601 were truncated exactly this way and
# both rows read "measured" (C2): a silent coverage loss, the class of defect
# phase 23 abolished everywhere else.
MEASURED_TRUNCATED = "measured_budget_truncated"

SHEET_DISPOSITIONS = (
    MEASURED,
    MEASURED_PARTIAL,
    MEASURED_TRUNCATED,
    VISION_ONLY,
    SKIPPED_CLASSIFIER,
    SKIPPED_NO_SCALE,
    NOT_APPLICABLE,
    ERRORED,
)

# Drawing-level-only disposition. A viewport whose OWN printed scale disagrees
# with the resolved page scale is deliberately masked out of the geometry
# (takeoff_pipeline off-scale exclusion, INV-08 §1.4): measuring it at the page
# scale would be ~60x wrong. That exclusion is CORRECT and today invisible —
# it exists as a logger.info and nothing more. It needs its own value so
# summary() can distinguish "excluded because measuring it would be wrong" from
# "dropped because it had no scale of its own".
EXCLUDED_OFF_SCALE = "excluded_off_scale"

# The gap is in the INPUT, not the engine. A drawing set that cites a sheet it
# does not contain cannot be measured for whatever lives on that sheet, and no
# detector — deterministic, ML or vision — can count objects that are not in
# the file. Crow's golden lists 10 stairs; the uploaded 4-page PDF holds
# A-101/A-201/A-401/A-601 and defers three times to enlarged plans A-111,
# A-112 and A-113 that are not in it. A-401 draws a STAIR PLAN and a STAIR
# SECTION, so the set shows what a stair looks like — it never says how many
# are installed. Reporting this as an engine miss sends someone to fix a
# detector; reporting it as a missing sheet gets the sheet uploaded.
NOT_IN_UPLOADED_SET = "not_in_uploaded_set"

# The set of dispositions that mean "this page produced no measurement".
# is_silent_loss fires when one of these coincides with measurable signal.
_NOT_MEASURED_DISPOSITIONS = (SKIPPED_CLASSIFIER, SKIPPED_NO_SCALE, NOT_APPLICABLE)

# ---------------------------------------------------------------------------
# Item statuses — the four-value client vocabulary, verbatim from
# scripts/export_takeoff_excel.py:7-10. Adopted unchanged because that
# module's About-sheet line ("No measurement path for this item yet. Do NOT
# read a blank as zero") is the thesis of INV-08.
# ---------------------------------------------------------------------------
ITEM_MEASURED = "MEASURED"            # geometry measured it off the drawing
ITEM_HUMAN_INPUT = "HUMAN INPUT"      # a human supplied it, in a human input file
ITEM_NEEDS_REVIEW = "NEEDS REVIEW"    # measured but flagged; confirm before use
ITEM_NOT_MEASURED = "NOT MEASURED"    # no measurement path — do NOT read as zero
ITEM_NOT_APPLICABLE = "NOT APPLICABLE"  # the drawing set genuinely has none

# An estimating convention the APP injects (1 EA Mobilization) — nobody
# measured it off a drawing and nobody supplied it. It used to publish as
# HUMAN INPUT, which claimed a human vouched for a number the app made up
# (C4). Its own value is the only honest place for it: the quantity is real
# and publishable, so NOT MEASURED would lie in the other direction.
ITEM_STANDARD = "STANDARD ITEM"

ITEM_STATUSES = (
    ITEM_MEASURED,
    ITEM_HUMAN_INPUT,
    ITEM_NEEDS_REVIEW,
    ITEM_NOT_MEASURED,
    ITEM_NOT_APPLICABLE,
    ITEM_STANDARD,
)


def _compact_ranges(indices: List[int]) -> str:
    """Render [23,24,25,38] as '23-25, 38' for the warning strings."""
    if not indices:
        return ""
    ordered = sorted(set(indices))
    spans: List[str] = []
    start = prev = ordered[0]
    for n in ordered[1:]:
        if n == prev + 1:
            prev = n
            continue
        spans.append(str(start) if start == prev else "%d-%d" % (start, prev))
        start = prev = n
    spans.append(str(start) if start == prev else "%d-%d" % (start, prev))
    return ", ".join(spans)


@dataclass
class DrawingCoverage:
    """One drawing/viewport inside a sheet."""

    region_id: str = ""
    title: str = ""            # "KING SUITE B - RCP PLAN" / "TYPICAL S.C.C.P. DETAIL"
    plan_kind: str = ""        # AR | RCP | FF | EM | FC | ""
    disposition: str = MEASURED
    reason: str = ""
    printed_scale_fpi: Optional[float] = None
    # None = not measured, NEVER 0.0. A drawing that produced no number and a
    # drawing that measured zero square feet are different facts.
    area_sf: Optional[float] = None
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "title": self.title,
            "plan_kind": self.plan_kind,
            "disposition": self.disposition,
            "reason": self.reason,
            "printed_scale_fpi": self.printed_scale_fpi,
            "area_sf": self.area_sf,
            "needs_review": self.needs_review,
        }


@dataclass
class SheetCoverage:
    """One PAGE OF THE SOURCE PDF — created for every page, before any routing.

    Not one row per *processed* sheet: the whole defect INV-08 documents is that
    18 of Moxy's 40 pages never became a processed sheet and therefore left no
    row anywhere. A row exists first; the disposition records what happened to it.
    """

    page_index: int
    sheet_name: str = ""
    sheet_type: str = ""               # the verdict the run actually routed on
    type_source: str = ""              # "title_block" | "full_page_text" | "default"
    # The verdict the classifier's two-source fallback WOULD give if full-page
    # text were consulted. Recorded, not acted on: measured over all four plan
    # sets, consulting page text costs Chelsea 26 -> 17 and Bob's 5 -> 4
    # deterministic-eligible pages while changing no skip count, so acting on it
    # here would trade one fixture for another. Classification repair is plan
    # 23-06's job, gated on the four-set check; this field is the evidence it
    # needs.
    sheet_type_full_text: str = ""
    classifier_keyword: str = ""       # the keyword that decided it (e.g. "COVER")
    classifier_context: str = ""       # ~+/-25 chars around the hit — auditable
    classifier_overruled: bool = False  # the skip veto fired (INV-08 §3.4)
    disposition: str = MEASURED
    reason: str = ""
    # {"plan_titles": 6, "printed_scales": 10, "viewports": 9, "schedules": 0}
    measurable_signal: Dict[str, int] = field(default_factory=dict)
    drawings: List[DrawingCoverage] = field(default_factory=list)
    items_emitted: int = 0
    cost_usd: float = 0.0
    # True when this sheet's remaining passes were skipped because the run
    # BudgetGuard refused a charge. Recorded separately from `disposition` so
    # the fact survives even where a stronger disposition (ERRORED, a skip)
    # outranks it.
    budget_truncated: bool = False

    @property
    def is_silent_loss(self) -> bool:
        """Not measured DESPITE carrying measurable signal — the Gap 8 alarm."""
        return (
            self.disposition in _NOT_MEASURED_DISPOSITIONS
            and sum(self.measurable_signal.values()) > 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_index": self.page_index,
            "sheet_name": self.sheet_name,
            "sheet_type": self.sheet_type,
            "type_source": self.type_source,
            "sheet_type_full_text": self.sheet_type_full_text,
            "classifier_keyword": self.classifier_keyword,
            "classifier_context": self.classifier_context,
            "classifier_overruled": self.classifier_overruled,
            "disposition": self.disposition,
            "reason": self.reason,
            "measurable_signal": dict(self.measurable_signal),
            "drawings": [d.to_dict() for d in self.drawings],
            "items_emitted": self.items_emitted,
            "cost_usd": self.cost_usd,
            "budget_truncated": self.budget_truncated,
            "is_silent_loss": self.is_silent_loss,
        }


@dataclass
class ItemCoverage:
    """One EXPECTED line item, whether or not it was found."""

    name: str
    unit: str = ""
    status: str = ITEM_NOT_MEASURED
    # None = not measured. NEVER 0.0 as a stand-in: a building with no CMU and a
    # building whose CMU was never measured must stay distinguishable.
    quantity: Optional[float] = None
    basis: str = ""                    # ceiling_area | wall_area | count | ...
    source_sheets: List[str] = field(default_factory=list)
    reason: str = ""
    expected_from: str = ""            # "manifest" | "vocabulary" | "library" | "detected"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "status": self.status,
            "quantity": self.quantity,
            "basis": self.basis,
            "source_sheets": list(self.source_sheets),
            "reason": self.reason,
            "expected_from": self.expected_from,
        }


@dataclass
class CoverageLedger:
    """The run's complete account of what it did and did not measure."""

    pages_in_source: int = 0
    sheets: List[SheetCoverage] = field(default_factory=list)
    items: List[ItemCoverage] = field(default_factory=list)
    # Sheet ids the drawing set CITES but does not CONTAIN, as produced by
    # cross_references.missing_referenced_sheets: one dict per sheet, with the
    # pages that cite it. This is an INPUT gap (see NOT_IN_UPLOADED_SET) and it
    # closes by uploading the sheet, never by more detector work.
    missing_sheets: List[Dict[str, Any]] = field(default_factory=list)

    # -- registration -------------------------------------------------------
    def register_page(self, page_index: int, **kw: Any) -> SheetCoverage:
        """Create (or update) the row for *page_index* and return it.

        Idempotent by construction: a second call for the same index updates and
        returns the existing row, never appends a duplicate. run_pdf_analysis
        registers every page up front and later stages enrich the same row, so
        double registration must be a no-op rather than a silent double count.
        """
        row = self.sheet(page_index)
        if row is None:
            row = SheetCoverage(page_index=page_index)
            self.sheets.append(row)
        for key, value in kw.items():
            if not hasattr(row, key):
                raise TypeError(
                    "SheetCoverage has no field %r (register_page page_index=%r)"
                    % (key, page_index)
                )
            setattr(row, key, value)
        return row

    def sheet(self, page_index: int) -> Optional[SheetCoverage]:
        """The ledger row for *page_index*, or None when it was never registered."""
        for row in self.sheets:
            if row.page_index == page_index:
                return row
        return None

    def add_item(self, item: ItemCoverage) -> ItemCoverage:
        """Append an expected-item row (found or not) and return it."""
        self.items.append(item)
        return item

    # -- the invariant ------------------------------------------------------
    def assert_accounted(self) -> List[int]:
        """Source page indices with no ledger row — must ALWAYS be empty.

        Returns the missing indices rather than raising, so a caller can decide
        between a hard failure (tests) and a loud report warning (a live run).
        """
        present = {row.page_index for row in self.sheets}
        return [i for i in range(self.pages_in_source) if i not in present]

    # -- reporting ----------------------------------------------------------
    def silent_loss_pages(self) -> List[int]:
        """Pages not measured although they carry measurable signal."""
        return sorted(row.page_index for row in self.sheets if row.is_silent_loss)

    def _count_disposition(self, *dispositions: str) -> int:
        return sum(1 for row in self.sheets if row.disposition in dispositions)

    def _count_drawings(self, *dispositions: str) -> int:
        return sum(
            1
            for row in self.sheets
            for d in row.drawings
            if d.disposition in dispositions
        )

    def _count_items(self, status: str) -> int:
        return sum(1 for it in self.items if it.status == status)

    def summary(self) -> Dict[str, Any]:
        """The headline block that goes into ``report["coverage"]`` (INV-08 §3.2)."""
        # A budget-truncated sheet is deliberately NOT counted as measured: it
        # did not finish the work it started, and a run that stopped early must
        # never present as complete (C2).
        measured = self._count_disposition(MEASURED, MEASURED_PARTIAL)
        budget_truncated = sum(1 for row in self.sheets if row.budget_truncated)
        vision_only = self._count_disposition(VISION_ONLY)
        skipped = self._count_disposition(SKIPPED_CLASSIFIER, SKIPPED_NO_SCALE)
        errored = self._count_disposition(ERRORED)
        not_applicable = self._count_disposition(NOT_APPLICABLE)

        items_measured = self._count_items(ITEM_MEASURED)
        items_needs_review = self._count_items(ITEM_NEEDS_REVIEW)
        items_not_measured = self._count_items(ITEM_NOT_MEASURED)
        items_human_input = self._count_items(ITEM_HUMAN_INPUT)
        items_standard = self._count_items(ITEM_STANDARD)
        items_total = len(self.items)

        pages_pct = (
            round(100.0 * measured / self.pages_in_source, 1)
            if self.pages_in_source > 0
            else 0.0
        )
        items_pct = (
            round(100.0 * items_measured / items_total, 1) if items_total > 0 else 0.0
        )

        return {
            "pages_in_source": self.pages_in_source,
            "sheets_measured": measured,
            "sheets_budget_truncated": budget_truncated,
            "sheets_vision_only": vision_only,
            "sheets_skipped": skipped,
            "sheets_errored": errored,
            "sheets_not_applicable": not_applicable,
            "drawings_measured": self._count_drawings(MEASURED, MEASURED_PARTIAL),
            "drawings_excluded_off_scale": self._count_drawings(EXCLUDED_OFF_SCALE),
            "drawings_dropped_no_scale": self._count_drawings(SKIPPED_NO_SCALE),
            "drawings_not_in_uploaded_set": self._count_drawings(NOT_IN_UPLOADED_SET),
            "sheets_referenced_but_missing": [
                str(m.get("sheet_id", "")) for m in self.missing_sheets
            ],
            "silent_loss_pages": self.silent_loss_pages(),
            "items_measured": items_measured,
            "items_needs_review": items_needs_review,
            "items_not_measured": items_not_measured,
            "items_human_input": items_human_input,
            "items_standard": items_standard,
            "coverage_pct_pages": pages_pct,
            "coverage_pct_items": items_pct,
        }

    def warnings(self) -> List[str]:
        """Escalation strings for ``report["coverage_warnings"]`` and summary.txt."""
        out: List[str] = []

        unaccounted = self.assert_accounted()
        if unaccounted:
            out.append(
                "%d source page(s) have no ledger row (pages %s) — the run's own "
                "accounting is incomplete; treat every total as a lower bound"
                % (len(unaccounted), _compact_ranges(unaccounted))
            )

        silent = [row for row in self.sheets if row.is_silent_loss]
        if silent:
            drawings = sum(
                int(row.measurable_signal.get("plan_titles", 0)) for row in silent
            )
            keywords = sorted(
                {row.classifier_keyword for row in silent if row.classifier_keyword}
            )
            kw_note = (
                " (deciding keyword%s: %s)"
                % ("" if len(keywords) == 1 else "s", ", ".join(keywords))
                if keywords
                else ""
            )
            out.append(
                "%d page(s) carry %d measurable plan drawing(s) but were NOT "
                "measured (pages %s)%s — their items are blank, NOT zero"
                % (
                    len(silent),
                    drawings,
                    _compact_ranges([row.page_index for row in silent]),
                    kw_note,
                )
            )

        overruled = [row for row in self.sheets if row.classifier_overruled]
        if overruled:
            out.append(
                "%d page(s) were classified as carrying no take-off content but "
                "hold scaled plan geometry (pages %s) — the classifier verdict "
                "was overruled and they ran the deterministic path only (zero API)"
                % (len(overruled), _compact_ranges([r.page_index for r in overruled]))
            )

        truncated = [row for row in self.sheets if row.budget_truncated]
        if truncated:
            out.append(
                "%d page(s) stopped mid-measurement because the API budget was "
                "exhausted (pages %s) — their remaining passes NEVER RAN, so "
                "every quantity on them is a lower bound and every item absent "
                "from them is unknown, NOT zero; this run is INCOMPLETE and "
                "closes only by raising the budget cap and re-running"
                % (
                    len(truncated),
                    _compact_ranges([row.page_index for row in truncated]),
                )
            )

        errored = [row for row in self.sheets if row.disposition == ERRORED]
        if errored:
            out.append(
                "%d page(s) errored during analysis (pages %s) — their quantities "
                "are missing, not zero"
                % (len(errored), _compact_ranges([r.page_index for r in errored]))
            )

        dropped = self._count_drawings(SKIPPED_NO_SCALE)
        if dropped:
            out.append(
                "%d drawing(s) were dropped for having no printed scale of their "
                "own — measuring them at a borrowed scale would be a squared error"
                % dropped
            )

        if self.missing_sheets:
            named = ", ".join(
                "%s (cited %dx)" % (m.get("sheet_id"), m.get("citations", 0))
                for m in self.missing_sheets
            )
            out.append(
                "this drawing set CITES %d sheet(s) it does not CONTAIN — %s. "
                "Anything drawn only on those sheets cannot be measured from "
                "what was uploaded, and its quantity is UNKNOWN, not zero. This "
                "is a gap in the INPUT: it closes by uploading the missing "
                "sheets, never by more detector work"
                % (len(self.missing_sheets), named)
            )

        not_in_set = self._count_drawings(NOT_IN_UPLOADED_SET)
        if not_in_set:
            out.append(
                "%d expected drawing(s) are NOT IN THE UPLOADED SET — they are "
                "cross-referenced by the sheets provided but absent from the "
                "file" % not_in_set
            )

        not_measured = self._count_items(ITEM_NOT_MEASURED)
        if not_measured:
            out.append(
                "%d expected line item(s) have NO measurement path — do NOT read "
                "their blank quantity as zero" % not_measured
            )

        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pages_in_source": self.pages_in_source,
            "summary": self.summary(),
            "warnings": self.warnings(),
            "sheets": [row.to_dict() for row in self.sheets],
            "items": [it.to_dict() for it in self.items],
            "missing_sheets": [dict(m) for m in self.missing_sheets],
        }
