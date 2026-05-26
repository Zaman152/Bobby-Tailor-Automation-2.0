# Bobby Tailor — StackCT Automated Estimation & Take-off

Automated construction estimation: logs into StackCT, scrapes every drawing page,
extracts measurements/schedules/components via Claude vision, applies estimation
formulas, and produces a structured take-off report with full source traceability.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY + StackCT login
```

## Run

```bash
# Web UI (recommended) — runs on http://localhost:5050
python3 app.py

# CLI — all projects
python3 main.py

# CLI — specific project
python3 main.py --project-id 7409312 --project-name "Some Project"
```

## Output

Each run creates its own folder under `./output/`:
```
output/
└── Project_Name_20260525_203144/
    ├── calculations.csv     ← takeoff quantities with formulas applied
    ├── raw_items.csv        ← every measurement/schedule row Claude extracted
    ├── summary.txt          ← human-readable summary
    └── takeoff.json         ← full structured data
```

## Architecture

```
app.py            Flask web UI + background job runner
main.py           CLI entry point
scraper.py        Orchestrator: login → page discovery → screenshot → analyze → calc → report
browser.py        Playwright control (login, navigate, screenshot the drawing canvas)
claude_analyzer.py  Claude vision extraction with prompt caching
calculator.py     Estimation tables + formula engine
reporter.py       Output generation (per-run folders, CSV + JSON + summary)
config.py         Settings loaded from .env
project_cache.py  24-hour project list cache
pdf_analyzer.py   Direct-PDF mode (skips browser if you have the drawings as PDF)
templates/        Web UI
```

## How it works

1. **Login** — Playwright authenticates via Auth0 (handles email → password flow)
2. **Discover pages** — Reads `data-page-id` attributes from the thumbnail grid (1 call, no per-page clicking)
3. **Screenshot** — Navigates to each drawing page, dismisses StackCT promo overlays via CSS, captures the `#canvas-interaction` element at 2x DPR. Image is auto-compressed to fit Anthropic's 5 MB limit.
4. **Analyze** — Sends each PNG to Claude with a cached extraction prompt. Auto-routes schedule/panel sheets to Sonnet for better tabular reading; everything else uses Haiku.
5. **Calculate** — Applies estimation tables (flooring, paint, drywall, framing, concrete, schedules) with real construction formulas.
6. **Report** — Writes 4 files per run inside a timestamped folder.

## Estimation Tables

All formulas live in `calculator.py → ESTIMATION_TABLES`. Edit those dict values to match your job's waste factors, coverage rates, sheet sizes, stud spacings, etc.

```python
ESTIMATION_TABLES = {
    "flooring":     {"waste_factor": 1.10, ...},     # area × 1.10
    "drywall":      {"sheet_size_sf": 32, "waste_factor": 1.12},
    "paint":        {"coverage_per_gallon": 350, "coats": 2},
    "wall_framing": {"stud_spacing_in": 16, ...},     # studs at 16" OC
    "concrete_slab":{"default_thickness_in": 4},      # 4" slab → cu yds
    "ceiling_grid": {"waste_factor": 1.08},
    "doors":        {...},
    "windows":      {...},
    ...
}
```

Every calculated row in `calculations.csv` has a `formula_applied` column showing the exact math.

## Cost

With Haiku (default) + prompt caching, a 30-page project runs ~$0.05.
Set `CLAUDE_MODEL=claude-sonnet-4-6` in `.env` for richer table extraction at ~3× cost.
