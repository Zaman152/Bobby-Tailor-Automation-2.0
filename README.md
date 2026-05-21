# Bobby Tailor — StackCT Automated Estimation Scraper

## Setup

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## Run

```bash
# All projects (one-off)
python main.py

# Specific project
python main.py --project-id 7409312 --project-name "LaserAway - Cumming GA"

# On schedule (daily 8am by default)
python main.py --schedule
```

## Output

Each run creates in `./output/`:
- `*_report.json` — full structured data
- `*_estimates.csv` — line items with source tracing
- `*_summary.txt` — human-readable summary
- `screenshots/` — one PNG per drawing page

## Architecture

```
main.py          Entry point + scheduler
scraper.py       Orchestration pipeline
browser.py       Playwright browser control (login, navigate, screenshot)
claude_analyzer.py  Claude API vision extraction
calculator.py    Apply estimation tables to extracted data
reporter.py      Generate JSON / CSV / summary reports
config.py        All settings via .env
```

## How it works

1. **Login** — Playwright logs into StackCT (2-step: email → password)
2. **Discover pages** — Clicks through sidebar sheets, records page IDs from URL
3. **Screenshot** — Navigates to each drawing page, captures full-resolution PNG
4. **Analyze** — Sends PNG to Claude API with structured extraction prompt
5. **Calculate** — Applies estimation tables to extracted measurements/components
6. **Report** — Generates CSV + JSON + summary with full source tracing

## Estimation Tables

Update `calculator.py → ESTIMATION_TABLES` with the client's actual tables once provided.
Current structure:
```python
ESTIMATION_TABLES = {
    "flooring": {"waste_factor": 1.10, ...},
    "wall_framing": {"stud_spacing": 16, ...},
    ...
}
```
