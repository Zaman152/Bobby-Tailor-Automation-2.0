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
