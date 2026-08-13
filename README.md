# Bobby Tailor — StackCT Automated Estimation & Take-off

Automated construction estimation: logs into StackCT (or takes a direct PDF
upload), extracts measurements deterministically from PDF vector geometry and
the text layer, uses Claude vision for semantic labeling and residual counting,
applies estimation formulas, and produces a structured take-off report with
full source traceability. Every human verification is persisted to a learning
store and applied automatically on future runs.

## Setup

```bash
pip install -r requirements.txt
pip install -e .            # installs the src/bobbytailor package (required)
playwright install chromium

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY + StackCT login
```

## Package layout

All application code lives in the `src/bobbytailor` package (installed
editable via `pip install -e .`). The only Python files at the repo root are
the two entry points: `app.py` (gunicorn/Flask, `app:app`) and `main.py` (CLI).

```
src/bobbytailor/
├── config.py            Settings loaded from .env (single source of env truth)
├── pipeline/            Orchestration: takeoff_pipeline (core), pdf_analyzer
│                        (PDF entry), pass matrix/model routing, calculator,
│                        aggregator, reporter, cross_references
├── deterministic/       Vector-geometry measurement engine: dimensions, walls,
│                        rooms, viewports, scale_solver/extraction/recalc,
│                        symbols, tables (schedules), footprint, legends
├── vision/              Claude vision: claude_analyzer (prompts/API), schemas
│                        (structured outputs), ensemble (N-run voting +
│                        BudgetGuard), fusion (provenance merge), overlay,
│                        verify_retry
├── learning/            Cross-run learning: store (SQLite), distill
│                        (corrections → vocabulary/assumptions), retrieval
│                        (per-run learned context)
├── scrape/              StackCT: browser (Playwright), scraper (entry point),
│                        capture_manifest, sheet_preview, stackct_sync
├── stores/              SQLite stores: stackct_store, job_store, project_cache
├── devtools/            Dev/benchmark-only inputs: companion_takeoff,
│                        object_manifest (NEVER used by the production path)
└── web/                 Flask: app factory (create_app), blueprints/ (auth,
                         projects, runs, reports, verify, settings, jobs),
                         jobs_runtime, auth, settings, seed_admin, plus the
                         package-local templates/ and static/ UI assets
```

Import style is absolute package paths everywhere
(`from bobbytailor.deterministic.walls import extract_walls`); there are no
root-level import shims.

## Plans-only input contract (production)

Production runs take **plan PDFs only** — a direct upload or a StackCT scrape.
No companion take-off PDFs, no golden CSVs, no hand-written manifests. The
pipeline never auto-discovers sibling `*takeoff*.pdf` files (that discovery is
confined to `bobbytailor.devtools` and `scripts/`).

Ground-truth take-off PDFs exist only for **evaluation**: benchmark scripts
pass them explicitly via `--takeoff-pdf` (see
`scripts/vision_only_benchmark.py`), and the scoring reference is never
visible to the pipeline under test.

## Learning loop

1. **Capture** — when a human verifies a run in the web UI (quantity fix, item
   rename, scale correction, wall height, missed item), the correction is
   persisted in-request to the learning DB (`{OUTPUT_DIR}/learning.db` by
   default, `LEARNING_DB_PATH` to override).
2. **Distill** — raw corrections are replayed into learned vocabulary
   (canonical names/units), assumptions (wall heights, scales), and an
   auto-generated internal manifest, keyed by project and project type.
3. **Apply** — every new run retrieves the relevant learned context at run
   start and injects it into prompts, aggregation naming, and calculator
   assumptions. Learned data only re-flags quantities (`re_verify`), it never
   silently substitutes deterministic geometry/text values.

Repeat runs of a verified project therefore improve automatically — no
manifest files required.

## Accuracy gate

One command scores the plans-only pipeline against the human take-offs in
`uploads/` (Crow Cass + Bob's Discount gate hard; Chelsea + Moxy tracked):

```bash
bash scripts/accuracy_gate.sh            # spends real API credits (~$5–15)
bash scripts/accuracy_gate.sh --budget 5 # cap per-run spend (USD)
```

Assertions per gating project: geometry/text-provenance quantity accuracy
≥ 97%, overall ≥ 90%, item-found ≥ 95%, zero silent misses, ~0 vision quantity
share, and two-run reproducibility within ±5% per item. The gate pins
`LEARNING_DB_PATH` to a fresh temp DB so scores are cold-pipeline and
machine-independent.

## VPS Deployment (Ubuntu)

Production deployment on Hostinger VPS or similar Ubuntu hosts.

### System requirements

- Ubuntu 20.04+ or Debian 11+
- Python 3.9+ (`pyproject.toml` declares `requires-python = ">=3.9"`)
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
pip install -e .

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
| `CLAUDE_MODEL_SCHEDULES` | Model for schedule/panel sheets | falls back to `CLAUDE_MODEL` |
| `HEADLESS` | Run browser headless | `true` |
| `OUTPUT_DIR` | Report output directory | `./output` |
| `CANVAS_STABILITY_TIMEOUT` | Max seconds waiting for canvas render | `15` |
| `CANVAS_STABILITY_CHECKS` | Consecutive stable hashes before capture | `2` |
| `MAX_PREVIEW_ROWS` | CSV preview row cap in web UI | `500` |
| `JOB_HISTORY_RETENTION_DAYS` | Days to keep job history in SQLite (0 = forever) | `90` |
| `RUN_SCHEDULE` | Cron expression for scheduled runs | `0 8 * * *` |
| `LEARNING_DB_PATH` | Learning store SQLite path | `{OUTPUT_DIR}/learning.db` |
| `API_BUDGET_PER_RUN_USD` | Hard API spend cap per run (BudgetGuard) | `10.0` |
| `ENSEMBLE_N` | Self-consistency ensemble size for vision counts | `3` |
| `CLAUDE_MODEL_SEMANTIC` | Model for semantic labeling passes | `claude-sonnet-5` |
| `CLAUDE_MODEL_DENSE` | Model for dense legend/schedule structuring | `claude-opus-4-8` |
| `CLAUDE_MODEL_ESCALATION` | Escalation model (`ESCALATION_ENABLED=true`) | `claude-fable-5` |
| `CLAUDE_MODEL_CLASSIFY` | Model for sheet classification | `claude-haiku-4-5` |

See `.env.example` for the full list and comments, and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the complete deployment guide
(env table, error recovery, learning DB backup, restart-on-deploy).

### Running with Gunicorn

Bind to localhost when using nginx; bind to `0.0.0.0` only if exposing directly:

```bash
source .venv/bin/activate
gunicorn -w 1 --threads 4 -b 127.0.0.1:5050 app:app --timeout 300
```

Use `--timeout 300` (or higher) — StackCT runs and PDF analysis can exceed default worker timeouts.

> **`-w 1` is mandatory. Do not raise the worker count.**
> All live run state — `jobs`, `uploads`, `object_manifests` and the
> single-active-job lock — lives in module-level dicts in one Python process
> (`src/bobbytailor/web/jobs_runtime.py`). A second worker does not share them,
> so an upload handled by worker A 404s when the follow-up `POST /api/pdf/run`
> lands on worker B ("Upload not found or expired"), `GET /api/status/<id>`
> returns 404 while a paid run completes invisibly, and the concurrency guard
> that stops two runs corrupting each other's learned context becomes
> per-worker. `--threads 4` gives all the concurrency this app needs: a takeoff
> already runs in its own daemon thread and the request returns a `job_id`
> immediately. If you ever need real multi-worker throughput, move that state
> into `bobbytailor.stores.job_store` **first**.

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
ExecStart=/home/ubuntu/bobby-tailor/.venv/bin/gunicorn -w 1 --threads 4 -b 127.0.0.1:5050 app:app --timeout 300
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

### Nginx reverse proxy (required)

**Not optional.** Gunicorn binds to `127.0.0.1` and session cookies are
`Secure`-only by default, so TLS termination in front of the app is part of the
supported deployment — without it, login silently fails (see
[Authentication](#authentication) step 4).

Serve on port 443 (with 80 redirecting) and proxy to Gunicorn:

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

    # MUST match MAX_UPLOAD_MB in .env (config.py default: 500).
    # If nginx is smaller, large plan sets fail with a bare 413 that never
    # reaches Flask and shows no in-app error.
    client_max_body_size 500M;
}
```

HTTPS with Let's Encrypt — run this immediately, before the first login:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Chromium launch flags

`bobbytailor/scrape/browser.py` launches Chromium with VPS-safe flags:

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
ADMIN_SEED_PASSWORD='<strong password>' python -m bobbytailor.web.seed_admin
# or generate a strong random password (printed once — store it immediately):
python -m bobbytailor.web.seed_admin --generate
```

This writes `ADMIN_EMAIL` and `ADMIN_PASSWORD_HASH` to `.env`. The plaintext
password is never stored in source control or in `.env`. Never commit `.env`.

Default admin email: `admin@bobbytailor.com` (override with `ADMIN_SEED_EMAIL`). To change the password, re-run with env overrides or manually update `ADMIN_PASSWORD_HASH` using:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'newpassword', bcrypt.gensalt(rounds=12)).decode())"
```

**3. Local development:**

Set either `FLASK_ENV=development` or `SESSION_COOKIE_SECURE=false` so the
session cookie is not `Secure`-only over plain HTTP:

```env
SESSION_COOKIE_SECURE=false
```

**4. Production — TLS is REQUIRED, not optional:**

Session cookies default to `Secure`-only. **Over plain HTTP the browser never
returns the session cookie: `/login` appears to succeed and then every request
redirects back to `/login` forever, with no error message anywhere.** That is
the intended default — a session cookie sent in clear text over a proxied LAN
or the public internet is a hijackable credential.

So one of these two is mandatory before you can log in:

- **Recommended:** terminate TLS at nginx (see [Nginx reverse proxy](#nginx-reverse-proxy-required)
  below) and run certbot. Leave `SESSION_COOKIE_SECURE` unset.
- **Only if you fully control the network path** (e.g. an SSH tunnel to
  `127.0.0.1`): set `SESSION_COOKIE_SECURE=false` explicitly. Do not do this on
  anything reachable from another machine.

`SESSION_COOKIE_SECURE` accepts `0` / `false` / `no` (case-insensitive) to
disable; anything else, including unset, keeps `Secure` on.

Rate limiting uses the in-process `memory://` store, which is correct for the
supported single-worker deployment (see [Running with Gunicorn](#running-with-gunicorn)).
A Redis-backed limiter (`RATE_LIMIT_STORAGE_URI=redis://127.0.0.1:6379`) only
becomes relevant if the in-process job state is moved to a shared store first.

### Security checklist

- Rotate `SECRET_KEY` immediately if leaked (invalidates all active sessions)
- Store only the bcrypt hash in `.env`; never store the plaintext password
- All state-changing endpoints require a valid session (no anonymous API access)
- All POST/PUT/DELETE requests require a valid CSRF token (`X-CSRFToken` header or `csrf_token` form field)
- Logout is POST-only to prevent logout CSRF via embedded images or links

### Troubleshooting

**Browser crashes with "Target closed":**

- Check `/dev/shm`: `df -h /dev/shm`
- Confirm `--disable-dev-shm-usage` is in `bobbytailor/scrape/browser.py` launch args
- Check memory: `free -h`

**Screenshots are blank:**

- Verify `playwright install chromium` completed
- Check logs for canvas stability timeout warnings
- Increase `CANVAS_STABILITY_TIMEOUT` in `.env`

**PDF upload fails:**

- Ensure nginx `client_max_body_size` matches `MAX_UPLOAD_MB` (see above); a
  mismatch produces a bare nginx 413 that never reaches Flask
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

**Job routes.** There is no single-job GET on `/api/jobs/`. The real routes are:

| Route | Returns |
|-------|---------|
| `GET /api/status/<job_id>` | Live progress for an in-memory (running/just-finished) job |
| `GET /api/jobs/active` | The currently running job, if any (sidebar mini-card) |
| `GET /api/jobs/history` | Paginated list of completed runs (`limit`, `offset`, `outcome`) |
| `GET /api/jobs/history/<job_id>` | Full detail for one completed run, including log tail |

The persisted history records (`/api/jobs/history` and
`/api/jobs/history/<job_id>`) include `mode_detail`: `"full"` or
`"analyze_only"` — indicating which mode ran.

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
app.py                     Gunicorn/Flask entry (app:app) — 5-line wrapper over
                           bobbytailor.web.app.create_app()
main.py                    CLI entry point (StackCT scrape runs)
src/bobbytailor/           The application package — see "Package layout" above
src/bobbytailor/web/templates/, .../static/
                           Web UI assets — package-local, resolved by Flask's
                           default `app.root_path` (no repo-root reach-up)
docs/design/               Design-system contract (bobby-tailor/MASTER.md)
docs/archive/              Archived legacy planning docs (Master.md, Masterv2.md)
scripts/                   Dev/CI tools: accuracy_gate.sh, vision_only_benchmark.py
scripts/archive/           Retired StackCT-era diagnostics (best-effort)
```

## How it works

1. **Input** — Playwright scrapes StackCT (login → page discovery → canvas
   capture + vector blob retention), or a plan PDF is uploaded directly. Both
   paths share the same `TakeoffPipeline` (entry-point parity).
2. **Deterministic first** — on vector sheets, quantities come from geometry +
   the text layer: viewport segmentation, zero-calibration scale solving from
   dimension strings, wall LF, room SF, symbol clusters, schedule tables,
   printed dimensions.
3. **Vision as semantic engine** — Claude labels regions/symbols/rooms via
   structured outputs (no numbers where geometry can answer); residual counts
   use N-run ensemble voting + tiled counting under a per-run BudgetGuard.
4. **Fusion** — deterministic and vision results merge with provenance ranking;
   vision can never overwrite a deterministic quantity. Out-of-band values get
   a verify-retry pass with targeted crops before being flagged.
5. **Learning** — learned vocabulary/assumptions from prior human verifications
   are injected at run start; new verifications persist to the learning store.
6. **Calculate & report** — estimation tables with real construction formulas;
   per-run folder with CSVs, `takeoff.json` (incl. provenance + API cost), and
   a human-readable summary.

## Estimation Tables

All formulas live in `bobbytailor/pipeline/calculator.py → ESTIMATION_TABLES`. Edit those dict values to match your job's waste factors, coverage rates, sheet sizes, stud spacings, etc.

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

**Companion take-off PDFs are evaluation-only.** The production pipeline never
reads them (plans-only contract) — sibling `*takeoff*.pdf` auto-discovery was
removed in Phase 21. Benchmarks pass the ground-truth take-off explicitly:

```bash
python3 scripts/vision_only_benchmark.py \
  --name crow \
  --plans-pdf "uploads/Crow - Cass White Road-Plans.pdf" \
  --takeoff-pdf "uploads/Crow - Cass White Road-Take offs.pdf"
```

**High-accuracy mode (default):** `export TAKEOFF_ACCURACY_MODE=high` runs Sonnet on floor-plan
count/measure/schedule/legend passes. One-command convergence gate:

```bash
python3 scripts/golden_convergence.py
```

### Run all tests

```bash
pytest -v
```

A bare `pytest` excludes the paid golden regression tests by default (`pytest.ini` sets `addopts = -m "not golden"`); opt in explicitly with `pytest -m golden`.

## Cost

> **Stale figure — pre-Phase-21.** The ~$0.05/run number below was measured
> before the Phase 21 accuracy work (model routing v2, N-run ensemble voting,
> verify-retry, tiled counting). Real per-run cost is now materially higher and
> depends on `TAKEOFF_ACCURACY_MODE`, `ENSEMBLE_N`, and sheet mix. Use
> `API_BUDGET_PER_RUN_USD` (default `10.0`) as the authoritative per-run cap and
> read the `api_cost` field in `takeoff.json` for the actual spend. This section
> is scheduled for re-measurement.

With Haiku (default) + prompt caching, a 30-page project ran ~$0.05 (pre-Phase-21).
Set `CLAUDE_MODEL=claude-sonnet-5` in `.env` for richer table extraction at higher cost.
