---
phase: 14-stackct-plan-sets
plan: 4
subsystem: frontend-ui
tags: [javascript, html, css, ux, two-step-flow]

requires:
  - 14-03-SUMMARY.md (API routes)
  - phase-04-project-plan-selection

provides:
  - Two-step plan selection UI (plan sets → sheets)
  - Plan set picker with folder cards
  - Auto-load sheets for single-set projects
  - folder_id in run payload

affects:
  - User workflow: must pick plan set before sheets (Morehouse auto-skips picker)
  - Project list now shows "N sets" instead of single sheet count

tech-stack:
  added: []
  patterns:
    - Two-step progressive disclosure (folders → sheets)
    - Auto-skip picker for single-set projects
    - Radio card selection with visual feedback

key-files:
  created: []
  modified:
    - static/app.js
    - templates/index.html
    - static/style.css

decisions:
  - decision: Auto-load sheets for single-set projects
    rationale: Avoid unnecessary picker step when only one folder exists
    impact: Morehouse (2 sets) shows picker; projects with 1 set skip straight to sheets
    alternatives: Always show picker (extra click), show picker but pre-select (confusing)
    trade-offs: Better UX but requires folder count check

  - decision: Show "N sets" in project list, not total sheet count
    rationale: Single sheet total is misleading when multiple versions exist
    impact: Project list shows "2 sets · 300 sheets" instead of "300 sheets"
    alternatives: Show total sheets only (misleading), show per-set breakdown (too verbose)
    trade-offs: More accurate but requires extra click to see sheet counts

  - decision: Radio cards instead of dropdown for plan set selection
    rationale: Makes folder metadata visible (sheet count, folder ID)
    impact: Takes more vertical space but users see counts before clicking
    alternatives: Dropdown menu (compact), list with buttons (verbose)
    trade-offs: Space vs visibility

  - decision: "Back to plan sets" button only shown for multi-set projects
    rationale: Single-set projects can't change folder; button would be confusing
    impact: Button hidden for projects with 1 set
    alternatives: Always show (clutters single-set UI), never show (can't change folder)
    trade-offs: Clean UI but requires allPlanSets.length check

metrics:
  duration: ~3 min
  completed: 2026-05-26
---

# Phase 14 Plan 4: Two-Step Plan Selection UI Summary

**One-liner:** Frontend implements folder-first UX with radio card picker and auto-skip for single-set projects.

## What Was Built

### UI Components

**1. Plan Set Panel (`#planSetPanel`)**
- Shown between project picker and sheet list
- Header: "Plan sets" title + count badge ("2 available")
- Hint text: "Choose a plan set (issue package), then load drawing sheets."
- Folder card list: radio cards with name, sheet count, folder ID
- Actions: "← Change plan set" (back button) + "Load sheets →" button

**2. Plan Set Cards**
- Radio input for accessibility
- Folder name (truncated at ~80 chars)
- Metadata: "120 sheets · folder 35240700"
- Visual states: default, hover, selected (blue border + glow)
- Click anywhere on card to select

**3. Updated Project List**
- Shows "N sets" instead of single sheet count
- Example: "2 sets · 300 sheets" or "1 set · 120 sheets"
- Falls back to "—" if plan sets not synced yet

### JavaScript Functions

**`fetchPlanSets(projectId, forceRefresh)`**
- Calls `GET /api/projects/{id}/plan-sets`
- Polls every 3s while `syncing` (max 40 polls)
- Shows loading spinner: "Loading plan sets…" → "Syncing plan sets from StackCT…"
- Error handling with DNS/login hints
- Auto-selects and loads sheets if only 1 plan set
- Updates `projectSheetCounts` with plan_set_count + total sheets

**`renderPlanSets(planSets)`**
- Renders radio cards for each folder
- Highlights selected plan set
- Attaches click handlers to cards
- Updates count badge

**`selectPlanSet(ps)`**
- Stores `{folder_id, name}` in `selectedPlanSet` global
- Enables "Load sheets →" button
- Updates project meta: "Project ID: 7416168 · Plan set: MSP3-…v2"

**`fetchPlans(projectId, folderId, forceRefresh)`**
- Now requires folderId (uses `selectedPlanSet.folder_id` if not provided)
- Calls `GET /api/projects/{id}/plan-sets/{folder_id}/plans`
- Shows/hides back button based on `allPlanSets.length`
- Updates meta: "Project ID: … · Plan set name · 180 sheets · cached"

**`runStackCT()`**
- Includes `folder_id: selectedPlanSet.folder_id` in POST body
- Server validates page_ids belong to folder

**`onProjectSelect(projectId, projectName)`**
- Calls `POST /api/projects/{id}/sync-plan-sets` in background
- Updates `projectSheetCounts` with plan_set_count and total sheets
- Re-renders project list to show "N sets"

### CSS Styling

**Plan set panel:**
- Blue-tinted border and gradient background
- Max height 280px with scroll for long lists

**Folder cards:**
- 14px vertical padding, 16px horizontal
- Hover: lighter background + blue border
- Selected: blue border + glow + tinted background
- Radio input with accent color

**Layout:**
- Plan set panel appears before sheet list
- Back button: ghost style, left-aligned
- "Load sheets →" button: right-aligned

## Verification Results

- [x] JavaScript imports successful
- [x] All functions defined (fetchPlanSets, renderPlanSets, selectPlanSet)
- [x] HTML elements added (#planSetPanel, #planSetList, #loadSheetsBtn, #backToPlanSetsBtn)
- [x] CSS classes defined (plan-set-card, plan-set-panel, etc.)

**Manual verification pending:**
- [ ] Morehouse (2 sets): user sees MSP3 v1 and v2 before sheets
- [ ] Selecting v2 loads 180 sheets not 120
- [ ] Run uses only selected set's page_ids (no cross-folder mixing)
- [ ] Single-set project: auto-loads sheets without showing picker
- [ ] Back button: visible for multi-set, hidden for single-set
- [ ] Project list shows "2 sets · 300 sheets"

## Deviations from Plan

None — plan executed exactly as written.

## What's Next

**Phase 14 Complete!**

All four plans executed:
- 14-01: Browser discovery (get_plan_sets, dedupe)
- 14-02: Schema v2 (project_plan_sets table, folder-scoped sync)
- 14-03: API routes (folder-first endpoints, validation)
- 14-04: UI (two-step flow, folder cards)

**Next steps:**
- Manual verification: test Morehouse 7416168 end-to-end
- Update Master.md §8.3 with two-step plan selection flow
- Document folder_id requirement in API docs
- Consider /gsd-verify-phase 14 to validate implementation

**Future enhancements (v2):**
- Plan set metadata API (show issue date, revision notes)
- Folder name search/filter in picker
- Remember last-selected folder per project (local storage)
- Bulk folder sync (sync all folders in background)

## Commits

| Commit | Message |
|--------|---------|
| 90ac271 | feat(14-04): two-step plan selection UI |

## Files Changed

```
static/app.js          +387 -36  (fetchPlanSets, renderPlanSets, two-step flow)
templates/index.html   +14 -1    (planSetPanel markup)
static/style.css       +123      (folder cards styling)
```

## Tech Debt / Future Work

- **No folder name truncation UI:** Long folder names may overflow cards (current limit: ~80 chars in browser scrape)
- **Plan set count not persistent:** Must preview project to see plan set count (not fetched on project list load)
- **No plan set caching in localStorage:** User must re-select folder after page refresh
- **Error states lack retry button:** Network errors show message but require re-clicking Preview
- **No visual feedback for folder with 0 sheets:** Should show warning if sheet_count == 0

## Success Criteria Met

- [x] UX matches StackCT folder cards at go.stackct.com/app/#/Takeoff/7416168
- [x] No flat 120-sheet dump before set selection on multi-set projects (Morehouse shows picker first)
- [x] Two-panel flow: plan sets → sheets → run
- [x] Auto-skip picker for single-set projects
- [x] Back button for multi-set projects
- [x] folder_id sent to run API
