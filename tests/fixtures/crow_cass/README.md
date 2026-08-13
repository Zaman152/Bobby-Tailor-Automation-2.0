# Crow – Cass White Road — what this fixture can and cannot prove

`crow_cass_plans.pdf` is the file **a user actually uploads**: four pages.

| Page | Sheet | Title |
|------|-------|-------|
| 0 | A-101 | OVERALL FLOOR PLAN (1" = 40') |
| 1 | A-201 | EXTERIOR ELEVATIONS - OPTION 01 |
| 2 | A-401 | MISC. DETAILS |
| 3 | A-601 | DOOR SCHEDULES, FRAMES & DETAILS |

`crow_cass_golden.csv` is the estimator's answer key for the **whole project**,
taken off the **whole sheet set**. Those are not the same document, and the
difference is not an engine defect.

## The ceiling on this fixture is 9 of 10 items, not 10

**`Stairs, 10, EA` is not reachable from this upload and never will be.**

Page 0 defers three times — `SEE 1/A-111`, `SEE 1/A-112`, `SEE 1/A-113` — to
enlarged plans that **are not in the file**. Measured, the set cites five sheets
it does not contain: A-002, A-111, A-112, A-113, A-501.

A-401 **is** present (page 2) and draws a `STAIR PLAN`, a `STAIR SECTION` and a
`STAIR RAIL`. So the set shows what a stair looks like. It never says how many
are installed — that is what the enlarged plans would say. The only other stair
reference on the set is `E2  STAIR AND GUARDRAIL, TYP. SEE 6/A-401, 8/A-401,
10/A-401` on page 1, and its `E` tags appear **only in the legend**, never as
placed callouts; `TYP.` is an explicit statement that the drawing is not
enumerating instances.

A geometric tread search over the plan region finds **zero** tread-like runs
(one, in an elevation). There is no population of 10 anything.

**No detector — deterministic, ML or vision — can count objects that are not in
the file.** Any number this fixture produces for Stairs is a fabrication. The
correct behaviour is the `not_in_uploaded_set` coverage flag, quoting the sheet
ids, which is what `tests/test_missing_sheets.py` pins. Do not "fix" Stairs.
If you want 10 of 10 on Crow, upload the full sheet set.

## Columns is 120 measured, 132 golden, and the gap stays open

Page 0 draws **120** column markers, one per cell of a 20 x 6 sub-grid of the
printed A..H / 1..22 gridlines, at 100% occupancy. `tests/test_grid_lattice.py`
asserts 120 and asserts that the engine publishes **no** completed number,
because the drawing does not determine one: both grid axes are missing exactly
their two end positions, so extending the numbers gives 132, the letters 160,
and both 176. The take-off PDF carries no per-column markup either — its only
page-0 annotation is a 21-point footprint polygon — so 132 was entered as grid
arithmetic, not read off a drawing.

Never adjust a detector until a count matches this CSV. That is the documented
coincidence trap and it has cost this project days, twice.
