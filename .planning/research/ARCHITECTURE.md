# Architecture Research

**Domain:** Browser automation + Vision AI extraction + Construction estimation pipeline  
**Researched:** 2026-05-26  
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                               │
│  Flask Web UI (app.py) — Tab-based interface → Sidebar Navigation       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │  Projects   │  │  PDF Upload  │  │   Reports   │  │   Settings   │  │
│  │   Selector  │  │   Analyzer   │  │   Browser   │  │    Config    │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └──────────────┘  │
└─────────┼────────────────┼─────────────────┼─────────────────────────────┘
          │                │                 │
          │ Background     │ Direct          │ File system
          │ thread         │ call            │ read
          │                │                 │
┌─────────▼────────────────▼─────────────────▼─────────────────────────────┐
│                       ORCHESTRATION LAYER                                 │
│  scraper.py — Main controller for StackCT pipeline                       │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │  • Coordinates browser → vision → calculator → reporter        │      │
│  │  • Manages page iteration with progress callbacks              │      │
│  │  • Error recovery and retry logic                              │      │
│  └───┬────────────────┬────────────────────┬───────────────────┬─┘      │
└──────┼────────────────┼────────────────────┼───────────────────┼────────┘
       │                │                    │                   │
   ┌───▼─────┐    ┌─────▼──────┐    ┌───────▼────────┐   ┌──────▼──────┐
   │ browser │    │   claude   │    │   calculator   │   │   reporter  │
   │  .py    │    │ _analyzer  │    │      .py       │   │     .py     │
   │         │    │    .py     │    │                │   │             │
   └────┬────┘    └─────┬──────┘    └────────┬───────┘   └──────┬──────┘
        │               │                    │                  │
        │               │                    │                  │
   ┌────▼──────┐   ┌────▼──────┐       ┌────▼──────┐     ┌─────▼──────┐
   │ StackCT   │   │ Claude    │       │ Estimation│     │  File I/O  │
   │ Website   │   │ Vision    │       │  Tables   │     │  CSV/JSON  │
   │ (Auth0    │   │   API     │       │  Engine   │     │  /TXT      │
   │  login)   │   │ (Anthropic│       │           │     │            │
   └───────────┘   │  Haiku/   │       └───────────┘     └────────────┘
                   │  Sonnet)  │
                   └───────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **app.py** | Flask web server, route handling, job orchestration | Web framework with threading for background jobs |
| **scraper.py** | Main pipeline orchestrator, coordinates browser→vision→calc→report | Async orchestration with callback hooks |
| **browser.py** | Playwright automation, Auth0 login, DOM scraping, canvas screenshots | Headless Chromium with high-DPI viewport |
| **claude_analyzer.py** | Image encoding, Claude API calls, JSON parsing | Vision LLM with cached prompts |
| **calculator.py** | Formula engine, waste factors, item classification | Rule-based pattern matching + math |
| **reporter.py** | CSV/JSON/TXT generation, data aggregation | File I/O with structured formatting |
| **project_cache.py** | Disk-based cache for StackCT project list (24h TTL) | JSON persistence with background refresh |
| **pdf_analyzer.py** | Alternative entry: PDF → PyMuPDF → images → same pipeline | Direct file upload, skips browser |
| **config.py** | Environment variable loading, global settings | .env with python-dotenv |

## Recommended Project Structure

**Current State:**
```
bobby-tailor/
├── app.py                    # Flask app (monolithic)
├── scraper.py                # Orchestrator
├── browser.py                # Playwright automation
├── claude_analyzer.py        # Vision extraction
├── calculator.py             # Estimation formulas
├── reporter.py               # Report generation
├── project_cache.py          # Cache layer
├── pdf_analyzer.py           # PDF mode
├── config.py                 # Settings (NEEDS FIX: hardcoded path)
├── main.py                   # CLI entry
├── templates/
│   └── index.html            # All-in-one UI (21KB, embedded CSS/JS)
├── output/                   # Generated reports + cache
│   ├── projects_cache.json
│   ├── screenshots/
│   └── {ProjectName}_{timestamp}/
└── uploads/                  # PDF uploads
```

**Target State (after refactor):**
```
bobby-tailor/
├── app.py                    # Flask app (ADD: plan/preview APIs)
├── scraper.py                # (MODIFY: add page_ids filter param)
├── browser.py                # (MODIFY: add canvas stability detection)
├── claude_analyzer.py        # (MODIFY: add cost tracking)
├── calculator.py             # (no change)
├── reporter.py               # (MODIFY: add api_usage to report)
├── project_cache.py          # (ADD: get_project_plans function)
├── pdf_analyzer.py           # (no change)
├── config.py                 # (FIX: relative .env path)
├── main.py                   # (no change)
├── templates/
│   └── index.html            # (COMPLETE REWRITE: sidebar layout)
├── static/                   # NEW: extract from HTML
│   ├── app.js                # UI logic
│   └── style.css             # Styling
├── output/                   # (no change)
└── uploads/                  # (no change)
```

### Structure Rationale

- **Flat module structure:** All core modules at root for easy import. No deep nesting needed for 10-file codebase.
- **Separation pending:** UI assets (JS/CSS) currently embedded in `index.html`. Extract to `static/` for maintainability when implementing sidebar redesign.
- **Output isolation:** Each report run gets its own timestamped folder to prevent file collisions and enable audit trail.
- **Cache strategy:** Project list cached to disk (not in-memory) so it persists across server restarts.
- **No database:** All data is ephemeral or file-based. No persistent storage beyond cache and reports.

## Architectural Patterns

### Pattern 1: Async Browser Automation with Sync Flask

**What:** Flask runs synchronously; browser automation uses async/await. Bridge with `asyncio.run_until_complete()` in background threads.

**When to use:** Playwright requires async context, but Flask/WSGI is sync-first.

**Trade-offs:**
- ✅ Allows long-running browser jobs without blocking Flask request handlers
- ✅ Each job gets isolated event loop (no cross-contamination)
- ❌ Cannot share browser context across requests (each job launches fresh browser)
- ❌ Thread-per-job model; does not scale to 100+ concurrent jobs (but not needed for this use case)

**Example:**
```python
# In app.py
def _stackct_job(job_id: str, ...):
    """Runs in background thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(run_project_scrape(...))
    loop.close()

t = threading.Thread(target=_stackct_job, args=(...), daemon=True)
t.start()
```

### Pattern 2: Callback-Based Progress Reporting

**What:** Orchestrator accepts optional `log_callback` and `progress_callback` functions. Background job passes these to scraper, which calls them during execution.

**When to use:** Long-running operations where UI needs real-time feedback.

**Trade-offs:**
- ✅ Decouples scraper from Flask (scraper works standalone in CLI mode)
- ✅ Simple to implement (no pub/sub, no WebSocket)
- ❌ Polling required on frontend (hits `/api/status/<job_id>` every 500ms)
- ❌ Log stored in-memory in `jobs` dict (lost on server restart)

**Example:**
```python
# In scraper.py
def log(msg: str):
    logger.info(msg)
    if log_callback:
        log_callback(msg)

await browser.screenshot_full_drawing(...)
log(f"[{idx}/{total}] Analyzing {sheet_name}...")
if progress_callback:
    progress_callback(idx, total, sheet_name)
```

### Pattern 3: Disk-Based Cache with Background Refresh

**What:** Project list cached as JSON file with 24h TTL. On app startup, background thread checks cache freshness and fetches live if stale.

**When to use:** Expensive API/browser operations where data changes infrequently.

**Trade-offs:**
- ✅ UI instant on reload (no 10-second browser launch wait)
- ✅ Survives server restart (cache persists to disk)
- ✅ Non-blocking refresh (background thread)
- ❌ Race condition possible during refresh (mitigated by checking `is_stale()` first)
- ❌ Single-writer assumption (breaks if multiple app instances on same filesystem)

**Example:**
```python
# In project_cache.py
def get_projects(force_refresh=False):
    cache = load_cache()
    if not force_refresh and cache and not is_stale(cache):
        return {**cache, "from_cache": True}
    # Fetch live...
```

### Pattern 4: Multi-Model LLM Routing

**What:** Sheet name used to heuristically select Claude model. Electrical/mechanical/schedules → Sonnet (smarter, more expensive). Floor plans → Haiku (cheaper, faster).

**When to use:** Cost optimization where some tasks need more intelligence than others.

**Trade-offs:**
- ✅ Saves ~70% on API costs (Haiku is 1/3 price of Sonnet)
- ✅ Minimal accuracy loss for simple floor plans
- ❌ Heuristic can misclassify (e.g., "OFFICE SCHEDULE" might route to Haiku)
- ❌ Model selection logic is in code, not configurable per-project

**Example:**
```python
# In claude_analyzer.py
def _pick_model(sheet_name: str) -> str:
    u = sheet_name.upper()
    if any(x in u for x in ["SCHEDULE", "PANEL", "RISER", "EQUIPMENT"]):
        return CLAUDE_MODEL_SCHEDULES  # Sonnet
    if u.startswith(("E", "M", "P")):  # Electrical, Mechanical, Plumbing sheets
        return CLAUDE_MODEL_SCHEDULES
    return CLAUDE_MODEL  # Haiku (default)
```

### Pattern 5: Prompt Caching for Vision Extraction

**What:** Claude's system prompt (2500+ tokens) marked with `cache_control: ephemeral`. First call per session pays full cost; subsequent calls use cached tokens (~90% savings).

**When to use:** Repeated API calls with large static prompts.

**Trade-offs:**
- ✅ Massive cost reduction (cached tokens are 1/10th price)
- ✅ No accuracy loss (exact same prompt)
- ❌ Cache expires after 5 minutes of inactivity
- ❌ Only helps multi-page runs (single-page jobs don't benefit)

**Example:**
```python
# In claude_analyzer.py
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": EXTRACTION_PROMPT,
                "cache_control": {"type": "ephemeral"}  # ← Cache this
            },
            {"type": "image", "source": {...}}
        ]
    }
]
```

## Data Flow

### Request Flow: StackCT Job

```
[User clicks "Run Project"]
    ↓
[POST /api/run/stackct] → creates job_id, spawns background thread
    ↓
[_stackct_job thread] → creates event loop
    ↓
[scraper.run_project_scrape()]
    ↓
[browser.start()] → Launch Chromium with high-DPI viewport
    ↓
[browser.login()] → Auth0 email/password flow
    ↓
[browser.get_all_page_ids(project_id)] → Scrape DOM [data-page-id] attributes
    ↓
For each page:
  ├─ [browser.screenshot_full_drawing()] 
  │    ├─ navigate_to_page() with URL retry loop
  │    ├─ _dismiss_popups() (inject CSS to hide HubSpot overlays)
  │    ├─ click "Fit to page" button
  │    ├─ sleep(5) for tile rendering ← CURRENT (fixed wait)
  │    └─ screenshot #canvas-interaction element
  │
  ├─ [claude_analyzer.analyze_drawing()]
  │    ├─ encode_image() with JPEG compression if >3.6MB
  │    ├─ _pick_model() (Haiku vs Sonnet heuristic)
  │    ├─ Claude API call with cached prompt
  │    └─ return JSON: {measurements, components, rooms, schedules, ...}
  │
  └─ [calculator.apply_estimation_tables()]
       ├─ _calculate_from_measurement()
       ├─ _calculate_from_component()
       ├─ _calculate_from_room() → 4 items per room (floor, ceiling, paint, drywall)
       ├─ _calculate_from_schedule()
       └─ return list of calculated items with formulas
    ↓
[reporter.generate_report()]
    ├─ _flatten_raw_extractions()
    ├─ _normalize_calculated()
    ├─ _group_by_sheet() / _group_by_category() / _group_by_table()
    ├─ Write to {ProjectName}_{timestamp}/:
    │    ├── takeoff.json
    │    ├── raw_items.csv
    │    ├── calculations.csv
    │    └── summary.txt
    └─ return {"sheets_processed": N, "total_line_items": M}
    ↓
[job status set to "done", result stored in jobs dict]
    ↓
[Frontend polls GET /api/status/<job_id> every 500ms, sees "done", fetches result]
```

### Data Flow: Plan Selection (NEW — to be implemented)

```
[User selects project, clicks "Preview Plans"]
    ↓
[GET /api/projects/<project_id>/plans]
    ↓
[project_cache.get_project_plans(project_id)]
    ↓
[_fetch_pages_for_project()] → new function
    ├─ Launch browser
    ├─ Login
    ├─ get_all_page_ids(project_id)
    └─ Return list of {page_id, sheet_name}
    ↓
[Frontend renders plan selection UI with checkboxes]
    ↓
[User selects specific pages, clicks "Run Selected"]
    ↓
[POST /api/run/stackct with {"page_ids": [123, 456, 789]}]
    ↓
[_stackct_job receives page_ids, passes to scraper]
    ↓
[scraper filters pages list: pages = [p for p in pages if p["page_id"] in page_ids_filter]]
    ↓
[Pipeline runs only on selected pages]
```

### Data Flow: Report Preview (NEW — to be implemented)

```
[User clicks "Preview" on report card]
    ↓
[GET /api/reports/<run_folder>/preview/calculations.csv]
    ↓
[Read CSV from disk, parse with csv.DictReader]
    ↓
[Return JSON: {"type": "csv", "rows": [...], "count": N}]
    ↓
[Frontend renders interactive data table:
  - Column sorting
  - Filter by sheet / item type
  - Search box
  - Export selected rows]
```

### State Management

```
┌──── In-Memory State (jobs dict) ────────────────────────────────┐
│  {                                                               │
│    "job_id": {                                                   │
│      "id": "a3f9bc12",                                           │
│      "type": "stackct" | "pdf",                                  │
│      "status": "queued" | "running" | "done" | "error",          │
│      "progress": 0-100,                                          │
│      "log": ["line1", "line2", ...],  ← last 100 lines          │
│      "result": {...} | None,                                     │
│      "error": "message" | None,                                  │
│      "project": "Project Name"                                   │
│    }                                                             │
│  }                                                               │
│  ⚠ Lost on server restart                                        │
└──────────────────────────────────────────────────────────────────┘

┌──── Disk State (output/) ───────────────────────────────────────┐
│  output/                                                         │
│  ├── projects_cache.json       ← 24h TTL, background refresh    │
│  ├── screenshots/              ← Per-run folders                │
│  │   └── {ProjectName}_{ts}/                                    │
│  │       ├── 001_A1.01_Floor_Plan.png                           │
│  │       └── 002_E2.01_Panel_Schedule.png                       │
│  └── {ProjectName}_{ts}/       ← Report outputs                 │
│      ├── takeoff.json                                            │
│      ├── raw_items.csv                                           │
│      ├── calculations.csv                                        │
│      └── summary.txt                                             │
│  ✅ Persists across restarts                                     │
└──────────────────────────────────────────────────────────────────┘
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| **1-3 concurrent jobs** | Current architecture is fine. Thread-per-job model works. |
| **5-10 concurrent jobs** | Add semaphore to limit concurrent browser instances (Chromium is memory-heavy). |
| **10+ concurrent jobs** | Switch to job queue (Celery + Redis) with worker pool. Separate browser pool from Flask. |
| **Multi-user** | Add authentication (Flask-Login or HTTP basic auth). Per-user job isolation. |
| **Cloud deployment** | Use headless Chromium with --no-sandbox. Ensure Playwright system deps installed. |

### Scaling Priorities

1. **First bottleneck:** Memory exhaustion from concurrent Chromium instances. Each browser uses ~300MB. Fix: Limit concurrent jobs to 3 with semaphore.
2. **Second bottleneck:** Claude API rate limits. Anthropic default is 50 requests/min. Fix: Implement exponential backoff retry; batch optimize with prompt caching.
3. **Third bottleneck:** Disk I/O for large screenshot folders. Fix: Optional S3/cloud storage for screenshots; local disk only for reports.

## Anti-Patterns

### Anti-Pattern 1: Fixed Sleep for Canvas Rendering

**What people do:** `await asyncio.sleep(5)` to wait for StackCT drawing tiles to load.

**Why it's wrong:**
- Wastes time on fast connections (tiles load in 2s, but we wait 5s)
- Fails on slow connections (VPS with poor network may need 10s)
- No feedback if rendering is stuck

**Do this instead:**
```python
async def _wait_for_canvas_stable(selector, timeout_s=15):
    """Poll canvas pixels until stable (2 consecutive identical screenshots)."""
    import hashlib
    prev_hash = None
    stable_count = 0
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        el = await page.query_selector(selector)
        buf = await el.screenshot()
        h = hashlib.md5(buf).hexdigest()
        if h == prev_hash:
            stable_count += 1
            if stable_count >= 2:
                return True
        else:
            stable_count = 0
        prev_hash = h
        await asyncio.sleep(0.8)
    return False
```

### Anti-Pattern 2: Hardcoded Filesystem Paths

**What people do:** `_env_path = Path("/Users/macbook/Desktop/Bobby Tailor/.env")`

**Why it's wrong:**
- Breaks on any other machine (Windows, Linux, different username)
- Requires manual path editing before deployment
- Makes codebase non-portable

**Do this instead:**
```python
# Relative to current file
_env_path = Path(__file__).parent / ".env"
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"
load_dotenv(dotenv_path=_env_path, override=True)
```

### Anti-Pattern 3: Embedding All UI Assets in Single HTML File

**What people do:** 21KB `index.html` with embedded CSS, JS, and inline styles.

**Why it's wrong:**
- Hard to maintain (find CSS rule in 900-line HTML file)
- No caching (browser re-downloads entire HTML on every reload)
- No hot reload during development
- Difficult for multiple developers to work on UI simultaneously

**Do this instead:**
- Extract to `static/app.js`, `static/style.css`
- Use `<link>` and `<script>` tags with proper cache headers
- Minify for production with build step (optional)

### Anti-Pattern 4: In-Memory Job State Without Persistence

**What people do:** Store all job state in `jobs` dict. On server restart, all running jobs are lost.

**Why it's wrong:**
- User loses progress if server crashes mid-job
- No audit trail of past jobs
- Cannot resume failed jobs

**Do this instead (future enhancement):**
- Persist jobs to SQLite or Redis with status updates
- On restart, check for "running" jobs and mark them "interrupted"
- Add "Resume" button in UI for interrupted jobs

### Anti-Pattern 5: Substring Matching for Item Classification

**What people do:**
```python
if "door" in description.lower():
    item_type = "doors"
```

**Why it's wrong:**
- False positives: "outdoor" contains "door", "expansion panel detail" contains "panel"
- No word boundary checking

**Do this instead (already implemented correctly):**
```python
import re
def _classify_item(description: str) -> Optional[str]:
    desc_lower = description.lower()
    for item_type, table in ESTIMATION_TABLES.items():
        for keyword in table["keywords"]:
            # Word boundary matching: "door" matches "door" or "doors" but not "outdoor"
            pattern = r'\b' + re.escape(keyword) + r's?\b'
            if re.search(pattern, desc_lower):
                return item_type
    return None
```

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **StackCT (go.stackct.com)** | Playwright browser automation with Auth0 login | No official API. DOM scraping required. Angular SPA with virtual scrolling (project list truncation risk). |
| **Anthropic Claude API** | REST API with JSON payloads | Vision models require base64-encoded images. Use `cache_control` for prompt caching. |
| **PyMuPDF (for PDF mode)** | Direct library import, render PDF pages to PNG | Zoom factor of 2.0 matches browser high-DPI. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **app.py ↔ scraper.py** | Direct async function call via `_run_async()` | Callbacks for log/progress. Job state updated in-place. |
| **scraper.py ↔ browser.py** | Async method calls on `StackCTBrowser` instance | Browser instance created per-job. Not shared across jobs. |
| **scraper.py ↔ claude_analyzer.py** | Synchronous function call (Claude SDK is sync) | Screenshot path passed as string. Returns dict. |
| **scraper.py ↔ calculator.py** | Synchronous function call | Passes list of extracted items. Returns list of calculated items. |
| **scraper.py ↔ reporter.py** | Synchronous function call | Passes all extracted + calculated. Writes to disk. Returns metadata dict. |
| **app.py ↔ project_cache.py** | Synchronous function call | Cache operations are blocking. Background refresh uses thread. |

## Component Build Order

For implementing Master.md Phase 1 & 2 features, follow this sequence to minimize integration issues:

### Phase 1: Foundation Fixes (Day 1)

1. **Fix `config.py` hardcoded path** (5 min)
   - Replace absolute path with relative `.env` lookup
   - Test: Run on different machine/directory
   - ✅ Enables deployment

2. **Add `Pillow` to requirements** (2 min)
   - Currently missing from `requirements.txt`
   - Needed for image compression in `claude_analyzer.py`
   - Test: `pip install -r requirements.txt` on fresh venv

3. **Add cost tracking to `claude_analyzer.py`** (15 min)
   - Capture `response.usage.input_tokens` and `output_tokens`
   - Calculate cost with pricing table
   - Add to returned dict as `_tokens_in`, `_tokens_out`, `_cost_usd`
   - Test: Run single-page job, check JSON output

4. **Aggregate cost in `reporter.py`** (10 min)
   - Sum `_cost_usd` across all extracted pages
   - Add `api_usage` section to `takeoff.json`
   - Add cost line to `summary.txt`
   - Test: Verify total cost appears in report

### Phase 2: Backend APIs (Day 1-2)

5. **Add plan fetching to `project_cache.py`** (30 min)
   - New function: `get_project_plans(project_id)`
   - Launches browser, logs in, calls `get_all_page_ids()`
   - Returns `{"plans": [...], "project_id": int}`
   - Test: Call directly from Python REPL

6. **Add `/api/projects/<id>/plans` route to `app.py`** (10 min)
   - Calls `project_cache.get_project_plans()`
   - Returns JSON list of pages
   - Test: `curl http://localhost:5050/api/projects/7409312/plans`

7. **Modify `scraper.py` to accept `page_ids_filter`** (15 min)
   - Add optional `page_ids_filter: List[int]` parameter
   - Filter `pages` list after `get_all_page_ids()`
   - Test: Run with `page_ids_filter=[123, 456]`, verify only 2 pages processed

8. **Modify `/api/run/stackct` to pass `page_ids`** (10 min)
   - Accept `page_ids: [int]` in POST body
   - Pass to `_stackct_job()` → `run_project_scrape()`
   - Test: POST with `{"mode": "specific", "project_id": 123, "page_ids": [456]}`

9. **Add report preview API to `app.py`** (20 min)
   - Route: `/api/reports/<run_folder>/preview/<filename>`
   - Read file, parse CSV/JSON/TXT
   - Return structured JSON
   - Test: Fetch `calculations.csv`, verify rows array

### Phase 3: Frontend Refactor (Day 2-3)

10. **Extract CSS to `static/style.css`** (30 min)
    - Move all `<style>` blocks from `index.html`
    - Add `<link rel="stylesheet" href="/static/style.css">`
    - Add industrial design color palette (see Master.md Section 8.1)
    - Test: Reload page, verify styling intact

11. **Extract JS to `static/app.js`** (30 min)
    - Move all `<script>` blocks
    - Add `<script src="/static/app.js"></script>`
    - Test: All buttons/dropdowns still functional

12. **Implement sidebar layout** (2 hours)
    - Replace tab-based UI with fixed sidebar (240px) + main content
    - Navigation: Projects, PDF Upload, Reports, Settings
    - Active job mini-card in sidebar
    - Test: Click each nav item, verify page switching

13. **Implement plan selection UI** (2 hours)
    - After project selected, "Preview Plans" button appears
    - Click → fetch `/api/projects/<id>/plans`
    - Render checklist with sheet names, type badges
    - "Select All", "Select None", filter by type dropdown
    - "Run Selected Plans (N)" button
    - Test: Select 3 pages, verify job runs only those

14. **Implement report preview UI** (2 hours)
    - Each report card has "Preview" button
    - Click → expand panel below card
    - Tabs: Summary / Calculations / Raw Items / JSON
    - Data table with sorting, filtering, search
    - Test: Click preview, sort by item_type, filter by sheet

### Phase 4: Reliability (Day 3-4)

15. **Add canvas stability detection to `browser.py`** (30 min)
    - New method: `_wait_for_canvas_stable(selector, timeout_s)`
    - Replace `await asyncio.sleep(5)` in `screenshot_full_drawing()`
    - Poll canvas pixels, wait for 2 consecutive identical screenshots
    - Test: Run on fast network (should complete faster) and slow network (should wait longer)

16. **Add project list scroll fix to `browser.py`** (15 min)
    - In `get_all_projects()`, scroll to bottom 5 times before scraping
    - Triggers Angular virtual scroll lazy loading
    - Test: Account with 50+ projects, verify all appear

### Phase 5: Polish (Day 4-5)

17. **Add Settings page** (1 hour)
    - Form for StackCT credentials, Claude API key
    - "Test Connection" buttons
    - Waste factor profile selector
    - Test: Save settings, verify `.env` updated

18. **Add error handling improvements** (1 hour)
    - Sanitize error messages for frontend (no stack traces)
    - Log full errors server-side only
    - Add retry logic for transient failures
    - Test: Force error (bad credentials), verify friendly message

19. **Add logging improvements** (30 min)
    - Structured logging with JSON formatter
    - Log rotation (daily, keep 7 days)
    - Per-job log files in report folder
    - Test: Run job, verify `{report_folder}/job.log` exists

## Verification Checklist

Before considering architecture implementation complete:

- [ ] **Plan selection works end-to-end:** User can preview pages and select subset before running
- [ ] **Report preview works:** Click preview, see interactive data table without downloading
- [ ] **Cost tracking visible:** Every report shows total API cost in summary
- [ ] **Canvas stability works:** Screenshot timing adapts to network speed
- [ ] **Config path fixed:** Runs on different machine without editing paths
- [ ] **Static assets split:** CSS and JS in separate files, not embedded in HTML
- [ ] **UI redesign matches spec:** Sidebar navigation, industrial design palette
- [ ] **Error handling graceful:** No stack traces in UI, friendly error messages
- [ ] **All tests pass:** Unit tests for calculator formulas, integration tests for pipeline

## Sources

- **Master.md** — Complete project specification, feature requirements, known gaps
- **Existing codebase** — `app.py`, `scraper.py`, `browser.py`, `claude_analyzer.py`, `calculator.py`, `reporter.py`, `project_cache.py`
- **Playwright documentation** — Browser automation patterns, async/await best practices
- **Anthropic Claude API docs** — Vision model usage, prompt caching, pricing
- **Flask documentation** — Background job patterns, static file serving

---

*Architecture research for: Bobby Tailor StackCT Estimation Automation*  
*Researched: 2026-05-26*  
*Confidence: HIGH (based on direct codebase inspection + Master.md requirements)*  
*Downstream consumer: ROADMAP.md will use component boundaries and build order for phase structure*
