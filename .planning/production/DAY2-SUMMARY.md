# DAY 2 — Make the report screen tell the truth

**Date:** 2026-08-14 · **Branch:** `accuracy/flag-dont-guess-coincidental-detections`
**Scope:** PRODUCTION-PLAN.md §2 Day 2 (items 2.1–2.6), against INV-A §4 and §3.
**Cost:** $0.00 — no paid API, no golden marker, no `ANTHROPIC_API_KEY` read.

---

## 1. Verdict

All six Day-2 items are done. The screen now reproduces the run's own ledger
instead of contradicting it, and the plans-only contract is stated on the
upload form rather than only in the docs.

Measured on the real saved Crow run
(`.planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_194607/`), before
and after, by driving the shipped classification rules over that run's own
`takeoff.json`:

| | before | after | the run's ledger says |
|---|---|---|---|
| the 31 rows with no measurement path | "Needs review", cell **`enter value`** | "Not measured", cell **`no measurement path`** | `items_not_measured: 31` |
| lines presented as awaiting a human | **42** | **11** | `items_needs_review: 11` |
| headline figure | **"9 / 51 line items verified" (18%)** | **"15.7% of the expected line items were measured"** | `coverage_pct_items: 15.7` |
| bulk control | "Confirm 11 remaining estimates **→ 100%**" | "Confirm 11 flagged estimates at their current value" | — |
| `coverage.json` | written, listed nowhere | Downloads rail + report card export menu | — |
| `unnamed_geometry` | 34 entries, rendered nowhere | a panel | — |
| `quantity_route` | in the CSV only | a per-row column + a REPRODUCIBILITY panel | — |

Five commits, plus this file. Verified in a real browser against the real run,
not only in tests — screenshots described in §5.

---

## 2. One claim in the brief was wrong, and the correction matters

**The brief says: "One click currently converts a 15.7%-coverage run into a
'100% verified' takeoff." It does not, and never could.**

Driven over the saved Crow run with the pre-fix rules, one click of
`Confirm 11 remaining estimates → 100%` moves the screen from **18% to 39%**.
The server's `accept_all_estimates` only targets rows that already carry a
number (`verify.py:752-755`), and all 31 NOT MEASURED rows carry `None`, so
they are never in `targets` and never confirmed.

So the defect is **not** "a button that fakes completion". It is:

1. a button whose label promises a destination it cannot reach, and
2. a headline percentage that was never a coverage figure to begin with —
   verified-rows over published-rows, which is a different quantity from
   measured-items over expected-items and happens to flatter the run (18 vs
   15.7).

Both are fixed, and the fix is the same one the brief asked for. But the
difference is worth writing down, because "the app lies about being finished"
and "the app measures the wrong thing and labels it optimistically" lead to
different fixes, and only the second one is true here. The 100% claim IS
reachable — by an estimator typing a value into each of the 31 blanks — which
is why the wording now says what a confirmed line is (HUMAN INPUT) rather than
calling the result verified.

**The bulk control was kept, scoped and renamed.** Confirming 11 flagged
estimates one at a time is real work and removing the control would have cost
the operator something for no honesty gain: it never touched the 31. It now
says what it accepts, and a dialog names what it leaves alone.

---

## 3. What changed

### 2.1 — NOT MEASURED is a third state · `8e51623`, `6b4a8cb`

`rowStatus()` read `source` / `needs_review` / `quantity` and nothing else, so
the pipeline's four-value vocabulary collapsed into two on screen. All 31 Crow
rows the run had explicitly recorded as having **no measurement path** rendered
as `! Needs review` with the cell text `enter value` — indistinguishable from a
row the estimator simply had not got to.

- New module **`src/bobbytailor/web/static/js/report-provenance.js`** — pure, no
  DOM, no fetch, no imports. `rowStatus`, `rowNeedsVerification`, `rowQtyNum`,
  `coverageFacts`, `routeLabel`, `reproducibilityRows`.
- `NOT MEASURED` → its own badge class (`ws-badge-notmeasured`, slate, not
  amber), its own row hatching, and the cell text `no measurement path`.
  `NOT APPLICABLE` gets `none in this set`. Neither is counted among the lines
  awaiting a human.
- `STANDARD ITEM` (Mobilization) gets its own badge too. It used to render as
  a green ✓ "Confirmed", which claimed somebody had vouched for a number the
  app injects by convention.
- **A row with no `provenance` key keeps the pre-28 classification, unchanged.**
  Same empty contract `reporter._coverage_lines` and `_reproducibility_lines`
  keep: *"the app has no measurement path for this"* is a claim only a run that
  recorded one is entitled to make, and a pre-23 blank has not earned it.

**Why a separate module.** These rules decide what a bidder believes about a
blank. Reached only through a 1,400-line DOM module that imports from a CDN,
they cannot be executed by a test. As a standalone ES module they run under
node against the real saved run — which is how both the before and the after
numbers in §1 were obtained.

### 2.2 — the banner reports coverage · `6b4a8cb`

`ws-banner` / `ws-progress-*` / `ws-done` are gone, markup and CSS both, so
nothing re-adopts the look.

The headline is `coverage_pct_items`, fetched from
`/api/reports/<run>/preview/coverage.json` and used **verbatim**, with
`takeoff.json`'s identical `coverage` block as the fallback for a run that
failed to write the file. Beside it, the ledger's own counts as chips
(8 measured · 11 need review · 31 not measured · 1 standard), the
warnings list from `coverage_warnings` in a `<details>`, and an explicit
paragraph:

> **31 line items have no measurement path.** Do not read those blanks as zero,
> and no button on this screen can turn one into a measured quantity. You can
> type your own estimate into any of them — it will publish as HUMAN INPUT.

A run with no ledger gets its counts derived from the rows and **no
percentage**: a ratio computed from the rows on screen is a different quantity
wearing `coverage_pct_items`' name, and inventing one is the defect this item
exists to fix.

### 2.3 — `coverage.json` is a listed artifact · `069175b`, `3c447fa`

It has been written by every run since phase 23, was in neither report
endpoint's file list, and was therefore reachable from no button on the page.

The two lists were two hand-maintained copies of the same tuple, which is
exactly how it was missed — adding an artifact required editing both. One
`RUN_ARTIFACTS` now, with a test asserting a second hardcoded list has not
reappeared. Surfaced in the workspace Downloads rail and in the report card's
Export menu.

### 2.4 / 2.5 — unnamed geometry and quantity route · `6b4a8cb`

- **Unidentified geometry panel** — 34 entries on the Crow run: id, kind,
  quantity, unit, sheet, and the reason it has no name (`no name source`,
  `label is drafting noise`). The copy states the fence the reporter states:
  this is an absence of a NAME, never of an object.
- **Route column** — rendered only when at least one row carries a
  `quantity_route`, so a pre-28-06 report renders byte-identically. An
  unrecognised route is presented as **not** reproducible, the same safe floor
  `aggregator._less_reproducible_route` applies.
- **REPRODUCIBILITY panel** — mirrors `summary.txt`'s section on screen,
  including both of its fences: a listed number is not thereby wrong, and this
  cannot see whether a row appears *at all* in a repeat run.

### 2.6 — the plans-only upload guard · `3c447fa`

`POST /api/pdf/upload` accepted `Crow - Cass White Road-Take offs.pdf` with a
bare 200 (INV-A §3). On a take-off PDF this app emits a confident report over
somebody else's quantities.

- `looks_like_completed_takeoff()` in `runs.py` matches `take[ _-]?offs?\b`,
  case-insensitively. It **warns, never refuses**: "Take-off Plaza - Plans.pdf"
  is a legitimate upload and no filename rule can know that. `intake form.pdf`
  and `overtaken.pdf` are pinned as non-matches.
- The browser holds **Analyze** until the operator ticks *"I confirm this file
  is a set of plans, not a completed take-off."* `runPDF` re-checks
  independently of the button's `disabled` attribute, because that attribute is
  only as good as the last event that set it and this run spends money.
- **The warning travels onto the RUN, not only the upload screen.** A dialog
  leaves no record; the job log does. Both PDF entry points open their log
  through the same guard — `/api/run/pdf` uploads and starts in one step and
  never sees the upload screen at all, which the old plan item would have
  missed.
- The upload form now states the contract unprompted: *"Upload the PLANS. Bobby
  Tailor measures drawings — it never reads a completed take-off, and cannot
  tell one apart from a drawing set once it starts."*

The structural guard is untouched: nothing scans the upload folder, only the
selected `upload_id` is opened, `run_pdf_analysis` still passes
`allow_discovery=False`. This is the sign on the door, not the lock.

---

## 4. The green badge — deliberately kept

INV-A calls the ✓ on `Exposed Structure` and `Sealed Concrete` "the UI paints
the worst errors green". That reads `ERR%` as an accuracy; `vision_only_benchmark.py:240`
computes it as an **error** percentage, so at 0.5% those are the engine's two
**best** numbers and a golden PASS.

Both rows keep the `ok` class, the green, and the ✓, and there is a test
(`test_the_engines_best_rows_keep_their_green_badge`) asserting they are not
demoted. **Only the word changed**, from `Confirmed` to `Measured` — "Confirmed"
claimed a human had signed off on a number no human had seen, which is the same
conflation the rest of this day removes. Anyone reading INV-A unread should
find that test before they find the badge.

---

## 5. Verified in a real browser

Tests are not the whole proof for a UI change, so the app was run against a
scratch `OUTPUT_DIR` holding a copy of the saved Crow run plus one synthetic
run carrying `quantity_route` values (the Crow run predates 28-06 and has
none), and driven through a real login:

- **Crow, Takeoff Summary** — "15.7% of the expected line items were measured /
  From this run's own coverage ledger (coverage.json), not from the rows on
  screen", chips `8 measured · 11 need review · 31 not measured · 1 standard`,
  the blanks paragraph, `4 coverage warnings from this run`, and `Canopy`
  rendering as `∅ NOT MEASURED` / `no measurement path` on a hatched row.
  `Coverage JSON` present in the Downloads rail.
- **Crow, panels** — `34 measured shapes the app could not name`, expanding to
  the full table; no REPRODUCIBILITY panel, correctly, because no row on that
  run carries a route.
- **Synthetic routed run** — the Route column renders `printed schedule`,
  `measured off drawing` and `model read the sheet` (the last in amber), and
  the panel reads `1 published number a repeat run may answer differently`.
- **Upload guard** — a take-off-named file shows the red warning and leaves
  Analyze disabled; ticking the box enables it; a plans-named file shows no
  warning. Driven through the real `/api/pdf/upload`.

Two contrast defects were found **only** this way and fixed: the new slate
badges and chips were dark-on-dark (this app ships a single dark theme), and
`.data-table td` out-specified the bare `.ws-route` colour rules so the
"model read the sheet" warning colour never applied. Neither was visible to any
test.

The four scratch uploads the drive created in `uploads/` were deleted;
`git status --porcelain .planning/paid-run-evidence/` is `0`.

---

## 6. Tests

**`tests/test_report_honesty.py` — 40 tests.** The classification rules are
exercised by running the shipped `report-provenance.js` under node
(`tests/js/report_provenance_harness.mjs`) against the real saved run's rows,
not by matching source text: what a reader ends up believing about a blank is a
behaviour, and a string match cannot tell an honest blank from a dishonest one.

**Every assertion was checked against the pre-fix code before it was written.**
The HEAD rules were re-implemented in a scratch module and run through the same
harness over the same run, producing the "before" column in §1 — 31 rows
labelled "Needs review" with `enter value`, 42 lines presented as awaiting a
human, an 18% derived headline. All 16 source-level pins were separately
confirmed to fail against the HEAD copies of the five files they cover.

Two guards worth naming:

- the browser's copies of the item statuses and the quantity routes are
  asserted against `pipeline/coverage.py` and `pipeline/aggregator.py`, so the
  vocabulary cannot drift into a third definition;
- a report with **no** provenance must classify exactly as it always did, which
  is what stops a pre-23 blank being retroactively told apart from a measured
  one.

### Results observed

| Run | Result |
|---|---|
| `tests/test_report_honesty.py` | **40 passed** |
| `test_report_honesty` + `test_deployment_contract` + `test_blueprint_parity` + `test_object_manifest_wiring` + `test_object_manifest` + `test_reporter_accuracy` + `test_scale_module` | **231 passed** |
| **Full offline suite** (`python3 -m pytest -q`) | see §6.1 |

### 6.1 Full suite

```
$ python3 -m pytest -q
2478 passed, 1 skipped, 2 deselected, 5 warnings in 3994.87s (1:06:34)
$ echo $?
0
```

Python 3.9, no `-m golden`, no `ANTHROPIC_API_KEY` read, no network. Zero
failures and zero errors in the output. The two deselected are the paid golden
markers, which is the correct state for an offline run; the 5 warnings are the
pre-existing SWIG `DeprecationWarning`s from a C-extension import.

Day 1 observed **2438 passed**; this day adds 40 and the count is **2478**, so
nothing was lost and nothing was silently skipped. The four mandated gates —
`test_phase23_acceptance.py`, `test_phase24_acceptance.py`,
`test_four_set_coverage.py` and the 24-09 determinism harness
(`test_determinism_harness.py`) — are inside this run and green.

`git status --porcelain .planning/paid-run-evidence/` → `0`.

---

## 7. gitnexus

`gitnexus_impact` on the two route handlers this day edits — `upload_pdf`,
`list_reports` — returns **LOW / 0 direct callers** each: they are HTTP
entrypoints with no in-graph callers.

`gitnexus_detect_changes` against `e5bf234` reports **risk_level: critical**,
88 changed symbols, 33 affected. **That number is inflated and should not be
read as a warning about this change.** Two reasons, both mechanical:

1. The index is stale (last indexed `5fab264`), so both JS files are re-parsed
   whole and every top-level `const` in them — `idx`, `key`, `qty`, `base`,
   `img` — is reported as "touched" whether or not it was.
2. Every affected process is a browser-side report or upload flow, which is
   precisely what this day changes by design: `OpenReportWorkspace → RowStatus`,
   `BindWorksheetEvents → RowQtyNum`, `RunPDF → …`. **Nothing in the pipeline,
   the measurement path, or the aggregator is touched.**

Re-run `npx gitnexus analyze` before trusting the next `detect_changes` on this
tree.

---

## 8. Deliberately NOT done

- **Nothing was changed server-side about `accept_all_estimates` or
  `_summary_counts`.** `verify.py`'s `verified_count` / `pct` are computed the
  same flawed way the old screen computed them, but no UI reads them (the
  worksheet recomputes from the rows it holds) and changing a response shape
  the browser ignores is churn. **Worth a follow-up:** if anything ever starts
  reading `_summary_counts`, it will read the 18%-shaped number, not the
  ledger's.
- **`.ws-badge-verified` / `-measured` / `-auto` / `-ok` colours are unchanged**,
  including their dark-text-on-translucent-fill contrast, which is not great on
  this dark theme. Restyling the existing badges is a separate decision and
  would have touched the two rows §4 says not to touch.
- **The `Stairs 1 EA` row on the saved Crow run still renders as MEASURED
  green.** That is what the *saved artifact* records; 28-03 stopped the
  confident `1.00` in the engine, and no UI change can retro-fix an artifact
  written before it. The next paid run is what shows this fixed.
- **No paid run.** Day 3 is the acceptance test for this work on the operator's
  actual path.

## 9. For whoever picks up Day 3

1. **The `coverage_pct_items` on screen is now the number the customer sees
   first.** If the Day-3 Crow run produces a coverage figure materially
   different from 15.7%, that is a real signal about the post-28 engine and not
   a UI artifact — the screen reads the ledger verbatim.
2. **The Day-3 run is the first one that will render the Route column and the
   REPRODUCIBILITY panel with real data.** The saved Crow run predates 28-06,
   so both were verified against a synthetic run. Look at them on the real one.
3. **Uploading an invalid PDF reports `Error: Internal server error`.** Found
   while driving the upload guard: `get_pdf_metadata` raises and the browser
   shows a 500. Not a Day-2 item and not fixed, but a real first-session
   papercut — a corrupt or password-protected PDF is a normal thing for an
   estimator to have.
4. `.env.example` is still short two entries (DAY1-SUMMARY §6) — unchanged, the
   sandbox still denies it.
