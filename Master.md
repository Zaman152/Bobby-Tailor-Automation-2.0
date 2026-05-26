# Bobby Tailor — StackCT Estimation Automation
## Complete Project Master Document v2.0
### One-Stop Guide for AI Agents, Developers & Stakeholders

---

> **Purpose of this document:** This is the single authoritative reference for building, understanding, extending, and deploying the Bobby Tailor StackCT Estimation & Take-off Automation system. Every agent, developer, or collaborator working on this project must read this document in full before writing a single line of code.

---

## Table of Contents

1. [Project Overview & Business Context](#1-project-overview--business-context)
2. [System Architecture](#2-system-architecture)
3. [Module-by-Module Deep Dive](#3-module-by-module-deep-dive)
4. [Data Flow & Extraction Logic](#4-data-flow--extraction-logic)
5. [Estimation Tables & Calculation Engine](#5-estimation-tables--calculation-engine)
6. [Current Gaps & Known Issues](#6-current-gaps--known-issues)
7. [Complete Feature Upgrade Plan](#7-complete-feature-upgrade-plan)
8. [UI/UX Complete Redesign Specification](#8-uiux-complete-redesign-specification)
9. [Step-by-Step Agent Implementation Guide](#9-step-by-step-agent-implementation-guide)
10. [File & Folder Structure (Target State)](#10-file--folder-structure-target-state)
11. [Environment & Deployment](#11-environment--deployment)
12. [Testing & Validation Checklist](#12-testing--validation-checklist)

---

## 1. Project Overview & Business Context

### 1.1 What This System Does

Bobby Tailor is a **construction quantity take-off automation platform** built for a construction estimation firm. It eliminates manual measurement reading from architectural and engineering drawings by:

1. **Logging into StackCT** (a cloud-based construction estimation SaaS) via a headless browser
2. **Discovering all drawing pages** in a project using DOM attribute scraping (not clicking each page)
3. **Screenshotting each drawing** at high resolution (2x DPI) by capturing the rendering canvas directly
4. **Sending screenshots to Claude Vision** (Anthropic API) which reads dimensions, annotations, schedules, panel tables, and room data from the images
5. **Applying construction estimation formulas** — waste factors, unit conversions, material quantities
6. **Generating structured reports** — CSV (raw items), CSV (calculated takeoff), JSON (full data), plain-text summary

### 1.2 Why This Exists

Manual take-off is:
- Time-consuming (hours per project)
- Error-prone (missed annotations, misread dimensions)
- Expensive (senior estimator hours)

This system can process a 30-page drawing set in ~5 minutes for ~$0.05 at Haiku pricing, producing a fully traceable quantity take-off with formulas shown.

### 1.3 Who Uses It

- **Bobby Tailor (client)** — construction estimator; reviews outputs, adjusts waste factors, exports CSVs to their bid system
- **Praivox (builder)** — maintains, deploys, extends the system

### 1.4 Key Terminology

| Term | Meaning |
|---|---|
| **Take-off** | Process of measuring quantities from construction drawings (e.g., "200 SF of flooring") |
| **Sheet / Page** | One drawing page in a StackCT project (e.g., "A1.01 – Floor Plan") |
| **Schedule** | A table embedded in a drawing (e.g., door schedule, panel schedule) |
| **Panel Schedule** | Electrical panel circuit table — each row = one circuit, columns = load per phase |
| **Waste Factor** | Multiplier to account for material waste during installation (e.g., 1.10 = 10% extra) |
| **Canvas** | The DOM element `#canvas-interaction` in StackCT where the drawing renders |
| **Estimation Table** | Named configuration in `calculator.py` mapping item types to formulas |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Flask Web UI (app.py)                      │
│  Tab: StackCT Projects │ Tab: Upload PDF │ Tab: Reports       │
└──────────────────────┬──────────────────────────────────────┘
                       │ Background thread per job
          ┌────────────▼─────────────┐
          │     scraper.py            │
          │  Orchestrator / Controller│
          └────┬──────────┬──────────┘
               │          │
    ┌──────────▼──┐  ┌────▼───────────┐
    │  browser.py  │  │claude_analyzer │
    │  Playwright  │  │    .py         │
    │  Automation  │  │ Claude Vision  │
    └──────┬───────┘  └────────┬───────┘
           │                   │
    StackCT Website       Anthropic API
    (Auth0 login,         (Vision extraction,
     DOM scraping,         JSON response)
     canvas screenshot)
                               │
                    ┌──────────▼──────────┐
                    │    calculator.py     │
                    │  Estimation Tables   │
                    │  Formula Engine      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │    reporter.py       │
                    │  CSV / JSON / TXT    │
                    │  Output Generation   │
                    └─────────────────────┘
```

### 2.2 Parallel Path: PDF Mode

```
User uploads PDF → pdf_analyzer.py → PyMuPDF renders pages → 
same Claude Vision pipeline → same calculator + reporter
```

### 2.3 Project Cache

```
project_cache.py → stores project list to disk (24h TTL)
                 → instant dropdown on UI reload
                 → background prefetch on app start
```

---

## 3. Module-by-Module Deep Dive

### 3.1 `config.py` — Settings & Environment

**What it does:** Loads all environment variables from `.env`, exposes typed constants to all modules.

**Key variables and what they control:**

| Variable | Default | Purpose |
|---|---|---|
| `STACKCT_EMAIL` | (required) | Auth0 login email for StackCT |
| `STACKCT_PASSWORD` | (required) | Auth0 login password |
| `ANTHROPIC_API_KEY` | (required) | Claude API key |
| `CLAUDE_MODEL` | `claude-haiku-4-5` | Default model for standard sheets |
| `CLAUDE_MODEL_SCHEDULES` | same as above | Override model for schedule-heavy sheets |
| `HEADLESS` | `true` | Run browser without UI (set `false` to watch it work) |
| `OUTPUT_DIR` | `./output` | Where reports/screenshots are saved |
| `PAGE_LOAD_TIMEOUT` | 30000ms | Playwright page load timeout |

**Agent note:** Never hardcode credentials. Always use `.env`. The path is hardcoded to `/Users/macbook/Desktop/Bobby Tailor/.env` — this must be updated for deployment to a server.

---

### 3.2 `browser.py` — Playwright Browser Controller

**What it does:** Controls a Chromium browser to log into StackCT, navigate to projects/pages, and capture high-quality screenshots of drawing canvases.

**Key methods:**

#### `start()`
- Launches Chromium with 2560×1600 viewport and 2x device pixel ratio
- This high-DPI setting is critical — it makes dimension text readable in screenshots
- Logs all API calls (agent.stackct, /takeoff/, /pages/) for debugging

#### `login() → bool`
- Navigates to `https://go.stackct.com/`
- Waits for redirect to Auth0 (`id.stackct.com`)
- Fills email → clicks Continue → fills password → clicks Submit
- Waits for redirect back to `go.stackct.com/app`
- **Edge case handled:** If already authenticated, skips login flow

#### `get_all_projects() → List[dict]`
- Navigates to `/app/#/Projects`
- Waits 3 seconds for Angular rendering
- Finds all `<a href*="Takeoff">` links, extracts project ID from URL
- Returns `[{id: int, name: str}, ...]`
- **Known issue:** Angular lazy rendering means some projects may be missed if the list is long — see Gap #1 in Section 6

#### `get_all_page_ids(project_id) → List[dict]`
- Navigates to `/app/#/Takeoff/{project_id}`
- Waits for `[data-page-id]` DOM attributes (StackCT embeds these in the thumbnail grid)
- Runs a single JS `evaluate()` call to extract ALL pages at once — no per-page clicking
- Returns `[{page_id: int, sheet_name: str}, ...]`
- **This is the most reliable part of the system** — DOM attribute scraping beats URL-based navigation

#### `screenshot_full_drawing(project_id, page_id, filepath) → bool`
1. Calls `navigate_to_page()` with URL verification loop
2. Calls `_dismiss_popups()` to hide HubSpot marketing overlays via CSS injection
3. Clicks "Fit to page" button (tries multiple selectors)
4. Waits 5 seconds for tile rendering
5. Tries `#canvas-interaction` first, then fallback selectors
6. Captures element screenshot (not viewport) — gives clean drawing without sidebars
7. Returns True if file > 5KB (sanity check)

#### `_dismiss_popups()`
- Injects CSS to hide HubSpot CTA overlays (StackCT's webinar promo popups)
- Also tries clicking common close buttons and pressing Escape
- **Critical:** Without this, popups appear over drawings in screenshots

---

### 3.3 `claude_analyzer.py` — Claude Vision Extraction

**What it does:** Encodes drawing screenshots to base64, sends to Claude Vision API with a detailed extraction prompt, parses structured JSON response.

#### Model Selection (`_pick_model()`)

```python
# Heuristic routing by sheet name:
# E*, M*, P* sheet codes → Sonnet (electrical/mechanical/plumbing)
# "SCHEDULE", "PANEL", "RISER", "EQUIPMENT", "FIXTURE" in name → Sonnet
# Everything else → Haiku (cheaper, still good for floor plans)
```

#### Image Compression (`encode_image()`)

Raw limit: 3.6MB before base64 encoding (Anthropic's 5MB base64 limit).

Algorithm:
1. If under limit → send as-is (maximum quality)
2. If over limit → iterative JPEG compression:
   - Start at quality=92, max_dim=3200
   - Each iteration: reduce quality by 8, reduce max_dim by 400
   - Stop when file is under 3.6MB
   - Maximum 8 iterations; last resort sends whatever size it got to

**Agent note:** Install Pillow (`pip install Pillow`). Without it, large PNGs will be sent uncompressed and may fail.

#### The Extraction Prompt

The `EXTRACTION_PROMPT` is cached via `cache_control: ephemeral` on the system parameter. This means the first call per session pays full prompt cost; subsequent calls use cached tokens (~90% savings).

The prompt instructs Claude to return JSON with these top-level keys:
- `sheet_type` — classification of the drawing
- `sheet_title` — title block text
- `scale` — scale annotation (e.g., "1/4" = 1'-0"")
- `measurements` — array of all dimension annotations
- `components` — array of counted items (doors, units, panels)
- `rooms` — array of rooms with area/dimensions
- `schedules` — array of schedule tables with full row data
- `materials` — array of material callouts
- `confidence` — high/medium/low quality assessment
- `notes` — notable observations

#### Critical Extraction Rules (baked into the prompt)

1. **Tables/Schedules are top priority** — every row of every schedule must be captured
2. **Panel schedules:** CKT number, DESCRIPTION, BKR (breaker size/poles), A/B/C phase loads, NOTE
3. **Never fabricate values** — blank cells must be omitted from row objects
4. **Read carefully** — text is small; Claude must examine every table row

---

### 3.4 `calculator.py` — Estimation Formula Engine

**What it does:** Takes Claude's raw extraction JSON and applies construction estimation formulas to produce order quantities.

#### Estimation Tables (full reference)

Each table is a named dict in `ESTIMATION_TABLES`:

| Table Key | Output Unit | Formula | Waste Factor | Keywords |
|---|---|---|---|---|
| `flooring` | sq_ft | area × 1.10 | 10% | floor, tile, carpet, lvt, vct, vinyl, hardwood, laminate |
| `drywall` | sheets | ceil(area × 1.12 / 32) | 12% | drywall, gypsum, gwb, gypboard, sheetrock, wallboard |
| `paint` | gallons | ceil(area × 2 coats / 350 sf/gal) | — | paint, primer, finish coat, epoxy |
| `wall_framing` | studs | ceil(length_ft × 12 / 16") + 1 × 1.10 | 10% | wall, partition, stud, framing, metal stud |
| `concrete_slab` | cy | area_sf × 4" / (12 × 27) | — | concrete, slab, footing, foundation |
| `ceiling_grid` | sq_ft | area × 1.08 | 8% | ceiling, acoustic, act, lay-in, ceiling tile, t-bar |
| `doors` | ea | count | — | door, swinging door, double door |
| `windows` | ea | count | — | window, glazing |
| `insulation` | sq_ft | area × 1.05 | 5% | insulation, batt, rigid, spray foam |
| `fire_extinguisher` | ea | count | — | fire extinguisher |
| `electrical_fixture` | ea | count | — | light fixture, led, exit sign, receptacle, switch, panel |

**To modify:** Edit the `ESTIMATION_TABLES` dict values in `calculator.py`. All formulas are implemented in `_apply_formula()`.

#### Processing Pipeline (`apply_estimation_tables()`)

```
1. measurements[]  → _calculate_from_measurement()
2. components[]    → _calculate_from_component()
3. rooms[]         → _calculate_from_room() (produces flooring + ceiling + paint + drywall per room)
4. schedules[]     → _calculate_from_schedule()
```

#### Smart Filtering (prevents junk output)

`_calculate_from_measurement()` actively rejects:
- Scale references ("1/4" = 1'-0"", "NTS", "reference")
- Temperature values (°F, °C)
- Catalog identifiers matching `[A-Z]+-\d+` patterns
- Rows where `formula_used == "no formula"` (e.g., mounting height dimensions) — these go to raw_items.csv only, not calculations.csv

`_calculate_from_schedule()` rejects:
- Rows with no numeric quantity (quantity = "Multiple", "Varies", "TBD", "-", "")
- Never fabricates "1 ea" as placeholder

#### Item Classification (`_classify_item()`)

Uses **word-boundary matching** (not substring), preventing false positives like "door" matching "outdoor" or "panel" matching "expansion panel detail".

Multi-word keywords require phrase match. Single keywords require exact token match (plurals handled: "door" matches "doors").

---

### 3.5 `reporter.py` — Output Generation

**What it does:** Takes raw extractions and calculated estimates, writes 4 files per run into a timestamped subfolder under `output/`.

#### Output Files

| File | Contents | Who uses it |
|---|---|---|
| `raw_items.csv` | Every measurement/component/room/material/schedule row Claude saw | Audit, debugging |
| `calculations.csv` | Items where estimation formulas were applied — has `formula_applied` column | Main deliverable for estimators |
| `summary.txt` | Human-readable summary with sheet log, category counts, and all calculated items | Quick review |
| `takeoff.json` | Complete structured data (raw + calculated + metadata) | Programmatic access, future integrations |

#### Run Folder Naming

Format: `{ProjectName}_{YYYYMMDD}_{HHMMSS}/`

Example: `Commercial_Office_Building_20260525_143022/`

#### CSV Field Reference — `calculations.csv`

| Column | Description |
|---|---|
| `item_type` | Which estimation table matched (flooring, drywall, etc.) |
| `description` | Human-readable item description |
| `raw_value` | Value as Claude read it from the drawing |
| `raw_unit` | Unit as Claude read it |
| `calculated_quantity` | Final quantity after formula |
| `calculated_unit` | Final unit (sq_ft, sheets, gallons, etc.) |
| `waste_factor` | Multiplier applied |
| `formula_applied` | The exact math as a string (e.g., "245 sf × 1.10 = 270 sf") |
| `estimation_table` | Which table was used |
| `source_sheet` | Which drawing page this came from |
| `source_location` | Where on the sheet |
| `source_text` | Raw text from the drawing |
| `specification` | Additional spec details if available |

---

### 3.6 `scraper.py` — Main Orchestrator

**What it does:** Connects browser → Claude → calculator → reporter in sequence for one or all projects.

#### `run_project_scrape()` Sequence

```
1. Start browser
2. Login
3. get_all_page_ids(project_id) → pages list
4. For each page:
   a. screenshot_full_drawing() → saves PNG
   b. analyze_drawing() → Claude JSON
   c. apply_estimation_tables() → calculated items
5. generate_report() → 4 output files
6. Close browser
```

#### Error Recovery

If screenshot fails:
1. Takes a debug screenshot of current state
2. Calls `make_navigation_decision()` — Claude analyzes the UI state
3. If decision is "skip" → moves to next page
4. Otherwise waits 5 seconds and retries once more

---

### 3.7 `pdf_analyzer.py` — PDF Mode

**What it does:** Skips the browser entirely. Accepts a PDF upload, renders each page to PNG via PyMuPDF (zoom=2.0 for 2x resolution), runs the same Claude + calculator + reporter pipeline.

Sheet name detection: Tries to extract standard sheet codes (A1.01, M3.2, etc.) from page text via regex. Falls back to "Page_N".

---

### 3.8 `project_cache.py` — Project List Cache

**What it does:** Stores StackCT project list to disk as JSON with a 24-hour TTL, so the UI dropdown loads instantly without launching a browser.

On app startup: `prefetch_in_background()` launches a background thread that fetches live if the cache is stale.

Cache file: `output/projects_cache.json`

---

### 3.9 `app.py` — Flask Web Application

**What it does:** Serves the web UI, manages background job threads, provides API endpoints.

#### API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Serve the main UI |
| `/api/projects` | GET | Return project list (from cache; `?refresh=1` forces live fetch) |
| `/api/projects/refresh` | POST | Force cache refresh |
| `/api/run/stackct` | POST | Start StackCT job (mode: all/specific) |
| `/api/run/pdf` | POST | Upload PDF and start analysis job |
| `/api/status/<job_id>` | GET | Poll job status and last 10 log lines |
| `/api/reports` | GET | List all report runs with file metadata |
| `/api/reports/<folder>/<file>` | GET | Download a specific file |

#### Job State Structure

```python
{
  "id": "a3f9bc12",
  "type": "stackct" | "pdf",
  "status": "queued" | "running" | "done" | "error",
  "progress": 0-100,
  "log": ["line1", "line2", ...],
  "result": {...} | None,
  "error": "message" | None,
  "project": "Project Name",
}
```

---

## 4. Data Flow & Extraction Logic

### 4.1 What Claude Extracts from Each Drawing Type

#### Floor Plans (sheet_type: floor_plan)
Claude looks for:
- **Room polygons** with labels (name, number, area in SF)
- **Dimension strings** along walls ("12'-6\"", "8'0\"")
- **Door symbols** with type tags (A, B, C → cross-references door schedule)
- **Window tags** (W1, W2, etc.)
- **Area callouts** (e.g., "CONFERENCE: 245 SF")
- **Material notes** ("VCT", "CPT", "PT" finish designations)

#### Electrical Drawings (sheet_type: schedule/panel_schedule)
Claude looks for:
- **Panel schedules** — structured tables with CKT, DESCRIPTION, BKR, phase loads
- **Panel header data** — voltage, phase count, wire count, main breaker size, bus rating
- **Load summaries** — total connected KVA, demand, diversity factor
- **Riser diagrams** — counting panels, transformers, disconnect switches

#### Mechanical Drawings
Claude looks for:
- **Equipment schedules** — fan coil units, AHUs, exhaust fans with CFM/kW specs
- **Duct dimensions** — sizes noted on supply/return paths
- **Equipment tags** — FCU-1, AHU-3, EF-5 with counts

#### Reflected Ceiling Plans
Claude looks for:
- **Ceiling area** (same as floor plan rooms)
- **Lighting fixture counts** by type
- **ACT grid notation** (2x2, 2x4)
- **Diffuser/grille symbols** with tags

#### Detail Sheets
Claude looks for:
- **Clearance dimensions** — "42\" MIN", "36\" MIN" (NEC clearance requirements)
- **Construction dimensions** — slab thickness, framing heights, insulation depths
- **Material callouts** with specifications

---

### 4.2 JSON Structure Claude Returns

```json
{
  "sheet_type": "floor_plan",
  "sheet_title": "LEVEL 1 FLOOR PLAN",
  "scale": "1/8\" = 1'-0\"",
  "measurements": [
    {
      "description": "north corridor length",
      "value": "52",
      "unit": "ft",
      "location": "north wall, grid line B-C",
      "raw_text": "52'-0\""
    }
  ],
  "components": [
    {
      "name": "PANEL HM1",
      "quantity": 1,
      "unit": "ea",
      "specification": "400A, 480Y/277V, 3-PHASE, 4-WIRE",
      "location": "electrical room 118"
    }
  ],
  "rooms": [
    {
      "name": "CONFERENCE 106",
      "area": 245,
      "dimensions": "17'-6\" x 14'-0\"",
      "notes": "VCT flooring, 9' ACT ceiling"
    }
  ],
  "schedules": [
    {
      "name": "PANEL HM1",
      "schedule_type": "panel_schedule",
      "header_info": "480Y/277V, 3PH, 4W, 400A MAIN, 400A BUS",
      "columns": ["CKT", "DESCRIPTION", "BKR", "A", "B", "C"],
      "rows": [
        {"CKT": "1", "DESCRIPTION": "PIU-2-3", "BKR": "20/1", "A": "4.0"},
        {"CKT": "3", "DESCRIPTION": "EH ENTRANCE", "BKR": "30/1", "B": "8.0"}
      ],
      "totals": "CONNECTED: 185 KVA, DEMAND: 142 KVA"
    }
  ],
  "materials": [],
  "confidence": "high",
  "notes": "All room areas visible. Panel schedule fully readable."
}
```

---

### 4.3 How Measurements Become Calculations

```
Raw: {"description": "east conference room", "area": 245, "unit": "sq_ft"}
     ↓ _calculate_from_room()
Output row 1: flooring → 245 × 1.10 = 269.5 sq_ft
Output row 2: ceiling_grid → 245 × 1.08 = 264.6 sq_ft
Output row 3: paint → ceil(62.5ft perimeter × 9ft height × 2 coats / 350) = 4 gallons
Output row 4: drywall → ceil(562.5 sf wall area × 1.12 / 32 sf/sheet) = 20 sheets
```

---

## 5. Estimation Tables & Calculation Engine

### 5.1 Full Formula Reference

#### Flooring
```
order_qty_sf = floor_area_sf × 1.10
```
Order 10% more than measured area to account for cutting waste, damaged pieces, and pattern matching.

#### Drywall (4'×8' sheets)
```
sheets = ceil(wall_area_sf × 1.12 / 32)
```
12% waste for cuts around doors/windows. 32 SF per standard 4×8 sheet.

#### Paint
```
gallons = ceil(paintable_area_sf × 2 / 350)
```
Two coats (primer + finish OR two finish coats). 350 SF coverage per gallon for standard latex.

#### Wall Framing (16" OC)
```
studs = ceil(wall_length_ft × 12 / 16) + 1
total_with_waste = ceil(studs × 1.10)
```
Plus 1 stud per corner. 10% waste for cuts and extras. Note: this counts wall studs only — top and bottom plates calculated separately.

#### Concrete Slab
```
cy = area_sf × thickness_in / (12 × 27)
```
Default 4" slab. 12 converts inches to feet; 27 converts cubic feet to cubic yards.

#### Ceiling Grid (ACT)
```
order_qty_sf = ceiling_area_sf × 1.08
```
8% waste for cuts at perimeter and around obstructions.

#### Insulation
```
order_qty_sf = area_sf × 1.05
```
5% waste for batts; more may be needed for spray foam (client should adjust).

### 5.2 How to Add a New Estimation Table

1. Open `calculator.py`
2. Add entry to `ESTIMATION_TABLES` dict:
```python
"hvac_ductwork": {
    "unit_out": "lf",
    "waste_factor": 1.15,
    "formula": "length × 1.15",
    "description": "Duct linear feet with 15% waste",
    "keywords": ["duct", "supply duct", "return duct", "diffuser duct"],
}
```
3. Add formula implementation to `_apply_formula()`:
```python
if item_type == "hvac_ductwork":
    wf = table["waste_factor"]
    return value * wf, "lf", f"{value:.0f} lf × {wf} waste = {value * wf:.0f} lf"
```
4. Adjust keywords to match Claude's typical descriptions for these items

---

## 6. Current Gaps & Known Issues

### Gap 1: Project List Truncation (High Priority)
**Problem:** `get_all_projects()` uses `a[href*="Takeoff"]` link scraping. StackCT's Angular app may not render all projects if the list is long (virtual scrolling).
**Fix:** Add scroll-to-bottom logic before scraping; or intercept the `/api/projects` XHR call directly.

### Gap 2: No Plan Selection Before Job Start (High Priority — User Reported)
**Problem:** When a project is selected, the job runs on ALL pages immediately. User has no way to preview which plans exist and select specific ones.
**Fix:** After selecting a project, show a plan selection step:
1. Fetch `get_all_page_ids()` for the selected project
2. Display thumbnail list with sheet names and checkboxes
3. User selects "All" or specific sheets
4. Job runs only on selected sheets

### Gap 3: No Preview in Reports Tab (High Priority — User Reported)
**Problem:** Reports are download-only. User cannot see content without downloading and opening files.
**Fix:** Add in-browser preview for:
- `summary.txt` → rendered as styled HTML
- `calculations.csv` → rendered as sortable/filterable data table
- `raw_items.csv` → same
- `takeoff.json` → collapsible JSON tree

### Gap 4: Screenshot Timing Fragility (Medium Priority)
**Problem:** `asyncio.sleep(5)` for tile rendering is a fixed wait. Slow network/VPS may need more; fast connections waste time.
**Fix:** Poll for canvas stability — screenshot repeatedly and compare pixel hashes until stable (no change in 1 second = loaded).

### Gap 5: No Progress Per-Sheet (Medium Priority)
**Problem:** Progress bar shows overall percentage but not what is currently being processed visually.
**Fix:** Show current sheet name prominently during processing, with a mini thumbnail of the screenshot being analyzed.

### Gap 6: No Cost Tracking (Medium Priority)
**Problem:** Users don't know how much each run costs in API tokens.
**Fix:** Log Claude API response token counts (`response.usage.input_tokens`, `response.usage.output_tokens`), calculate cost per run, display in reports.

### Gap 7: Single-file Output Mode for PDF (Low Priority)
**Problem:** PDF uploads don't support selecting individual pages.
**Fix:** After uploading PDF, show page thumbnails and allow selection before running.

### Gap 8: config.py has a hardcoded Mac path (Critical for Deployment)
**Problem:** `_env_path = Path("/Users/macbook/Desktop/Bobby Tailor/.env")` will fail on any server.
**Fix:** Use `Path(__file__).parent / ".env"` for relative path, falling back to `Path.home()` search.

### Gap 9: No Auth or Multi-user Support (Low Priority)
**Problem:** Anyone who can reach `localhost:5050` can run jobs.
**Fix:** Add simple password protection (Flask-Login with single admin user, or environment-based HTTP basic auth).

### Gap 10: Stack Trace Leaks in API Responses (Low Priority)
**Problem:** Error states sometimes expose full Python stack traces via job error field.
**Fix:** Sanitize error messages for end users; log full traces server-side only.

---

## 7. Complete Feature Upgrade Plan

### Phase 1: Critical UX Fixes (Implement First)

#### Feature 1.1: Plan Selection Workflow

**Trigger:** User selects a specific project and clicks "Preview Plans"

**Backend change** (`app.py`):
```python
@app.route("/api/projects/<int:project_id>/plans")
def get_project_plans(project_id):
    """Fetch all drawing pages for a project without running analysis."""
    from project_cache import get_project_pages  # new function
    return jsonify({"plans": get_project_pages(project_id)})
```

**`project_cache.py` addition:**
```python
async def _fetch_pages(project_id: int) -> list:
    b = StackCTBrowser()
    await b.start()
    try:
        if not await b.login(): raise RuntimeError("Login failed")
        return await b.get_all_page_ids(project_id)
    finally:
        await b.close()
```

**UI flow:**
1. User selects project → "Preview Plans" button appears
2. Click → loading spinner → list of sheets appears with checkboxes
3. Columns: checkbox, sheet number, sheet name, type badge (Floor Plan / Electrical / etc.)
4. Buttons: "Select All", "Select None", "Select by Type" dropdown
5. "Run Selected Plans (N)" button → starts job only for checked page IDs

**`/api/run/stackct` change:** Accept optional `page_ids: [int]` in POST body; if present, only run those pages.

---

#### Feature 1.2: In-Browser Report Preview

**Reports tab redesign:**

Each report card expands to show:

**Summary tab** (default): Renders `summary.txt` content as styled HTML with color-coded categories

**Calculations table tab**: Interactive data table showing `calculations.csv` with:
- Column sorting (click header)
- Filter by sheet (dropdown), filter by item type (dropdown)
- Search box (searches description + source_text)
- Color coding: green = high confidence, yellow = medium, red = low
- Export selected rows as CSV

**Raw Items tab**: Same as calculations table but for `raw_items.csv`

**JSON tab**: Collapsible tree viewer for `takeoff.json`

**Backend change** (`app.py`):
```python
@app.route("/api/reports/<run_folder>/preview/<filename>")
def preview_report_file(run_folder, filename):
    """Return file content as JSON for in-browser preview."""
    path = Path(OUTPUT_DIR) / run_folder / filename
    if filename.endswith(".csv"):
        import csv
        with open(path) as f:
            reader = csv.DictReader(f)
            return jsonify({"rows": list(reader)})
    elif filename.endswith(".json"):
        return send_file(str(path))
    elif filename.endswith(".txt"):
        return jsonify({"text": path.read_text()})
```

---

#### Feature 1.3: Fix Hardcoded Path in config.py

```python
# Replace this:
_env_path = Path("/Users/macbook/Desktop/Bobby Tailor/.env")

# With this:
_env_path = Path(__file__).parent / ".env"
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"
load_dotenv(dotenv_path=_env_path, override=True)
```

---

### Phase 2: Extraction Quality Improvements

#### Feature 2.1: Cost Tracking Per Run

In `claude_analyzer.py`, capture usage:
```python
response = client.messages.create(...)
usage = response.usage

# Pricing as of Claude 4 family (update if changed)
PRICING = {
    "claude-haiku-4-5":   {"in": 1.0,  "out": 5.0},    # per 1M tokens
    "claude-sonnet-4-6":  {"in": 3.0,  "out": 15.0},
}
p = PRICING.get(model, {"in": 3.0, "out": 15.0})
cost = (usage.input_tokens * p["in"] + usage.output_tokens * p["out"]) / 1_000_000

return {
    ...extracted,
    "_tokens_in": usage.input_tokens,
    "_tokens_out": usage.output_tokens,
    "_cost_usd": round(cost, 6),
    "_model": model,
}
```

Aggregate in `reporter.py` and add to `takeoff.json` and `summary.txt`.

---

#### Feature 2.2: Canvas Stability Detection

Replace fixed `asyncio.sleep(5)` with pixel hash polling:
```python
async def _wait_for_canvas_stable(self, selector: str, timeout_s: int = 15) -> bool:
    import hashlib
    prev_hash = None
    stable_count = 0
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        el = await self.page.query_selector(selector)
        if el:
            buf = await el.screenshot()
            h = hashlib.md5(buf).hexdigest()
            if h == prev_hash:
                stable_count += 1
                if stable_count >= 2:  # stable for 2 consecutive checks
                    return True
            else:
                stable_count = 0
            prev_hash = h
        await asyncio.sleep(0.8)
    return False
```

---

#### Feature 2.3: Multi-page Project Scroll Fix

In `get_all_projects()`, scroll to bottom of project list to trigger Angular lazy loading:
```python
# After page load, scroll project list container to bottom repeatedly
for _ in range(5):
    await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(1.5)
```

---

### Phase 3: UI/UX Complete Overhaul

See Section 8 for full specification.

---

### Phase 4: Advanced Features (Future)

#### Feature 4.1: Per-Sheet Confidence Review
After analysis, show a review interface where user can:
- See the screenshot side-by-side with extracted data
- Mark items as "accepted", "rejected", or "needs review"
- Manually edit quantities
- Re-run analysis on a specific sheet

#### Feature 4.2: Client-Specific Waste Factor Profiles
Store named profiles in a JSON config file:
```json
{
  "standard": {"flooring": 1.10, "drywall": 1.12, "paint": 1.0},
  "high_waste_demo": {"flooring": 1.20, "drywall": 1.15, "paint": 1.05},
  "client_ABC": {"flooring": 1.08, "drywall": 1.10}
}
```
Let user select profile before running.

#### Feature 4.3: StackCT Webhook / Scheduled Runs
APScheduler is already in the codebase. Add UI for:
- Setting a cron schedule per project
- Automatic email/Slack notification when run completes
- Diff mode: show what changed since last run

#### Feature 4.4: Export to Excel
Add `xlsxwriter` output with:
- Sheet 1: Summary dashboard with totals by category
- Sheet 2: Calculations with conditional formatting
- Sheet 3: Raw items
- Styled with client branding

---

## 8. UI/UX Complete Redesign Specification

### 8.1 Design Direction

**Aesthetic:** Industrial-precision. Dark-mode professional tool. Think Bloomberg Terminal meets modern SaaS — dense, information-rich, but organized. Construction is a physical, serious industry; the UI should feel like a precision instrument, not a consumer app.

**Color Palette:**
```css
--bg-base: #0b0d11;          /* Near-black base */
--bg-surface: #141720;       /* Card backgrounds */
--bg-elevated: #1c1f2e;      /* Modal/dropdown backgrounds */
--border-subtle: #252a3a;    /* Default borders */
--border-active: #3b82f6;    /* Active/focus borders */
--accent-primary: #3b82f6;   /* Blue — primary actions */
--accent-secondary: #6366f1; /* Indigo — secondary */
--accent-success: #10b981;   /* Green — done/positive */
--accent-warning: #f59e0b;   /* Amber — caution */
--accent-danger: #ef4444;    /* Red — error */
--text-primary: #f1f5f9;     /* Main text */
--text-secondary: #94a3b8;   /* Secondary/muted text */
--text-tertiary: #475569;    /* Disabled/placeholder */
--accent-construction: #f97316; /* Orange — construction theme accent */
```

**Typography:**
```
Display/Headers: "DM Mono" (monospace, engineering precision feel)
Body: "Inter" (clean, readable)
Data/Numbers: "JetBrains Mono" (numbers align, professional data display)
```
Load from Google Fonts:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

---

### 8.2 Layout Structure

```
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR (240px fixed)    │  MAIN CONTENT (flex 1)       │
│                           │                               │
│  [BT Logo + wordmark]     │  [Contextual header]          │
│                           │                               │
│  Navigation:              │  [Page content]               │
│  • Projects               │                               │
│  • PDF Upload             │                               │
│  • Reports                │                               │
│  • Settings               │                               │
│                           │                               │
│  ─────────────────────    │                               │
│  [Active Job Status]      │                               │
│  (live mini card)         │                               │
└──────────────────────────────────────────────────────────┘
```

Replace the current tab-based layout with a **fixed sidebar + main content** layout. This gives more space and feels more like a professional application.

---

### 8.3 Page: Projects (StackCT)

```
Header: "StackCT Projects"   [Refresh ↻]   [Last synced: 2 min ago]

┌─────────────────────────────────────────────────────────────────┐
│  SCOPE                                                           │
│  ○ All Projects   ● Specific Project                            │
└─────────────────────────────────────────────────────────────────┘

[if Specific Project selected:]

Search: [____________________] ← live filter on project list

Project List:
┌───────────────────────────────────────────────────────────────┐
│  ● Office Complex – Downtown     │ 12 sheets   ID: 7409312    │
│  ○ Retail Build-Out – Unit 4A    │ 8 sheets    ID: 7388201    │
│  ○ Parking Structure Phase 2     │ 24 sheets   ID: 7412009    │
└───────────────────────────────────────────────────────────────┘

[PREVIEW PLANS →]  ← enabled only when project selected

┌── Plan Selection Panel (appears after clicking Preview Plans) ──┐
│  Loading plans...  [spinner]                                     │
│  ─ or ─                                                          │
│  ☑ Select All  [ Filter by type ▼ ]                              │
│                                                                   │
│  ☑  A1.01   Floor Plan Level 1          [Floor Plan]             │
│  ☑  A1.02   Floor Plan Level 2          [Floor Plan]             │
│  ☑  A3.01   Enlarged Toilet Room Plans  [Floor Plan]             │
│  ☐  E1.01   Electrical Riser Diagram    [Electrical]             │
│  ☑  E2.01   Panel Schedule HM1         [Schedule]               │
│  ☐  M1.01   Mechanical Floor Plan      [Mechanical]             │
│  ...                                                             │
│                                                                   │
│  [RUN SELECTED PLANS (4) →]                                      │
└──────────────────────────────────────────────────────────────────┘
```

**Sheet type badges** use color coding:
- Floor Plan → blue
- Electrical → yellow
- Mechanical → orange
- Schedule → purple
- Other → gray

---

### 8.4 Page: Active Job (Live Monitor)

When a job is running, a full-page job monitor appears (or slides in as a panel):

```
┌─── JOB MONITOR ─────────────────────────────────────────────────┐
│  Project: Office Complex – Downtown          Job: a3f9bc12       │
│  Started: 14:23:05                           Status: ● RUNNING   │
│                                                                   │
│  ████████████████████░░░░░░░░░░░  68%   [8 / 12 sheets]         │
│                                                                   │
│  Currently analyzing: E2.01 – Panel Schedule HM1                 │
│                                                                   │
│  ┌─ SHEET LOG ──────────────────────────────────────────────┐    │
│  │  ✓  A1.01  Floor Plan L1      18 meas  3 rooms  2 comp  │    │
│  │  ✓  A1.02  Floor Plan L2      21 meas  5 rooms  4 comp  │    │
│  │  ✓  A3.01  Toilet Plans        6 meas  2 rooms  0 comp  │    │
│  │  ✓  E1.01  Riser Diagram       4 meas  8 comp   0 rooms │    │
│  │  ⟳  E2.01  Panel Schedule    analyzing...               │    │
│  │  ○  M1.01  Mechanical Plan    pending                    │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─ LOG CONSOLE ────────────────────────────────────────────┐    │
│  │  [14:23:11] Logged in to StackCT                        │    │
│  │  [14:23:14] Found 12 drawing pages                      │    │
│  │  [14:23:19] A1.01: 18 measurements, 3 rooms extracted  │    │
│  │  [14:23:24] A1.01: 12 calculated takeoff items          │    │
│  │  [14:23:29] A1.02: 21 measurements, 5 rooms extracted  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  [CANCEL JOB]                                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

### 8.5 Page: Reports

```
Header: "Reports"   [↻ Refresh]   [🔍 Search reports...]

┌─── REPORT CARDS ────────────────────────────────────────────────┐
│                                                                   │
│  ┌─ Office Complex – Downtown ──────────────────── May 25, 2026 ─┐ │
│  │  12 sheets  ·  847 raw items  ·  312 calculated  ·  $0.04    │ │
│  │                                                               │ │
│  │  [📊 Preview]  [📥 Calculations CSV]  [📋 Raw CSV]  [{ }]    │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Retail Build-Out – Unit 4A ─────────────────── May 24, 2026 ─┐ │
│  │  8 sheets  ·  421 raw items  ·  158 calculated  ·  $0.02     │ │
│  │  [📊 Preview]  [📥 Calculations CSV]  [📋 Raw CSV]  [{ }]    │ │
│  └───────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

#### Report Preview Panel (expands below card on click)

```
[Summary] [Calculations] [Raw Items] [JSON]   ← tab strip

── Calculations view ──────────────────────────────────────────────
Filter: [All Sheets ▼]  [All Types ▼]  [🔍 search...]   [Export CSV]

 item_type    │ description          │ qty    │ unit   │ sheet      │ formula
 ─────────────┼──────────────────────┼────────┼────────┼────────────┼─────────────────────
 flooring     │ Conf Room 106        │ 269.5  │ sq_ft  │ A1.01      │ 245 × 1.10 = 269.5
 ceiling_grid │ Conf Room 106        │ 264.6  │ sq_ft  │ A1.01      │ 245 × 1.08 = 264.6
 paint        │ Paint for Conf 106   │ 4      │ gal    │ A1.01      │ ceil(562 × 2/350)
 drywall      │ Drywall Conf 106     │ 20     │ sheets │ A1.01      │ ceil(562 × 1.12/32)
 flooring     │ Open Office 201      │ 863.5  │ sq_ft  │ A1.02      │ 785 × 1.10 = 863.5
 ...
──────────────────────────────────────────────────────────────────
 Totals: flooring 2,847 sq_ft │ drywall 312 sheets │ paint 89 gal
```

---

### 8.6 Page: PDF Upload

```
┌─── PDF ANALYSIS ─────────────────────────────────────────────────┐
│  Project Name: [________________________]                         │
│                                                                   │
│  ┌──── DROP ZONE ────────────────────────────────────────────┐   │
│  │                                                            │   │
│  │          📄  Drop your PDF here                           │   │
│  │              or click to browse                           │   │
│  │                                                            │   │
│  │  Supports: Construction drawings, floor plans, schedules  │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [After upload: shows page count and file size]                   │
│  "Office_Plans.pdf  ·  24 pages  ·  18.4 MB"                     │
│                                                                   │
│  ┌─ Page Selection (optional) ──────────────────────────────┐    │
│  │  ○ Analyze all 24 pages                                  │    │
│  │  ● Select pages: [1] [2] [3] ... [24]   ← thumbnail grid│    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  [ANALYZE PDF →]                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

### 8.7 Sidebar: Active Job Mini-Card

When a job is running, the sidebar shows a persistent mini-card:

```
┌─ ACTIVE JOB ───────────────┐
│ ● Office Complex           │
│ ████████░░░ 68%  8/12     │
│ E2.01 – Panel HM1          │
│ [View Details →]           │
└────────────────────────────┘
```

---

### 8.8 Settings Page

```
┌─── SETTINGS ─────────────────────────────────────────────────────┐
│                                                                   │
│  StackCT Credentials                                             │
│  Email:    [_____________________________]                        │
│  Password: [_____________________________] [Test Connection]      │
│                                                                   │
│  Claude API                                                       │
│  API Key:    [sk-ant-...            ] [Test]                     │
│  Default Model: [claude-haiku-4-5 ▼]                             │
│  Schedule Model: [claude-sonnet-4-6 ▼]                           │
│                                                                   │
│  Estimation Defaults                                             │
│  Waste Profile: [Standard ▼]  [Edit Profiles]                    │
│                                                                   │
│  Output                                                           │
│  Output Directory: [./output        ]                            │
│  Keep screenshots: [○ Yes  ● No]                                 │
│                                                                   │
│  [SAVE SETTINGS]                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 9. Step-by-Step Agent Implementation Guide

This section tells the AI agent exactly what to implement, in what order, in what files.

### Step 0: Prerequisites

Before writing any code:

```bash
# Confirm environment
python3 --version    # Must be 3.10+
pip install -r requirements.txt
playwright install chromium
pip install Pillow   # Required for image compression (not in requirements.txt!)

# Update requirements.txt to add:
echo "Pillow>=10.0.0" >> requirements.txt
```

---

### Step 1: Fix config.py (5 minutes)

File: `config.py`

Replace the hardcoded path block:
```python
# OLD (delete this):
_env_path = Path("/Users/macbook/Desktop/Bobby Tailor/.env")
load_dotenv(dotenv_path=_env_path, override=True)

# NEW (replace with this):
_env_path = Path(__file__).parent / ".env"
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"
load_dotenv(dotenv_path=_env_path, override=True)
```

---

### Step 2: Add Plan Fetching API (30 minutes)

**File: `project_cache.py`** — add at bottom:
```python
async def _fetch_pages_for_project(project_id: int) -> list:
    """Fetch page list for a specific project. Requires browser login."""
    from browser import StackCTBrowser
    b = StackCTBrowser()
    await b.start()
    try:
        if not await b.login():
            raise RuntimeError("Login failed")
        return await b.get_all_page_ids(project_id)
    finally:
        await b.close()


def get_project_plans(project_id: int) -> dict:
    """Return list of drawing pages for a specific project."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        pages = loop.run_until_complete(_fetch_pages_for_project(project_id))
        loop.close()
        return {"plans": pages, "project_id": project_id}
    except Exception as e:
        logger.error(f"Plan fetch failed: {e}")
        return {"plans": [], "error": str(e)}
```

**File: `app.py`** — add new route:
```python
@app.route("/api/projects/<int:project_id>/plans")
def get_project_plans(project_id):
    """Return drawing page list for plan selection UI."""
    from project_cache import get_project_plans
    result = get_project_plans(project_id)
    return jsonify(result)
```

**File: `app.py`** — modify `/api/run/stackct` to accept `page_ids`:
```python
@app.route("/api/run/stackct", methods=["POST"])
def run_stackct():
    data = request.json or {}
    mode = data.get("mode", "all")
    project_id = data.get("project_id")
    project_name = data.get("project_name", "Project")
    page_ids = data.get("page_ids")  # NEW: optional list of specific page IDs

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "stackct", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name, "mode": mode
    }

    t = threading.Thread(
        target=_stackct_job,
        args=(job_id, mode, project_id, project_name, page_ids),  # pass page_ids
        daemon=True
    )
    t.start()
    return jsonify({"job_id": job_id})
```

**File: `scraper.py`** — modify `run_project_scrape` signature:
```python
async def run_project_scrape(
    project_id: int,
    project_name: str,
    page_ids_filter: Optional[List[int]] = None,  # NEW
    log_callback=None,
    progress_callback=None
) -> dict:
    ...
    pages = await browser.get_all_page_ids(project_id)
    
    # NEW: filter if specific pages requested
    if page_ids_filter:
        pages = [p for p in pages if p["page_id"] in page_ids_filter]
        log(f"Filtered to {len(pages)} selected pages")
    ...
```

---

### Step 3: Add Report Preview API (20 minutes)

**File: `app.py`** — add preview endpoint:
```python
@app.route("/api/reports/<run_folder>/preview/<filename>")
def preview_report_file(run_folder, filename):
    """Return file content for in-browser preview."""
    if "/" in run_folder or ".." in run_folder or "/" in filename or ".." in filename:
        return jsonify({"error": "Invalid path"}), 400
    path = Path(OUTPUT_DIR) / run_folder / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404

    if filename.endswith(".csv"):
        import csv
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return jsonify({"type": "csv", "rows": rows, "count": len(rows)})
    elif filename.endswith(".json"):
        return jsonify({"type": "json", "data": json.loads(path.read_text())})
    elif filename.endswith(".txt"):
        return jsonify({"type": "text", "text": path.read_text()})
    return jsonify({"error": "Unsupported format"}), 400
```

---

### Step 4: Full UI Rebuild (2-4 hours)

Replace `templates/index.html` completely. The new template must implement:

**Layout:** Fixed sidebar (240px) + scrollable main content.

**Sidebar contents:**
```html
<nav class="sidebar">
  <div class="logo-block">
    <span class="logo-icon">BT</span>
    <span class="logo-text">Bobby Tailor</span>
  </div>
  <ul class="nav-links">
    <li class="active" onclick="navigate('projects')">📋 Projects</li>
    <li onclick="navigate('pdf')">📄 PDF Upload</li>
    <li onclick="navigate('reports')">📊 Reports</li>
    <li onclick="navigate('settings')">⚙ Settings</li>
  </ul>
  <div class="active-job-mini" id="activeJobMini" style="display:none">
    <!-- Populated by JS when job is running -->
  </div>
</nav>
```

**Projects page — Plan Selection Panel:**
```javascript
async function loadProjectPlans(projectId) {
  const panel = document.getElementById('planSelectionPanel');
  panel.innerHTML = '<div class="loading">Loading plans...</div>';
  panel.style.display = 'block';
  
  const res = await fetch(`/api/projects/${projectId}/plans`);
  const data = await res.json();
  
  // Render plan list with checkboxes
  panel.innerHTML = `
    <div class="plan-controls">
      <button onclick="selectAllPlans()">Select All</button>
      <button onclick="selectNonePlans()">Select None</button>
      <select onchange="filterPlansByType(this.value)">
        <option value="">All Types</option>
        <option value="electrical">Electrical</option>
        <option value="mechanical">Mechanical</option>
        <option value="architectural">Architectural</option>
      </select>
    </div>
    <div class="plan-list">
      ${data.plans.map(p => `
        <label class="plan-row">
          <input type="checkbox" class="plan-check" value="${p.page_id}" checked>
          <span class="sheet-name">${p.sheet_name || 'Unnamed'}</span>
          <span class="sheet-badge ${getSheetType(p.sheet_name)}">${getSheetType(p.sheet_name)}</span>
        </label>
      `).join('')}
    </div>
    <button class="run-btn" onclick="runSelectedPlans(${projectId})">
      Run Selected Plans (<span id="selectedCount">${data.plans.length}</span>)
    </button>
  `;
}

function getSheetType(name) {
  const u = (name || '').toUpperCase();
  if (/^E\d/.test(u) || u.includes('ELECTRICAL')) return 'electrical';
  if (/^M\d/.test(u) || u.includes('MECHANICAL')) return 'mechanical';
  if (/^P\d/.test(u) || u.includes('PLUMBING')) return 'plumbing';
  if (u.includes('SCHEDULE') || u.includes('PANEL')) return 'schedule';
  return 'architectural';
}
```

**Reports page — expandable preview:**
```javascript
async function expandReport(runFolder) {
  const previewEl = document.getElementById(`preview-${runFolder}`);
  if (previewEl.style.display !== 'none') {
    previewEl.style.display = 'none';
    return;
  }
  
  previewEl.innerHTML = '<div class="loading">Loading preview...</div>';
  previewEl.style.display = 'block';
  
  // Load calculations CSV for preview
  const res = await fetch(`/api/reports/${encodeURIComponent(runFolder)}/preview/calculations.csv`);
  const data = await res.json();
  
  previewEl.innerHTML = renderDataTable(data.rows, ['item_type', 'description', 'calculated_quantity', 'calculated_unit', 'formula_applied', 'source_sheet']);
}

function renderDataTable(rows, columns) {
  if (!rows.length) return '<p class="empty">No data</p>';
  return `
    <div class="table-controls">
      <input type="text" placeholder="🔍 Search..." oninput="filterTable(this)">
      <select onchange="filterByColumn(this, 'item_type')">
        <option value="">All Types</option>
        ${[...new Set(rows.map(r => r.item_type))].map(t => `<option>${t}</option>`).join('')}
      </select>
    </div>
    <div class="data-table-wrapper">
      <table class="data-table">
        <thead><tr>${columns.map(c => `<th onclick="sortTable('${c}')">${c} ⇅</th>`).join('')}</tr></thead>
        <tbody>${rows.slice(0, 500).map(row =>
          `<tr>${columns.map(c => `<td class="cell-${c}">${row[c] || ''}</td>`).join('')}</tr>`
        ).join('')}</tbody>
      </table>
      ${rows.length > 500 ? `<p class="table-note">Showing 500 of ${rows.length} rows</p>` : ''}
    </div>
  `;
}
```

---

### Step 5: Add Cost Tracking (20 minutes)

**File: `claude_analyzer.py`** — modify `analyze_drawing()` return:
```python
# After parsing JSON response, add:
PRICING = {
    "claude-haiku-4-5":  {"in": 1.0, "out": 5.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-opus-4-6":   {"in": 15.0, "out": 75.0},
}
p = PRICING.get(model, {"in": 3.0, "out": 15.0})
input_tokens = response.usage.input_tokens
output_tokens = response.usage.output_tokens
cost = (input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000

extracted["_tokens_in"] = input_tokens
extracted["_tokens_out"] = output_tokens
extracted["_cost_usd"] = round(cost, 6)
extracted["_model_used"] = model
```

**File: `reporter.py`** — aggregate in `generate_report()`:
```python
total_cost = sum(d.get("_cost_usd", 0) for d in all_extracted)
total_tokens_in = sum(d.get("_tokens_in", 0) for d in all_extracted)
total_tokens_out = sum(d.get("_tokens_out", 0) for d in all_extracted)

report["api_usage"] = {
    "total_cost_usd": round(total_cost, 4),
    "total_tokens_in": total_tokens_in,
    "total_tokens_out": total_tokens_out,
}
```

---

### Step 6: Canvas Stability Detection (20 minutes)

**File: `browser.py`** — replace `asyncio.sleep(5)` in `screenshot_full_drawing()`:

```python
# Replace:
await asyncio.sleep(5)

# With:
await self._wait_for_canvas_stable('#canvas-interaction', timeout_s=15)

# Add method to class:
async def _wait_for_canvas_stable(self, selector: str, timeout_s: int = 15) -> bool:
    """Wait until canvas stops changing pixel content (drawing fully loaded)."""
    import hashlib
    prev_hash = None
    stable_count = 0
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            el = await self.page.query_selector(selector)
            if el:
                buf = await el.screenshot()
                h = hashlib.md5(buf).hexdigest()
                if h == prev_hash:
                    stable_count += 1
                    if stable_count >= 2:
                        logger.info(f"Canvas stable after {time.time() - (deadline - timeout_s):.1f}s")
                        return True
                else:
                    stable_count = 0
                prev_hash = h
        except Exception:
            pass
        await asyncio.sleep(0.8)
    logger.warning("Canvas stability timeout — proceeding anyway")
    return False
```

---

## 10. File & Folder Structure (Target State)

```
bobby-tailor/
├── .env                          ← credentials (never commit)
├── .env.example                  ← template (commit this)
├── .gitignore
├── requirements.txt              ← add Pillow>=10.0.0
├── README.md
│
├── app.py                        ← Flask app (add new routes)
├── main.py                       ← CLI entry point
├── config.py                     ← fix hardcoded path
├── scraper.py                    ← add page_ids_filter param
├── browser.py                    ← add canvas stability detection
├── claude_analyzer.py            ← add cost tracking
├── calculator.py                 ← estimation formulas (edit waste factors here)
├── reporter.py                   ← add api_usage to report
├── project_cache.py              ← add get_project_plans()
├── pdf_analyzer.py               ← unchanged
│
├── templates/
│   └── index.html                ← complete rewrite (Section 8)
│
├── static/                       ← NEW: separate static files
│   ├── app.js                    ← extracted from index.html
│   └── style.css                 ← extracted from index.html
│
└── output/                       ← generated, gitignored
    ├── projects_cache.json
    ├── run.log
    └── {ProjectName}_{timestamp}/
        ├── takeoff.json
        ├── raw_items.csv
        ├── calculations.csv
        └── summary.txt
```

---

## 11. Environment & Deployment

### 11.1 Local Development

```bash
# Clone and set up
git clone <repo>
cd bobby-tailor
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Edit .env with your credentials

# Run
python3 app.py
# Open http://localhost:5050
```

### 11.2 Hostinger VPS Deployment (Ubuntu)

```bash
# On the VPS
sudo apt update && sudo apt install -y python3-pip python3-venv

cd /home/ubuntu/bobby-tailor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium   # installs system deps

# Set environment (production)
cp .env.example .env
nano .env  # add real credentials

# Run with gunicorn (production WSGI)
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5050 app:app --timeout 300

# Optional: systemd service for auto-start
# Create /etc/systemd/system/bobby-tailor.service
# Enable: systemctl enable bobby-tailor && systemctl start bobby-tailor
```

### 11.3 Environment Variables Reference

```env
# StackCT
STACKCT_EMAIL=your@email.com
STACKCT_PASSWORD=yourpassword

# Anthropic
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-haiku-4-5
CLAUDE_MODEL_SCHEDULES=claude-sonnet-4-6

# Browser
HEADLESS=true

# Output
OUTPUT_DIR=./output
```

### 11.4 Headless Chrome on VPS

StackCT uses JavaScript-heavy rendering. For VPS deployment:
```bash
# Install Chromium deps on Ubuntu
sudo apt install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2
```

If StackCT blocks headless browsers, add to `browser.py`:
```python
args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
```

---

## 12. Testing & Validation Checklist

### Pre-Run Checks
- [ ] `.env` file exists with correct credentials
- [ ] `playwright install chromium` has been run
- [ ] `Pillow` is installed (`pip show Pillow`)
- [ ] `output/` directory exists (auto-created by app)
- [ ] StackCT credentials valid (test with Settings → Test Connection)
- [ ] Anthropic API key valid (test with Settings → Test)

### After Each Code Change
- [ ] Run `python3 app.py` and confirm it starts without errors
- [ ] Navigate to a project, load plans (verify plan selection panel appears)
- [ ] Run a single-page job (pick one sheet, not all)
- [ ] Confirm `calculations.csv` has rows with `formula_applied` values
- [ ] Confirm `raw_items.csv` has schedule_row entries
- [ ] Open Reports tab, click Preview, confirm table renders

### Quality Checks for Extraction
- [ ] Panel schedules: each circuit row appears in `raw_items.csv` as a `schedule_row`
- [ ] Room areas generate 4 rows each in `calculations.csv` (flooring, ceiling, paint, drywall)
- [ ] No phantom rows with `table_used: "none"` in `calculations.csv` (those belong in raw only)
- [ ] `formula_applied` column is never empty in `calculations.csv`
- [ ] Temperature values and scale notations don't appear as measurements

### Known False Positive Patterns to Watch
If you see these in calculations.csv, the classifier needs tuning:
- Mounting heights (e.g., "42 MIN" NEC clearances) appearing as wall_framing
- Panel IDs (e.g., "HM1") appearing as measurements with value "1"
- Scale annotations ("1/4" = 1'-0"") appearing as measurements

---

## Appendix A: Quick Reference — Claude Prompt Output Validation

When debugging Claude's JSON output, check for these patterns:

**Good measurement extraction:**
```json
{"description": "north wall length", "value": "52", "unit": "ft", "raw_text": "52'-0\""}
```

**Bad — should be filtered out:**
```json
{"description": "scale", "value": "1/4", "unit": "= 1'-0\""}  ← scale annotation
{"description": "panel", "value": "HM1", "unit": "ea"}          ← catalog identifier
{"description": "temperature", "value": "75", "unit": "°F"}     ← design condition
```

**Good schedule extraction:**
```json
{
  "name": "PANEL HM1",
  "rows": [
    {"CKT": "1", "DESCRIPTION": "PIU-2-3", "BKR": "20/1", "A": "4.0"},
    {"CKT": "3", "DESCRIPTION": "RECEPTACLES", "BKR": "20/1", "B": "6.0"}
  ]
}
```

**Bad — fabricated quantity:**
```json
{"name": "PANEL HM1", "rows": [{"QUANTITY": "1", "DESCRIPTION": "Panel"}]}
```

---

## Appendix B: Estimation Formula Quick Reference

| Material | Raw Input | Formula | Example |
|---|---|---|---|
| Flooring | Room SF | SF × 1.10 | 245 SF → 269.5 SF order |
| Drywall | Wall SF | ceil(SF × 1.12 / 32) | 562 SF → 20 sheets |
| Paint | Wall SF | ceil(SF × 2 / 350) | 562 SF → 4 gallons |
| Framing | LF wall | ceil(LF×12/16)+1 × 1.10 | 50 LF → 43 studs |
| Concrete | Room SF | SF × 4 / (12×27) | 500 SF → 6.17 CY |
| ACT Ceiling | Room SF | SF × 1.08 | 245 SF → 264.6 SF |
| Insulation | Area SF | SF × 1.05 | 300 SF → 315 SF |

---

*Document version: 2.0 | Created by Praivox for Bobby Tailor project | Last updated: May 2026*

*This document should be updated whenever significant architectural decisions are made, new modules are added, or the StackCT platform changes its DOM structure.*