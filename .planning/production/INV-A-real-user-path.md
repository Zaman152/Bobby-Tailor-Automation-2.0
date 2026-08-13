# INV-A — Does the real user path actually work?

**Investigator A · read-only · zero paid API · 2026-08-13**
Scope: browser upload → run → report for a PLANS-only project, with an optional manifest.

---

## TL;DR — blunt verdict

**The plumbing works. The deployment command and the report screen do not.**

1. **A user CAN upload a manifest through the web UI.** This was the suspected blocker and it is
   NOT one. `POST /api/pdf/manifest/upload` exists, `index.html:245-263` renders a real file
   picker plus a "Download CSV template" link, `app.js:416-441` wires it, and I proved the id
   reaches the analysis thread as `manifest_path`. Nothing here needs building.

2. **The web path and the benchmark path are the SAME function.** Both
   `scripts/vision_only_benchmark.py:753` and `web/jobs_runtime.py:362` call
   `pdf_analyzer.run_pdf_analysis()`. Every number the two paid Crow runs produced is the number
   the browser would produce. There is no second, worse pipeline hiding behind the UI. The
   plans-only guard and the manifest no-discovery guard live INSIDE that shared function
   (`pdf_analyzer.py:476-478`, `allow_discovery=False`) and are covered by
   `tests/test_pipeline_parity.py:972` / `:1015` — so the web path is protected by construction,
   not by benchmark-only scaffolding.

3. **BLOCKER — the documented production command breaks the app.**
   `docs/DEPLOYMENT.md:13` prescribes `gunicorn -w 2`. `uploads`, `object_manifests` and `jobs`
   are plain module-level dicts (`web/jobs_runtime.py:21-27`). With 2 workers, roughly half of
   every upload→run and every status poll lands on the wrong process and 404s. I reproduced it.
   **Ship `-w 1` or the user's first real session fails in front of them.**

4. **MAJOR — the report screen contradicts the honesty work the pipeline does.**
   On the real saved Crow run, the pipeline says `MEASURED 8 / NEEDS REVIEW 11 / NOT MEASURED 31`
   and `coverage_pct_items: 15.7`. The browser worksheet renders that same file as
   **"9 / 51 line items verified"** with a button labelled **"Confirm 11 remaining estimates → 100%"**.
   `reports-workspace.js` never reads `provenance`, `coverage`, `coverage_warnings` or
   `unnamed_geometry` — grep returns zero hits for all four. The downloaded CSV IS honest
   (`provenance` + `quantity_route` columns); only the screen is not.

**Can a real user get a correct take-off from the browser today?** They can get *a* take-off, and
the manifest does reach it. They cannot get a *correct* one, and — worse — the screen will not
tell them which rows are the wrong ones. Two of the three green ✓ "Confirmed" area rows on the
Crow run (`Exposed Structure` and `Sealed Concrete`, both 397,600 SF) are the ~0.5%-accurate
numbers. **The UI paints the worst errors green and the honest blanks amber.**

Shortest credible path: 1 day of web-path work (single worker + worksheet honesty) gets the app
to "safe to put in front of an estimator". Accuracy is a separate track and is the real gate.

---

## 1. What actually happens on upload → run → report

Traced and then executed. Driver scripts are in the session scratchpad
(`drive_web.py`, `worker_sim.py`, `drive_reports.py`); all stubs are test-harness-only and no
API key was used.

```
GET  /                               -> 302 /login?next=/
GET  /api/reports  (no session)      -> 401 {"error":"Authentication required"}
POST /login                          -> 302 /
POST /api/pdf/upload  (real Crow plans, 1,150,646 B)
                                     -> 200 {"upload_id":"96819250","page_count":4, pages:[
                                           {A-101 floor_plan},{A-201 elevation},{A-401 detail}...]}
POST /api/pdf/manifest/upload (crow_manifest.csv, 3 rows)
                                     -> 200 {"manifest_id":"aa552f73","count":3, objects:[...]}
GET  /api/pdf/manifest/template      -> 200  name,unit,aliases,measure,height_ft,thickness_in
POST /api/pdf/run  {upload_id, object_manifest_id}
                                     -> 200 {"job_id":"16ea20dc"}
   _pdf_job received:
     pdf_path      = uploads/96819250_Crow_-_Cass_White_Road-Plans.pdf
     project_name  = Crow Cass
     manifest_path = uploads/manifest_aa552f73.csv     <-- the manifest DOES arrive
GET  /api/status/16ea20dc            -> 200 {status, progress, current_sheet, log...}
GET  /api/reports                    -> 200 {"reports":[...]}
GET  /api/reports/<run>/preview/takeoff.json -> 200
GET  /api/reports/<run>/scale        -> 200 (sheet images for row → drawing traceability)
```

Route map: `web/blueprints/runs.py` (upload/manifest/run) → `web/jobs_runtime.py::_pdf_job`
(thread) → `pipeline/pdf_analyzer.py::run_pdf_analysis` → `TakeoffPipeline.run_project` →
`generate_report` writes `output/<Project>_<ts>/{takeoff.json, takeoff_summary.csv, raw_items.csv,
calculations.csv, summary.txt, coverage.json}` → `web/blueprints/reports.py` lists and previews it
→ `static/js/reports-workspace.js` renders it.

No 500s anywhere. The auth gate (`web/app.py:110-117`) correctly 401s API calls and 302s pages.
`tests/test_blueprint_parity.py` + `tests/test_object_manifest.py`: **48 passed** offline.

Both target projects parse fine offline: Crow 4 pp, Bob's Discount 7 pp
(`A2.0 title_sheet, A8.0 floor_plan, A2.0 schedule, D1.0 floor_plan, C402.4 elevation,
A156.10 schedule, A8.3 floor_plan`).

## 2. Manifest through the web UI — NOT a blocker

`object_manifests` is populated by `runs.py:267` from the browser upload, not by a CLI flag or a
hand-placed file. The UI hint text at `index.html:250-254` explains the contract correctly
("name + unit, no quantities … guarantees every listed object appears in the take-off — flagging
any it cannot find"), and the saved Crow run confirms that guarantee is real: `Columns-H-35'`
appears with `source=manifest_missing`, `provenance=NOT MEASURED`.

Two residual gaps, both small:
- The manifest is attached to the **PDF page's** run form and to the StackCT form; there is no way
  to attach a manifest to a project once and reuse it. Small projects, low pain.
- Nothing tests the `object_manifest_id → manifest_path` hop (`grep object_manifest_id tests/`
  returns nothing). It works today; a refactor could silently drop it.

## 3. Plans-only guard on the web path — HOLDS, with one hole

Structurally sound: no production module imports `devtools.companion_takeoff`
(`grep -rn companion_takeoff src/bobbytailor --include='*.py' | grep -v devtools` → empty), and
`run_pdf_analysis` passes `allow_discovery=False`. The "plans.pdf and takeoffs.pdf in one folder"
scenario is safe because **nothing scans the folder** — only the explicitly selected `upload_id`
is opened.

The hole is human, not code: **`POST /api/pdf/upload` accepted `Crow - Cass White Road-Take offs.pdf`
with a 200** and I could have run it as if it were plans. There is no filename heuristic, no
"this looks like a completed take-off" warning, and no copy anywhere in the UI stating the
plans-only contract. On a 4-page take-off PDF the app would happily emit a confident, meaningless
report.

## 4. Does the UI surface the phase 23/24/28 honesty work? — NO (except one buried tab)

`grep -n "provenance\|coverage\|NOT MEASURED\|unnamed_geometry\|quantity_route" reports-workspace.js`
→ **zero hits**. `rowStatus()` (`reports-workspace.js:361-371`) reads only `source`, `quantity`,
`needs_review`, `auto_verified`.

Replaying that exact function over the real saved run
`.planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_194607/takeoff.json`:

| | browser worksheet says | takeoff.json says |
|---|---|---|
| labels | Needs review 42 · Confirmed 9 | NOT MEASURED 31 · NEEDS REVIEW 11 · MEASURED 8 · STANDARD ITEM 1 |
| headline | **"9 / 51 line items verified (18%)"** | `coverage_pct_items: 15.7`, `items_not_measured: 31` |
| call to action | **"Confirm 11 remaining estimates → 100%"** | `!! 31 expected line item(s) have NO measurement path — do NOT read their blank quantity as zero` |

Consequences, concretely:

- **NOT MEASURED is rendered as "Needs review" with the cell text `enter value`.** `Columns`,
  `Canopy`, `Concrete Curb`, `Dock Leveler` … all 31 look like rows the app *could* have done and
  merely wants confirmed. The distinction phase 23 built — *the app has no measurement path for
  this* — does not exist on screen.
- **The green ✓ "Confirmed" badge is where the worst numbers live.** The nine green rows include
  `Exposed Structure 397,600 SF` and `Sealed Concrete 397,600 SF` — the two items measured at
  ~0.5% accuracy. They carry no review flag, so the UI marks them done.
- `coverage.json` is written and is fetchable (`/api/reports/<run>/preview/coverage.json` → 200)
  but **no UI element links it** — it is absent from the file lists in `reports.py:125-131` and
  `:195-201`, and from the Downloads panel.
- `unnamed_geometry` (34 entries on this run — geometry that WAS measured but never named) is in
  the JSON and rendered nowhere.
- The one honest surface is the **"Run Log" tab**, which dumps `summary.txt` verbatim
  (`reports-workspace.js:1247-1253`) — and that file does carry the full COVERAGE block,
  `NOT MEASURED 31 ← do NOT read these as zero`, and the wall-height / silhouette cross-check
  warnings. It is behind a tab named "Run Log", two clicks from a screen that says the opposite.
- The **downloaded CSV is honest**: `takeoff_summary.csv` header is
  `item,quantity,unit,confidence,needs_review,source,review_notes,source_sheets,line_count,provenance[,quantity_route]`
  (`reporter.py:1084-1086`). So the artifact and the screen disagree, and the screen is the one
  the user reads first.

## 5. Single-worker constraint — reproduced, BLOCKER as documented

`docs/DEPLOYMENT.md:13` → `gunicorn -w 2 -b 127.0.0.1:5050 app:app --timeout 300`.
State that must be shared and is not: `jobs`, `uploads`, `object_manifests`
(`web/jobs_runtime.py:21-27`), plus the rate limiter's `memory://` default
(`web/auth.py:33`, already flagged at `DEPLOYMENT.md:81`).

Two independent app processes, same `uploads/` dir, replaying the ids the first one issued:

```
WORKER A: upload_id=6ed29e9f manifest_id=7a2f6403 (both live in THIS process only)
WORKER A: POST /api/pdf/run     -> 200 {'job_id': '541af909'}
--------
WORKER B: POST /api/pdf/run     -> 404 {'error': 'Upload not found or expired'}
WORKER B: GET /api/status/541af909 -> 404 {'error': 'Job not found'}
WORKER B: GET /api/jobs/active  -> 200 {'active': False, 'job': None}
```

What the user sees with `-w 2`: "Upload not found or expired" on ~half of Analyze clicks; and when
the run does start, the progress monitor polls `/api/status/<id>`, hits the other worker, and
`pollJobMonitor` does `if (!res.ok) return;` (`app.js:620`) — it **swallows the 404 and keeps
polling forever**. The bar sits at 0% while a paid run completes invisibly in the background.

Two further multi-worker consequences worth naming: the single-active-job guard
(`register_job`, `jobs_runtime.py:48-53`) is per-process, so two paid runs can execute
simultaneously (double spend, concurrent writes to the same SQLite learning store); and a gunicorn
worker restart between upload and run silently invalidates every `upload_id`/`manifest_id`, since
neither dict has any persistence or TTL and `uploads/` is never cleaned.

`web/blueprints/verify.py` is fine — every override writes to a file in the run folder, so the
verification worksheet survives a restart and would survive multi-worker.

## 6. Deployment friction not in the doc

`config.py:116-140` hard-requires `STACKCT_EMAIL`, `STACKCT_PASSWORD` **and** `ANTHROPIC_API_KEY`
at import; a plans-only customer with no StackCT account cannot boot the app without inventing
values. And `create_app()` unconditionally runs `prefetch_in_background()`
(`web/app.py:73-75`) plus a 24-h APScheduler StackCT sync — in my first drive that spawned
Playwright/Chromium and produced a live login attempt at startup. For the stated deployment
(plans uploaded in a browser, StackCT never used) both are pure liability.

---

## Evidence index

- Driver scripts (scratchpad, not committed): `drive_web.py`, `worker_sim.py`, `drive_reports.py`
- Real run replayed: `.planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_194607/`
- Offline suite: `pytest tests/test_blueprint_parity.py tests/test_object_manifest.py` → 48 passed
- Real PDFs used read-only: `uploads/Crow - Cass White Road-Plans.pdf`,
  `uploads/Crow - Cass White Road-Take offs.pdf`, `uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf`
- Zero paid API calls: `_pdf_job` was replaced with a capture stub in every drive.
