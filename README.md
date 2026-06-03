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

## VPS Deployment (Ubuntu)

Production deployment on Hostinger VPS or similar Ubuntu hosts.

### System requirements

- Ubuntu 20.04+ or Debian 11+
- Python 3.10+
- 2 GB RAM minimum (4 GB recommended for concurrent jobs)
- Chromium system dependencies via Playwright

### Installation

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv

cd /home/ubuntu
git clone <repo-url> bobby-tailor
cd bobby-tailor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

playwright install chromium
playwright install-deps chromium

cp .env.example .env
# Edit .env with StackCT and Anthropic credentials
mkdir -p uploads output output/screenshots
```

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `STACKCT_EMAIL` | StackCT login email | (required) |
| `STACKCT_PASSWORD` | StackCT login password | (required) |
| `ANTHROPIC_API_KEY` | Anthropic API key (`sk-ant-...`) | (required) |
| `CLAUDE_MODEL` | Model for general drawings | `claude-haiku-4-5` |
| `CLAUDE_MODEL_SCHEDULES` | Model for schedule/panel sheets | `claude-sonnet-4-6` |
| `HEADLESS` | Run browser headless | `true` |
| `OUTPUT_DIR` | Report output directory | `./output` |
| `CANVAS_STABILITY_TIMEOUT` | Max seconds waiting for canvas render | `15` |
| `CANVAS_STABILITY_CHECKS` | Consecutive stable hashes before capture | `2` |
| `MAX_PREVIEW_ROWS` | CSV preview row cap in web UI | `500` |
| `JOB_HISTORY_RETENTION_DAYS` | Days to keep job history in SQLite (0 = forever) | `90` |
| `RUN_SCHEDULE` | Cron expression for scheduled runs | `0 8 * * *` |

See `.env.example` for the full list and comments.

### Running with Gunicorn

Bind to localhost when using nginx; bind to `0.0.0.0` only if exposing directly:

```bash
source .venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:5050 app:app --timeout 300
```

Use `--timeout 300` (or higher) — StackCT runs and PDF analysis can exceed default worker timeouts.

### StackCT catalog database

Project and plan lists are stored in `{OUTPUT_DIR}/stackct.db` (SQLite). The UI reads the database first; live StackCT browser sync runs only when data is missing or past `STACKCT_CACHE_TTL_HOURS` (default 24). **Only one StackCT browser login runs at a time** — concurrent Refresh and Preview requests are queued. Legacy `projects_cache.json` / `plans_cache/` are migrated once on first startup.

### Systemd service (auto-start on boot)

Create `/etc/systemd/system/bobby-tailor.service`:

```ini
[Unit]
Description=Bobby Tailor Estimation Automation
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/bobby-tailor
Environment="PATH=/home/ubuntu/bobby-tailor/.venv/bin"
ExecStart=/home/ubuntu/bobby-tailor/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5050 app:app --timeout 300
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bobby-tailor
sudo systemctl start bobby-tailor
sudo systemctl status bobby-tailor
```

### Nginx reverse proxy (optional)

Serve on port 80/443 and proxy to Gunicorn:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    client_max_body_size 100M;
}
```

HTTPS with Let's Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Chromium launch flags

`browser.py` launches Chromium with VPS-safe flags:

- `--no-sandbox` — required in Docker and many restricted environments
- `--disable-dev-shm-usage` — routes shared memory to `/tmp` when `/dev/shm` is capped at 64 MB
- `--disable-blink-features=AutomationControlled` — reduces automation fingerprinting

Optional `.env` tuning for slow VPS links:

- `CANVAS_STABILITY_TIMEOUT=20` — max seconds to wait for drawing tiles to finish rendering
- `CANVAS_STABILITY_CHECKS=2` — consecutive matching pixel hashes before capture

### Docker (alternative)

If you run in Docker, increase shared memory:

```yaml
services:
  bobby-tailor:
    build: .
    ipc: host
    # or: shm_size: 1gb
    mem_limit: 2g
```

### Security notes

**Firewall:** Expose only 80/443 (and SSH). Keep Gunicorn on `127.0.0.1:5050`:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

**Credentials:** Never commit `.env` to git (already in `.gitignore`).

**Updates:** Periodically refresh Playwright and Chromium:

```bash
source .venv/bin/activate
pip install --upgrade playwright
playwright install chromium
```

## Application Authentication

Bobby Tailor uses session-based authentication with bcrypt password hashing and CSRF protection.

### Setup

**1. Generate a secret key:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Add the output as `SECRET_KEY=<value>` in your `.env` file.

**2. Seed the admin account (once):**

```bash
python seed_admin.py
```

This writes `ADMIN_EMAIL` and `ADMIN_PASSWORD_HASH` to `.env`. Never commit `.env`.

Default admin email: `admin@bobbytailor.com`. To change the password, re-run with env overrides or manually update `ADMIN_PASSWORD_HASH` using:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'newpassword', bcrypt.gensalt(rounds=12)).decode())"
```

**3. Local development:**

Set `FLASK_ENV=development` so `SESSION_COOKIE_SECURE` is `False` over plain HTTP:

```env
FLASK_ENV=development
```

**4. Production (HTTPS required):**

Unset `FLASK_ENV` (or set to `production`). Session cookies are `Secure`-only; app will not work over plain HTTP.

For multi-worker gunicorn, use a Redis-backed rate limiter to share state:

```env
RATE_LIMIT_STORAGE_URI=redis://127.0.0.1:6379
```

### Security checklist

- Rotate `SECRET_KEY` immediately if leaked (invalidates all active sessions)
- Store only the bcrypt hash in `.env`; never store the plaintext password
- All state-changing endpoints require a valid session (no anonymous API access)
- All POST/PUT/DELETE requests require a valid CSRF token (`X-CSRFToken` header or `csrf_token` form field)
- Logout is POST-only to prevent logout CSRF via embedded images or links

### Troubleshooting

**Browser crashes with "Target closed":**

- Check `/dev/shm`: `df -h /dev/shm`
- Confirm `--disable-dev-shm-usage` is in `browser.py` launch args
- Check memory: `free -h`

**Screenshots are blank:**

- Verify `playwright install chromium` completed
- Check logs for canvas stability timeout warnings
- Increase `CANVAS_STABILITY_TIMEOUT` in `.env`

**PDF upload fails:**

- Ensure `client_max_body_size` is large enough in nginx (see above)
- Confirm `uploads/` directory exists and is writable

## Run

```bash
# Web UI (recommended) — runs on http://localhost:5050
python3 app.py

# CLI — all projects
python3 main.py

# CLI — specific project
python3 main.py --project-id 7409312 --project-name "Some Project"
```

### Job History

The **Job History** tab provides a persistent record of all completed takeoff and PDF analysis runs. History survives Flask restarts (stored in SQLite alongside the StackCT project cache).

- Filter by outcome: Success, Partial, Failed, Cancelled
- Expand any row to see error/warning messages and the last 80 log lines
- **Open Report** opens the run directly in the Reports workspace
- Retention: configure `JOB_HISTORY_RETENTION_DAYS` in `.env` (default: 90 days; set `0` to disable pruning)

## Production takeoff runs

### Recommended sheet count

For live client demos, select **≤ 15 sheets** per run. Larger sets are fine for unattended VPS jobs but can exceed demo session time.

```json
{
  "mode": "specific",
  "project_id": 7409312,
  "project_name": "Demo Project",
  "page_ids": [101, 102, 103, 104, 105],
  "folder_id": 5
}
```

### REUSE_SCREENSHOTS behavior

Set `REUSE_SCREENSHOTS=true` (default) to skip re-downloading pages you already have:

- On each run start, Bobby Tailor scans prior `output/screenshots/<ProjectName>_*/` folders for existing images.
- Any page whose `.jpg` is found and is **> 1 000 bytes** is copied to the new run folder via `shutil.copy2` — no browser load, no download.
- Pages with no cached image proceed through the normal browser capture.
- To force a completely fresh capture, set `REUSE_SCREENSHOTS=false` in `.env`.

**When reuse helps:** Re-analyzing the same set of drawings with a different Claude model — captures complete in seconds.

### Two-phase capture / analyze explanation

Bobby Tailor deliberately splits every job into two phases:

1. **Pass 1 — Capture** (browser required): All screenshots are downloaded before Claude is called once. The browser is closed after this pass to free memory.
2. **Pass 2 — Analyze** (no browser): Claude processes each captured image and writes `{page_id}_analysis.json` beside the screenshot as a crash-recovery cache.
3. **Pass 3 — Report**: Aggregates all extractions into `takeoff.json`, `calculations.csv`, `raw_items.csv`, and `summary.txt`.

Progress weights reflect this split: capturing = 0–40%, analyzing = 40–90%, reporting = 95–100%.

### analyze_only — recovery after crash

If the server or Claude call fails mid-analysis, restart without re-screenshotting:

```bash
# Via API — finds the latest run folder for "My Project" automatically
POST /api/run/stackct
{
  "project_name": "My Project",
  "analyze_only": true
}
```

Or with an explicit folder:

```bash
POST /api/run/stackct
{
  "project_name": "My Project",
  "analyze_only": true,
  "manifest_dir": "My_Project_20260601_143000"
}
```

Pages with an existing `{page_id}_analysis.json` cache are **skipped** automatically. Only pages still `pending` or `failed` are sent to Claude, so you pay only for the work not yet done.

### Partial reports

If some sheets fail (capture error, Claude timeout, etc.) the run still completes:

- Successful sheets produce a full `takeoff.json` + CSVs.
- Failed sheets appear in `sheets_failed` in the JSON and are logged in `summary.txt`.
- A `partial: true` flag is set in `takeoff.json` when at least one sheet failed.

Identify partial outputs by checking:

```bash
python3 -c "import json; d=json.load(open('output/My_Project_.../takeoff.json')); print(d.get('partial', False))"
```

### Linked Sheet Auto-Follow (Phase 18)

When a drawing sheet references a detail on another sheet (e.g., detail bubble "17 / C-4"),
the scraper automatically discovers and captures the linked sheet before resolving
cross-references.

**Configuration:**

| Variable | Default | Description |
|---|---|---|
| `AUTO_INCLUDE_LINKED_SHEETS` | `true` | Capture and analyze linked sheets automatically |
| `MAX_LINKED_SHEETS` | `10` | Maximum linked sheets added per run (cost guard) |
| `MAX_LINKED_DEPTH` | `1` | Recursion depth (v1: no recursive follow) |

**Behavior when `AUTO_INCLUDE_LINKED_SHEETS=true`:**
- After analyzing selected sheets, unresolved `ref_sheet` codes are collected
- Linked page_ids are matched from the StackCT catalog (same folder only)
- Linked pages are captured and analyzed in a second pass
- `takeoff.json` includes `linked_sheets_added[]` with `{page_id, sheet_name, ref_from}`
- Cross-references previously marked `target_sheet_not_found` may now resolve

**Behavior when `AUTO_INCLUDE_LINKED_SHEETS=false`:**
- No extra capture; `takeoff.json` includes `linked_sheets_suggested[]` for manual follow-up

**Limits:**
- Only sheets in the same `folder_id` are followed
- Recursive link-following (depth > 1) is not supported in v1

---

## API Reference

### POST `/api/run/stackct` — Start a StackCT job

**Full run (default):**
```json
{
  "mode": "specific",
  "project_id": 7409312,
  "project_name": "My Project",
  "page_ids": [101, 102, 103],
  "folder_id": 5
}
```

**Analyze-only — re-run Claude on an existing capture without browser:**
```json
{
  "project_name": "My Project",
  "analyze_only": true
}
```
Automatically finds the most-recent run folder for `project_name`. Uses the
existing `manifest.json` to skip pages already analyzed (unless they have no
`{page_id}_analysis.json` cache). Useful to recover from mid-run crashes or
re-analyze with a new Claude model.

**Analyze-only with explicit folder:**
```json
{
  "project_name": "My Project",
  "analyze_only": true,
  "manifest_dir": "My_Project_20260601_143000"
}
```
`manifest_dir` can be an absolute path or a folder name relative to
`output/screenshots/`.

**Response:**
```json
{ "job_id": "a1b2c3d4" }
```

**Job object** (`GET /api/jobs/<job_id>`):
- `mode_detail`: `"full"` or `"analyze_only"` — indicates which mode ran.

---

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

## Testing

### Generalization suite — synthetic fixtures, no API needed, CI-safe

```bash
# All plan types (no API, CI-safe)
pytest tests/test_takeoff_generalization.py -v
```

Covers all 8 sheet types (floor_plan, elevation, civil_site, schedule, detail, title_sheet, roof_plan, mep_plan) using
synthetic extraction JSON. Zero API calls — runs in ~0.05 s. Required green before every merge.

### Golden regression — client reference accuracy

```bash
# Client regression (requires golden PDFs)
pytest tests/test_golden_takeoff.py -v -m golden
```

Runs end-to-end through `run_pdf_analysis` on the Crow Cass and Bob's Discount PDF fixtures and validates each
canonical item against `tests/fixtures/{project}/golden.csv` using `GoldenValidator` (≥97% accuracy threshold).
These tests auto-skip when PDF fixtures are absent; place PDFs at:

- `tests/fixtures/crow_cass/crow_cass_plans.pdf`
- `tests/fixtures/bobs_discount/bobs_discount_plans.pdf`

#### Golden regression fixtures

The golden PDFs are client files — they are not committed to the repository. An operator must supply them
before the golden tests can produce scores (tests auto-skip when absent).

**Automated setup (from `uploads/` drop folder):**

```bash
bash scripts/setup_golden_fixtures.sh
```

The script copies source files from `uploads/` when they exist and exits cleanly when they are absent.

**Manual copy commands:**

```bash
# Crow Cass
cp "uploads/Crow - Cass White Road-Plans.pdf" \
   tests/fixtures/crow_cass/crow_cass_plans.pdf

# Bob's Discount Furniture
cp "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf" \
   tests/fixtures/bobs_discount/bobs_discount_plans.pdf
```

After copying, re-run `pytest tests/test_golden_takeoff.py -v -m golden` to score both projects.
The acceptance threshold is **≥97%** on both fixtures.

### Run all tests

```bash
pytest -v
```

## Cost

With Haiku (default) + prompt caching, a 30-page project runs ~$0.05.
Set `CLAUDE_MODEL=claude-sonnet-4-6` in `.env` for richer table extraction at ~3× cost.
