# Phase 23 — deferred items

Out-of-scope discoveries logged during execution. NOT fixed in the plan that found them.

---

## DEF-23-01 — `SCALE: 1-1/2" = 1'-0"` parses as 1/2, not 1 1/2

**Found during:** 23-02 Task 1 (printed-scale parser hardening).
**Where:** `src/bobbytailor/deterministic/printed_scale.py` — `_ANCH_MIXED_RE` requires
whitespace between the whole part and the fraction, so a HYPHENATED mixed number falls through
to the plain-fraction rule.

**Evidence (real, Bob's A8.3 page 6, two callouts):**

```
'SCALE: 1-1/2" = 1'-0"'   parses 1/2 -> 0.5 paper inches -> 2.0 ft/in
architecturally it is    1.5 paper inches            -> 0.6667 ft/in
```

**Why it was NOT fixed in 23-02:**

1. It is a **different defect** from BUG-A (split stacked fraction) and BUG-B (unanchored scan),
   which are 23-02's entire scope. It is wrong *before* the change too, so it is not a regression.
2. Correcting it moves 2 extra Bob's rows, making the four-fixture sweep `changed=9 unchanged=381`
   and breaking the `changed=7 unchanged=383` pin that 23-02 exists to establish (INV-03 §4.1).
   Verified by running exactly that experiment as a negative control.
3. D-07 forbids widening a parser rule without the before/after diff being re-derived and agreed.

**Pinned meanwhile:** `test_hyphenated_mixed_number_keeps_its_pre_change_value` asserts the
current 2.0, with the reason in the docstring, so the behaviour is documented rather than latent.

**To fix properly:** allow `[\s-]+` in `_ANCH_MIXED_RE`, re-derive the four-fixture sweep, and
update both the pinned totals and `tests/fixtures/printed_scale_pre_sp2.json`'s `_expected`.
Both affected callouts are on Bob's A8.3 STANDARD DETAILS (a detail sheet), so nothing measured
today depends on them — which is why this is safe to defer, not safe to ignore.

---

## DEF-23-02 — the offline suite rewrites tracked fixture PDFs

**Found during:** 23-02 Task 1, staging the first commit.
**Where:** `tests/fixtures/synthetic/dimensions_synthetic.pdf`,
`floorplan_synthetic.pdf`, `symbols_synthetic.pdf`.

Running `python3 -m pytest -q` leaves all three modified in the working tree — they are
regenerated on each run and the bytes differ (PyMuPDF writes a timestamp). This is pre-existing
(unrelated to the scale parser) and is the same class of problem commit `e2fa735`
("purge test-pollution") addressed for `output/`.

**Impact:** every `git status` after a test run shows spurious modifications, so a careless
`git add -A` commits churn — and it makes "is the tree clean?" useless as a check.

**To fix:** generate them into a tmp_path fixture, or add them to `.gitignore` and build them
in a session-scoped fixture. Not attempted in 23-02: it touches test infrastructure shared by
several suites and is unrelated to SP-2.

---

## DEF-23-03 — `main=None` on Bob's pages 3 and 4 after the scale fix

**Found during:** 23-02 Task 3, probe acceptance.

`scripts/scale_probe.py` now reports the correct per-callout values on Bob's
(`page 3 distinct_fpi=[1.0, 10.6667]`, `page 4 distinct_fpi=[2.0, 4.0, 8.0]`) but
`main=None` on both. This is **BUG-C**, the rotation-unaware callout↔viewport binding
(INV-04 §4 BUG-C): every Bob's page is `/Rotate 270`, and `match_scales_to_viewports`
implements "the label sits at the drawing's bottom" as `y1 <= cy` in *unrotated* space.

**Not a deferral — it is scheduled.** Plan 23-07 owns it, and 23-02's constraints explicitly
forbid starting it here. Logged only so the `main=None` reading in the probe output is not
mistaken for a defect introduced by SP-2. It is present identically before the change.

---

## DEF-23-04 — `test_max_region_guard_rejects_sheet_scale_regions` passes for the wrong reason

**Found during:** 23-03 Task 1, adding the `dropped_regions` out-list test.
**Where:** `tests/test_room_fill.py::test_max_region_guard_rejects_sheet_scale_regions`.

The fixture builds a 60' × 40' room at 1/4" = 1'-0", i.e. **1,080 × 720 pt**, on an **800 × 800 pt**
page starting at (100, 100). The room overflows the page, so its region **touches the clip edge**
and is discarded as "the outside" — the `max_region_sf` guard the test is named for is never
reached. Proven by instrumenting `measure_enclosed_area` with the new out-list: `dropped_regions`
comes back **empty**, which it could not be if the size filter had fired.

**Impact:** the assertion (`is None`) is correct, so nothing is broken today — but the test does not
in fact pin the behaviour it claims to, and would keep passing if `MAX_REGION_SF` were deleted.

**NOT fixed here** because rewriting an existing pin is out of this plan's scope (the change would
be indistinguishable from tuning a guard, which INV-08 risk 6 forbids without its own justification).
The new `test_oversize_rejection_is_recorded_when_an_out_list_is_supplied` draws its 1,200 SF region
at 1/8" so it genuinely fits on the page, and DOES exercise the size filter — so the behaviour is now
covered even though the older test remains vacuous.

**To fix:** redraw the fixture at a scale that fits the page (or enlarge the page) and assert
`dropped_regions` is non-empty, so the guard is what makes the test pass.

---

## DEF-23-05 — a non-HM door FRAME canonicalises into a DOOR bucket

**Found during:** 23-04 Task 3, checking the emitted item names against
`aggregator.ITEM_NAME_MAP`.
**Where:** `src/bobbytailor/pipeline/aggregator.py:119-126`.

`ITEM_NAME_MAP` has exactly ONE frame rule —
`hollow.?metal.*frame|frame.*hollow.?metal|frame.*\bhm\b|\bhm\b.*frame` → `Frame-HM` — and it fires
only for hollow metal. Every other frame material falls through to the DOOR rules below it:

| Emitted item | Canonicalises to | Correct? |
|---|---|---|
| `Door Frames-HM` | `Frame-HM` | yes |
| `Door Frames-AL` | `Doors-AL` (via `door.*alum`) | **no — a frame is billed as a door** |
| `Door Frames-STL` | `Doors` (generic catch-all) | **no** |

Measured: Bob's emits `Door Frames-AL 2`, Moxy emits `Door Frames-AL 5` and `Door Frames-STL 6`.
Those six-to-eleven units are currently added to a door line item.

**Impact is bounded and pre-existing.** `component_library` already emitted `Door Frames-AL` before
23-04 (`_MAT_CODE_ALIAS` mapped `ALUM → AL`), so this is not a regression — 23-04 only makes it
visible on two more plan sets. Neither Bob's nor Moxy's golden carries a non-HM frame row, so
nothing scores worse.

**NOT fixed here** because `aggregator.py` is not in 23-04's `files_modified`, and adding
`Frame-AL` / `Frame-STL` canonical names changes the item vocabulary every scored fixture matches
against — that is a naming decision with its own blast radius, not a door-schedule fix.

**To fix:** add generic frame rules (`frame.*\balum?\b` → `Frame-AL`, `frame.*\bstl\b|frame.*steel`
→ `Frame-STL`) ABOVE the door rules in `ITEM_NAME_MAP`, and re-score all four saved runs.

---

## DEF-23-06 — the synthetic fixture PDFs are rewritten by every test run

**Found during:** 23-04, staging each commit.
**Where:** `tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf`.

`git status` reports all three as modified after any full `pytest -q`, because the fixtures are
regenerated on use and PyMuPDF embeds a creation timestamp. The bytes differ, the content does not.

**Impact:** every run dirties the working tree, so a `git add -A` would sweep three unrelated binary
files into an unrelated commit. Pre-existing; not introduced by 23-04 (which staged files
individually, per the commit protocol).

**To fix:** generate them into `tmp_path` instead of the repo, or make the writer deterministic
(`doc.set_metadata({})` plus a fixed `creationDate`), then re-commit the fixtures once.
