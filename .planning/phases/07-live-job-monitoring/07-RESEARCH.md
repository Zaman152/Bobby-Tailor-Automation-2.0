# Phase 7: Live Job Monitoring - Research

**Researched:** 2026-05-26
**Domain:** Flask job progress tracking, callback patterns, real-time UI updates
**Confidence:** HIGH

## Summary

This phase transforms the basic job progress display into a rich live monitoring experience. Users currently see only a percentage and generic log lines; after this phase they'll see:
- Which specific sheet is being processed (e.g., "E2.01 – Panel HM1")
- Per-sheet extraction counts (measurements, rooms, components)
- A persistent sidebar mini-card showing active job status
- Structured log entries rather than plain text

Research focused on:
1. **Scraper callback enrichment** — Adding structured data to `progress_callback` and `log_callback` payloads
2. **Job status API extensions** — New fields for current sheet, structured log, extraction counts
3. **Sidebar mini-card pattern** — Persistent UI component per Master §8.7

**Current state assessment:**
- `scraper.py` has `progress_callback(idx, total, sheet_name)` — basic but lacks extraction counts
- `app.py` job status returns only `log[-10:]` as strings — no structure
- `app.py` stores `progress` as percentage only — no sheet index or name
- No sidebar job display exists in `templates/index.html`
- Claude extraction returns counts in `extracted` dict — available but not surfaced

**Primary recommendation:** Enrich callback payloads at source (scraper), extend job dict schema in app.py, add new `/api/jobs/active` endpoint, and implement sidebar mini-card component.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | >=3.0.0 | Web framework | Already in use; job status routes are Flask endpoints |
| JavaScript (vanilla) | ES6+ | Frontend polling | Already in use for job status; no framework needed for this scope |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Server-Sent Events (SSE) | Native | Real-time push | **Optional v2** — could replace polling but adds complexity; polling at 1s interval is sufficient for this use case |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polling `/api/status` | WebSocket | WebSocket is overkill for single-user tool with 1s polling; adds connection management complexity |
| Inline sidebar JavaScript | Alpine.js | Would require new dependency; vanilla JS sufficient for this scope |
| Per-sheet log entries | Full event stream | Event stream adds backend complexity; structured log array is simpler and sufficient |

**Installation:**

No new dependencies required — all tools already present.

## Architecture Patterns

### Pattern 1: Enriched Callback Signature

**What:** Extend `progress_callback` to include structured data about current sheet processing state.

**Current signature:**
```python
progress_callback(current: int, total: int, sheet_name: str)
```

**Proposed signature:**
```python
progress_callback(
    current: int,
    total: int,
    sheet_name: str,
    phase: str = "analyzing",  # "screenshotting" | "analyzing" | "calculating"
    extraction: dict = None    # {"measurements": N, "components": N, "rooms": N}
)
```

**When to use:** Call after each major phase of sheet processing.

**Example integration:**
```python
# In scraper.py run_project_scrape()
log(f"[{idx}/{total}] Screenshotting {sheet_name}...")
if progress_callback:
    progress_callback(idx, total, sheet_name, phase="screenshotting")

# After Claude analysis
n_meas = len(extracted.get("measurements", []))
n_comp = len(extracted.get("components", []))
n_rooms = len(extracted.get("rooms", []))
if progress_callback:
    progress_callback(idx, total, sheet_name, phase="analyzing",
                      extraction={"measurements": n_meas, "components": n_comp, "rooms": n_rooms})
```

### Pattern 2: Structured Log Entries

**What:** Replace plain string log entries with structured dicts for richer UI display.

**Current:**
```python
job["log"].append(f"[{current}/{total}] Analyzing {sheet}...")
```

**Proposed:**
```python
job["log"].append({
    "timestamp": datetime.now().isoformat(),
    "type": "sheet_progress",  # "info" | "sheet_progress" | "sheet_complete" | "error"
    "sheet_index": current,
    "sheet_total": total,
    "sheet_name": sheet,
    "message": f"Analyzing {sheet}...",
    "extraction": None  # or {"measurements": N, ...} when complete
})
```

**When to use:** All job logging should use structured entries for JOB-03 compliance.

**Frontend parsing:**
```javascript
const entry = log[i];
if (entry.type === "sheet_complete") {
    displaySheetResult(entry.sheet_name, entry.extraction);
} else {
    displayLogLine(entry.message);
}
```

### Pattern 3: Extended Job Status Schema

**What:** Extend the job dict in `app.py` to store richer state needed by UI.

**Current schema:**
```python
jobs[job_id] = {
    "id": job_id, "type": "stackct", "status": "queued",
    "progress": 0, "log": [], "result": None, "error": None,
    "project": project_name, "mode": mode
}
```

**Proposed schema:**
```python
jobs[job_id] = {
    "id": job_id,
    "type": "stackct",
    "status": "queued",  # "queued" | "running" | "done" | "error"
    "progress": 0,
    "log": [],  # Now structured entries
    "result": None,
    "error": None,
    "project": project_name,
    "mode": mode,
    # NEW fields for JOB-01, JOB-02:
    "started_at": None,           # ISO timestamp
    "current_sheet": {            # JOB-02
        "index": 0,
        "total": 0,
        "name": None,
        "phase": None             # "screenshotting" | "analyzing" | "calculating"
    },
    "sheets_completed": [],       # JOB-03: [{name, extraction: {...}}]
}
```

### Pattern 4: Active Job Endpoint

**What:** Add `/api/jobs/active` endpoint that returns the currently running job (if any).

**Why needed:** Sidebar mini-card (JOB-04) needs to know if any job is running without knowing the job ID.

**Example:**
```python
@app.route("/api/jobs/active")
def get_active_job():
    """Return the currently running job, if any."""
    for job in jobs.values():
        if job["status"] == "running":
            return jsonify({
                "active": True,
                "job": {
                    "id": job["id"],
                    "project": job["project"],
                    "progress": job["progress"],
                    "current_sheet": job["current_sheet"],
                }
            })
    return jsonify({"active": False, "job": None})
```

### Pattern 5: Sidebar Mini-Card Component

**What:** A persistent UI component in the sidebar that shows active job status (Master §8.7).

**HTML structure:**
```html
<div class="active-job-mini" id="activeJobMini" style="display: none;">
    <div class="mini-header">
        <span class="status-dot running"></span>
        <span class="project-name" id="miniProjectName">—</span>
    </div>
    <div class="mini-progress">
        <div class="mini-bar" id="miniProgressBar" style="width: 0%"></div>
        <span class="mini-pct" id="miniProgressPct">0%</span>
        <span class="mini-count" id="miniSheetCount">0/0</span>
    </div>
    <div class="mini-sheet" id="miniCurrentSheet">—</div>
    <a href="#" onclick="showJobDetails()" class="mini-link">View Details →</a>
</div>
```

**JavaScript polling:**
```javascript
async function pollActiveJob() {
    const resp = await fetch('/api/jobs/active');
    const data = await resp.json();
    const el = document.getElementById('activeJobMini');
    
    if (data.active) {
        el.style.display = 'block';
        document.getElementById('miniProjectName').textContent = data.job.project;
        document.getElementById('miniProgressBar').style.width = data.job.progress + '%';
        document.getElementById('miniProgressPct').textContent = data.job.progress + '%';
        document.getElementById('miniSheetCount').textContent = 
            `${data.job.current_sheet.index}/${data.job.current_sheet.total}`;
        document.getElementById('miniCurrentSheet').textContent = 
            data.job.current_sheet.name || '—';
    } else {
        el.style.display = 'none';
    }
}

// Poll every 1 second when page is active
setInterval(pollActiveJob, 1000);
```

## Anti-Patterns to Avoid

- **Overloading callback with too many params:** Use a single structured `progress_info` dict instead of positional args
- **Storing entire extraction in job dict:** Store only counts, not full extraction data (memory concern for large jobs)
- **Polling too frequently:** 1s interval is sufficient; sub-second polling wastes bandwidth
- **Breaking existing callback contracts:** New params should be optional with defaults for backward compatibility

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Real-time push | Custom WebSocket server | Polling at 1s interval | Single-user tool; polling is simpler and sufficient |
| Progress bar animations | Custom CSS transitions | CSS `transition: width 0.3s` | Browser handles smoothing automatically |
| Timestamp formatting | Manual string concatenation | `datetime.isoformat()` | Standard format, parseable by JS `Date()` |

## Common Pitfalls

### Pitfall 1: Breaking Backward Compatibility

**What goes wrong:** Adding required params to `progress_callback` breaks callers that don't pass them.

**How to avoid:** Use optional params with defaults:
```python
def progress_callback(current, total, sheet_name, phase="analyzing", extraction=None):
```

### Pitfall 2: Memory Growth in Long Jobs

**What goes wrong:** Storing full log entries forever causes memory growth on very long runs.

**How to avoid:** Cap log array size (e.g., keep last 100 entries) or store only summary for completed sheets:
```python
if len(job["log"]) > 100:
    job["log"] = job["log"][-100:]
```

### Pitfall 3: Race Conditions in Job Dict Updates

**What goes wrong:** Background thread updates job dict while Flask route reads it, causing inconsistent state.

**How to avoid:** For this single-user tool, the risk is minimal. For production, use `threading.Lock` or move to proper job queue (Celery).

### Pitfall 4: Polling When Tab Is Hidden

**What goes wrong:** JavaScript keeps polling even when browser tab is background, wasting resources.

**How to avoid:** Use `document.visibilityState` to pause polling when hidden:
```javascript
document.addEventListener('visibilitychange', () => {
    if (document.hidden) pausePolling();
    else resumePolling();
});
```

## Code Examples

### Enriched Progress Callback in scraper.py

```python
# In run_project_scrape(), after Claude analysis
extracted = analyze_drawing(str(screenshot_path), sheet_name)
extracted["_page_id"] = page_id

# Build extraction counts
extraction_counts = {
    "measurements": len(extracted.get("measurements", [])),
    "components": len(extracted.get("components", [])),
    "rooms": len(extracted.get("rooms", [])),
    "schedules": len(extracted.get("schedules", []))
}

if progress_callback:
    progress_callback(idx, total, sheet_name,
                      phase="complete",
                      extraction=extraction_counts)
```

### Extended Job Status Route

```python
@app.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    return jsonify({
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "progress": job["progress"],
        "started_at": job.get("started_at"),
        "current_sheet": job.get("current_sheet", {}),
        "sheets_completed": len(job.get("sheets_completed", [])),
        "log": job["log"][-20:],  # Last 20 structured entries
        "project": job["project"],
        "error": job["error"],
        "has_result": job["result"] is not None,
    })
```

### Sidebar Mini-Card CSS

```css
.active-job-mini {
    margin-top: auto;
    padding: 12px;
    background: var(--surface-secondary);
    border-radius: 6px;
    border: 1px solid var(--border-color);
}

.mini-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--status-running);
    animation: pulse 1.5s infinite;
}

.mini-progress {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
}

.mini-bar {
    flex: 1;
    height: 4px;
    background: var(--accent-green);
    border-radius: 2px;
    transition: width 0.3s ease;
}

.mini-sheet {
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.mini-link {
    display: block;
    margin-top: 8px;
    font-size: 12px;
    color: var(--accent-blue);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Plain string logs | Structured log entries with types | Modern web apps | Enables rich UI rendering of log data |
| Percentage-only progress | Sheet index + name + phase | UX best practices | Users understand what's happening, not just how much |
| No active job display | Persistent sidebar mini-card | Dashboard patterns | Users always know if something is running |

## Open Questions

None — requirements are clear from Master §8.4 and §8.7, and implementation path is straightforward with existing callback infrastructure.

## Verification Checklist for Planning

Before creating PLAN.md files, verify:

- [x] `scraper.py` callback locations identified (lines 76-77 for progress, 22-25 for log)
- [x] `app.py` job dict schema locations identified (lines 152-156, 182-186)
- [x] `/api/status/<job_id>` route identified (lines 195-210)
- [x] Master §8.4 and §8.7 UI specs reviewed
- [x] No existing `/api/jobs/active` endpoint (needs to be created)
- [x] Current frontend polling pattern identified in `templates/index.html`

## Files Requiring Changes

Based on codebase analysis:

1. **`scraper.py`** — Enrich `progress_callback` calls with phase and extraction counts
2. **`pdf_analyzer.py`** — Same callback enrichment for PDF mode
3. **`app.py`** — Extend job dict schema, update `_stackct_job` and `_pdf_job` to populate new fields, add `/api/jobs/active` endpoint
4. **`templates/index.html`** — Add sidebar mini-card HTML, JavaScript polling for active job

## Testing Approach

### Unit Testing

1. **Callback signature tests:**
   - Mock `progress_callback` and verify it receives all expected fields
   - Verify extraction counts match actual extraction data

2. **Job status API tests:**
   - Start job, poll `/api/status/<id>`, verify `current_sheet` populated
   - Verify `/api/jobs/active` returns running job or `{active: false}`

### Integration Testing

1. **End-to-end progress flow:**
   - Start StackCT job via API
   - Poll status until complete
   - Verify log entries have structure (not plain strings)
   - Verify `sheets_completed` count matches sheets processed

### Manual Testing

1. **UI verification:**
   - Start job, verify sidebar mini-card appears
   - Verify progress bar updates smoothly
   - Verify current sheet name updates as sheets process
   - Verify mini-card disappears when job completes

## Sources

### Primary (HIGH confidence)

- Master.md §8.4: Active Job (Live Monitor) — Project specification
- Master.md §8.7: Sidebar Active Job Mini-Card — UI specification
- Flask Documentation: Application Factories and Blueprints — Route patterns

### Secondary (MEDIUM confidence)

- JavaScript Page Visibility API — MDN Web Docs
- CSS Transitions — MDN Web Docs

## Metadata

**Confidence breakdown:**
- Callback enrichment: **HIGH** — Existing pattern, simple extension
- Job status API: **HIGH** — Flask native, well-understood
- Sidebar mini-card: **HIGH** — Standard dashboard pattern, spec in Master.md
- Polling vs WebSocket: **HIGH** — Polling sufficient for single-user tool

**Research date:** 2026-05-26
**Valid until:** ~2026-08-26 (90 days — Flask patterns stable, UI spec fixed)
