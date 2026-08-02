# CLEANUP MANIFEST — artifact + junk inventory

Audit date: 2026-08-02 (branch `accuracy/flag-dont-guess-coincidental-detections`).
Read-only audit; nothing was deleted. All sizes measured with `du` on disk.

## TL;DR

- **~1.13 GB of the repo's 1.3 GB `output/` tree is safely reclaimable** — 96% of `output/` is
  `output/screenshots/` (1,255 MB), and most of that is June-era duplicate HD renders and dead
  test-project captures. All plans-only screenshots are regenerable for free (local `fitz` render
  from `uploads/` PDFs — `scripts/vision_only_benchmark.py:646`).
- **Must survive in `output/`**: `learning.db` (+`-wal`/`-shm`), `stackct.db`, the **16 run dirs
  referenced by git-tracked reports**, each kept run's **paired `screenshots/<stamp>` dir** (run
  `takeoff.json` embeds `screenshots/<dir>/page_NNNN.png` links — `src/bobbytailor/pipeline/reporter.py:426`),
  and the one-and-only Chelsea / Moxy StackCT-era result dirs that back `reports/accuracy/*.csv`.
- **`reports/` (18 MB, 82 git-tracked files) is scored accuracy history: KEEP ALL.** The
  `vision_summary.json` / `takeoff_result.json` files are recorded outputs of paid API runs.
  Two new untracked gate files (`moxy_run3.json`, `moxy_run4.json`) belong to the in-flight branch — commit, don't clean.
- **Blocking bug found: the test suite pollutes real `output/`.** 297+ top-level run dirs
  (`Test_Proj_*`, `Scale_Proj_*`, `Fused_Proj_*`, `Old_Shape_*`), 373 empty
  `output/screenshots/{Test,Test_Project,Settings_Parity,Isolation_Project,Determinism_PDF}_*` dirs, a fake
  `Crow_Cass_20260802_222708` run, and the root `MagicMock/` tree are all test artifacts — new ones were
  created **today at 22:26–22:27 by the currently-running suite**. Fix test `OUTPUT_DIR` isolation
  first or the junk regrows immediately.
- `data/` (12 KB) is orphaned — zero references to `state_store`/`stream_store` anywhere in
  `src/`, `scripts/`, `tests/`. `.codegraph/` (2.6 MB) is a stale pre-GitNexus index. `MagicMock/`
  is empty dirs. All deletable.
- **Do not run any cleanup while the pytest suite is running** (it is, right now — `.pytest_cache`
  and `output/` were touched at 22:31 / 22:27 today).

Estimated reclaimed disk: **~1.13–1.15 GB** (out of ~1.32 GB audited).

---

## (a) `output/` — 455 top-level entries, 1.3 GB, git-ignored

Git status: fully ignored (`.gitignore:8`), `git ls-files output` → 0 tracked files.
`config.py:73` `OUTPUT_DIR = ./output`; `config.py:74` `SCREENSHOTS_DIR = output/screenshots`;
`config.py:77` `STACKCT_DB_PATH = output/stackct.db`;
`src/bobbytailor/learning/store.py:95-96` `LEARNING_DB_PATH = output/learning.db` (env-overridable).

### a.1 What is REFERENCED (evidence)

| Referencer | Evidence | Consequence |
|---|---|---|
| Learning DB | `learning/store.py:95-96`; backup doctrine in `docs/DEPLOYMENT.md:139,145` ("accumulated human knowledge of the installation") | `output/learning.db` + `-wal` + `-shm` **MUST SURVIVE** |
| Live project DB | `config.py:77`; used across `stores/stackct_store.py`, `web/`, `scrape/` (15 files) ; mtime **today** 22:27 | `output/stackct.db` **MUST SURVIVE** |
| git-tracked reports | 17 distinct `output/...` literals inside `reports/**` (grep, all EXIST) | 16 VisionOnly run dirs + `output/screenshots` **MUST SURVIVE** (list in a.4) |
| Run `takeoff.json` → sheet images | `reporter.py:426` stores `screenshots/<dir>/page_NNNN.png` rel paths; web UI serves them (`web/blueprints/runs.py:55`) | every kept run dir needs its **paired screenshots dir** (pairing table in a.4) |
| Screenshot reuse cache | `scrape/sheet_preview.py:31-44` matches `output/screenshots/<ProjectPrefix>_*` newest-first; `scraper.py:678-682` reuses before capturing; README.md:402 | keep the **newest complete set per real project** |
| Web Reports list | `web/blueprints/reports.py:121` lists every `output/` subdir except `screenshots` | every junk run dir shows up in the UI — cleanup improves the product |
| Replay fixtures | `tests/replay_analyzer.py:1-22` — fixtures live at `tests/fixtures/replay/{sha256}.json`, **NOT** in `output/`; dir currently holds only `.gitkeep` | no replay recordings in `output/`; but VisionOnly run dirs contain paid-run JSON → ARCHIVE not DELETE |

### a.2 `output/screenshots/` — 1,255 MB, 452 dirs (the real disk hog)

| Bucket (prefix) | Dirs | Size | Verdict | Justification |
|---|---:|---:|---|---|
| `VisionOnly_Moxy_Knoxville_20260628_*` (x3) | 3 | **438 MB** | **DELETE** | old hi-DPI renders (146 MB each, 40 pages); superseded by the four 15 MB Jul-17 sets that back the tracked moxy gate runs; regenerable free via fitz from `uploads/Moxy...Plans.pdf` |
| `Bobs_Discount_Test_*` (Jun 27–28) | 18 | **318 MB** | **DELETE** | dead "Test" project from June StackCT experiments; 7-page partial sets; no report references |
| `Crow_Cass_Test_*` (Jun 27–28) | 20 | **143 MB** | **DELETE** | same June test-project era; 4-page partial sets |
| `Crow_-_Cass_White_Road_*` | 5 | 140 MB | **DELETE 4, KEEP newest** | keep `..._20260630_234238` (47 MB, 21 pages, newest full set = reuse cache for the real Crow project); delete 2 older 47 MB sets + 2 empty dirs |
| `Moxy_Diag_20260628_040321` | 1 | 44 MB | **DELETE** | one-off diagnostic (2 pages @ ~22 MB) |
| `VisionOnly_Bobs_Discount{,_Manifest}_202606*` | 2 | 35 MB | **DELETE** | June benchmark era; scores already tracked in `reports/vision_only/Bobs_Discount{,_Manifest}/` |
| `Bobs_Discount_Kennesaw_StackCT_20260627_*` | 1 | 18 MB | **ARCHIVE** | browser-captured from StackCT (`scrape/scraper.py` Pass 1) — NOT regenerable without a StackCT account/session |
| `Crow_Cass_White_Road_*` (no dashes) | 2 | 14 MB | **DELETE** | June variant-name era, superseded |
| `VisionOnly_Crow_Cass_*` | 8 | 13.5 MB | **KEEP 2, DELETE 6** | keep `_20260715_062822` + `_20260715_070930` (paired to report-referenced runs, a.4) |
| `VisionOnly_Crow_{Tiling,Cass_Manifest,Cass_Fresh}` | 3 | 21 MB | **DELETE** | June/Jul-early experiments; scores tracked in git |
| 12 small `VisionOnly_*` sets paired to tracked runs | 12 | ~12 MB | **KEEP** | pairing table a.4 (Bobs_G1/G3, Crow_A1/A2/F2/Final/MAN/N1/R1/S1, + 4 Moxy Jul-17) |
| `VisionOnly_Bobs_G2_*` | 1 | 2.2 MB | **UNSURE→ARCHIVE** | only `reports/accuracy_gate/bobs_g2.log` exists (no .json); trivial size |
| `Crow_-_Cass_White_Road-Plans_20260715_191703` | 1 | 1 MB | **KEEP** | newest capture under the exact current upload name (`uploads/Crow - Cass White Road-Plans.pdf`) |
| `{Test,Test_Project}_*` (110+110), `Settings_Parity_*` (51), `Isolation_Project_*` (51), `Determinism_PDF_*` (51) | **373** | ~0 MB | **DELETE** | empty dirs; pytest pollution (names from `tests/test_blueprint_parity.py` et al.); recreated by suite until isolation is fixed |

Screenshots subtotal: keep ~75 MB, archive ~20 MB, **delete ~1,110 MB**.

### a.3 `output/` top-level run dirs + loose files

| Bucket | Count | Size | Verdict | Justification |
|---|---:|---:|---|---|
| `Test_Proj_*` (103), `Scale_Proj_*` (101), `Fused_Proj_*` (47), `Old_Shape_*` (46) | 297 | 8.5 MB | **DELETE** | pytest pollution — names appear as `"Fused Proj"` / `"Old Shape"` in `tests/test_reporter_accuracy.py:64,122`; new dirs stamped `20260802_2226xx` created by today's running suite |
| `Crow_Cass_20260802_222708` | 1 | ~0.03 MB | **DELETE** | fake run from today's suite — its `takeoff.json` references non-existent `screenshots/crow/` fixture paths |
| `Crow_Cass_*` (Jun 28 – Jul 17, real R&D iterations) | 76 | 2.4 MB | **DELETE all but latest** | keep `Crow_Cass_20260717_043721` (last real run); the rest are superseded probe iterations |
| `Crow_Cass_Test_*` (20), `Bobs_Discount_Test_*` (18) | 38 | 5.1 MB | **DELETE** | dead June test projects |
| 16 report-referenced `VisionOnly_*` run dirs | 16 | ~10 MB | **KEEP** | referenced by git-tracked `reports/**` (a.4) |
| Non-referenced `VisionOnly_*` run dirs (`VisionOnly_Crow_Cass` older stamps, `VisionOnly_Bobs_Discount{,_Manifest}`, `VisionOnly_Crow_{Tiling,Cass_Fresh,Cass_Manifest}`, `VisionOnly_Moxy_Knoxville_20260628_043339`, `VisionOnly_Crow_Cass_20260627_211339`) | ~12 | ~7 MB | **ARCHIVE** | contain `takeoff.json`/`spec_tables.json` from **paid API runs** — recorded-run rule: archive, never delete |
| `Invitation_to_Bid_-_25-382_AL,_Chelsea,_Bear_Creek_Rd_20260627_171054` | 1 | 0.4 MB | **KEEP** | the ONLY Chelsea result ever; source of `reports/accuracy/chelsea_comparison.csv` (100% score) |
| `Moxy_Knoxville_-_Addendum_A_City_Comment_Revision_20260627_171145` | 1 | 0.4 MB | **KEEP** | the only full-name Moxy result; source era of `reports/accuracy/moxy_comparison.csv` |
| `Crow_-_Cass_White_Road_20260701_000626`, `Crow_-_Cass_White_Road-Plans_20260715_192505` | 2 | ~5 MB | **KEEP** | latest full-name Crow runs (webapp-visible history for the real project) |
| `Crow_-_Cass_White_Road_20260628_061922`, `Crow_Cass_White_Road_20260628_045605`, `Bobs_Discount_Kennesaw_StackCT_20260627_233154` | 3 | ~1.3 MB | **ARCHIVE** | StackCT-era originals; Kennesaw is the only Bob's full-project run |
| `output/Archive.zip` | 1 | 55 KB | **DELETE** | verified duplicate: zip lists exactly the two Chelsea/Moxy dirs above (same timestamps), which still exist unpacked |
| `output/stackct.db` | 1 | 0.4 MB | **KEEP** | live app DB (mtime today) |
| `output/stackct 2.db` | 1 | 0.3 MB | **DELETE** | Finder-style duplicate, Jun 27 |
| `output/stackct.db.empty-bak` | 1 | 0.2 MB | **DELETE** | empty backup, Jun 27 |
| `output/learning.db{,-wal,-shm}` | 3 | 0.26 MB | **KEEP (sacred)** | the learning-loop DB — `docs/DEPLOYMENT.md:139` |
| `output/webapp.log` | 1 | 0.3 MB | **DELETE** | dev log (gitignored `*.log`), Jul 15 |
| `output/.DS_Store` | 1 | — | **DELETE** | Finder junk |

### a.4 Definitive `output/` MUST-SURVIVE list

Databases: `learning.db`, `learning.db-wal`, `learning.db-shm`, `stackct.db`.

Report-referenced run dir → paired screenshots dir (pairing extracted from each run's `takeoff.json`):

| Run dir (KEEP) | Paired `screenshots/` dir (KEEP) |
|---|---|
| `VisionOnly_Bobs_G1_20260715_173331` | `VisionOnly_Bobs_G1_20260715_172329` |
| `VisionOnly_Bobs_G3_20260715_182541` | `VisionOnly_Bobs_G3_20260715_181734` |
| `VisionOnly_Crow_A1_20260715_212614` | `VisionOnly_Crow_A1_20260715_211904` |
| `VisionOnly_Crow_A2_20260715_215449` | `VisionOnly_Crow_A2_20260715_214607` |
| `VisionOnly_Crow_Cass_20260715_063739` | `VisionOnly_Crow_Cass_20260715_062822` |
| `VisionOnly_Crow_Cass_20260715_071654` | `VisionOnly_Crow_Cass_20260715_070930` |
| `VisionOnly_Crow_F2_20260715_082130` | `VisionOnly_Crow_F2_20260715_081606` |
| `VisionOnly_Crow_Final_20260715_072611` | `VisionOnly_Crow_Final_20260715_071750` |
| `VisionOnly_Crow_MAN_20260715_220702` | `VisionOnly_Crow_MAN_20260715_215933` |
| `VisionOnly_Crow_N1_20260715_170939` | `VisionOnly_Crow_N1_20260715_170034` |
| `VisionOnly_Crow_R1_20260715_085526` | `VisionOnly_Crow_R1_20260715_084814` |
| `VisionOnly_Crow_S1_20260715_161536` | `VisionOnly_Crow_S1_20260715_160808` |
| `VisionOnly_Moxy_Knoxville_20260717_013825` | `VisionOnly_Moxy_Knoxville_20260717_011939` |
| `VisionOnly_Moxy_Knoxville_20260717_021348` | `VisionOnly_Moxy_Knoxville_20260717_015307` |
| `VisionOnly_Moxy_Knoxville_20260717_043126` | `VisionOnly_Moxy_Knoxville_20260717_041129` |
| `VisionOnly_Moxy_Knoxville_20260717_045741` | `VisionOnly_Moxy_Knoxville_20260717_044247` |

Plus per-project latest / one-of-a-kind (KEEP): `Crow_Cass_20260717_043721`,
`Crow_-_Cass_White_Road_20260701_000626`, `Crow_-_Cass_White_Road-Plans_20260715_192505`,
`Invitation_to_Bid_-_25-382_AL,_Chelsea,_Bear_Creek_Rd_20260627_171054`,
`Moxy_Knoxville_-_Addendum_A_City_Comment_Revision_20260627_171145`,
screenshots cache `screenshots/Crow_-_Cass_White_Road_20260630_234238` (newest full Crow set) and
`screenshots/Crow_-_Cass_White_Road-Plans_20260715_191703`.

## (b) `reports/` — 18 MB, 82 git-tracked files — KEEP ALL

- `reports/accuracy/` (12 KB): human-vs-app comparison CSVs + README (Chelsea 100%, Moxy). **KEEP.**
- `reports/accuracy_gate/` (11 MB): the gate history (`crow*.json/.log`, `bobs_g*.json/.log`,
  `moxy*.json`) — each JSON has dual-run reproducibility + cost data (`cost_total_usd`). **KEEP**;
  these are the paid-run audit trail. The superseded `.log` files (e.g. `crow_a1.log`…`crow_run.log`)
  are git-tracked so deleting them reclaims nothing locally — not worth touching.
- `reports/vision_only/` (7 MB): per-project `score.json` / `gap_report.txt` / `vision_summary.json`
  / `takeoff_result.json` + `RESULTS.md` (the honest plans-only baseline). These are the recorded
  outputs of live vision runs — **KEEP; they are the cheap substitute for re-spending API credits.**
- **Untracked**: `reports/accuracy_gate/moxy_run3.json`, `moxy_run4.json` — produced by the current
  branch's in-flight work (git status also shows modified `reports/vision_only/Moxy_Knoxville/*`).
  **KEEP — should be committed with the branch, not cleaned.**
- Stale-vs-keep verdict: nothing in `reports/` qualifies as safely stale; it is all scored history.

## (c) `data/` — 12 KB, git-ignored (`.gitignore:38`) — ORPHANED

Contents: `data/state_store.db/` (a **directory** holding `mem%3Ahealth.bin`, `mem%3Aaudit.bin`,
Jun 6) and `data/stream_store/` (empty, May 26).
Evidence of orphanhood: `grep -rn "state_store|stream_store" src scripts tests` → **zero hits**.
Nothing in the app reads or writes either path; they predate the current architecture (likely an
abandoned tool's artifact). **DELETE** (flagged UNSURE only because origin is unidentified — but
zero in-repo references and 12 KB total).

## (d) Root junk

| Path | Size | Git | Verdict | Justification |
|---|---:|---|---|---|
| `MagicMock/` | 0 B (17 empty dirs) | untracked | **DELETE** | classic test bug: a `MagicMock` used as `OUTPUT_DIR`/`SCREENSHOTS_DIR` got `os.makedirs()`-ed (`MagicMock/mock.OUTPUT_DIR/4432562352/...`, Jul 14–15). Fix the offending test during restructure |
| `./.DS_Store`, `output/.DS_Store` | 12 KB | ignored | **DELETE** | only 2 in repo (excl. `.git`) |
| `Master.md` | 67 KB | tracked | **ARCHIVE → `docs/archive/Master.md`** (git mv) | legacy v2.0 master doc; still cited by comments in `static/style.css:5-6` ("Tokens: Master.md §8.1") and `static/app.js:5` — comment-only refs, safe to move; update the comment paths |
| `Masterv2.md` | 110 KB | tracked | **ARCHIVE → `docs/archive/Masterv2.md`** (git mv) | superseded planning source-of-truth; already gap-analyzed in `.planning/MASTERv2-GAP-ANALYSIS.md`; cited in `tests/test_extraction_prompt.py:1` docstring only |
| `design-system/` (3 .md) | 24 KB | tracked | **KEEP-IN-PLACE** (or fold into `docs/design/` during restructure) | referenced by `.planning/phases/15-premium-ui-ux-revamp/*` plans; it is the UI spec (`MASTER.md`, `pages/{reports,projects}.md`); no code reads it |
| `.codegraph/` | 2.6 MB | ignored (`.gitignore:18`) | **DELETE** | pre-GitNexus index (`codegraph.db`, last touched Jun 4); superseded by `.gitnexus/` (excluded via `.git/info/exclude`); zero references in code/docs |
| `.cursor/rules/` (3 .mdc) | 12 KB | **tracked** | **KEEP** (UNSURE) | tracked editor rules; only `.cursor/projects/` is ignored. Delete only if Cursor is abandoned |
| `.pytest_cache/` | 120 KB | ignored | **KEEP** | regenerated automatically; **currently in use by the running suite** |
| `src/bobbytailor.egg-info/` | small | ignored (`*.egg-info/`) | **DELETE** (optional) | build artifact; `pip install -e` regenerates |
| `.gitnexus/` | — | excluded | **KEEP** | active GitNexus index required by CLAUDE.md workflow |

## (e) `scripts/` — 15 files, 356 KB

| File | Class | Verdict | Evidence |
|---|---|---|---|
| `accuracy_gate.sh` | production tool (PAID) | **KEEP** | 13 refs; learning-isolation doctrine at lines 30–72; tested by `tests/test_benchmark_scoring.py:429` |
| `vision_only_benchmark.py` | production tool (PAID) | **KEEP** | 24 refs; writes `reports/vision_only/**`; scoring imported by `score_report_dir.py` |
| `export_takeoff_excel.py` | production tool | **KEEP** | `docs/PIPELINE-GROUND-TRUTH.md:439` (client-ready workbook) |
| `golden_convergence.py` | production gate (PAID) | **KEEP** | README.md:670; phase-20 plans (20-13/20-14) name it the accuracy gate |
| `setup_golden_fixtures.sh` | production support | **KEEP** | README.md:635 (golden fixture setup for operators) |
| `geom_probe.py` | offline R&D probe (FREE) | **KEEP** | `docs/PIPELINE-GROUND-TRUTH.md:188,236` — "iterate the deterministic geometry offline for FREE" |
| `fusion_probe.py` | offline R&D probe (FREE) | **KEEP** | same, lines 189, 237 |
| `scale_probe.py` | offline R&D probe (FREE) | **KEEP** | `docs/PIPELINE-GROUND-TRUTH.md:241` |
| `room_probe.py` | offline R&D probe (FREE) | **KEEP** | no doc refs, but part of the active room-engine work (commits `b4e084d`…`3f54cec`, Jul 17) |
| `score_report_dir.py` | offline R&D probe (FREE) | **KEEP** | back-compat explicitly preserved per `.planning/phases/21-accuracy-learning-engine/21-17-SUMMARY.md:130` |
| `_diag_chelsea.json` | one-off scratch | **DELETE (git rm)** | 241 KB tracked JSON dump, Jun 27; zero references anywhere; git history retains it |
| `network_capture.py` | one-off scratch (StackCT era) | **DELETE (git rm)** | zero references; StackCT network sniffing superseded by plans-only mission; recoverable from git |
| `diagnose_fixture.py` | one-off scratch | **DELETE (git rm)** | zero references |
| `audit_plan_sets.py` | one-off (StackCT era) | **ARCHIVE** (e.g. `scripts/archive/`) | referenced only by historical `.planning/phases/14-stackct-plan-sets/` docs (14-DISCOVERY.md:4); StackCT code path still exists in `src/bobbytailor/scrape/` |
| `discover_plan_sets.py` | one-off (StackCT era) | **ARCHIVE** | same phase-14 docs; explicitly called "diagnostic tool, optional" in `14-01-SUMMARY.md:146` |

## Reclaimed-disk estimate

| Bucket | Reclaim |
|---|---:|
| `output/screenshots/` deletions (a.2) | ~1,110 MB |
| `output/` top-level run-dir deletions (a.3) | ~17 MB |
| `output/` loose files (Archive.zip, stackct dupes, webapp.log) | ~0.9 MB |
| `.codegraph/` | 2.6 MB |
| `scripts/` scratch (working tree) | ~0.25 MB |
| `data/`, `MagicMock/`, `.DS_Store` | ~0.03 MB |
| **Total** | **~1.13 GB** |

## Ordered execution plan (for the cleanup phase)

1. **First fix test isolation** (tests writing `Test_Proj_*`/`Scale_Proj_*`/`Fused_Proj_*`/`Old_Shape_*`
   run dirs, empty screenshot dirs, and `MagicMock/` into the real repo — `tests/test_reporter_accuracy.py`
   and `tests/test_blueprint_parity.py` are entry points; `tests/conftest.py:39` isolates
   `LEARNING_DB_PATH` but nothing isolates `OUTPUT_DIR` suite-wide). Otherwise junk regrows on every run.
2. Wait for the running suite to finish; then delete DELETE-bucket items.
3. Create one `output/_archive_20260802.zip` (or move to external storage) containing the
   ARCHIVE-bucket items (StackCT captures + non-referenced paid VisionOnly run dirs) before removal.
4. `git rm` the scratch scripts + `git mv` `Master.md`/`Masterv2.md` → `docs/archive/` (update the
   two comment references in `static/style.css` / `static/app.js`).
5. Verify: web Reports page still renders sheet images for every kept run (pairing table a.4);
   `sqlite3 output/learning.db ".tables"` intact; `pytest` collection unaffected.

## Explicitly protected (never touched by this plan)

`uploads/` (307 MB plan PDFs — the irreplaceable inputs), `human_inputs/`, `tests/` (incl.
`tests/fixtures/` 8.9 MB golden + `tests/fixtures/replay/` seam), `.planning/`,
`docs/PIPELINE-GROUND-TRUTH.md`, `.env`, `output/learning.db*`, `output/stackct.db`.
