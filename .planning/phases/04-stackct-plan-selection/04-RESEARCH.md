# Phase 4: StackCT Plan Selection - Research

**Researched:** 2026-05-26
**Domain:** Flask API endpoints, StackCT browser automation, JavaScript UI
**Confidence:** HIGH

## Summary

Phase 4 enables users to choose which drawing sheets to analyze before spending API credits. This addresses Gap #2 from Master.md ("No Plan Selection Before Job Start") — currently, selecting a project runs analysis on ALL pages immediately with no preview.

The implementation follows a straightforward pattern already established in the codebase:
1. Add a plans-fetching endpoint that reuses the existing `browser.get_all_page_ids()` method
2. Modify the run API to accept an optional `page_ids` filter
3. Add a plan-selection UI panel with checkboxes and type filtering

**Primary recommendation:** Follow Master.md Step 2 exactly — the patterns and code snippets are already defined and proven compatible with the existing codebase.

## Standard Stack

### Core (Already in Codebase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | 2.3+ | Web framework | Already powers the app |
| Playwright | 1.40+ | Browser automation | Already used for StackCT login/scraping |
| asyncio | stdlib | Async execution | Already used for browser tasks |

### Supporting (Already in Codebase)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| project_cache.py | local | Project list caching | Extend for page caching |
| browser.py | local | StackCT browser controller | Has `get_all_page_ids()` already |
| scraper.py | local | Job orchestrator | Modify to accept page filter |

### No New Dependencies
This phase requires no new libraries. All functionality builds on existing modules.

## Architecture Patterns

### Pattern 1: Reuse Browser Session from Cache Pattern
**What:** Use the same async browser fetch pattern as `project_cache._fetch_from_stackct()`
**When to use:** Fetching page list from StackCT
**Example:**
```python
async def _fetch_pages_for_project(project_id: int) -> list:
    from browser import StackCTBrowser
    b = StackCTBrowser()
    await b.start()
    try:
        if not await b.login():
            raise RuntimeError("Login failed")
        return await b.get_all_page_ids(project_id)
    finally:
        await b.close()
```

### Pattern 2: Sync Wrapper for Async in Flask Route
**What:** Create new event loop for async browser calls (Flask routes are sync)
**When to use:** Any Flask route calling async browser methods
**Example:**
```python
def get_project_plans(project_id: int) -> dict:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        pages = loop.run_until_complete(_fetch_pages_for_project(project_id))
        return {"plans": pages, "project_id": project_id}
    finally:
        loop.close()
```

### Pattern 3: Optional Filter Parameter
**What:** Accept optional `page_ids` list and filter discovered pages
**When to use:** Selective processing
**Example:**
```python
if page_ids_filter:
    pages = [p for p in pages if p["page_id"] in page_ids_filter]
    log(f"Filtered to {len(pages)} selected pages")
```

### Anti-Patterns to Avoid
- **Don't cache page lists:** Projects can have pages added/removed frequently — always fetch fresh
- **Don't require page_ids:** Make it optional to maintain backward compatibility with existing clients

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Page discovery | New scraping logic | `browser.get_all_page_ids()` | Already handles DOM attribute extraction |
| Async execution | Custom thread management | `asyncio.new_event_loop()` pattern | Matches existing `project_cache.py` |
| Type detection | Complex classification | Simple sheet_name parsing | Sheet names contain type indicators |

**Key insight:** The browser.py `get_all_page_ids()` method already returns `[{page_id, sheet_name}]` — we just need to expose this via a new API endpoint.

## Common Pitfalls

### Pitfall 1: Flask/Async Mixing
**What goes wrong:** Using `asyncio.run()` in Flask context
**Why it happens:** Flask routes are sync, browser methods are async
**How to avoid:** Use `new_event_loop()` + `run_until_complete()` pattern (see project_cache.py)
**Warning signs:** "Event loop is already running" errors

### Pitfall 2: Name Collision
**What goes wrong:** Function `get_project_plans` in both app.py route decorator and import
**Why it happens:** Flask route and helper function share same name
**How to avoid:** Import with alias: `from project_cache import get_project_plans as _get_plans`
**Warning signs:** Import errors or wrong function called

### Pitfall 3: Background Job Context
**What goes wrong:** Passing complex objects (like Flask request) to background threads
**Why it happens:** Flask context doesn't persist across threads
**How to avoid:** Pass only primitive values (int, str, list) to `_stackct_job`
**Warning signs:** "Working outside of request context" errors

## Code Examples

### Plans API Endpoint (from Master.md Step 2)
```python
# app.py
@app.route("/api/projects/<int:project_id>/plans")
def get_plans(project_id):
    """Return drawing page list for plan selection UI."""
    from project_cache import get_project_plans as _get_plans
    result = _get_plans(project_id)
    return jsonify(result)
```

### Run API with page_ids (from Master.md Step 2)
```python
# app.py - modified run_stackct route
page_ids = data.get("page_ids")  # Optional list of specific page IDs

# Pass to background job
t = threading.Thread(
    target=_stackct_job,
    args=(job_id, mode, project_id, project_name, page_ids),
    daemon=True
)
```

### Scraper Filter (from Master.md Step 2)
```python
# scraper.py
async def run_project_scrape(
    project_id: int,
    project_name: str,
    page_ids_filter: Optional[List[int]] = None,
    log_callback=None,
    progress_callback=None
) -> dict:
    ...
    pages = await browser.get_all_page_ids(project_id)
    
    if page_ids_filter:
        pages = [p for p in pages if p["page_id"] in page_ids_filter]
        log(f"Filtered to {len(pages)} selected pages")
```

## Existing Codebase Assets

### Available Methods
- `browser.get_all_page_ids(project_id)` → returns `[{page_id, sheet_name}]`
- `project_cache.get_projects()` → pattern to follow for plans
- `scraper.run_project_scrape()` → accepts callbacks, needs page filter

### Existing Data Structures
```python
# Page object (from browser.get_all_page_ids)
{
    "page_id": 1234567,
    "sheet_name": "A1.01 - Floor Plan Level 1"
}
```

### Existing UI Structure
- Templates in `templates/index.html` (single-page app)
- All JavaScript inline currently
- Uses fetch() for API calls

## Sheet Type Classification

Sheet names typically follow construction drawing conventions:
- **Architectural:** A1.xx, A2.xx, A3.xx (floor plans, elevations, details)
- **Electrical:** E1.xx, E2.xx (riser diagrams, panel schedules)
- **Mechanical:** M1.xx, M2.xx (HVAC plans)
- **Plumbing:** P1.xx
- **Schedules:** Often in sheet name: "Panel Schedule", "Door Schedule"

Simple heuristic for UI filtering:
```javascript
function getSheetType(sheetName) {
    const upper = sheetName.toUpperCase();
    if (upper.startsWith('A') || upper.includes('FLOOR') || upper.includes('PLAN')) return 'architectural';
    if (upper.startsWith('E') || upper.includes('ELECTRICAL')) return 'electrical';
    if (upper.startsWith('M') || upper.includes('MECHANICAL') || upper.includes('HVAC')) return 'mechanical';
    if (upper.includes('SCHEDULE')) return 'schedule';
    return 'other';
}
```

## Sources

### Primary (HIGH confidence)
- Master.md Step 2 (Plan Fetching API) — exact implementation code
- Master.md Section 8.3 (Projects Page UI spec) — exact UI wireframe
- browser.py — verified `get_all_page_ids()` returns required structure
- project_cache.py — verified async wrapper pattern
- scraper.py — verified function signature for modification

### Secondary (MEDIUM confidence)
- REQUIREMENTS.md PLAN-01..PLAN-05 — requirement definitions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all existing code, no new deps
- Architecture: HIGH — follows established patterns in codebase
- Pitfalls: HIGH — documented from codebase analysis

**Research date:** 2026-05-26
**Valid until:** Indefinite (internal codebase patterns)
