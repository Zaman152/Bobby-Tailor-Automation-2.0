# Pitfalls Research

**Domain:** Construction Take-off Automation (Playwright Scraping + Claude Vision + Flask Job Runner)
**Researched:** May 26, 2026
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Angular Virtual Scrolling Truncates Project List

**What goes wrong:**
The `get_all_projects()` function uses DOM scraping (`a[href*="Takeoff"]`) on StackCT's Angular SPA, which implements lazy/virtual scrolling. Only visible DOM elements are rendered initially—projects below the fold don't exist in the DOM until the user scrolls down. This causes the system to silently miss projects in production.

**Why it happens:**
Modern Angular apps (especially enterprise SaaS like StackCT) use virtual scrolling for performance when dealing with hundreds of list items. The DOM at page load time contains only the first 20-30 visible items. Playwright's page load waits (`waitForLoadState`) don't trigger scroll actions, so it only sees the initially rendered viewport.

**How to avoid:**
1. Before scraping links, scroll to the bottom of the project list container multiple times to trigger Angular's lazy rendering:
   ```python
   for _ in range(5):
       await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
       await asyncio.sleep(1.5)  # Allow Angular to render new items
   ```
2. Alternative (more robust): Intercept the underlying `/api/projects` XHR call using `page.on("response")` and extract project list from the JSON payload instead of scraping DOM. This bypasses client-side rendering entirely.

**Warning signs:**
- Project dropdown in UI shows different counts on each cache refresh
- Users report "my project isn't showing up" but it's visible when they log into StackCT manually
- Project count in cache file is consistently lower than what user expects

**Phase to address:**
Phase 1 (Critical UX Fixes) — Browser Module Enhancement

---

### Pitfall 2: Claude Vision Hallucinates Panel Schedule Row Counts

**What goes wrong:**
Claude Vision API demonstrates 40-55% accuracy on symbol-based instance counting (door counts, window counts, circuit counts) in construction drawings, even with Sonnet/Opus models. It excels at OCR (text extraction) with 85-95% accuracy but frequently:
- Undercounts schedule rows by 30-50% when tables span multiple columns or wrap across pages
- Fabricates "clean" values (e.g., filling blank cells with "0" or guessing breaker sizes)
- Conflates similar-looking symbols (exit signs vs. emergency lights, receptacles vs. switches)

**Why it happens:**
Vision models are trained on diverse web images—not domain-specific technical drawings. Construction schedules use:
- Tiny font sizes (6-8pt) with high information density
- Ambiguous visual symbols that require domain knowledge (breaker trip curves, load phase notation)
- Context-dependent interpretation (a blank row might mean "same as above" or "not applicable")

Per academic research (arXiv 2601.04819, Jan 2026): "Symbol-centric drawing understanding—especially reliable counting—remains unsolved with proprietary frontier systems often achieving 0.40-0.55 accuracy."

**How to avoid:**
1. **High-resolution preprocessing:** Capture screenshots at 2x DPI minimum (already implemented). Consider 3x for schedule-heavy sheets.
2. **Confidence gating:** Parse Claude's `confidence` field in the response; route "medium" or "low" confidence outputs to human review queue.
3. **Ground outputs with explicit constraints:** In the prompt, instruct: "Count every visible row in the table. If a row is blank or unclear, mark it as 'unclear' in notes—do not guess values."
4. **Structured validation:** After extraction, validate row counts against heuristics:
   - Panel schedules: circuit count should be even (most panels have paired odd/even circuits)
   - Equipment schedules: if quantity column sums to < 5 for a 30-unit building, flag for review
5. **Dual-model verification (future):** For critical sheets, run extraction through both Haiku and Sonnet, compare outputs, flag discrepancies.

**Warning signs:**
- Calculated takeoff quantities are 30-50% lower than client's manual estimates
- Panel schedule totals (connected KVA) don't match sum of individual circuit loads
- Users report "circuit 24 is missing" but it's visible in the source drawing screenshot
- JSON output has panels with only 6 circuits when drawing clearly shows 42

**Phase to address:**
Phase 2 (Extraction Quality Improvements) — Vision Prompt Engineering + Confidence Thresholds

---

### Pitfall 3: Flask Request Context Leaks Into Background Threads

**What goes wrong:**
Flask's `request`, `g`, and `session` objects are thread-local proxies that are only valid within the request thread that created them. When `app.py` spawns a background thread for a scraping job and that thread tries to access `request.json` or `current_app.config`, it causes:
- `RuntimeError: Working outside of request context`
- Silent data corruption if contexts from multiple requests get mixed
- Memory leaks as context objects remain referenced by daemon threads

**Why it happens:**
Flask's context system (via Werkzeug's `LocalStack`) uses thread-local storage. When you do `threading.Thread(target=job_function)`, the new thread does **not** inherit the parent's request context. The `request` proxy in the worker thread points to nothing, or worse, points to whatever request happened to be active when the worker thread accesses it (race condition).

**How to avoid:**
1. **Never pass Flask proxy objects to background threads.** Extract plain data before spawning:
   ```python
   # BAD: request is a proxy
   t = threading.Thread(target=scraper.run, args=(request,))
   
   # GOOD: extract data as primitives
   data = request.json
   project_id = data.get("project_id")
   t = threading.Thread(target=scraper.run, args=(project_id,))
   ```
2. **Use a proper task queue (Celery/RQ) for production.** They handle context isolation automatically and provide retry/monitoring.
3. **If staying with threads,** use `queue.Queue` for inter-thread communication (it's thread-safe) and ensure all shared state is protected by locks or use immutable data structures.
4. **Limit Flask to 1 worker in production** if using threads with SQLite (as mentioned in Master.md)—multiple workers + threads + SQLite = lock errors.

**Warning signs:**
- Intermittent `RuntimeError: Working outside of request context` in logs
- Job state dict shows data from wrong project (user submitted project A, job processed project B)
- SQLite database errors: "database is locked"
- Flask process crashes after 10-20 concurrent jobs

**Phase to address:**
Phase 1 (Critical Fixes) — Replace Threading with Celery/RQ, or Phase 0 (immediate): Add validation that no Flask proxies are passed to threads.

---

### Pitfall 4: Headless Chrome Crashes on VPS Due to Shared Memory Exhaustion

**What goes wrong:**
Playwright launches Chromium in headless mode on a VPS (Hostinger Ubuntu). Under load (multiple concurrent jobs), the browser process crashes with:
- `Target closed` / `Browser disconnected` errors
- No visible stack trace—just a sudden browser shutdown mid-screenshot
- System logs show OOM (out of memory) killer or `SIGBUS` errors

The root cause is Docker/Linux default shared memory (`/dev/shm`) is only **64MB**. Chromium uses shared memory for compositor buffers, video rendering, and tab isolation. When a drawing screenshot exceeds this tiny limit, the renderer process crashes.

**Why it happens:**
Desktop environments automatically allocate 50% of RAM to `/dev/shm`. Cloud VPS and Docker containers default to 64MB for security (to prevent fork bombs). StackCT drawings rendered at 2x DPI generate 5-15MB bitmaps per page—three concurrent jobs can easily exhaust 64MB.

**How to avoid:**
1. **If using Docker:** Add to `docker-compose.yml`:
   ```yaml
   services:
     bobby-tailor:
       shm_size: "1gb"
       # OR
       ipc: host  # Share host's /dev/shm (simpler but less isolated)
   ```
2. **If running on bare-metal VPS:** Add Playwright launch arg `--disable-dev-shm-usage` to route shared memory to disk-backed `/tmp` instead:
   ```python
   browser = await playwright.chromium.launch(
       args=["--no-sandbox", "--disable-dev-shm-usage"]
   )
   ```
   Note: Disk-backed is slower but prevents crashes.
3. **Install system dependencies:** Run `npx playwright install-deps chromium` on first deploy—missing `libnss3`, `libatk1.0-0`, etc., cause silent failures.
4. **Resource monitoring:** Add health check that kills and restarts browser if memory > 80% (prevents cascading failures).

**Warning signs:**
- Job logs show "screenshot successful" but file size is 0 bytes or < 5KB
- Browser crashes after 3rd or 4th page in a 12-page job (cumulative memory pressure)
- `dmesg` output on VPS shows "Out of memory: Kill process [chromium]"
- Flakiness disappears when running only 1 job at a time

**Phase to address:**
Phase 0 (Pre-deployment) — Infrastructure Setup; Phase 2 — Add memory monitoring + auto-restart

---

### Pitfall 5: Fixed Sleep for Canvas Rendering is Brittle Across Networks

**What goes wrong:**
`browser.py` uses `await asyncio.sleep(5)` after navigating to a drawing page to wait for tile rendering. This fixed 5-second wait:
- Is too short on slow VPS connections (especially WAN routing to StackCT's servers) → screenshots capture partially loaded drawings
- Is too long on fast connections (LAN or cached content) → wastes 4 seconds per page × 30 pages = 2 minutes per job
- Doesn't detect actual rendering completion—it's just guessing

**Why it happens:**
StackCT uses a tile-based rendering system (similar to Google Maps) where the drawing is split into 256×256px tiles that stream in asynchronously. There's no single "DOMContentLoaded" event. The canvas may **appear** loaded (white background present) but tiles continue streaming for 3-10 seconds depending on:
- Network latency to StackCT's CDN
- Drawing complexity (50MB PDF vs. 5MB PDF)
- Server-side processing time (StackCT may rasterize on demand)

**How to avoid:**
Replace fixed sleep with **pixel hash stability detection:**
```python
async def _wait_for_canvas_stable(self, selector: str, timeout_s: int = 15) -> bool:
    """Screenshot canvas repeatedly until pixels stop changing (tiles fully loaded)."""
    import hashlib
    prev_hash = None
    stable_count = 0
    deadline = time.time() + timeout_s
    
    while time.time() < deadline:
        el = await self.page.query_selector(selector)
        if el:
            buf = await el.screenshot()
            h = hashlib.md5(buf).hexdigest()
            if h == prev_hash:
                stable_count += 1
                if stable_count >= 2:  # Stable for 2 consecutive checks (1.6s)
                    logger.info(f"Canvas stable after {time.time() - (deadline - timeout_s):.1f}s")
                    return True
            else:
                stable_count = 0
            prev_hash = h
        await asyncio.sleep(0.8)
    
    logger.warning(f"Canvas stability timeout after {timeout_s}s—proceeding with whatever loaded")
    return False
```

This approach:
- Completes in 2-3 seconds on fast networks (vs. waiting full 5s)
- Continues waiting up to 15s on slow networks (vs. failing after 5s)
- Provides deterministic "loaded" state instead of hoping

**Warning signs:**
- Screenshots show white rectangles where drawing tiles should be (incomplete rendering)
- Claude returns "unable to read dimensions—no text visible" on sheets that definitely have text
- Extraction works perfectly on local dev machine but fails 40% of the time on VPS
- Adding `sleep(10)` "fixes" the issue (symptom, not solution)

**Phase to address:**
Phase 2 (Extraction Quality) — Browser Module Robustness

---

## Moderate Pitfalls

### Pitfall 6: Large CSV Preview Crashes Browser Tab

**What goes wrong:**
When implementing the "Report Preview" feature (Phase 1 planned), naively loading `calculations.csv` (potentially 5,000+ rows × 15 columns) into a browser data table causes:
- Tab becomes unresponsive for 10-20 seconds while rendering
- Scroll lag (5-10 FPS) due to thousands of DOM elements
- Memory usage spikes to 500MB+ for a single table, causing mobile browsers to crash

**Why it happens:**
Each table row is a DOM element. Rendering 5,000 `<tr>` elements × 15 `<td>` = 75,000 DOM nodes. Browser layout engines recalculate styles, reflow geometry, and repaint on every scroll event. Even modern browsers can't handle this at 60fps.

**How to avoid:**
1. **Virtual scrolling (recommended):** Only render the 50-100 rows currently visible in viewport. Libraries:
   - `react-window` (React)
   - `@tanstack/virtual` (framework-agnostic)
   - Or build custom: track scroll position, calculate visible range, render only `data.slice(startIdx, endIdx)`
2. **Pagination:** Show 500 rows per page, load pages on demand
3. **Web Worker parsing:** Parse CSV in background thread so UI stays responsive during initial load
4. **Lazy column rendering:** Render only 5-7 visible columns initially; load others when user scrolls horizontally
5. **Download threshold:** If file > 10,000 rows, show preview of first 1,000 rows + "Download full CSV" button instead of trying to render all

**Warning signs:**
- Browser DevTools show "Long Task" warnings (>50ms) during table render
- Scroll fps drops below 30 on report preview
- Mobile users report "app froze" when opening large reports
- Memory profiler shows 300MB allocated to single table

**Phase to address:**
Phase 1 (Report Preview Feature) — Implement virtual scrolling from the start, not as a retrofit

---

### Pitfall 7: Screenshot Timing Race with HubSpot Popups

**What goes wrong:**
StackCT injects HubSpot marketing popups ("Book a Demo," "Webinar Signup") that appear 3-5 seconds after page load. If the screenshot is captured before `_dismiss_popups()` runs, or if the popup reappears after dismissal, the screenshot contains a large overlay blocking 30% of the drawing.

**Why it happens:**
Third-party marketing tools load asynchronously with random delays (they don't want to block page load metrics). HubSpot specifically has "time on page" triggers—popup appears after 3-5 seconds to avoid annoying users who bounce quickly.

Current `_dismiss_popups()` implementation:
- Injects CSS to hide known selectors (`#hubspot-messages-iframe-container`)
- Clicks close buttons
- Presses Escape key

But if HubSpot updates their DOM structure or introduces new popup types, the CSS selectors break.

**How to avoid:**
1. **Defensive wait:** Wait 6 seconds **before** dismissing popups (let them appear first), then dismiss, then screenshot.
2. **Mutation observer:** Inject a JS mutation observer that watches for new iframes/modals and hides them immediately:
   ```python
   await self.page.evaluate("""
       const observer = new MutationObserver(mutations => {
           document.querySelectorAll('iframe[src*="hubspot"], .modal-overlay').forEach(el => {
               el.style.display = 'none';
           });
       });
       observer.observe(document.body, { childList: true, subtree: true });
   """)
   ```
3. **Element screenshot vs. full page:** Already implemented—targeting `#canvas-interaction` element avoids capturing sidebars/popups that aren't overlaid on the canvas.
4. **Upstream fix:** Ask StackCT support if there's a URL parameter to disable popups (e.g., `?embed=1` or `?source=api`).

**Warning signs:**
- Claude extracts text from popup ("Book a Demo") as if it's part of the drawing
- Screenshots show "✕" close button in the corner (popup was visible)
- Extraction confidence drops from "high" to "low" without drawing complexity change
- Users report "why is there marketing text in my takeoff?"

**Phase to address:**
Phase 2 (Extraction Quality) — Enhanced popup blocking before screenshots

---

### Pitfall 8: No Cost Tracking Leads to Bill Shock

**What goes wrong:**
Claude API bills by token count. At scale:
- Haiku: $1 / 1M input tokens, $5 / 1M output tokens
- Sonnet: $3 / 1M input, $15 / 1M output

A 30-page project at 2x DPI:
- 30 images × ~1,200 tokens/image (vision) = 36k input tokens
- 30 responses × ~1,000 tokens/response (JSON) = 30k output tokens
- Haiku: $0.036 + $0.150 = **$0.19** per run
- Sonnet (schedule-heavy): $0.108 + $0.450 = **$0.56** per run

If users run 100 projects/month: $19–$56/month. Without tracking, the bill arrives and finance escalates.

**Why it happens:**
`claude_analyzer.py` doesn't capture `response.usage.input_tokens` and `response.usage.output_tokens`. The `reporter.py` module doesn't aggregate costs. Users have no visibility into spend per project or per sheet type.

**How to avoid:**
1. **Capture usage in every Claude call:**
   ```python
   response = client.messages.create(...)
   usage = response.usage
   cost_usd = (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000
   extracted["_tokens_in"] = usage.input_tokens
   extracted["_tokens_out"] = usage.output_tokens
   extracted["_cost_usd"] = round(cost_usd, 6)
   extracted["_model_used"] = model
   ```
2. **Aggregate in reporter.py:**
   ```python
   total_cost = sum(d.get("_cost_usd", 0) for d in all_extractions)
   report["api_usage"] = {
       "total_cost_usd": round(total_cost, 4),
       "total_tokens_in": sum(...),
       "total_tokens_out": sum(...),
       "average_cost_per_sheet": round(total_cost / len(all_extractions), 4)
   }
   ```
3. **Display in UI:** Show cost in reports tab: "12 sheets · 847 items · **$0.19**"
4. **Budget alerts:** If cost > $1.00 per run, show warning: "This project is schedule-heavy (used Sonnet); consider reviewing plan selection to exclude non-essential sheets."

**Warning signs:**
- Monthly Anthropic bill is 3x higher than expected
- Users run the same project 10 times during testing (no cost visibility = no incentive to optimize)
- No way to justify cost to client ("how much did this analysis cost?")

**Phase to address:**
Phase 2 (Extraction Quality) — Add token tracking to all Claude calls

---

### Pitfall 9: No Plan Selection Wastes API Calls on Irrelevant Sheets

**What goes wrong:**
User selects "Office Building Project" which contains 30 sheets:
- A1.01–A1.05: Floor plans (relevant)
- A2.01–A2.08: Building sections (not needed for take-off)
- A3.01–A3.04: Details (not needed)
- E1.01–E1.08: Electrical (relevant)
- M1.01–M1.05: Mechanical (not needed)

Without plan selection, the system processes **all 30 sheets**, wasting:
- 15 irrelevant screenshots × 5s = 75 seconds
- 15 irrelevant API calls × $0.006 = $0.09
- Claude's attention on useless data (detail sheets of stair railings)
- 15 pages of junk in the raw output

**Why it happens:**
Current flow: User clicks project → job starts immediately on ALL pages. No opportunity to review/filter.

**How to avoid:**
1. **Add plan selection step (Master.md Phase 1 feature):**
   - After user selects project, show "Preview Plans" button
   - Fetch `get_all_page_ids()` → display list with checkboxes
   - User selects "Floor Plans" + "Electrical" only
   - Job runs on selected subset

2. **Smart defaults:** Pre-check only sheets matching keywords:
   - Floor plan, electrical, panel schedule, equipment schedule
   - Uncheck: sections, details, site plans, cover sheets

3. **Save selections as "profiles":** "Electrical takeoff profile" = only E* and P* sheets

**Warning signs:**
- Output contains 200 measurements from architectural detail sheets (bolt spacings, flashing details)
- Cost per run is 2x higher than necessary
- Users manually delete 50% of rows from calculations.csv every time
- User feedback: "I only need electrical, why does it analyze plumbing?"

**Phase to address:**
Phase 1 (Critical UX Fixes) — Plan Selection Feature (already identified in Master.md Gap #2)

---

### Pitfall 10: Hardcoded Mac Path Breaks All Deployments

**What goes wrong:**
`config.py` contains:
```python
_env_path = Path("/Users/macbook/Desktop/Bobby Tailor/.env")
```

On any other machine (VPS, Docker, different developer's laptop), this path doesn't exist → `load_dotenv()` silently fails → all environment variables are `None` → system crashes on first API call with "ANTHROPIC_API_KEY is not set."

**Why it happens:**
Developer tested locally, hardcoded their own path, didn't test deployment. Classic "works on my machine" scenario.

**How to avoid:**
```python
# Find .env relative to this file (config.py location)
_env_path = Path(__file__).parent / ".env"

# Fallback to current working directory
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"

# Last resort: check user home directory
if not _env_path.exists():
    _env_path = Path.home() / ".env"

load_dotenv(dotenv_path=_env_path, override=True)

# Validate required vars are present
required = ["STACKCT_EMAIL", "STACKCT_PASSWORD", "ANTHROPIC_API_KEY"]
missing = [v for v in required if not os.getenv(v)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {missing}. Check .env file at {_env_path}")
```

**Warning signs:**
- Flask starts successfully but crashes on first job with "NoneType has no attribute..."
- Logs show "Loading .env from /Users/macbook/..." on a server at `/home/ubuntu/...`
- StackCT login fails with "email is None"

**Phase to address:**
Phase 0 (Immediate—before any deployment) — Fix in `config.py`, add to pre-deploy checklist

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Using threading instead of Celery | No new dependencies, faster to implement | Context leaks, no retries, no monitoring, doesn't scale | MVP/demo only; must migrate before production |
| Fixed `sleep(5)` instead of stability detection | Simpler code (2 lines vs. 20 lines) | Wastes time on fast connections, fails on slow ones | Never—speed variance is too high |
| Loading entire CSV into browser DOM | No virtualization library dependency | Tab crashes on 10k+ rows, poor UX | Only if guaranteed max 500 rows |
| Skipping plan selection feature | Faster to ship | Users waste money on irrelevant sheets, poor UX | Never—users explicitly requested this |
| Not tracking API costs | Less code to maintain | Surprise bills, no cost optimization data | Never—financial visibility is critical |
| Hardcoded estimation waste factors | Avoids building profile UI | Can't adjust per client, inflexible | MVP only; Phase 4 should add profiles |
| Single Playwright browser for all jobs | Avoids browser pool management | Browser crashes kill all concurrent jobs | Acceptable if max 1-2 concurrent jobs |
| No authentication on Flask app | Faster to deploy | Anyone on network can run expensive jobs | Acceptable on private VPS; unacceptable on public IP |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Playwright + StackCT | Using `page.goto()` wait strategies (`networkidle`, `load`) for canvas rendering | Wait for specific canvas element, then pixel hash stability check |
| Claude Vision + Drawings | Assuming OCR accuracy equals counting accuracy | High confidence for text extraction; human review gate for counts |
| Flask + Threading | Passing `request` object to background thread | Extract primitives (`request.json → dict`) before spawning thread |
| PyMuPDF + PDF rendering | Using default DPI (72) for PDF rasterization | Use `zoom=2.0` for 144 DPI to match screenshot quality |
| Browser + VPS | Running with default `/dev/shm` (64MB) | Add `--disable-dev-shm-usage` flag or increase shm to 1GB |
| CSV + Browser | Using `FileReader.readAsText()` for large files | Use `Blob.stream()` + `TextDecoderStream` + virtual scrolling |
| Background Jobs + User | No progress visibility during 5-minute jobs | Real-time progress updates via polling + websocket (future) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Not installing Pillow for image compression | Anthropic API rejections: "image exceeds 5MB" | `pip install Pillow`, add to requirements.txt | First large (>3.6MB) screenshot |
| Running all jobs in one browser instance | First crash kills all jobs, memory leak over time | Browser pool: 1 browser per job, close after completion | After 3-4 concurrent jobs |
| Storing all screenshots forever | Disk fills up, `output/` reaches 10GB+ | Delete screenshots after 7 days, or add `--keep-screenshots=false` flag | After 100+ runs |
| No timeout on Claude API calls | Job hangs forever if API is down | Set `timeout=60` on `client.messages.create()` | First time Anthropic has outage |
| Loading 30 drawings × 5MB each into memory | Python process OOMs (killed at 2GB) | Process and delete each screenshot immediately after Claude call | Projects with >20 large drawings |
| No rate limiting on StackCT navigation | IP gets soft-banned for "bot-like behavior" | Add 0.5-1s delay between page navigations | High-velocity testing (>100 pages/hour) |
| Gunicorn with 10 workers + threads + SQLite | Database lock errors, corrupted data | Use Gunicorn `workers=1` with SQLite, or switch to PostgreSQL | First time 2+ workers write simultaneously |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Hardcoded credentials in `config.py` | Credentials leaked in git history, screenshots | Always use `.env`, add `.env` to `.gitignore`, provide `.env.example` |
| Exposing stack traces in API responses | Information leakage, reveals internal paths | Sanitize error messages for users; log full traces server-side only |
| No authentication on Flask app | Anyone can run expensive jobs, access reports | Add HTTP Basic Auth or Flask-Login with environment-based password |
| Serving user-uploaded PDFs without validation | PDF exploits (malformed files crash PyMuPDF) | Validate PDF magic bytes, set max file size (100MB), run PyMuPDF in try/except |
| Storing reports with guessable filenames | Enumeration attack: guess `/output/Project_20260525_120000/` | Add random token to folder names: `Project_20260525_120000_a3f9bc12/` |
| No HTTPS on production deployment | Credentials sent in plaintext over network | Use Nginx reverse proxy with Let's Encrypt SSL, or Caddy auto-HTTPS |
| Logging full API keys in debug output | Keys visible in log files, terminal output | Log only first 8 chars: `sk-ant-api03-abc12345...` |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No preview of what will be processed | Users waste money running all 30 sheets when they needed 5 | Plan selection UI with checkboxes (Gap #2) |
| Reports are download-only | Must download, open Excel, scroll to find data | In-browser preview with search/filter (Gap #3) |
| No feedback during 5-minute jobs | User thinks it froze, refreshes page, loses progress | Real-time progress: "Analyzing E2.01 – Panel HM1 (8/12)" |
| No cost visibility | Finance escalates after surprise bill | Show cost per run: "$0.19 (12 sheets, Haiku)" |
| Error messages are technical | User sees "RuntimeError: context" → confused, contacts support | User-friendly: "Job failed. Please try again or contact support. [Error ID: a3f9]" |
| Can't retry single failed sheet | One sheet fails → must rerun entire 30-sheet job | Per-sheet retry button in reports view (future) |
| No confidence indicators | User doesn't know extraction quality | Color-code items: green (high conf), yellow (medium), red (review needed) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces:

- [ ] **Screenshot capture:** Verify file size > 5KB (current check), but also check pixel diversity (all-white screenshot = render failure)
- [ ] **Claude extraction:** Returns valid JSON, but `measurements: []`, `components: []`, `schedules: []` are all empty (API succeeded but saw nothing)
- [ ] **Calculation rows:** `formula_applied` is populated, but `calculated_quantity` is 0 or negative (formula logic bug)
- [ ] **CSV export:** File exists and has headers, but body is empty (generator didn't yield rows)
- [ ] **Report preview:** Table renders, but columns are misaligned (header count ≠ row count)
- [ ] **Plan selection:** Checkboxes work, but `page_ids` parameter isn't passed to scraper (all pages still run)
- [ ] **Cost tracking:** Tokens logged, but pricing dict is outdated (bill shock from wrong rates)
- [ ] **Background job:** Returns 200 OK, but exception in worker thread is swallowed (job silently fails, status stuck at "running")

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Missed projects (virtual scroll) | LOW | Run cache refresh, manually trigger scrape for missing project |
| Hallucinated schedule rows | HIGH | Manual review + correction by human estimator, re-run with higher model |
| Context leak crash | MEDIUM | Restart Flask process, fix thread code, re-run failed jobs |
| Browser crash on VPS | LOW | Add shm fix + restart, jobs auto-retry on next user request |
| Slow canvas rendering | LOW | Add stability detection, jobs automatically complete faster |
| Large CSV crash | MEDIUM | Implement virtual scrolling, users can still download CSV in meantime |
| No plan selection | LOW | Add feature, users can manually delete unwanted rows from CSV until then |
| Missing cost data | MEDIUM | Backfill costs by re-parsing API logs if retained; going forward, add tracking |
| Hardcoded path | HIGH | Fix config.py, redeploy—no recovery needed for prior runs |
| Popup in screenshot | MEDIUM | Re-run specific sheet with improved popup blocking |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Angular virtual scrolling truncation | Phase 1 (Browser) | Run on project with >50 projects, compare count to StackCT UI |
| Vision hallucination | Phase 2 (Extraction Quality) | Compare 10 sample panel schedules: system count vs. manual count |
| Flask context leaks | Phase 0 (Immediate) or Phase 1 (Celery migration) | Load test: 10 concurrent jobs, check logs for RuntimeError |
| VPS Chrome crashes | Phase 0 (Deploy Setup) | Run 5 concurrent jobs on VPS, monitor with `htop` + `dmesg` |
| Fixed sleep fragility | Phase 2 (Extraction Quality) | Measure avg. completion time: before (5s/page) vs. after (2-3s/page) |
| Large CSV preview | Phase 1 (Report Preview) | Open 5,000-row calculations.csv, verify scroll fps >30 |
| HubSpot popup leakage | Phase 2 (Browser Robustness) | Review 20 random screenshots for popup artifacts |
| No cost tracking | Phase 2 (Extraction Quality) | Verify every run has `api_usage` field with non-zero cost |
| No plan selection | Phase 1 (Critical UX) | User acceptance test: select 3 of 10 sheets, verify only 3 processed |
| Hardcoded path | Phase 0 (Before Deploy) | Deploy to clean VM, verify .env loads without error |

## Phase-Specific Research Flags

Based on this pitfalls research, recommend deeper investigation during:

**Phase 1 (Plan Selection + Preview):**
- Needs deeper research: Virtual scrolling libraries (compare `react-window` vs. `@tanstack/virtual` performance)
- Needs deeper research: Best UX pattern for multi-select with "Select by type" grouping

**Phase 2 (Extraction Quality):**
- Needs deeper research: Optimal image resolution for Claude Vision (2x DPI vs. 3x DPI cost/benefit)
- Needs deeper research: Confidence scoring calibration (how well does Claude's self-reported confidence correlate with accuracy?)

**Phase 3 (UI Overhaul):**
- Standard patterns apply: Dark mode design system, no special research needed

**Phase 4 (Advanced Features):**
- Needs deeper research: Waste factor profiles (industry standards by construction type)
- Needs deeper research: Excel export libraries (openpyxl vs. xlsxwriter for 10k-row performance)

## Sources

**Playwright + Angular scraping:**
- Puppeteer networkidle is not a scraping strategy (DEV Community, 2026)
- How to Scrape Single-Page Apps (SPAs) with Playwright in 2026 (DEV Community)
- Scalable Web Scraping with Playwright and Browserless (2026 Guide)
- When Tests Should Run Headless vs Headed in Playwright (Currents.dev, Feb 2026)

**Claude Vision accuracy:**
- arXiv:2601.04819 - "Evaluation of Vision Language Models on Construction Drawing Understanding" (Jan 2026)
  - Key finding: "Instance counting remains unsolved (0.40–0.55 accuracy) with proprietary frontier systems"
- Claude Vision API: Image Analysis At Production Scale (Developers Digest, 2026)
- Can Claude Perform Good Estimates? A First-Principles Accuracy Test (Provision.com)
  - Real-world test: 51% underestimate accuracy on bridge construction takeoff

**Flask threading:**
- The Flask Concurrency Trap: Why the "Quick Threading Fix" Breaks at Scale (Medium, 2026)
- Background Tasks with Celery — Flask Documentation (3.2.x)
- Speed Up Your Python Program With Concurrency (Real Python)

**VPS Playwright deployment:**
- 2026 OpenClaw Headless Playwright/Chromium on Resident Gateways: Docker shm, Sandbox & macOS Quotas (MacCDN Blog)
- Docker | Playwright (Official Docs)
- Troubleshooting Playwright Timeouts on Linux Servers (TechNetExperts, 2026)
- Docker Compose Testing: Playwright, Grid, API (ScrollTest)

**Browser CSV rendering:**
- Memory limits: when to chunk CSV client-side vs server-side (Elysiate, 2026)
- Best Practices for Handling Large CSV Files Efficiently (Dromo)
- Streams API - Web APIs (MDN)
- Streams—The definitive guide (web.dev)

**Project context:**
- Master.md Section 6: Current Gaps & Known Issues (Bobby Tailor project)

---

*Pitfalls research for: Construction Take-off Automation (Playwright + Claude Vision + Flask)*
*Researched: May 26, 2026*
*Confidence: HIGH (all major pitfalls verified with 2026 sources)*
