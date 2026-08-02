---
phase: 22-production-restructure-cleanup
plan: 02
status: complete
requirements:
  - RESTRUCTURE-SPEC-S2
  - RESTRUCTURE-SPEC-S3
completed: 2026-08-03
---

# 22-02 Summary — DELETE bucket + ARCHIVE bucket

## What shipped

**Task 1 — Step 2 DELETE (commit `e2fa735`)**
Purged the regenerable junk from `output/` against an explicit keep-list (never negated globs),
plus the two tracked scratch files.

| Metric | Before | After |
|---|---|---|
| `output/` size | 1.3 GB | **154 MB** (~1.13 GB reclaimed) |
| `output/` top-level entries | 450 | **27** |
| `output/screenshots/` dirs | ~400 | **18** |
| `MagicMock/` at repo root | present | **absent** |

Removed: 297 pytest-pollution run dirs (`Test_Proj_*`, `Scale_Proj_*`, `Fused_Proj_*`, `Old_Shape_*`),
373 empty screenshot dirs, June-era superseded HD renders (Moxy 438 MB, Bobs_Discount_Test 318 MB,
Crow_Cass_Test 143 MB, and the rest of §4.1), `output/Archive.zip`, `stackct 2.db`,
`stackct.db.empty-bak`, `webapp.log`, `.DS_Store`, `.codegraph/`, `bobbytailor.egg-info/`.
`git rm`: `scripts/_diag_chelsea.json` (241 KB), `scripts/network_capture.py`.
`.gitignore` gained `MagicMock/` and `output/_archive/`.

**Task 2 — Step 3 ARCHIVE (this commit)**
`output/_archive/stackct-era-20260802.zip` (19.5 MB) created from the §4.2 list, integrity-verified
with `unzip -t` ("No errors detected") **before** any original was removed. Contents: the StackCT
browser captures (not regenerable without a StackCT session), ~12 non-report-referenced paid-run
`VisionOnly_*` dirs, the two StackCT-era Crow originals, and `data/`.
`git mv` relocated the three StackCT-era one-off diagnostics to `scripts/archive/`, each with its
repo-ROOT parent count corrected to `parents[2]` (one level deeper).

## Must-survive contract — independently re-verified

Every item in RESTRUCTURE-SPEC §4.3 was re-checked directly after the session interruption (not
taken on the executor's word, since its work was not safety-reviewed):

- **Databases**: `learning.db` (+`-wal`/`-shm`) and `stackct.db` intact; `sqlite3 .tables` lists all
  5 learning tables (`learning_vocabulary`, `learning_corrections`, `learning_assumptions`,
  `learning_manifests`, `learning_metadata`) and all 6 stackct tables.
- **All 16 report-referenced run↔screenshots pairs present** (Bobs G1/G3, Crow A1/A2/Cass×2/F2/
  Final/MAN/N1/R1/S1, Moxy ×4) — each run dir and its timestamp-paired screenshots dir.
- **All 5 one-of-a-kind runs present**, including the only Chelsea result ever produced and the
  full-name Moxy 20260627 run.
- **Both scraper reuse caches present** (`Crow_-_Cass_White_Road_20260630_234238`,
  `…-Plans_20260715_191703`).
- Sacred paths untouched: `uploads/`, `human_inputs/`, `reports/`, `tests/`, `.planning/`, `.env`.

## Deviations

1. **Session interruption mid-Task-2.** The executor agent hit a session limit after creating and
   verifying the zip and staging the script moves, but before committing or writing this SUMMARY.
   Recovery was done in the main session: state re-verified from disk (above), one piece of new junk
   removed (see 2), then committed. No work was redone or lost.
2. **One new artifact removed during recovery**: `output/screenshots/Diagnose_Crow_Cass_20260802_235920`
   (936 KB, 2 PNG page renders) was created by the executor's own verification run of the relocated
   `diagnose_fixture.py`. It is regenerable diagnostic output, deleted as part of finishing the step.
   Note this class of pollution is *script*-generated, not pytest-generated, so the 22-01 conftest
   isolation does not cover it — scripts writing to `output/` remain a (minor, known) gap, recorded
   for the hardening phase rather than fixed here.
3. **5 dangling provenance paths in benchmark score files — deliberate, per spec.** A cross-check of
   every run-dir name mentioned anywhere under `reports/` (37 found) against surviving `output/`
   entries showed 5 missing, all June-era **screenshot** dirs:
   `VisionOnly_Bobs_Discount_20260627_212454`, `VisionOnly_Bobs_Discount_Manifest_20260627_215915`,
   `VisionOnly_Crow_Cass_Fresh_20260628_054501`, `VisionOnly_Crow_Cass_Manifest_20260627_215121`,
   `VisionOnly_Crow_Tiling_20260627_222114`.
   They are referenced only as provenance breadcrumbs (`detail[].sheet =
   output/screenshots/<dir>/page_NNNN.png`, ~45 hits each) inside tracked
   `reports/vision_only/*/vision_summary.json`. RESTRUCTURE-SPEC §4.1 lists exactly these for
   deletion with the rationale "scores tracked in `reports/vision_only/`" / "experiments; scores
   tracked in git" — the *scores* are preserved in git, only the regenerable PNG renders are gone
   (regenerable free from `uploads/` via fitz). No code reads these paths; the web Reports flow reads
   `output/<run>/takeoff.json`, and all 16 must-survive run↔screenshot pairs (all 20260715/20260717)
   are intact. **Consequence accepted, not a defect:** clicking through to the source image of a
   June-era benchmark score is no longer possible without re-rendering.
4. **`gitnexus_detect_changes()` unavailable** (MCP tool not reachable in this runtime); change scope
   verified with `git status --short` / `git diff --stat` instead. The GitNexus index stays stale by
   design until the phase's Step 8 reindex in 22-04.

## Verification

- `unzip -t output/_archive/stackct-era-20260802.zip` → "No errors detected in compressed data".
- `sqlite3 output/learning.db ".tables"` / `stackct.db ".tables"` → both succeed, full table lists.
- §4.3 keep-list → 16/16 pairs + 5/5 unique runs + 2/2 caches + 4/4 DB files present.
- `python3 -m pytest -q` (bare — golden excluded by default since 22-01) → green.
- Archived scripts parse under Python 3.9 and resolve ROOT via `parents[2]`.
- Reference cross-check: all 37 run-dir names mentioned under `reports/` resolved against surviving
  `output/` entries; the only 5 misses are the spec-sanctioned June-era screenshot renders (Deviation 3).

## Next

22-03 (wave 3): Step 4 legacy-docs archive + Step 5 web-asset relocation into the package.
