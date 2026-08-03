# INV-08 — Silent Zeros: the Coverage Ledger

**Gap 8 implementation map.** Read-only investigation, zero API calls. Every behavioural claim
below is pasted probe output from the real PDFs in `uploads/`; every code claim carries `file:line`.

---

## TL;DR

1. **The defect is live and larger than the ground-truth doc records.** §12 says the classifier fix
   took Moxy's skipped sheets from **28 → 2**. On today's HEAD, running the pipeline's own
   classification path against the real 40-page Moxy PDF, **18 of 40 pages are still skipped
   entirely** — including 16 consecutive guestroom prototype sheets (pages 23–38). The killer
   keyword is no longer `"WALL COVERING"`; it is **`"COVER PLATE"`** in an electrical keynote that
   bleeds into the title-block crop. Whole-word matching did not fix the class of bug, it only
   changed which substring wins.

2. **Those 18 pages are not empty — they are the highest-value sheets in the set.** Replaying
   `_measure_room_fills` verbatim on four of the skipped pages yields **4,500 SF of measured
   enclosed regions**, and the numbers are literally §14's accuracy table: page 27 `KING SUITE B -
   RCP` = **341.7 SF** (§14's ID-411 row), page 31 `QQ C - RCP` = **284.3 SF** (§14's ID-415 row),
   page 23 `KING A - RCP` = **229.4 SF** (§14's ID-407 row). **§14's 7.0% Gyp-Ceiling result was
   produced by a probe calling the engine directly; a real run cannot reach those sheets at all.**

3. **Nothing anywhere says so.** `run_project` does `continue` on the skip sentinel
   (`takeoff_pipeline.py:2841-2846`), so a skipped page never enters `all_extracted`;
   `reporter.py:115` then sets `sheets_processed = len(all_extracted)`. A 40-page Moxy run renders
   `Sheets analyzed: 22` in `summary.txt` (`reporter.py:821`) and "22 sheets" in the web UI
   (`web/static/app.js:930`). The other 18 pages leave **no row, no flag, no count** in any
   artifact.

4. **The honest bookkeeping already exists — on the wrong path.** The StackCT scraper builds
   `sheets_skipped` and attaches `report["partial"] / sheets_failed / sheets_skipped /
   sheets_succeeded` (`scraper.py:606, 858-865, 1041-1045`). The **PDF-upload path — the one every
   plans-only ground-truth run uses** — calls `generate_report` with none of it
   (`pdf_analyzer.py:398-403`). Fix the asymmetry by moving the ledger into `generate_report`'s
   contract, not by duplicating scraper code.

5. **`quantity: 0.0` is emitted for items that were never measured.**
   `aggregator.py:426-435` formats a `manifest_missing` row as `quantity_fmt: "—"` but ships the
   numeric field as the defaultdict's `0.0`. Every numeric consumer — `takeoff.json`,
   `export_takeoff_excel.py:40 float(qty or 0)`, scoring — reads a blank as a zero. **`quantity`
   must become `Optional[float]` with `None` for "not measured".**

6. **Nine silent-drop paths** are enumerated in §2 with file:line. Four of them
   (`fusion.py:1540`, `:1554`, `:1559`, `room_fill.py:140`) mean a *successfully measured* room fill
   can be computed and then thrown away with no trace — including the one at `fusion.py:1559-1560`,
   which directly violates the contract `select_fill_for_basis`'s own docstring states
   (`room_fill.py:135-138`: *"the caller must flag, never substitute"* — the caller `continue`s).

7. **Deliverable:** `src/bobbytailor/pipeline/coverage.py` — a `CoverageLedger` with one
   `SheetCoverage` row per **page of the source PDF** (not per processed sheet), one
   `DrawingCoverage` row per viewport/drawing, and one `ItemCoverage` row per expected line item,
   plus a **skip veto** (evidence outranks a keyword) and four new report fields. The
   `MEASURED / HUMAN INPUT / NEEDS REVIEW / NOT MEASURED` vocabulary from
   `scripts/export_takeoff_excel.py:38-47` becomes the ledger's `ItemStatus` enum and **moves into
   `src`** — see §5.

**One-line acceptance:** `len(report["coverage_ledger"]) == report["coverage"]["pages_in_source"] ==
fitz.open(pdf).page_count`, for every PDF, always. If a page is not in the ledger, the run is a bug.

---

## 1. Evidence (all free, all reproducible)

### 1.1 Per-page coverage audit — reproduces the pipeline's own decisions

Probe written for this investigation (recommend promoting to `scripts/coverage_probe.py`, §6.1). It
replicates exactly four pipeline decisions: `pdf_analyzer.py:319` (`classify_sheet_type_from_text`
with **title block only**), `takeoff_pipeline.py:1220` (`plan_passes` → `[]` ⇒ skip),
`takeoff_pipeline.py:1239` (`_DETERMINISTIC_SHEET_TYPES` membership), and
`takeoff_pipeline.py:1804-1806` (`plan_titles` + `extract_printed_scales`, the room-fill gate).

**Moxy — `uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf`:**

```
pg   type(tb-only)  type(+fulltext) passes   det?     titles scales note
0    title_sheet    title_sheet    0        NO       0      0      SKIPPED ENTIRELY (no row anywhere in the report)
1    title_sheet    title_sheet    0        NO       11     0      SKIPPED ENTIRELY (no row anywhere in the report)
2    floor_plan     schedule       4        yes      0      1      det-eligible but 0 room-fill titles
...
9    floor_plan     floor_plan     4        yes      2      2
...
23   title_sheet    title_sheet    0        NO       6      10     SKIPPED ENTIRELY (no row anywhere in the report)
24   title_sheet    title_sheet    0        NO       6      10     SKIPPED ENTIRELY (no row anywhere in the report)
25   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
26   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
27   title_sheet    title_sheet    0        NO       5      13     SKIPPED ENTIRELY (no row anywhere in the report)
28   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
29   title_sheet    title_sheet    0        NO       6      10     SKIPPED ENTIRELY (no row anywhere in the report)
30   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
31   title_sheet    title_sheet    0        NO       6      10     SKIPPED ENTIRELY (no row anywhere in the report)
32   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
33   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
34   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
35   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
36   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
37   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
38   title_sheet    title_sheet    0        NO       5      9      SKIPPED ENTIRELY (no row anywhere in the report)
39   floor_plan     floor_plan     4        yes      0      6      det-eligible but 0 room-fill titles
----------------------------------------------------------------------------------------------------
type histogram (title-block only, i.e. what the pipeline uses): {'title_sheet': 18, 'floor_plan': 13, 'elevation': 9}
pages skipped entirely      : 18  [0, 1, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38]
pages with no det. geometry : 9  [3, 4, 5, 15, 16, 17, 18, 19, 20]
pages that reach the report : 22 of 40
```

The `titles` column is the point: **pages 23–38 each carry 5–6 `"<NAME> - AR/RCP PLAN"` viewport
titles and 9–13 printed scale callouts** — the exact signal `_measure_room_fills` needs — and every
one is discarded before geometry runs.

**Crow — `uploads/Crow - Cass White Road-Plans.pdf`** (4 pages, 0 skipped, but note `titles=0` on
page 0, the sheet every passing number comes from):

```
pg   type(tb-only)  type(+fulltext) passes   det?     titles scales note
0    floor_plan     floor_plan     4        yes      0      5      det-eligible but 0 room-fill titles
1    elevation      elevation      2        NO       0      4      no deterministic geometry (vision-only path)
2    detail         detail         2        NO       0      13     no deterministic geometry (vision-only path)
3    detail         detail         2        NO       0      2      no deterministic geometry (vision-only path)
pages skipped entirely      : 0  []
pages that reach the report : 4 of 4
```

**Bob's — `uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf`:**

```
0    title_sheet    title_sheet    0        NO       0      0      SKIPPED ENTIRELY (no row anywhere in the report)
6    floor_plan     detail         4        yes      0      7      det-eligible but 0 room-fill titles
pages skipped entirely      : 1  [0]
pages that reach the report : 6 of 7
```

Note page 6: `type(tb-only)=floor_plan` but `type(+fulltext)=detail`. **`pdf_analyzer.py:319` passes
only `title_block_text`**, so `sheet_type_hint` is always a truthy string and
`takeoff_pipeline.py:1214-1216`'s `sheet_type or classify_sheet_type_from_text(title_block_text,
full_page_text)` never consults full-page text on the PDF path. The classifier's documented
two-source fallback is dead code in the plans-only run. The ledger must record **which text source
produced the verdict**.

### 1.2 Which keyword killed each page

```
0  [('COVER SHEET', 'EVATEARCHITECT.COM CS-00 COVER SHEET 25-13.01 *INDICATES CONS'), ('COVER', ...)]
1  [('COVER SHEET', '... LC-00 LIGHTING COVER SHEET ...'), ('SHEET INDEX', '... CS-01 SHEET INDEX ...')]
23 [('COVER', 'ABEL ON THE LIGHT SWITCH COVER PLATE INDICATING "MASTER')]
24 [('COVER', 'ABEL ON THE LIGHT SWITCH COVER PLATE INDICATING "MASTER')]
...  (identical for 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38)
```

`_KW_TITLE_BLOCK_ONLY = frozenset(["INDEX", "COVER"])` (`sheet_pass_matrix.py:153`) is trusted
inside the title block. `get_title_block_text` crops the bottom-right ~15%, which on these sheets
catches an electrical keynote block containing **"PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE"**.
`_hit` (`sheet_pass_matrix.py:178-188`) matches `COVER` as a whole word → `title_sheet`
(`sheet_pass_matrix.py:219`) → `plan_passes` returns `[]` (`sheet_pass_matrix.py:51`) →
`run_sheet` returns the skip sentinel (`takeoff_pipeline.py:1220-1228`).

Pages 0 and 1 are genuine cover/index sheets. **Pages 23–38 are 16 guestroom prototypes.**

### 1.3 What was thrown away — `_measure_room_fills` replayed on the skipped pages

Replaying `takeoff_pipeline.py:1798-1848` verbatim (same clip constants, same callout anchoring,
same `flag_implausible_unit`) on four of the skipped pages:

```
--- page 23 : 6 plan titles
    KING A                 AR        193.2 SF  @ 4.00 ft/in  regions=[173.5, 11.5, 8.3]
    KING A                 FF        198.3 SF  @ 4.00 ft/in  regions=[112.3, 24.0, 19.2, 14.5]
    KING A                 FF        185.1 SF  @ 4.00 ft/in  regions=[113.6, 24.0, 14.7, 13.4]
    KING A                 FC     no printed scale under title -> DROPPED
    KING A                 EM        166.7 SF  @ 4.00 ft/in  regions=[166.7]
    KING A                 RCP       229.4 SF  @ 4.00 ft/in  regions=[121.8, 34.2, 19.9, 13.4]
--- page 27 : 5 plan titles
    KING SUITE B           AR        369.9 SF  @ 4.00 ft/in  regions=[249.4, 34.4, 26.2, 25.1]
    KING SUITE B           RCP       341.7 SF  @ 4.00 ft/in  regions=[216.8, 37.7, 33.4, 24.7]
    KING SUITE B           FC        190.9 SF  @ 4.00 ft/in  regions=[29.0, 28.5, 26.5, 19.3]
    KING SUITE B           EM        302.5 SF  @ 4.00 ft/in  regions=[292.1, 10.4]
--- page 31 : 6 plan titles
    QQ C                   AR        260.4 SF  @ 4.00 ft/in  regions=[228.2, 16.8, 15.4]
    QQ C                   RCP       284.3 SF  @ 4.00 ft/in  regions=[170.9, 40.2, 34.5, 15.3]
--- page 38 : 5 plan titles
    ACC BUNK               RCP       458.5 SF  @ 4.00 ft/in  regions=[290.4, 64.2, 63.2, 29.5]

TOTAL measurable SF on pages the pipeline SKIPPED: 4500.0
```

Cross-check against §14's blind result table: **ID-411 = 341.7** (page 27 RCP), **ID-415 = 284.3**
(page 31 RCP), **ID-407 = 229.4** (page 23 RCP). Identical. §14's engine numbers came from a direct
call; the pipeline never reaches them. `ACC BUNK - RCP 458.5` is also §14.2's open ~2× clip defect
— it would be flagged `needs_review`, which is correct behaviour, but it is *also* invisible today.

Note the fourth line of page 23: **`KING A FC — no printed scale under title -> DROPPED`**. That is
`takeoff_pipeline.py:1819 (if ps is None: continue)` — a per-drawing silent drop *inside* a sheet
that itself is silently skipped.

### 1.4 The §11.1 off-scale exclusion is log-only, not reported

```
sheet 'page0': excluding off-scale viewport R3 (TYPICAL S.C.C.P. JOINT DETAIL) — its printed scale 0.0093 ft/pt differs from the resolved page scale 0.5556 ft/pt; measuring it here would be 60x wrong
sheet 'page0': excluding off-scale viewport R4 (TYPICAL S.C.C.P./ SF DETAIL) — ... 60x wrong
sheet 'page0': excluding off-scale viewport R5 (TYPICAL S.C.C.P. CORNER DETAIL) — ... 60x wrong
sheet 'page0': excluding off-scale viewport R6 (TYP. S.C.C.P. MITERED CORNER) — ... 60x wrong
RETURN KEYS: ['_main_plan_region', '_scale_result', '_viewports_with_scales', 'footprint', 'fpp',
              'room_fills', 'rooms', 'schedules', 'sheet_name', 'symbol_groups', 'viewports',
              'wall_lf_by_class', 'walls']
symbol_groups= 36 walls= 281 rooms= 6 room_fills= 0 fpp= 0.5555555555555556
```

**Answer to the brief's question: NO, the exclusion is not reported.** It exists only as
`logger.info` at `takeoff_pipeline.py:1694-1700`. The returned bundle has no `excluded_viewports`
key, so nothing downstream — `fuse_sheet`, the merged dict, `reporter` — can ever surface it. The
exclusion is *correct* (§11.1) but a client cannot see that four S.C.C.P. details were deliberately
not measured. `room_fills=0` on Crow's main floor plan is the CONCERNS H1 silent zero, also
unreported.

### 1.5 The vector room engine returns zero on Moxy, silently

`scripts/room_probe.py "uploads/Moxy...-Plans.pdf" --fpi 8.0`:

```
Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf: 40 pages, assumed scale 8.0 ft/in (fpp=0.1111)
  page  7 [floor_plan]: ERROR AttributeError: 'NoneType' object has no attribute 'fpp'
  ... (29 pages)
== TOTAL rooms=0  ceiling-area(sum of room polygons)=0 SF  perimeter-sum=0 LF
```

(The probe's own `AttributeError` is `select_main_plan` returning `None` under the probe's
`[(v, None)]` call shape — a probe bug, not a pipeline bug. The load-bearing line is
`TOTAL rooms=0`.) `_deterministic_bundle` calls `extract_rooms` at `takeoff_pipeline.py:1708`
and stores `[]` with no flag. Note the probe itself silently `continue`s past every non-plan sheet
(`room_probe.py:76-77`) — the same blindness reproduced in the tooling.

---

## 2. Every path where a quantity becomes 0 / None / absent with no flag reaching the report

| # | Path | Location | What is lost | Reported today? |
|---|------|----------|--------------|-----------------|
| **S1** | Classifier → `title_sheet` → `plan_passes` returns `[]` → skip sentinel | `sheet_pass_matrix.py:219, 51`; `takeoff_pipeline.py:1220-1228` | The whole sheet: zero API, zero geometry | **No** |
| **S2** | `run_project` drops the sentinel: `if extracted.get("_skipped"): … continue` | `takeoff_pipeline.py:2841-2846` | The sheet never enters `all_extracted`, so `sheets_processed` (`reporter.py:115`) under-reports | **No** (PDF path). Scraper path records it: `scraper.py:858-865, 1041-1045` |
| **S3** | Sheet type not in `_DETERMINISTIC_SHEET_TYPES` → no geometry at all | `takeoff_pipeline.py:236, 1235-1243` | 9 Moxy elevation pages, 3 of Crow's 4 pages, Bob's page 4 — the sheets holding Bob's golden elevation SF | **No** |
| **S4** | Off-scale viewport masked out of walls/rooms/symbols | `takeoff_pipeline.py:1687-1700` | 4 viewports on Crow page 0 (§1.4). Correct, but invisible | **No** — `logger.info` only |
| **S5** | `_deterministic_bundle` gates all geometry on `fpp > 0` | `takeoff_pipeline.py:1704-1712` | `walls/rooms/symbols = []` when scale is unsolved (§11.4: legitimate on Bob's) | **No** |
| **S6** | `_measure_room_fills` — 4 bare `continue`s per drawing | `takeoff_pipeline.py:1819` (no printed scale), `:1823` (`fpp<=0`), `:1831` (empty clip), `:1835` (`measure_enclosed_area` → `None`) | Individual named drawings, e.g. `KING A - FC PLAN` (§1.3) | **No** |
| **S7** | `room_fill` failure swallowed | `takeoff_pipeline.py:1743-1744` (`logger.debug`) | The whole sheet's fills | **No** |
| **S8** | `_fuse_room_fills` — three silent early returns | `fusion.py:1540` (`if not fills: return`), `:1554` (`if not wanted: return`), `:1559-1560` (`if pick is None: continue`) | **Successfully measured areas, discarded.** `:1554` fires whenever no vocabulary/manifest entry carries an area basis — i.e. **plans-only, the mission mode** | **No** |
| **S9** | `select_fill_for_basis` excludes flagged fills | `room_fill.py:140` (`… and not f.needs_review`) | If *all* fills of a discipline are flagged, returns `None` → S8 `continue` → row vanishes. **Flag-don't-guess degrades into drop-and-be-silent.** Docstring `room_fill.py:135-138` explicitly says the caller must flag; `fusion.py:1560` does not | **No** |
| **S10** | `_route_deterministic` returns `None` → legacy vision path | `takeoff_pipeline.py:1483-1489, 1517-1519, 1526-1538` | Deterministic measurement silently downgraded to vision | **No** (CONCERNS `:144`) |
| **S11** | Per-sheet error dict counted as a processed sheet | `takeoff_pipeline.py:1553-1571`; consumed at `:2938-2947` (`if "error" not in extracted`) | Zero estimates. `sheet_log` (`reporter.py:144-170`) has no `error` field and reads `d.get("sheet_type")`, which the error dict does not set (it sets `_sheet_type`) → renders as `type=None` with 0 items | **No** |
| **S12** | Aggregator emits `0.0` for a never-measured manifest item | `aggregator.py:406-420` sets `manifest_missing`; `:435` ships `"quantity": qty` where `qty` is the defaultdict `0.0`; only `quantity_fmt` gets `"—"` (`:427-428`) | The numeric field says zero. `export_takeoff_excel.py:40` (`float(qty or 0) <= 0`) then infers NOT MEASURED from the value — a guess, not a record | Partially — `quantity_fmt` only |
| **S13** | No manifest ⇒ no completeness guarantee at all | `aggregator.py:406` (`if manifest:`) | In plans-only mode nothing enumerates expected items, so an unmeasured item has **no row of any kind**. §12b's "computed 0, converted 0 correctly, reported 0" and Bob's civil/elevation/lintel items are this case | **No** |
| **S14** | Aggregator suppresses legend-shadowed duplicates | `aggregator.py:362-371` (`continue`) | A measured row silently deleted when a legend covers the name | **No** |
| **S15** | Fusion drops "pure drafting noise" clusters | `fusion.py:1108-1114` (`logger.debug`, `continue`) | Correct behaviour (~60 junk Crow clusters), but a dropped real object is indistinguishable | **No** |

**What `reporter.generate_report` DOES surface today** (`reporter.py:111-180`): `sheets_processed`
(non-skipped only), `api_usage`, `budget`, `fusion_rejected` (`:100-109, 127`), `takeoff_summary`
with per-row `needs_review` / `confidence` / `review_reasons` / `auto_verified`,
`scale_calibration` (`:176-179`), `sheet_log` (`:144-170`), `linked_sheets_*`, and in `summary.txt`
a `SCALE CONFIDENCE` section (`:737-780`) and `PROVENANCE BREAKDOWN` (`:783-812`).

**What it does not surface: S1–S15, i.e. every form of absence.** The report is a complete account
of what *was* found and a total silence about what was not.

---

## 3. Design — the Coverage Ledger

### 3.1 The invariant

> Every page of the source PDF, every drawing on a measured page, and every expected line item is
> accounted for as exactly one of **measured / flagged / explicitly-not-applicable**. A quantity
> that was not measured is `None`, never `0.0`, and always carries a reason.

### 3.2 New module: `src/bobbytailor/pipeline/coverage.py` (Python 3.9)

```python
"""Per-run coverage ledger — every page, drawing and expected item accounted for.

A blank must never render as a zero. This module holds the record of what the
run did NOT measure, so the report can state it explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Sheet dispositions ──────────────────────────────────────────────────────
MEASURED            = "measured"             # deterministic geometry produced numbers
MEASURED_PARTIAL    = "measured_partial"     # some drawings measured, some dropped
VISION_ONLY         = "vision_only"          # reached vision passes, no geometry engine
SKIPPED_CLASSIFIER  = "skipped_classifier"   # title_sheet / empty pass list
SKIPPED_NO_SCALE    = "skipped_no_scale"     # fpp <= 0, nothing measurable
NOT_APPLICABLE      = "not_applicable"       # genuine cover/index — no take-off content
ERRORED             = "errored"              # exception; degraded per-sheet

# ── Item statuses (verbatim vocabulary from export_takeoff_excel.py:7-10) ───
ITEM_MEASURED     = "MEASURED"
ITEM_HUMAN_INPUT  = "HUMAN INPUT"
ITEM_NEEDS_REVIEW = "NEEDS REVIEW"
ITEM_NOT_MEASURED = "NOT MEASURED"
ITEM_NOT_APPLICABLE = "NOT APPLICABLE"


@dataclass
class DrawingCoverage:
    """One drawing/viewport inside a sheet."""
    region_id: str = ""
    title: str = ""                     # "KING SUITE B - RCP PLAN" / "TYPICAL S.C.C.P. DETAIL"
    plan_kind: str = ""                 # AR | RCP | FF | EM | FC | ""
    disposition: str = MEASURED
    reason: str = ""
    printed_scale_fpi: Optional[float] = None
    area_sf: Optional[float] = None     # None = not measured, NEVER 0.0
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]: ...


@dataclass
class SheetCoverage:
    """One PAGE OF THE SOURCE PDF — created for every page, before any routing."""
    page_index: int
    sheet_name: str = ""
    sheet_type: str = ""
    type_source: str = ""               # "title_block" | "full_page_text" | "default"
    classifier_keyword: str = ""        # the keyword that decided it (e.g. "COVER")
    classifier_context: str = ""        # ±25 chars around the hit — auditable
    classifier_overruled: bool = False  # skip veto fired (§3.4)
    disposition: str = MEASURED
    reason: str = ""
    measurable_signal: Dict[str, int] = field(default_factory=dict)
    # {"plan_titles": 6, "printed_scales": 10, "viewports": 9, "schedules": 0}
    drawings: List[DrawingCoverage] = field(default_factory=list)
    items_emitted: int = 0
    cost_usd: float = 0.0

    @property
    def is_silent_loss(self) -> bool:
        """Skipped/not-measured DESPITE carrying measurable signal — the Gap 8 alarm."""
        return (
            self.disposition in (SKIPPED_CLASSIFIER, SKIPPED_NO_SCALE, NOT_APPLICABLE)
            and sum(self.measurable_signal.values()) > 0
        )


@dataclass
class ItemCoverage:
    """One EXPECTED line item, whether or not it was found."""
    name: str
    unit: str = ""
    status: str = ITEM_NOT_MEASURED
    quantity: Optional[float] = None    # None = not measured. NEVER 0.0 as a stand-in.
    basis: str = ""                     # ceiling_area | wall_area | count | …
    source_sheets: List[str] = field(default_factory=list)
    reason: str = ""
    expected_from: str = ""             # "manifest" | "vocabulary" | "library" | "detected"


@dataclass
class CoverageLedger:
    pages_in_source: int = 0
    sheets: List[SheetCoverage] = field(default_factory=list)
    items: List[ItemCoverage] = field(default_factory=list)

    def register_page(self, page_index: int, **kw) -> SheetCoverage: ...
    def sheet(self, page_index: int) -> Optional[SheetCoverage]: ...
    def summary(self) -> Dict[str, Any]: ...
    def warnings(self) -> List[str]: ...
    def assert_accounted(self) -> List[str]:
        """Pages in source with no ledger row — must always be empty."""
    def to_dict(self) -> Dict[str, Any]: ...
```

`summary()` returns the block that goes into the report:

```python
{
  "pages_in_source": 40,
  "sheets_measured": 13, "sheets_vision_only": 9, "sheets_skipped": 18,
  "sheets_errored": 0, "sheets_not_applicable": 2,
  "drawings_measured": 41, "drawings_excluded_off_scale": 0,
  "drawings_dropped_no_scale": 3,
  "silent_loss_pages": [23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
  "items_measured": 3, "items_needs_review": 5,
  "items_not_measured": 16, "items_human_input": 1,
  "coverage_pct_pages": 55.0, "coverage_pct_items": 12.5,
}
```

`warnings()` produces the escalations, e.g.
`"16 pages classified title_sheet carry 84 measurable plan drawings — measurement was skipped, NOT zero (pages 23-38)"`.

### 3.3 New report fields (all additive — no existing key renamed, per 03-02/03-03)

| Field | Type | Content |
|---|---|---|
| `coverage` | dict | `CoverageLedger.summary()` — the headline numbers |
| `coverage_ledger` | list | One `SheetCoverage.to_dict()` **per page of the source PDF** |
| `item_coverage` | list | One `ItemCoverage` per expected item incl. the unfound ones |
| `coverage_warnings` | list[str] | `CoverageLedger.warnings()` |
| `pages_in_source` | int | `doc.page_count`. `sheets_processed` keeps its meaning |
| `_files["coverage_json"]` | str | `<run>/coverage.json` |

Per-row additions to `takeoff_summary` (`aggregator.py:433-448`): `provenance` (the four-value
vocabulary) and `measured` (bool). `quantity` becomes `Optional[float]`.

`summary.txt` gains a **COVERAGE** section between `API USAGE` and `SCALE CONFIDENCE`
(`reporter.py:846-848`):

```
──────────────────────────────────────────────────────────────────────
COVERAGE  (a blank is NOT a zero)
──────────────────────────────────────────────────────────────────────
Pages in source PDF:          40
  measured (geometry):        13
  vision-only (no geometry):   9
  skipped by classifier:      18   ← 16 of these carry measurable drawings
  not applicable (cover/idx):  2
  errored:                     0
Drawings dropped (no printed scale of their own):   3
Viewports excluded as off-scale (measuring them would be wrong):  0

!! 16 pages classified title_sheet carry 84 measurable plan drawings
   (pages 23-38, keyword "COVER" matched "COVER PLATE" in the title-block crop).
   These sheets were NOT MEASURED. Their items are blank, not zero.

Expected line items:          24
  MEASURED                     3
  NEEDS REVIEW                 5
  HUMAN INPUT                  1
  NOT MEASURED                15   ← do NOT read these as zero
```

`takeoff_summary.csv` (`reporter.py:690-708`): add a `provenance` column; write the **empty string**
for a `NOT MEASURED` quantity, not `0`. `score_report_dir._num` (`scripts/score_report_dir.py:24-33`)
already maps `""` / `"—"` to `None`, so scoring stays correct by construction.

### 3.4 The skip veto — evidence outranks a keyword

Recording the skip is necessary but insufficient: a ledger that faithfully reports "we threw away
the 16 sheets holding every guestroom quantity" is honest and still 4% accurate. The structural fix
is that **a keyword must not be able to veto measurable geometry**.

Rule, in `run_sheet` before returning the sentinel:

> If `plan_passes` is empty **and** the page carries ≥ 1 `"<NAME> - AR/RCP PLAN"` title with a
> printed scale directly beneath it, **or** ≥ 1 non-title-block viewport with a solved scale, then
> the `title_sheet` verdict is overruled: `resolved_type = "floor_plan"`,
> `classifier_overruled = True`, and the sheet runs the **deterministic path only** (zero API).

This is not tuning to a count — the trigger is the *presence of scaled plan geometry*, a
position/shape signal (rule 6). On Moxy it recovers pages 23–38 with zero API spend; on Crow it
changes nothing (page 0 already classifies `floor_plan`); on Bob's page 0 it changes nothing
(`titles=0, scales=0` — a real cover sheet, correctly `NOT_APPLICABLE`). The audit in §1.1 is
exactly the offline check for this.

---

## 4. Implementation map — function by function

Ordered. Each step is independently testable offline.

**1. `src/bobbytailor/pipeline/coverage.py` — NEW.** The dataclasses and constants of §3.2. Pure
data + formatting, no I/O, no PDF dependency. Python 3.9: `from __future__ import annotations`,
`typing.Optional/List/Dict`, no `X | Y`, no `list[str]` at runtime.

**2. `src/bobbytailor/pipeline/provenance.py` — NEW.** Move `scripts/export_takeoff_excel.py:38-47`
`_provenance` into src as `provenance_of_row(row) -> str`, corrected to read the ledger rather than
sniff the value:
```python
def provenance_of_row(row):
    if row.get("status"):              # ItemCoverage-backed rows
        return row["status"]
    q = row.get("quantity")
    if q is None:                      # None = never measured (S12 fix)
        return ITEM_NOT_MEASURED
    if row.get("needs_review"):
        return ITEM_NEEDS_REVIEW
    if str(row.get("source") or "").lower() in ("manifest", "human", "learned",
                                                "manifest_missing"):
        return ITEM_HUMAN_INPUT
    return ITEM_MEASURED
```
Then `export_takeoff_excel.py` imports it and deletes its local copy. **Yes, the logic should move
into src** — the script's classification is (a) inferred from the value rather than recorded, so a
genuine measured zero and a never-measured item are indistinguishable, and (b) unreachable for the
web UI, the JSON, the CSV and the API, which is where clients actually read the numbers. The script
keeps only the workbook formatting.

**3. `sheet_pass_matrix.classify_sheet_type_from_text` (`:191-263`) — return the reason.** Add
`classify_sheet_type_verbose(title_block_text, full_page_text="") -> Tuple[str, str, str, str]`
returning `(sheet_type, source, keyword, context)`. Keep the existing 1-arg function as a thin
wrapper (`return classify_sheet_type_verbose(...)[0]`) so all current callers and
`tests/test_sheet_pass_matrix.py` are untouched.

**4. `pdf_analyzer.run_pdf_analysis` (`:251`, page loop `:306-331`).**
   - Construct `ledger = CoverageLedger(pages_in_source=doc.page_count)` and
     `ledger.register_page(...)` for **every** page — including pages excluded by page selection
     (`disposition=NOT_APPLICABLE, reason="not selected for analysis"`).
   - `:319` — call `classify_sheet_type_verbose(title_block_text, doc[i].get_text())` and store all
     four values on the `SheetCoverage`. Passing full-page text as the second arg restores the
     classifier's documented fallback (§1.1, Bob's page 6).
   - Compute `measurable_signal` once per page from `plan_titles(page)`,
     `extract_printed_scales(page)`, `segment_viewports(page)` — all zero-API, ~0.2 s/page as
     measured in §1.1.
   - Pass `coverage=ledger` into `pipeline.run_project(...)` and then into `generate_report(...)`
     (`:398-403`). `run_project` has exactly one caller, so this is a safe signature change; keep
     it keyword-only with a `None` default so the scraper path is unaffected until step 9.

**5. `TakeoffPipeline.run_sheet` (`:1171-1228`).**
   - Accept `coverage: Optional[SheetCoverage] = None`.
   - Before the `if not passes:` return (`:1220`), apply the **skip veto** of §3.4. When it fires:
     set `coverage.classifier_overruled = True`, `resolved_type = "floor_plan"`, recompute
     `passes`, and continue into the deterministic branch.
   - When the veto does not fire, enrich the sentinel:
     `{"_skipped": True, "sheet_type", "sheet_name", "sheet_source", "_skip_reason",
       "_skip_keyword", "_skip_context", "_measurable_signal"}` and set
     `coverage.disposition = SKIPPED_CLASSIFIER` (or `NOT_APPLICABLE` when
     `measurable_signal` is all zeros).

**6. `TakeoffPipeline._deterministic_bundle` (`:1587-1762`).**
   - `:1687-1700` — accumulate the off-scale exclusions into a local
     `excluded: List[DrawingCoverage]` alongside the existing `geometry_mask.append` and
     `logger.info`, and add `"excluded_viewports": excluded` to the returned dict (`:1748-1762`).
   - `:1704-1712` — when `fpp <= 0`, record `SKIPPED_NO_SCALE` with the reason rather than silently
     leaving `walls/rooms/symbols` empty.
   - `:1743-1744` — the `except` around `_measure_room_fills` must record a `DrawingCoverage` with
     `disposition=ERRORED` instead of `logger.debug`.

**7. `TakeoffPipeline._measure_room_fills` (`:1773-1848`).** Change the return type to
`Tuple[List[RoomFillResult], List[DrawingCoverage]]` (or accept an out-list). Replace each of the
four bare `continue`s with an appended `DrawingCoverage`:
   - `:1819` → `reason="no printed scale beneath the title — measuring it at a borrowed scale would be a squared error"`
   - `:1823` → `reason="printed scale parsed to fpp <= 0"`
   - `:1831` → `reason="clip rectangle degenerate"`
   - `:1835` → `reason="no enclosed region survived the min/max region filter"`
   Also record `MAX_REGION_SF` rejections from `measure_enclosed_area` — CONCERNS H1 notes
   `room_fill.py:73` silently drops regions > 900 SF while the pipeline-side `_MAX_UNIT_SF` check
   flags. Add an out-parameter `dropped_regions: Optional[List[float]] = None` to
   `measure_enclosed_area` (`room_fill.py:180-240`) so the ledger can say *"3 regions of 1,240 /
   980 / 1,510 SF were rejected as larger than one unit"*. **Do not change the 900 SF constant**
   (§14.2 — fix the clip, not the threshold).

**8. `room_fill.select_fill_for_basis` (`:128-144`).** `:140`'s `and not f.needs_review` makes a
flagged fill vanish. Change to: prefer unflagged matches; if none, return the smallest flagged
match **with its flag intact** so the caller emits a `NEEDS REVIEW` row instead of nothing. This
keeps the docstring's promise (`:135-138`) instead of quietly breaking it.

**9. `fusion._fuse_room_fills` (`:1516-1597`).** The three silent exits become records on
`bundle["coverage_notes"]`:
   - `:1540` `if not fills:` → note `"no measurable plan drawing on this sheet"`, return.
   - `:1554` `if not wanted:` → note `"N room fills measured (…SF) but no vocabulary/manifest item
     has an area basis — the measurements were discarded"`. **This is the plans-only failure mode**:
     with no manifest, `vocab_map` frequently carries no `basis`, so every measured area is dropped.
   - `:1559-1560` `if pick is None:` → emit an `ItemCoverage(status=ITEM_NOT_MEASURED,
     quantity=None, reason="no <KIND> plan drawing measured for basis <basis>")` instead of
     `continue`.

**10. `TakeoffPipeline.run_project` (`:2652-2951`).**
   - `:2841-2846` — replace the bare `continue` with a ledger update, then `continue`. The sentinel
     stays out of `all_extracted` (preserving every downstream contract) but is now recorded.
   - `:2938-2947` — the `if "error" not in extracted` guard must set `disposition=ERRORED` with the
     message on the ledger row.
   - Copy `_geometry`/`excluded_viewports`/room-fill drops off each merged dict onto its
     `SheetCoverage` after `all_extracted.append(extracted)` (`:2864`).
   - Expose `self.coverage_ledger` so `pdf_analyzer` can hand it to `generate_report`.

**11. `aggregator.aggregate_takeoff` (`:235-449`).**
   - `:435` — emit `"quantity": None` when `is_unknown` (`manifest_missing`). This is the single
     highest-value one-line change in the map: it stops a never-measured item from serialising as
     `0.0`.
   - `:433-448` — add `"provenance": provenance_of_row(...)` and `"measured": bool`.
   - `:406` — generalise the completeness guarantee beyond `if manifest:`. Build the expected-item
     set from `manifest` ∪ `learned.expected_items` ∪ `library` names ∪ the project vocabulary, so
     **plans-only runs also get a NOT MEASURED row** for an expected item that never appeared
     (S13, §12b, Bob's civil/elevation/lintel items).
   - `:362-371` — the legend-shadow `continue` should append a `review_reasons` entry
     `"suppressed as a duplicate of legend item <X>"` on the surviving bucket.

**12. `reporter.generate_report` (`:21-253`).** Accept `coverage: Optional[CoverageLedger] = None`.
   - Add the four fields of §3.3 to the `report` dict (`:111-171`).
   - Add `"error": d.get("error")` and `"sheet_type": d.get("sheet_type") or d.get("_sheet_type")`
     to each `sheet_log` entry (`:144-170`) so S11 errored sheets stop rendering as `type=None`.
   - Write `<run>/coverage.json` next to `scale_calibration.json` (`:194-198` pattern) and register
     it in `_files` (`:242-251`).

**13. `reporter._write_summary` (`:814-987`) and `_write_takeoff_summary_csv` (`:690-708`).**
   Add `_coverage_lines(report)` (mirroring `_scale_confidence_lines` at `:737`, fully None-guarded
   so pre-23 reports render unchanged) and insert it at `:846-848`. In the CSV, add `provenance`
   and write `""` for a `None` quantity.

**14. `scripts/export_takeoff_excel.py`.** Import `provenance_of_row` from step 2; add a
`Coverage` worksheet rendering `report["coverage_ledger"]` one row per PDF page; extend the About
sheet with `Pages in source PDF` / `Pages measured` / `Pages skipped`. `NOT MEASURED` rows keep a
**blank** quantity cell.

**15. `scrape/scraper.py` (`:606, 741, 858-865, 1004-1045`).** Replace the ad-hoc
`sheets_skipped` / `sheets_failed` lists with the same `CoverageLedger`, so both entry points emit
one shape. Keep `report["sheets_skipped"]` as a derived alias for backward compatibility
(`web/blueprints/reports.py`, `web/jobs_runtime.py:143` read it).

---

## 5. Alignment with `scripts/export_takeoff_excel.py`, and whether it moves into src

**Align, and move the logic.** The workbook's four-value vocabulary
(`export_takeoff_excel.py:7-10, 132-135`) is exactly right and its About-sheet line — *"No
measurement path for this item yet. Do NOT read a blank as zero"* — is the thesis of this whole
investigation. Adopt it verbatim as `ItemCoverage.status`.

What must change is **where the classification is decided**. Today `_provenance`
(`export_takeoff_excel.py:38-47`) *infers* provenance from the value: `float(qty or 0) <= 0 → NOT
MEASURED`. Three consequences:

1. A genuinely measured zero (a building with no CMU) is indistinguishable from a never-attempted
   measurement.
2. An item that produced **no row at all** — Moxy's Gyp Ceiling, Bob's lintels, every plans-only
   unmeasured item (S13) — cannot be labelled `NOT MEASURED`, because there is nothing to label.
   The exporter can only classify rows that exist, and absence is precisely the defect.
3. Only Excel users see it. The JSON, `takeoff_summary.csv`, the web results view and the API all
   ship the bare number.

So: `ItemStatus` and `provenance_of_row` live in `src/bobbytailor/pipeline/` (steps 1–2), are
computed from the ledger's *record* of what happened, are written into `takeoff.json` /
`takeoff_summary.csv` / `summary.txt`, and the script becomes a formatter that reads
`row["provenance"]`. `scripts/export_takeoff_excel.py` keeps ownership of layout, colours and the
About sheet — that is genuinely presentation.

---

## 6. Offline verification (zero API, all free)

### 6.1 Promote the audit probe

Land §1.1's script as `scripts/coverage_probe.py` (`--pdf`, `--json`). It is the ledger's oracle: it
computes, without running the pipeline, what the ledger must contain.

```bash
python3 scripts/coverage_probe.py "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
python3 scripts/coverage_probe.py "uploads/Crow - Cass White Road-Plans.pdf"
python3 scripts/coverage_probe.py "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
python3 scripts/coverage_probe.py "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
```

**Acceptance (pre-fix values are the §1.1 output above):**
- Moxy `pages skipped entirely` : **18 → 2** (pages 0 and 1, the real cover and index).
- Moxy `silent_loss_pages` : **16 → 0** — no page is skipped while carrying plan titles + scales.
- Crow: unchanged (0 skipped) — proves the veto is not a blanket "measure everything".
- Bob's: `1 → 1` skipped (page 0, `titles=0 scales=0`) — a real cover sheet stays skipped and is
  classified `NOT_APPLICABLE`, not silently dropped.

### 6.2 Ledger completeness assertion (the invariant)

```bash
python3 - 'output/<run>/takeoff.json' 'uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf' <<'PY'
import fitz, json, sys
r = json.load(open(sys.argv[1]))
n = fitz.open(sys.argv[2]).page_count          # the report carries no source-PDF path today
led = r["coverage_ledger"]
assert r["coverage"]["pages_in_source"] == n, (r["coverage"]["pages_in_source"], n)
assert len(led) == n, (len(led), n)
assert {s["page_index"] for s in led} == set(range(n))
assert all(s["disposition"] for s in led)
print("ledger complete:", n, "pages,", r["coverage"]["silent_loss_pages"], "silent losses")
PY
```

(Optional and cheap: also add `report["source_pdf"]` in step 12 — `generate_report` has no record
of its own input today, which is itself a provenance gap.)

### 6.3 The no-silent-zero assertion

```bash
python3 - <<'PY'
import json
r = json.load(open('output/<run>/takeoff.json'))
bad = [x for x in r["takeoff_summary"]
       if x.get("quantity") == 0.0 and x.get("provenance") == "MEASURED"]
assert not bad, bad          # a measured zero must be a real measured zero
none_rows = [x for x in r["takeoff_summary"] if x.get("quantity") is None]
assert all(x["provenance"] in ("NOT MEASURED", "NEEDS REVIEW") for x in none_rows)
print("ok:", len(none_rows), "explicit NOT-MEASURED rows")
PY
```

### 6.4 Room-fill recovery on the previously-skipped sheets

Re-run the §1.3 replay against the ledger: for Moxy pages 23–38 the ledger must contain
`DrawingCoverage` rows whose `area_sf` match the probe's numbers (page 27 RCP `341.7`, page 31 RCP
`284.3`, page 23 RCP `229.4`), and a `dropped` row for `KING A - FC PLAN` with
`reason="no printed scale beneath the title…"`. **Validate by title and area against the drawing,
never against a golden total** (rule 6 / §14.3).

### 6.5 Off-scale exclusion now visible

```bash
python3 -c "
import sys,logging; sys.path[:0]=['.','src']
import fitz
from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline
p=TakeoffPipeline(analyzer=lambda *a,**k:{}); PDF='uploads/Crow - Cass White Road-Plans.pdf'
d=fitz.open(PDF); b=p._deterministic_bundle(d[0],d,PDF,0,'page0','floor_plan')
ex=b['excluded_viewports']; print(len(ex)); [print(e.region_id, e.title, e.reason) for e in ex]
assert len(ex)==4"
```
Pre-fix this raises `KeyError: 'excluded_viewports'` (see the `RETURN KEYS` dump in §1.4);
post-fix it prints the four S.C.C.P. details.

### 6.6 Suite

```bash
python3 -m pytest -q            # pytest.ini already sets -m "not golden" — zero paid calls
```
New tests to add (all synthetic, no PDF, matching the existing `generalization` marker style):
- `tests/test_coverage_ledger.py` — dataclass round-trip; `assert_accounted` catches a missing page;
  `is_silent_loss` true iff skipped **and** signal > 0.
- `tests/test_sheet_pass_matrix.py` — `classify_sheet_type_verbose` returns
  `("title_sheet", "title_block", "COVER", …)` for a keynote containing `"COVER PLATE"`, and the
  1-arg wrapper is byte-identical to today for every existing case.
- `tests/test_takeoff_pipeline.py` — skip veto: a stub page with one `"X - RCP PLAN"` title + a
  printed scale is **not** skipped and carries `classifier_overruled=True`; a stub page with
  neither **is** skipped with `disposition=SKIPPED_CLASSIFIER`.
- `tests/test_aggregator.py` — a `manifest_missing` bucket yields `quantity is None` (not `0.0`) and
  `provenance == "NOT MEASURED"`.
- `tests/test_fusion.py` — `_fuse_room_fills` with fills but no area-basis vocabulary appends a
  coverage note instead of returning silently.
- `tests/test_reporter_accuracy.py` — `generate_report(coverage=None)` renders exactly as today
  (backward compatibility), and with a ledger emits all four new fields plus the COVERAGE section.
- `tests/test_room_fill.py` — `select_fill_for_basis` returns a flagged fill (with the flag) when
  every candidate is flagged, instead of `None`.

---

## 7. Risks

1. **The skip veto increases scope, and could increase cost.** 16 recovered Moxy sheets on the
   legacy vision path would be real API spend. *Mitigation:* the veto routes to the
   **deterministic-only** path (`_route_deterministic`, zero API) and marks the sheet
   `MEASURED_PARTIAL` with `reason="classifier overruled; deterministic geometry only"`. Vision
   labelling for these sheets is a separate, budget-gated decision.

2. **`quantity: Optional[float]` is a type change on a public field.** Audited consumers:
   `scripts/score_report_dir.py:24-33` (`_num` already returns `None` for `""`/`"—"`) — safe;
   `scripts/export_takeoff_excel.py:40` (`float(qty or 0)`) — safe, and rewritten anyway;
   `reporter._write_takeoff_summary_csv:700` already prefers `quantity_fmt` — safe;
   `web/static/app.js` renders strings. **Any remaining consumer doing bare `float(row["quantity"])`
   must be found before landing** — `grep -rn 'quantity' src/bobbytailor/web/`.

3. **Ledger volume.** 40 pages × ~6 drawings ≈ 240 rows — negligible next to `raw_line_items`. But
   `coverage_ledger` goes in `takeoff.json`, which the web UI already loads whole; keep
   `DrawingCoverage` flat and drop raw bitmaps/region lists.

4. **A loud ledger is not accuracy.** Landing this makes Moxy report *"16 sheets not measured"*
   honestly and, without the veto, leaves the score at 4%. The veto is the part that moves accuracy;
   the ledger is the part that keeps it honest. Ship both, and do **not** let a green coverage
   number become the new target — coverage measures accounting, not correctness.

5. **The classifier is still keyword-based.** The veto is a backstop, not a fix. `"COVER PLATE"`
   today, some other whole-word collision tomorrow. The ledger's `classifier_keyword` /
   `classifier_context` fields make the next instance a two-second diagnosis instead of a
   multi-day one, but the durable fix (title-block *field* parsing rather than bag-of-words over a
   bottom-right crop) belongs to the classification gap, not this one.

6. **Do not tune `MAX_REGION_SF` / `_MAX_UNIT_SF` while wiring their drop-records.** §14.2 is
   explicit: `ACC BUNK - RCP 458.5 SF` (§1.3) is the ~2× clip defect. Recording it as
   `NEEDS REVIEW` is in scope; moving the threshold to make it pass is the §10 coincidence trap.

7. **`run_project`'s signature.** It has exactly one caller (`pdf_analyzer.py:371`), but
   `run_sheet` has four (`takeoff_pipeline.py:1056, 2827`; `scraper.py:503, 840, 1263`). Every new
   parameter must be keyword-only with a `None` default so the scraper path is untouched until
   step 15.
