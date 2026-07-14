# Phase 21 — Live-Testing Readiness UAT

**Purpose:** human sign-off that the plans-only, self-improving pipeline is
ready for live client testing (roadmap criterion 7, V3-PROD-02).
Each numbered section maps to a Phase 21 roadmap success criterion; sections
8–9 cover the two Manual-Only Verifications from 21-VALIDATION.md.

**Prerequisites**

- `pip install -e .` done; `.env` populated (StackCT + Anthropic + web auth)
- App running: `python3 app.py` (dev) or gunicorn per docs/DEPLOYMENT.md
- The four benchmark PDF pairs present in `uploads/` (21-CONTEXT Benchmark
  Protocol)
- NOTE ON COST: sections 2, 4, 5, 6 spend real API credits. The full gate run
  (section 2) is roughly $5–15.

---

## UAT 1 — Plans-only upload produces a complete, flag-explicit takeoff
*(criterion 1: zero silent misses; flags approach zero on vector CAD PDFs)*

1. Open `http://localhost:5050`, log in.
2. Upload **only** `uploads/Crow - Cass White Road-Plans.pdf` via the PDF tab
   (no companion take-off, no manifest, no calibration input) and run.
3. When the run completes, open the report.

**Expect:**
- [ ] Run completes without any manifest/companion prompt or error
- [ ] Report contains items across the expected categories (bollards, columns,
      footprint SF, wall LF, door/window schedule rows, site quantities)
- [ ] Every quantity row shows provenance (geometry / text_layer /
      schedule / vision_ensemble)
- [ ] Anything the pipeline could not establish deterministically is
      explicitly flagged `needs_review` (with a reason) — no blank/absent
      quantities without a flag
- [ ] The flagged subset is small relative to the total item count

## UAT 2 — Accuracy gate passes on Crow + Bob (plans-only)
*(criterion 2: geometry/text ≥97%, overall ≥90%, item-found ≥95%; this is
also the PENDING live gate run deferred from 21-17's human checkpoint)*

```bash
bash scripts/accuracy_gate.sh          # spends API credits; ~$5–15
```

**Expect:**
- [ ] Exit code 0 (hard gate = Crow Cass + Bob's Discount)
- [ ] Per-project report: geometry/text-provenance quantity accuracy ≥ 97%
- [ ] Overall quantity accuracy ≥ 90% on both gating projects
- [ ] Item-found ≥ 95%, zero silent misses (every expected item present or
      flagged), vision quantity share ≈ 0 on these vector PDFs
- [ ] Chelsea + Moxy scored and recorded as tracking-only (never gate)

## UAT 3 — Zero-calibration per-viewport scale detection
*(criterion 3: main-plan viewport scale wins on multi-scale sheets)*

1. In the UAT-1 Crow run report, open the Scale & Verify panel
   (`/api/reports/<run>/scale` backs it).

**Expect:**
- [ ] Every sheet shows an auto-detected scale with a confidence level and a
      source (solved from dimension strings / printed notation) — no human
      calibration was performed at any point
- [ ] Crow page 1 main plan resolves **1" = 40'** with HIGH confidence
      (printed scale cross-validated by the 1136' × 350' overall dimensions;
      the old ~1"=20' research figure was disproven in 21-07 — a 3024-pt
      sheet cannot hold 1136 ft at 20 fpi), and NOT a detail-callout scale
- [ ] Footprint on the Crow main plan reports ≈ 397,600 SF (±0.1%)

## UAT 4 — Learning loop: verify → persist → repeat-run application
*(criterion 4: corrections survive the run and apply with no manifest)*

1. In the UAT-1 report, correct one item name (e.g. rename a legend-derived
   item to your canonical name) and confirm one quantity via the Verify panel.
2. Confirm the learning store recorded it (adjust path if `LEARNING_DB_PATH`
   is set):
   `sqlite3 output/learning.db "SELECT scope, item_pattern, corrected_value FROM learning_corrections ORDER BY id DESC LIMIT 5;"`
   and the distilled vocabulary:
   `sqlite3 output/learning.db "SELECT raw_pattern, canonical_name, unit FROM learning_vocabulary ORDER BY id DESC LIMIT 5;"`
3. Delete or ignore the run folder, then re-run the SAME plans PDF (UAT-1
   steps) with no extra inputs.

**Expect:**
- [ ] Correction visible in `learning.db` immediately after saving (survives
      deleting the run folder)
- [ ] The repeat run applies the learned name automatically (row marked
      `source=learned`); quantity provenance is untouched
- [ ] Learned data only re-flags conflicting quantities (`re_verify`) — it
      never silently overwrites a geometry/text value

## UAT 5 — Run-to-run reproducibility within ±5%
*(criterion 5: ensemble kills run-to-run variance)*

Covered mechanically by the gate's `--repro` double-runs (UAT 2). Spot-check:

```bash
python3 scripts/vision_only_benchmark.py --name crow \
  --plans-pdf "uploads/Crow - Cass White Road-Plans.pdf" \
  --takeoff-pdf "uploads/Crow - Cass White Road-Take offs.pdf" --repro
```

**Expect:**
- [ ] The two runs' per-item quantity deltas are all ≤ 5%
- [ ] No item appears in one run but silently vanishes in the other

## UAT 6 — StackCT parity run
*(criterion 1/criterion 6 support: both entry points behave identically)*

1. From the Projects tab, sync a StackCT project, select a plan set and a
   small sheet subset (≤ 15), and run.

**Expect:**
- [ ] Run completes through capture → analyze → report with progress bands
- [ ] Report rows show the same provenance/flag structure as the PDF-upload
      path (deterministic quantities on vector-blob sheets, ensemble on
      raster) — no manifest/companion involvement
- [ ] Scale & Verify and the learning capture work identically to UAT 3/4

## UAT 7 — Package structure, suite, boot, docs
*(criterion 6: structured package; pytest green; app boots; README documents
the layout)*

```bash
ls *.py                                          # expect ONLY: app.py main.py
python3 -m pytest tests/ -q -m "not golden"      # expect: 833+ passed, exit 0
python3 -c "from bobbytailor.web.app import create_app; create_app()" && echo boot-ok
gunicorn -w 1 -b 127.0.0.1:5051 app:app --timeout 60 &   # then: curl -sf localhost:5051/login; kill %1
```

**Expect:**
- [ ] Exactly two root Python files (`app.py`, `main.py`); no import shims
- [ ] Full non-golden suite green
- [ ] App boots via the blueprint factory; `/login` serves 200 through
      gunicorn per docs
- [ ] README "Package layout" section matches `src/bobbytailor/` reality;
      docs/DEPLOYMENT.md commands work as written

## UAT 8 — Reviewed-items workflow (Manual-Only row 1)
*(V3-PROD-02: human verifies ONLY the flagged subset)*

1. In any completed run, open the review panel.

**Expect:**
- [ ] The panel surfaces exactly the flagged subset (needs_review /
      fusion_rejected / learned re_verify), not the full item list
- [ ] Each flag carries a reason (budget_exhausted, ensemble disagreement,
      unknown_candidate_id, low-confidence scale, …)
- [ ] Working the list end-to-end is demo-grade: correcting/confirming each
      row clears or downgrades its flag

## UAT 9 — Learning-loop UX through the web UI (Manual-Only row 2)
*(V3-LEARN-01..03 end-to-end through the UI, not the API)*

1. Repeat UAT 4 but exclusively through UI interactions (no sqlite3 checks):
   verify a run, re-run the project, and look for the applied-corrections
   indication on the new run.

**Expect:**
- [ ] The repeat run visibly reflects the earlier verification (learned names
      applied, previously-confirmed rows not re-flagged)
- [ ] No manifest file was created or requested anywhere in the flow

---

## Sign-off checklist

- [ ] UAT 1–9 all pass (check every box above)
- [ ] Deployment docs verified against reality (boot via gunicorn per
      docs/DEPLOYMENT.md; env table matches `.env.example`)
- [ ] `learning.db` backup procedure executed once successfully
      (copy + restore per docs/DEPLOYMENT.md)
- [ ] Push to GitHub `Zaman152/Bobby-Tailor-Automation-2.0` at this milestone
      (locked process decision)

**Signed off by:** ______________  **Date:** ______________

*Failing steps: list the UAT number, the observed behavior, and the expected
behavior; the phase is not live-ready until every gating item passes.*
