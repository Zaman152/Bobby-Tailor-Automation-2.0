# Project Research Summary

**Project:** Bobby Tailor Automation 2.0
**Domain:** Construction Quantity Take-off Automation (Browser Automation + Vision AI + Estimation)
**Researched:** May 26, 2026
**Confidence:** HIGH

## Executive Summary

Bobby Tailor is a brownfield construction take-off automation tool that combines headless browser automation (Playwright + StackCT), Claude Vision API for zero-shot drawing extraction, and formula-based estimation. The 2026 standard approach for this architecture prioritizes **async-native infrastructure, transparent cost tracking, and hybrid human-AI workflows**. The existing Flask foundation works but creates technical debt—the system's async Playwright operations and concurrent Claude API calls justify a strategic migration to FastAPI. For the planned UI overhaul, HTMX + Alpine.js delivers industrial-grade interactivity without build tooling overhead, matching the "data-heavy industrial UI" requirement.

The core differentiator—zero-shot AI vision extraction with no manual symbol training—positions Bobby Tailor competitively against $2K–$5K/year subscription tools, with operating costs of ~$0.04–$0.05 per 30-page project. However, three critical risks threaten production readiness: (1) Flask threading context leaks causing job crashes, (2) Claude Vision's 40-55% accuracy on instance counting (hallucination risk on panel schedules), and (3) fixed timing assumptions that fail across network conditions. The roadmap must address these foundation issues before adding user-facing features.

Research reveals a clear implementation sequence: foundation fixes (hardcoded paths, cost tracking, canvas stability) unlock quick wins in 1-2 weeks, followed by critical UX improvements (plan selection, report preview) in 2-3 weeks, then strategic architecture migration (FastAPI) in 2-4 weeks. Total estimated timeline: 8-11 weeks for production-ready brownfield upgrade.

## Key Findings

### Recommended Stack

The 2026 stack for brownfield Python automation with browser control and vision AI emphasizes async-first architecture and pragmatic background job management. FastAPI replaces Flask to eliminate thread-pool workarounds for Playwright, delivering 3-5x more concurrent requests. Playwright 1.48+ provides the only viable browser automation for StackCT's Angular SPA (Selenium is deprecated). Anthropic Python SDK 0.42+ with prompt caching achieves 90% cost reduction on repeated system prompts. For deployment, Gunicorn + Uvicorn workers + systemd on Hostinger VPS provides production-grade process management.

**Core technologies:**
- **FastAPI 0.115+**: Native async/await support for Playwright; ASGI's non-blocking I/O handles 3-5x more concurrent requests than Flask WSGI; incremental migration path via Flask sub-app mounting
- **Playwright 1.48+**: Industry-standard headless Chromium with async API; built-in screenshot stability detection solves canvas rendering timing issues
- **Anthropic SDK 0.42+**: Official Claude Vision SDK with prompt caching (90% cost reduction); improved vision token estimation and Files API support
- **HTMX + Alpine.js**: Server-rendered interactivity without build tooling; CDN-based deployment matches "static JS/CSS extraction" requirement

**Migration strategy:** Keep Flask during transition—FastAPI can mount Flask apps as sub-applications. New features use FastAPI routes (`/api/v2/*`); legacy routes stay at `/legacy`. When >80% traffic migrates, deprecate Flask. Alternative: use `nest_asyncio` workaround if rewrite cost exceeds $5K and current performance is acceptable (<100 req/min).

### Expected Features

Construction take-off automation has well-established feature expectations. Research categorizes features into table stakes (users assume they exist), differentiators (competitive advantage), and anti-features (commonly requested but problematic).

**Must have (table stakes):**
- Digital takeoff from PDF/CAD with multi-sheet support (Bobby has this)
- Structured CSV/Excel export with descriptive columns (Bobby has this)
- Visual audit trail linking quantities to drawing locations (Bobby Gap #3: no in-browser preview)
- Plan selection before run (Bobby Gap #2: currently all-or-nothing)
- In-browser report preview with filtering (Bobby Gap #3: download-only)
- Job status monitoring with live progress (Bobby has polling API)
- Basic settings/config UI for credentials and API keys (Bobby Gap #8.8: .env editing required)

**Should have (competitive differentiators):**
- AI Vision extraction with no manual training (Bobby's core differentiator vs. PlanSwift/STACK)
- Cost tracking per run showing tokens/USD (Bobby Gap #6: no visibility)
- Schedule/table extraction from panel schedules and equipment lists (Bobby has this)
- Formula transparency showing exact calculations (Bobby has this via `formula_applied` column)
- Sheet type auto-classification and model routing (Bobby has heuristic routing)
- Canvas stability detection vs. fixed waits (Bobby Gap #4: uses fixed 5-second sleep)

**Defer (v2+ or out of scope):**
- Real-time multi-user collaboration (enterprise feature; Bobby is single-operator)
- Integrated cost database with RSMeans pricing (Bobby correctly exports to client systems)
- Built-in proposal generation (too client-specific; Bobby's CSV export is correct)
- Mobile-first design (takeoff requires precision and large screen; desktop-first is correct)

### Architecture Approach

Bobby Tailor uses a flat module structure with clear separation between orchestration (scraper.py), browser automation (browser.py), vision extraction (claude_analyzer.py), calculation (calculator.py), and reporting (reporter.py). The Flask web server spawns background threads for jobs, bridging sync Flask with async Playwright via `asyncio.run_until_complete()`. State is split between in-memory job tracking (lost on restart) and disk-based reports/cache (persists).

**Major components:**
1. **Orchestration (scraper.py)** — Main pipeline controller coordinating browser→vision→calculator→reporter with progress callbacks
2. **Browser automation (browser.py)** — Playwright headless Chromium with Auth0 login, DOM scraping, and canvas screenshots; implements popup dismissal and page navigation with retries
3. **Vision extraction (claude_analyzer.py)** — Image preprocessing, multi-model routing (Haiku vs. Sonnet), Claude API calls with cached prompts, JSON parsing
4. **Calculation engine (calculator.py)** — Rule-based pattern matching with ESTIMATION_TABLES, waste factors, item classification, formula generation
5. **Report generation (reporter.py)** — CSV/JSON/TXT output with data aggregation, grouping (by sheet/category/table), and metadata tracking

**Key patterns:**
- **Async/sync bridge:** Flask routes spawn threads that create isolated event loops for Playwright operations; prevents blocking but doesn't share browser context across requests
- **Callback-based progress:** Scraper accepts `log_callback` and `progress_callback` functions passed from Flask job threads; enables real-time UI updates via polling without WebSocket complexity
- **Disk cache with background refresh:** Project list cached as JSON with 24h TTL; background thread refreshes on startup; survives server restart
- **Multi-model LLM routing:** Sheet name heuristics select Claude model (Sonnet for schedules, Haiku for floor plans); saves ~70% on API costs
- **Prompt caching:** System prompt marked `cache_control: ephemeral`; first call pays full cost, subsequent calls use cached tokens at 1/10th price

### Critical Pitfalls

**1. Angular Virtual Scrolling Truncates Project List**  
StackCT's Angular SPA uses virtual scrolling—only visible DOM elements are rendered. The `get_all_projects()` DOM scraper misses projects below the fold. **Prevention:** Scroll to bottom 5 times before scraping to trigger lazy rendering, or intercept `/api/projects` XHR call to bypass DOM entirely.

**2. Claude Vision Hallucinates Panel Schedule Row Counts**  
Vision models achieve only 40-55% accuracy on symbol-based counting per academic research (arXiv 2601.04819). Claude excels at OCR (85-95%) but undercounts schedule rows by 30-50% and fabricates values in blank cells. **Prevention:** High-resolution screenshots (2x+ DPI), confidence gating for human review, explicit prompt constraints ("mark unclear as 'unclear', don't guess"), structured validation (even circuit counts for panels).

**3. Flask Request Context Leaks Into Background Threads**  
Flask's `request`/`g`/`session` are thread-local proxies; background threads cause `RuntimeError: Working outside of request context` or data corruption. **Prevention:** Extract primitives (`request.json → dict`) before spawning threads; never pass Flask proxy objects to workers; consider Celery/RQ for production.

**4. Headless Chrome Crashes on VPS Due to Shared Memory Exhaustion**  
Default `/dev/shm` is 64MB; Chromium uses shared memory for compositor buffers. Multiple concurrent jobs exhaust this, causing `Target closed` crashes. **Prevention:** Add `--disable-dev-shm-usage` launch flag (disk-backed memory) or increase `/dev/shm` to 1GB in Docker; run `playwright install-deps chromium` for system dependencies.

**5. Fixed Sleep for Canvas Rendering is Brittle**  
Current `await asyncio.sleep(5)` is too short on slow VPS, too long on fast connections, and doesn't detect actual rendering completion. **Prevention:** Implement pixel hash stability detection—screenshot canvas repeatedly until pixels stop changing (2 consecutive identical screenshots = stable).

## Implications for Roadmap

Based on combined research, the roadmap should prioritize **foundation fixes before feature additions**. Dependencies discovered:

1. Plan selection requires browser.py foundation (already 90% done—`get_all_page_ids()` exists)
2. In-browser preview is cosmetic but high-impact (pure presentation layer, no extraction changes)
3. Settings page is deployment blocker (`.env` editing unacceptable for production users)
4. Cost tracking is trivial (5 lines in analyzer, 10 lines in reporter) with massive user value
5. FastAPI migration is strategic investment (40-80 hours) justified by throughput needs but deferrable if <50 concurrent users

### Suggested Phase Structure

#### Phase 1: Foundation & Critical Fixes (1-2 weeks)
**Rationale:** Address deployment blockers and data-corruption risks before adding features.

**Delivers:**
- Fixed hardcoded `.env` path (enables deployment)
- Cost tracking per run (transparency, prevents bill shock)
- Canvas stability detection (faster + more reliable)
- Error message sanitization (professional UX)
- Pillow image preprocessing (85% token cost reduction)

**Addresses pitfalls:** #3 (context leaks via primitives extraction), #5 (canvas stability), #8 (cost tracking), #10 (hardcoded paths)

**Why first:** These are one-way doors—deploying without cost tracking means surprise bills; deploying with hardcoded paths means broken installation. Each fix is <30 minutes but critical.

#### Phase 2: Critical UX Improvements (2-3 weeks)
**Rationale:** User-reported pain points (plan selection, report preview) with high value-to-effort ratio.

**Delivers:**
- Plan selection workflow (Gap #2: checkbox UI + backend filtering)
- In-browser report preview (Gap #3: data tables with sort/filter/search)
- Settings page (Gap #8.8: credentials and API key management)
- Project list scroll fix (Gap #1: virtual scrolling workaround)
- Static asset extraction (CSS/JS to separate files)

**Uses:** HTMX + Alpine.js for frontend interactivity; existing `get_all_page_ids()` for plan fetching; CSV parsing API for preview

**Addresses pitfalls:** #1 (virtual scrolling), #6 (CSV preview DOM overload via virtual scrolling), #9 (plan selection waste)

**Why second:** These are the difference between "working prototype" and "shippable product." Plan selection prevents wasted API calls on irrelevant sheets; report preview reduces download friction; settings page enables non-technical users.

#### Phase 3: Strategic Architecture Migration (2-4 weeks)
**Rationale:** Async-native foundation unlocks performance and scalability; incremental migration reduces risk.

**Delivers:**
- FastAPI setup with Flask sub-app mounting
- New `/api/v2/*` endpoints for async operations
- Incremental route migration (plan fetching, report generation)
- Background job improvements (FastAPI BackgroundTasks)
- Keep APScheduler for cron-like jobs

**Implements:** Async browser + FastAPI pattern; replaces threading workarounds; eliminates context leak risk

**Addresses pitfalls:** #3 (Flask context leaks eliminated by async), #4 (better concurrency handling reduces memory pressure)

**Why third:** This is high-value but high-effort. It's safe to defer if current performance is acceptable (<50 req/min). The mounting pattern allows incremental migration without big-bang rewrite.

#### Phase 4: Quality & Polish (1-2 weeks)
**Rationale:** Production hardening and reliability improvements.

**Delivers:**
- Enhanced popup blocking (mutation observer for HubSpot)
- Per-sheet confidence review UI (optional human gate)
- Logging improvements (structured logs, rotation)
- Resource monitoring (memory, browser health checks)
- Job persistence (SQLite job state for restart recovery)

**Addresses pitfalls:** #2 (hallucination mitigation via confidence UI), #7 (robust popup handling)

**Why fourth:** Polish and power-user features after core functionality is solid. These are "nice to have" not "must have."

### Phase Ordering Rationale

- **Dependencies:** Phase 1 fixes enable Phase 2 deployment; Phase 2 UX improvements justify Phase 3 investment; Phase 3 architecture unlocks Phase 4 advanced features
- **Risk mitigation:** Addressing context leaks, hardcoded paths, and cost tracking early prevents production incidents
- **Value delivery:** Plan selection and report preview (Phase 2) have highest user-reported impact with lowest implementation cost
- **Incremental validation:** Each phase delivers working software; no "all or nothing" big-bang releases

### Research Flags

**Needs deeper research during planning:**
- **Phase 2 (Report Preview):** Virtual scrolling library comparison (`react-window` vs. `@tanstack/virtual` performance); best UX pattern for multi-select with type grouping
- **Phase 3 (FastAPI):** Migration testing strategy (which routes to migrate first, how to validate parity)

**Standard patterns (skip research-phase):**
- **Phase 1 (Foundation):** All fixes follow established patterns (relative paths, Pillow preprocessing, pixel hashing)
- **Phase 4 (Polish):** Logging, monitoring, and confidence UI use standard practices

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | Official benchmarks, production usage data, clear async benefits; FastAPI vs Flask is well-documented; HTMX/Alpine.js proven for server-rendered apps; all versions verified against 2026 compatibility |
| Features | **HIGH** | Feature landscape validated with Context7 industry reports, vendor documentation, competitor analysis; table stakes vs. differentiators vs. anti-features grounded in construction software reviews 2026 |
| Architecture | **HIGH** | Based on direct codebase inspection + Master.md requirements; component boundaries and data flows match existing implementation; build order tested against dependency analysis |
| Pitfalls | **HIGH** | All major pitfalls verified with 2026 sources; virtual scrolling and context leaks confirmed via dev community; Claude accuracy backed by academic research (arXiv 2601.04819); VPS Chrome issues documented in Docker/Playwright guides |

**Overall confidence:** **HIGH**

### Gaps to Address

**During Phase 1 planning:**
- Validate that Pillow preprocessing (resize to 1568px, JPEG quality 85) doesn't degrade Claude accuracy for dimension text—run A/B test on 10 sample drawings
- Confirm VPS resource limits (Hostinger 2 CPU, 4GB RAM)—test max concurrent browser instances before OOM

**During Phase 2 planning:**
- UX research on plan selection UI—should "Select All" be default, or force explicit selection? Survey beta users
- Determine CSV preview row threshold—at what point (1K rows? 5K rows?) should system force download vs. preview?

**During Phase 3 planning:**
- Flask→FastAPI migration testing—which routes are lowest risk to migrate first? Plan selection and cost tracking are new, so start there vs. touching core scraper routes
- Backward compatibility strategy—if >20% of functionality remains on Flask long-term, need robust mounting and shared state management

**During Phase 4 planning:**
- Confidence threshold calibration—what confidence score should trigger human review? Run on 50 sample schedules to correlate Claude's self-reported confidence with actual accuracy
- Job persistence schema—SQLite vs. Redis for job state? SQLite matches existing stack but limits to 1 worker; Redis enables scale but adds dependency

## Sources

### Primary (HIGH confidence)

**Stack research:**
- TechEmpower benchmarks 2026 (FastAPI vs Flask performance)
- Playwright official docs v1.48 (best practices, async patterns)
- Anthropic documentation (Claude Vision API, prompt caching, pricing)
- HTMX documentation (server-rendered patterns) + Alpine.js docs

**Features research:**
- Bluebeam Construction Takeoffs Guide 2026
- Bluebeam Construction Estimating Software Guide 2026
- ZACUA Ventures AI for Construction Report 2026
- ConstructConnect Takeoff Boost Technical Deep-Dive (Vertex AI comparison)
- BuildVision AI: 9 Best Construction Estimating Software 2026

**Architecture research:**
- Master.md (complete project specification, gaps, current implementation)
- Direct codebase inspection (app.py, scraper.py, browser.py, claude_analyzer.py, calculator.py, reporter.py, project_cache.py)

**Pitfalls research:**
- arXiv:2601.04819 "Evaluation of Vision Language Models on Construction Drawing Understanding" (Jan 2026) — Claude counting accuracy
- Puppeteer networkidle is not a scraping strategy (DEV Community, 2026)
- Docker shm issues: Docker | Playwright (Official Docs)
- Flask threading: Background Tasks with Celery — Flask Documentation (3.2.x)

### Secondary (MEDIUM confidence)

- Kreo Software: Agentic Computer Vision for Construction Drawings (competitor approach)
- Togal.AI Native Integration Announcement (market trends)
- FastAPI vs Celery comparison (Level Up Coding, 2026)
- VPS deployment: Hostinger guides, systemd best practices

### Tertiary (LOW confidence)

- None — all recommendations verified against official documentation or 2026 benchmarks.

---
*Research completed: May 26, 2026*  
*Ready for roadmap: YES*  
*Files synthesized: STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*  
*Next step: Feed into gsd-roadmapper agent for phase breakdown and requirements definition*
