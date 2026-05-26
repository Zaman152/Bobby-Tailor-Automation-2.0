# Bobby Tailor — StackCT Estimation Automation

## What This Is

Bobby Tailor is a construction quantity take-off automation platform for a construction estimation firm. It logs into StackCT via headless browser, screenshots drawing pages, extracts measurements and schedules with Claude Vision, applies construction estimation formulas, and delivers CSV/JSON/text reports. A Flask web UI supports StackCT project runs, PDF upload mode, and report browsing. Built and maintained by Praivox for client Bobby Tailor.

## Core Value

End-to-end automated take-off from StackCT drawings (or uploaded PDFs) that produces traceable, formula-backed quantity calculations estimators can trust and export — faster and more consistently than manual measurement.

## Requirements

### Validated

- ✓ StackCT Auth0 login and session handling — existing (`browser.py`)
- ✓ Project list discovery with 24h disk cache — existing (`project_cache.py`, `app.py`)
- ✓ DOM-based page discovery via `data-page-id` — existing (`browser.py`)
- ✓ High-DPI canvas screenshots with popup dismissal — existing (`browser.py`)
- ✓ Claude Vision extraction with model routing and image compression — existing (`claude_analyzer.py`)
- ✓ Estimation tables and formula engine (flooring, drywall, paint, framing, etc.) — existing (`calculator.py`)
- ✓ Report generation (raw_items.csv, calculations.csv, summary.txt, takeoff.json) — existing (`reporter.py`)
- ✓ StackCT scrape orchestration with per-page error recovery — existing (`scraper.py`)
- ✓ PDF upload analysis path (PyMuPDF → same pipeline) — existing (`pdf_analyzer.py`)
- ✓ Flask UI with background jobs, status polling, report download — existing (`app.py`, `templates/index.html`)
- ✓ Environment-based config with relative `.env` path — existing (`config.py`)
- ✓ Pillow in requirements for image compression — existing (`requirements.txt`)

### Active

- [ ] Plan selection workflow — preview sheets, checkboxes, run selected `page_ids` only (Gap #2, Master §7.1.1)
- [ ] In-browser report preview — summary, sortable/filterable tables, JSON tree (Gap #3, Master §7.1.2)
- [ ] Fix project list truncation — scroll/lazy-load or API intercept (Gap #1, Master §7.2.3)
- [ ] Canvas stability detection — replace fixed sleep with pixel-hash polling (Gap #4, Master §7.2.2)
- [ ] Per-sheet progress in job monitor — current sheet name + mini log (Gap #5, Master §8.4)
- [ ] API cost tracking per run — tokens and USD in reports (Gap #6, Master §7.2.1)
- [ ] UI/UX overhaul — sidebar layout, industrial dark theme, settings page (Master §8)
- [ ] PDF page selection before analysis (Gap #7, Master §8.6)
- [ ] Sanitize API error messages for end users (Gap #10)
- [ ] Add Pillow verification and `.env.example` alignment in docs

### Out of Scope

- Multi-user auth / Flask-Login — deferred; single-operator tool on trusted network (Master Gap #9)
- Scheduled runs with email/Slack — Phase 4 future (Master §7.4.3)
- Per-sheet manual review UI with accept/reject — Phase 4 future (Master §7.4.1)
- Client-specific waste factor profiles UI — Phase 4 future (Master §7.4.2)
- Excel export with branding — Phase 4 future (Master §7.4.4)
- Replacing StackCT or building a full estimation ERP — this automates take-off from existing drawings only

## Context

**Source of truth:** `Master.md` v2.0 (May 2026) — architecture, gaps, upgrade plan, UI spec, agent implementation order.

**Brownfield state:** Python 3.10+ monolith (~10 modules). Recent successful run in `output/Bid_for_Baking_Social_*`. GitNexus/CodeGraph indexed. Critical path fixes in Master Steps 1–3 not yet implemented in code (no `page_ids` filter, no preview API, tab-based UI).

**Known gaps (priority):** No plan picker before job; reports download-only; project list may truncate; fixed 5s canvas wait; no cost visibility in UI.

**Users:** Bobby Tailor (estimator, reviews CSVs); Praivox (build/deploy).

**Deployment target:** Local dev + Hostinger VPS with gunicorn, headless Chromium (Master §11).

## Constraints

- **Tech stack**: Python, Flask, Playwright, Anthropic API, PyMuPDF — established; extend in place
- **Credentials**: Never hardcode; `.env` only; do not commit secrets
- **StackCT DOM**: Relies on `#canvas-interaction`, `[data-page-id]`, Auth0 flow — brittle if StackCT changes
- **API limits**: Claude Vision ~5MB base64; compression required for large PNGs
- **Performance**: 30-page set ~5 minutes target at Haiku pricing (~$0.05/run cited in Master)
- **Security**: Sanitize paths on report endpoints; no stack traces to UI

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Master.md as planning source of truth | User directive; comprehensive brownfield spec | — Pending |
| Phase 1 = critical UX (plan select + preview + config) before UI shell | Master §7 ordering; unblocks user-reported pain | — Pending |
| Keep Flask monolith; extract static JS/CSS on UI rebuild | Minimal migration risk; Master §10 target structure | — Pending |
| Haiku default, Sonnet for schedule/electrical sheets | Cost vs accuracy tradeoff already in `claude_analyzer.py` | ✓ Good |
| Skip codebase map; infer from Master + code scan | User asked to proceed with existing docs | — Pending |

---
*Last updated: 2026-05-26 after GSD project initialization from Master.md*
