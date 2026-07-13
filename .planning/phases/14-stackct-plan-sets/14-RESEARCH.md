# Phase 14 Research: StackCT Plan Sets & Folders (Version Selection)

**Researched:** 2026-05-26  
**Trigger:** User clarification — Preview Plans must not load all sheets at once. Example: *Morehouse Spelman - 70% CDs Set* has **two plan versions**; user picks folder/version first, then sheets, then preview/run.

---

## 1. What went wrong (current app)

### Intended UX (user)

```
Project → Preview Plans
  → Step A: "2 plan sets" (or folders / versions) — pick one
  → Step B: Sheet checklist for THAT set only
  → Run Selected / calculations on chosen sheets only
```

### Built UX (Phase 4 + 13)

```
Project → Preview Plans
  → Immediately scrape ALL [data-page-id] on #/Takeoff/{project_id}
  → Flat list of 120 checkboxes (may mix multiple folders/versions)
```

### Root cause

| Layer | Assumption | Reality in StackCT |
|-------|------------|-------------------|
| `browser.get_all_page_ids()` | One thumbnail grid = one plan list | Pages live under **folders**; grid may show all folders, one folder, or wrong default |
| `project_plans` DB table | `(stackct_id, page_id)` unique | Missing **`folder_id` / `plan_set_id`** — cannot serve per-version preview |
| Sheet count on list | Total pages in DB | Should be **"N sets"** or **"Set A: 60 · Set B: 60"**, not a single misleading total |
| Master.md §8.3 | Flat sheet checklist | Never specified folder/version step |

**Morehouse (7416168) — confirmed live (2026-05-26):**

| Plan set (folder) | `data-folder-id` | Sheets |
|-------------------|------------------|--------|
| MSP3- ISSUE FOR BID-COMBINED**v1** | `35240700` | **120** |
| MSP3- ISSUE FOR BID-COMBINED**v2** | `35240694` | **180** |

These match the two folder cards on `https://go.stackct.com/app/#/Takeoff/7416168` (truncated in UI as “MSP3- ISSUE F…”).

Our old `get_all_page_ids()` without clicking a folder returned **120** page IDs — effectively **v1 only**, not both sets. Picking the wrong set (or merging) would break takeoff accuracy.

---

## 2. How StackCT actually organizes plans

From [StackCT developer docs](https://www.stackct.com/developers-docs-tutorials/) and help center:

1. **Project** — container (what we list today as 26 cached jobs).
2. **Folders** — under *Plans and Documents*; separate architectural vs electrical, **revisions/addenda**, custom names (e.g. version labels).
   - Default roots: **Plans**, **Bookmarks**, **Supporting Documents**
   - API: `GET /api/v2/Projects/{projectId}/Folders`, nested `GET /api/v2/Folders/{folderId}/Folders`
3. **Pages** — drawing sheets inside a folder; have `page_id` (what we scrape as `data-page-id`).
4. **Version sets** (Documents workflow) — group of documents issued on a date; revisions of same sheet name. Related but distinct from folder tree; may matter for some jobs.

**Terminology warning:** StackCT API uses **"Takeoff"** for a *measurement line item type* (area, linear, count), not for "plan set". In UI copy use **plan set**, **folder**, or **version** — not "takeoff" for this step.

---

## 3. What each project type needs (audit plan)

Run a **discovery pass** on a representative sample (browser + network log), not only Morehouse:

| Project | ID (known) | Why include |
|---------|------------|-------------|
| Morehouse Spelman - 70% CDs Set | 7416168 | User report: 2 versions |
| ATL 081 - GMP R2 | 7414097 | Large set (~120 sheets); login/cache issues |
| Bid for Baking Social | (cache) | Successful past run |
| Small retail job (~8 sheets) | TBD | Single-folder baseline |
| Project with only Supporting Docs | TBD | Edge case |

**Per project, record:**

- Count of **top-level folders** under Plans (exclude Bookmarks unless needed)
- Sheet count **per folder** vs **total** on default `#/Takeoff/{id}` view
- Whether URL changes when selecting a folder (hash/query params)
- Whether `agent.stackct` API calls return folder-scoped page lists (preferred if stable)

**Deliverable:** `14-DISCOVERY.md` table filled from one scripted Playwright run (read-only).

---

## 4. Recommended target architecture

### 4.1 Data model (SQLite v2)

```sql
-- Plan organization layer (NEW)
CREATE TABLE project_plan_sets (
    stackct_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL,          -- StackCT folder id
    name TEXT NOT NULL,
    parent_folder_id INTEGER,
    sheet_count INTEGER,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, folder_id)
);

-- Extend pages (BREAKING: re-sync required)
CREATE TABLE project_plans (
    stackct_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL DEFAULT 0,
    page_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL DEFAULT '',
    sheet_type TEXT,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, folder_id, page_id)
);
```

- **Project list:** show `plan_set_count` and optionally top set names; avoid one big `sheet_count` until a set is chosen.
- **TTL:** sync folder list on project select; sync pages per folder on set select or background warm.

### 4.2 API shape

| Endpoint | Purpose |
|----------|---------|
| `GET /api/projects/<id>/plan-sets` | List folders/versions `{folder_id, name, sheet_count, synced_at}` |
| `GET /api/projects/<id>/plan-sets/<folder_id>/plans` | Sheets for one set only |
| `POST /api/projects/<id>/sync-plan-sets` | Warm folder index |
| `POST /api/projects/<id>/plan-sets/<folder_id>/sync-plans` | Warm sheets for one folder |

Keep existing `/plans` as deprecated alias or redirect with `?folder_id=` required.

### 4.3 UI flow (Master §8.3 update)

```
[Preview Plans →]
┌─ Plan sets (2) ─────────────────────────────┐
│ ○ 70% CDs Set (Issued 2025-03-01)  60 sh  │
│ ○ 100% CDs Set (Issued 2025-06-15)  60 sh │
└───────────────────────────────────────────┘
        ↓ user selects one
┌─ Sheets in "70% CDs Set" ─────────────────┐
│ ☑ Select All  [Filter by type ▼]         │
│ ☑ A1.01 Floor Plan L1                     │
│ ...                                       │
│ [Run Selected Plans (N) →]                │
└───────────────────────────────────────────┘
```

`page_ids` sent to `/api/run/stackct` must be scoped to the selected `folder_id` (validate server-side).

### 4.4 Browser / sync implementation options

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **A. DOM folder tree** on Plans page | No API key; matches current Playwright approach | Fragile selectors; must click each folder | **v1** if DOM is stable |
| **B. Intercept `agent.stackct` JSON** after login | Faster than clicking; folder-scoped pages | Undocumented; may break | **Spike in discovery** — if HAR shows stable folder+pages endpoints, prefer over A |
| **C. Official StackCT REST API** (`/api/v2/...`) | Stable contract | Requires API credentials not in `.env` today; legal/onboarding | **v2** if Bobby has API access |

**Do not** parallelize browser logins. One lock; sync folder list once per project, then one folder's pages at a time.

---

## 5. Impact on existing features

| Feature | Change |
|---------|--------|
| Phase 13 DB cache | Schema migration + re-sync all projects |
| Sheet counts API | Return `plan_sets` summary, not flat `counts[id]` only |
| Scraper `run_project_scrape` | Require `folder_id`; filter pages to that folder |
| Reports | Store `folder_id` / set name in `takeoff.json` metadata |
| PDF mode | Unchanged |

---

## 6. Why Phase 13 alone could not fix this

Phase 13 solved **how often** we hit StackCT (cache, lock, TTL). It did not model **what** we fetch (folder boundary). Caching 120 merged pages makes the wrong behavior **faster**, not correct.

---

## 7. Recommended execution order

1. **Discovery script** (`scripts/discover_plan_sets.py`) — login once, loop 5 projects, output folder tree + page counts (no Claude spend).
2. **Update Master.md §8.3** — two-step plan selection wireframe.
3. **Phase 14 plans** — schema → browser/sync → API → UI → scraper validation.
4. **Re-verify** Morehouse + ATL 081 + one small job in browser before merge.

**Do not** mark Phase 4/9/13 complete for "plan selection" until Phase 14 passes verifier.

---

## 8. Open questions for Bobby (human)

1. For "two versions" — are these **folders under one project**, **two StackCT projects**, or **version sets** in Documents?
2. Should runs ever combine sheets from **multiple** folders in one job, or always one folder per run?
3. Is official StackCT API access available (would avoid DOM fragility)?

---

## Metadata

**Confidence:** HIGH on folder/version concept; MEDIUM on exact DOM/API until discovery script runs on live account.

**Next command:** `/gsd-plan-phase 14` after user confirms discovery sample projects and answers §8.
