# Phase 17 — UAT Checklist: Production Takeoff Pipeline

**Status:** AWAITING SIGN-OFF  
**Created:** 2026-06-02  
**Signed by:** _____________  
**Signed date:** _____________

---

## Purpose

Verify that the full production pipeline is ready for client demos and VPS deployment. Each scenario below must be executed manually against a live StackCT project before Phase 17 is marked complete.

---

## Scenario 1 — Full fresh run (10 sheets)

**Goal:** End-to-end run produces a complete, error-free report.

**Steps:**

1. Open the web UI at `http://localhost:5050` (or your VPS URL).
2. Select a project with at least 10 available sheets.
3. Choose any 10 sheets and click **Run**.
4. Observe the progress bar moving through Capture (0–40%) → Analyze (40–90%) → Report (95–100%).
5. When complete, open `output/<ProjectName>_<timestamp>/takeoff.json`.

**Pass criteria:**

- [ ] Progress bar completes to 100% without freezing or error toast.
- [ ] `takeoff.json` exists and contains `sheets_processed: 10`.
- [ ] `calculations.csv` and `summary.txt` are present in the run folder.
- [ ] `manifest.json` exists inside `output/screenshots/<ProjectName>_<timestamp>/`.
- [ ] No `"error"` key in `takeoff.json` at the root level.

---

## Scenario 2 — Re-run with REUSE_SCREENSHOTS (same 10 sheets)

**Goal:** Capture completes in < 30 seconds when all screenshots are cached.

**Pre-condition:** Scenario 1 completed successfully.  
**Pre-condition:** `REUSE_SCREENSHOTS=true` in `.env` (this is the default).

**Steps:**

1. Select the **same** project and the **same** 10 sheets.
2. Click **Run** and note the wall-clock time for the Capture phase (0 → 40% on progress bar).

**Pass criteria:**

- [ ] Capture phase (0–40% on bar) finishes in **< 30 seconds**.
- [ ] Log messages contain `"Using cached screenshot"` for each of the 10 sheets.
- [ ] `browser.download_drawing_image` is not called (verify via logs — no "Screenshotting" entries for cached sheets).
- [ ] Full report is produced identically to Scenario 1.

---

## Scenario 3 — Kill server mid-analyze → analyze_only recovery

**Goal:** After a mid-run crash, `analyze_only` resumes from where it stopped.

**Steps:**

1. Start a fresh 10-sheet run.
2. During the **Analyze** phase (progress bar between 40–90%), stop the Flask server (`Ctrl-C` or `kill <pid>`).
3. Confirm the run folder exists at `output/screenshots/<ProjectName>_<timestamp>/`.
4. Restart the server.
5. Use `analyze_only` to recover:
   ```json
   POST /api/run/stackct
   {
     "project_name": "<ProjectName>",
     "analyze_only": true
   }
   ```
6. Watch the job complete.

**Pass criteria:**

- [ ] Server restart succeeds without database corruption.
- [ ] `analyze_only` run starts without error.
- [ ] Sheets already analyzed (those with `{page_id}_analysis.json` present) are **skipped** (logged as "Using cached analysis").
- [ ] Only un-analyzed sheets are sent to Claude.
- [ ] Final report is produced with all sheets accounted for.
- [ ] `mode_detail: "analyze_only"` appears in `GET /api/jobs/<job_id>` response.

---

## Scenario 4 — Sheet with slash in name

**Goal:** A sheet named with a `/` (e.g., `"A/B-Floor Plan"`) does not crash the capture or report.

**Steps:**

1. In StackCT, confirm or note any sheet whose name contains `/`.  
   *(If none exist live, you may test by running the unit test: `pytest tests/test_scraper_pipeline.py::TestPartialFailure::test_slash_in_sheet_name_does_not_crash -v`)*
2. Include that sheet in a run alongside 2–3 normal sheets.
3. Let the run complete.

**Pass criteria:**

- [ ] Run completes without a `FileNotFoundError` or `OSError`.
- [ ] The slash-named sheet appears in the report (or in `sheets_failed` with a capture reason — not a path error).
- [ ] Screenshot filename for that sheet uses `-` instead of `/` (e.g., `002_A-B-Floor_Plan.jpg`).

---

## Scenario 5 — Cancel at sheet 5 → partial or clean cancel

**Goal:** Cancelling mid-run produces either a partial report or a clean cancellation with no data corruption.

**Steps:**

1. Start a 10-sheet run.
2. Click **Cancel** (or call `POST /api/jobs/<job_id>/cancel`) after the 5th sheet appears in the log.
3. Wait for the job to finish.

**Pass criteria:**

- [ ] Job transitions to status `"cancelled"` or `"partial"` — never `"running"` stuck state.
- [ ] If sheets were completed before cancel: a partial `takeoff.json` exists with `"partial": true`.
- [ ] No corrupted `manifest.json` (must be valid JSON parseable by `json.load`).
- [ ] UI shows a cancellation message — not a silent hang.
- [ ] Re-running the same project immediately after cancel works without errors.

---

## Sign-off

| Scenario | Tester | Result | Notes |
|----------|--------|--------|-------|
| 1 — Fresh 10-sheet run | | ☐ Pass / ☐ Fail | |
| 2 — Reuse screenshots < 30 s | | ☐ Pass / ☐ Fail | |
| 3 — Crash recovery via analyze_only | | ☐ Pass / ☐ Fail | |
| 4 — Slash in sheet name | | ☐ Pass / ☐ Fail | |
| 5 — Cancel at sheet 5 | | ☐ Pass / ☐ Fail | |

**All scenarios passing?** ☐ Yes / ☐ No (see notes)

**Phase 17 approved for production?** ☐ Yes / ☐ No

**Signed:** _________________________  
**Date:** _________________________
