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
