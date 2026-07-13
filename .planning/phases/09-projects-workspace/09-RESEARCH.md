# Phase 09: Projects Workspace — Research

**Phase Goal:** The Projects page delivers the full StackCT workflow: pick scope, preview plans, select sheets, run.

**Depends on:** Phase 4 (StackCT Plan Selection APIs), Phase 8 (UI Shell Foundation)

**Requirements:** UI-04

---

## 1. Dependency Analysis

### Phase 4 Dependencies (StackCT Plan Selection)

Phase 4 provides the backend APIs that Phase 09 UI must consume:

| Phase 4 Plan | Artifact | Phase 09 Consumes |
|--------------|----------|-------------------|
| 04-01 | `GET /api/projects/<id>/plans` | Projects page fetches plan list after project selection |
| 04-01 | `project_cache` helper extensions | Sheet count metadata for project list |
| 04-02 | `page_ids` param on `/api/run/stackct` | "Run Selected" sends only checked plan IDs |
| 04-03 | Minimal plan-selection HTML (if any) | Phase 09 replaces/enhances with polished UI |

**Required Phase 4 Artifacts:**
- `GET /api/projects/<id>/plans` returns `{plans: [{page_id, sheet_name, sheet_type}, ...], project_name, project_id}`
- `/api/run/stackct` accepts optional `page_ids: number[]` parameter
- `scraper.py` filters to only those `page_ids` when provided

### Phase 8 Dependencies (UI Shell Foundation)

Phase 8 provides the layout shell that Phase 09 slots into:

| Phase 8 Plan | Artifact | Phase 09 Consumes |
|--------------|----------|-------------------|
| 08-01 | Base layout template + sidebar | Projects is a sidebar nav item |
| 08-02 | Theme tokens (colors, typography) | Projects page uses CSS variables |
| 08-03 | `static/app.js` + `static/style.css` | Projects JS/CSS lives in these files |

**Required Phase 8 Artifacts:**
- Fixed sidebar with nav items (Projects active by default)
- CSS variables for dark theme: `--bg-card`, `--text-primary`, `--accent-blue`, etc.
- Page container structure for content area

---

## 2. Master §8.3 Layout Analysis

The Master document specifies the Projects page layout in §8.3:

### Scope Toggle
```
┌─────────────────────────────────────────────────────────────────┐
│  SCOPE                                                           │
│  ○ All Projects   ● Specific Project                            │
└─────────────────────────────────────────────────────────────────┘
```
**Current State:** Exists in `index.html` as `.mode-toggle` buttons — functional.

### Project List (Specific Project mode)
```
Search: [____________________] ← live filter on project list

Project List:
┌───────────────────────────────────────────────────────────────┐
│  ● Office Complex – Downtown     │ 12 sheets   ID: 7409312    │
│  ○ Retail Build-Out – Unit 4A    │ 8 sheets    ID: 7388201    │
│  ○ Parking Structure Phase 2     │ 24 sheets   ID: 7412009    │
└───────────────────────────────────────────────────────────────┘
```
**Current State:** Uses `<select>` dropdown — needs upgrade to searchable radio list with sheet counts.

### Plan Selection Panel (after Preview Plans)
```
[PREVIEW PLANS →]  ← enabled only when project selected

┌── Plan Selection Panel (appears after clicking Preview Plans) ──┐
│  ☑ Select All  [ Filter by type ▼ ]                              │
│                                                                   │
│  ☑  A1.01   Floor Plan Level 1          [Floor Plan]             │
│  ☑  A1.02   Floor Plan Level 2          [Floor Plan]             │
│  ☐  E1.01   Electrical Riser Diagram    [Electrical]             │
│  ☑  E2.01   Panel Schedule HM1          [Schedule]               │
│  ...                                                             │
│                                                                   │
│  [RUN SELECTED PLANS (4) →]                                      │
└──────────────────────────────────────────────────────────────────┘
```
**Current State:** Does not exist — needs full implementation.

### Sheet Type Badges (color coding)
- Floor Plan → blue
- Electrical → yellow
- Mechanical → orange
- Schedule → purple
- Other → gray

---

## 3. Current UI Code Analysis

### File: `templates/index.html`

**Existing Scope Toggle (lines 250-260):**
- Two `.mode-btn` buttons: "All Projects" and "Specific Project"
- JavaScript `setMode(mode)` toggles between them
- Works correctly, matches Master design

**Existing Project Selection (lines 262-277):**
- Uses `<select>` dropdown populated from `/api/projects`
- Shows project name only (no sheet count)
- No search/filter capability
- **Needs:** Replace with searchable list showing sheet counts

**Existing Run Button (lines 279-282):**
- Single "Run Estimation" button
- Posts to `/api/run/stackct` with `mode`, `project_id`, `project_name`
- **Needs:** Add "Preview Plans" step before run

**Missing Components:**
1. Project search input
2. Project list with radio selection (not dropdown)
3. Sheet count display per project
4. "Preview Plans" button
5. Plan Selection Panel (checkboxes, Select All, type filter)
6. Sheet type badges
7. "Run Selected Plans" button with count

---

## 4. API Integration Points

### Existing APIs (working)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/projects` | GET | List all projects (cached) |
| `/api/projects?refresh=1` | GET | Force live fetch |
| `/api/run/stackct` | POST | Start analysis job |

### Required APIs (from Phase 4)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/projects/<id>/plans` | GET | List drawing pages for a project |

### Run Endpoint Enhancement (from Phase 4)

Current `/api/run/stackct` body:
```json
{
  "mode": "all" | "specific",
  "project_id": 123,
  "project_name": "Office Complex"
}
```

Phase 4 enhanced body:
```json
{
  "mode": "all" | "specific",
  "project_id": 123,
  "project_name": "Office Complex",
  "page_ids": [456, 789, 1011]  // optional: only these sheets
}
```

---

## 5. Implementation Approach

### Plan 09-01: Projects Page Layout

**Scope:** Implement Master §8.3 layout structure
- Searchable project list with sheet counts
- Radio selection for projects
- "Preview Plans" button (disabled until project selected)
- Plan Selection Panel container (hidden until Preview clicked)

**Depends on:**
- Phase 8 plans for base layout/theme
- Phase 4-01 to know sheet count per project (may cache with projects)

### Plan 09-02: Wire Plan Selection + Run

**Scope:** Connect UI to Phase 4 backend APIs
- Fetch plans via `GET /api/projects/<id>/plans` when Preview clicked
- Render plan checkboxes with sheet type badges
- Implement Select All / type filter
- Wire "Run Selected" to POST `/api/run/stackct` with `page_ids`

**Depends on:**
- Plan 09-01 for UI structure
- Phase 4-01 for plans API
- Phase 4-02 for `page_ids` on run endpoint

---

## 6. Success Criteria (from ROADMAP)

1. User toggles between "All Projects" and "Specific Project" scope modes ✓ (exists)
2. Specific-project mode shows searchable project list with sheet counts (needs 09-01)
3. "Preview Plans" opens the plan-selection panel integrated with Phase 4 APIs (needs 09-01, 09-02)
4. "Run Selected" starts analysis only for checked `page_ids` from this page (needs 09-02)

---

## 7. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Phase 4 APIs not ready | 09-01 can stub API responses; 09-02 must wait for Phase 4 |
| Sheet counts not cached | May need Phase 4-01 to extend `project_cache` to include counts |
| Sheet type inference | Phase 4 may need heuristics to classify sheets; fallback to "Other" |

---

*Research completed: 2026-05-26*
