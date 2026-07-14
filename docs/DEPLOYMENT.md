# Bobby Tailor — Deployment Guide

Production deployment reference for the `src/bobbytailor` package layout
(Phase 21). For first-time VPS provisioning (nginx, systemd, TLS, firewall)
see the [VPS Deployment section of the README](../README.md#vps-deployment-ubuntu);
this document is the operational contract: entry points, environment,
restart discipline, error recovery, and data durability.

## Entry points

| Surface | Command | Notes |
|---------|---------|-------|
| Web UI / API (production) | `gunicorn -w 2 -b 127.0.0.1:5050 app:app --timeout 300` | Root `app.py` is a 5-line wrapper: `from bobbytailor.web.app import create_app; app = create_app()` |
| Web UI (local dev) | `python3 app.py` | Flask dev server on port 5050 |
| CLI scrape run | `python3 main.py [--project-id N]` | StackCT scrape → analyze → report |
| Admin seeding (once) | `python -m bobbytailor.web.seed_admin` | Writes `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` to `.env` |
| Accuracy gate (CI/manual) | `bash scripts/accuracy_gate.sh` | Spends real API credits (~$5–15/run) |

The application must be installed as a package before any entry point works:

```bash
pip install -r requirements.txt
pip install -e .
playwright install chromium && playwright install-deps chromium
```

## Environment variables

Names and sources only — values live exclusively in `.env` (never commit it;
`.env.example` is the value template). `bobbytailor/config.py` is the single
reader; it crash-fails at startup when a required variable is missing.

### Required

| Variable | Purpose |
|----------|---------|
| `STACKCT_EMAIL` / `STACKCT_PASSWORD` | StackCT login (Auth0) |
| `ANTHROPIC_API_KEY` | Claude API key (console.anthropic.com) |
| `SECRET_KEY` | Flask session signing — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` | Web login (bcrypt hash) — seed via `python -m bobbytailor.web.seed_admin` |

### Cost & accuracy controls

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_BUDGET_PER_RUN_USD` | `10.0` | Hard per-run API spend cap (BudgetGuard). A charge that would exceed the cap is refused; the run degrades (see Error recovery) rather than overspending. |
| `ENSEMBLE_N` | `3` | Self-consistency samples for vision-counted quantities |
| `TAKEOFF_ACCURACY_MODE` | `high` | `high` adds legend passes on floor plans; `standard` is the 3-pass floor |
| `COUNT_TILING` / `COUNT_TILING_GRID` | off / `2x2` | Tiled counting for dense sheets |
| `RENDER_TARGET_PX` | `1568` | Whole-sheet render long-edge target (API-fidelity sweet spot) |

### Model routing

| Variable | Default | Route |
|----------|---------|-------|
| `CLAUDE_MODEL` | `claude-haiku-4-5` | General drawings baseline |
| `CLAUDE_MODEL_SCHEDULES` | `CLAUDE_MODEL` | Schedule count/measure passes |
| `CLAUDE_MODEL_SEMANTIC` | `claude-sonnet-5` | Semantic labeling (rooms/symbols/legends) |
| `CLAUDE_MODEL_DENSE` | `claude-opus-4-8` | Dense legend/schedule structuring |
| `CLAUDE_MODEL_CLASSIFY` | `CLAUDE_MODEL` | Sheet-type classification |
| `CLAUDE_MODEL_ESCALATION` | `claude-fable-5` | Escalation (only when `ESCALATION_ENABLED=true`) |

### Learning store

| Variable | Default | Purpose |
|----------|---------|---------|
| `LEARNING_DB_PATH` | `{OUTPUT_DIR}/learning.db` | SQLite file holding human-verified corrections, distilled vocabulary, assumptions, and auto-generated manifests. Survives run-folder deletion. |

### Web / scraping / storage

| Variable | Default | Purpose |
|----------|---------|---------|
| `OUTPUT_DIR` | `./output` | Reports, screenshots, `stackct.db`, `learning.db` |
| `HEADLESS` | `true` | Playwright browser mode |
| `CANVAS_STABILITY_TIMEOUT` / `CANVAS_STABILITY_CHECKS` | `15` / `2` | Canvas render waits |
| `REUSE_SCREENSHOTS` | `true` | Reuse cached captures AND cached vector blobs |
| `AUTO_INCLUDE_LINKED_SHEETS` / `MAX_LINKED_SHEETS` | `true` / `10` | Linked-sheet auto-follow + cost guard |
| `STACKCT_CACHE_TTL_HOURS` | `24` | Catalog re-sync interval |
| `JOB_HISTORY_RETENTION_DAYS` | `90` | Job history pruning (0 = keep forever) |
| `MAX_PREVIEW_ROWS` | `500` | CSV preview cap in UI |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | Use `redis://127.0.0.1:6379` for multi-worker gunicorn |
| `FLASK_ENV` | (unset) | `development` disables Secure-only cookies for plain-HTTP local dev |
| `RUN_SCHEDULE` | `0 8 * * *` | Cron for scheduled CLI runs |

## Deploying new code: restart is REQUIRED

Gunicorn workers and the Playwright job threads hold references to imported
`bobbytailor` modules for the life of the process — there is no hot reload of
package modules, and background threads keep old module objects alive even if
files change on disk. After every `git pull` / code change:

```bash
sudo systemctl restart bobby-tailor     # or: kill -HUP <gunicorn master pid>
```

Never rely on `--reload` in production; a StackCT job mid-run would keep
executing pre-deploy code in its thread while new requests hit post-deploy
code.

## Error recovery semantics

The pipeline is per-sheet fault-isolated — a failed sheet never aborts the run.

**Per-sheet degradation.** A sheet that errors (capture failure, Claude
timeout, malformed response) produces an error dict (`{"error": ...,
"sheet_source": ...}` with zeroed usage fields) and the run continues.
`takeoff.json` lists the failures in `sheets_failed` and sets
`"partial": true`; successful sheets still produce full CSVs/reports. Recovery:
re-run with `analyze_only: true` — pages with an existing
`{page_id}_analysis.json` cache are skipped, so you pay only for the work not
yet done.

**Budget exhaustion (`budget_exhausted`).** Every vision call site charges the
per-run BudgetGuard with the completed call's cost; a charge that would exceed
`API_BUDGET_PER_RUN_USD` is refused and its result discarded. When an ensemble
cannot finish within budget it aborts to the current-best value flagged
`needs_review` with `reason=budget_exhausted` — never a silent partial number.
Flagged rows land in the reviewed-items subset (see below). If a run shows
budget-exhausted flags, either raise `API_BUDGET_PER_RUN_USD` or reduce sheet
count per run.

**Raster fallback.** Sheets without usable vector data (scanned/rasterized
PDFs, StackCT pages without a retained blob) automatically fall back to the
vision-only extraction path with ensemble voting; quantities from that path
carry `vision_ensemble` provenance and lower confidence, so they surface in
the review subset rather than masquerading as exact.

**Reviewed-items workflow.** Humans verify ONLY the flagged subset: open the
run in Reports → the review panel lists rows with `needs_review`, provenance
conflicts (`fusion_rejected`), or learned re-verify flags. Each correction is
persisted in-request to the learning store and applied automatically on the
next run of that project (names, quantity context, scale, wall heights). The
goal state on vector CAD plans is a review list that approaches zero.

## Data durability & backup

| Data | Location | Backup |
|------|----------|--------|
| Learning store (corrections, vocabulary, assumptions, auto-manifests) | `{OUTPUT_DIR}/learning.db` (or `LEARNING_DB_PATH`) | **Copy the file**: `cp output/learning.db /backup/learning-$(date +%F).db`. It is a single self-contained SQLite file; restoring = copying it back. Back it up before every deploy — it is the accumulated human knowledge of the installation. |
| StackCT catalog + job history | `{OUTPUT_DIR}/stackct.db` | Same copy semantics; losing it only costs a re-sync + history |
| Run outputs | `{OUTPUT_DIR}/<Project>_<timestamp>/` | Reports are reproducible from a re-run; archive as needed |
| Secrets | `.env` | Never in git; store in your secret manager |

SQLite files can be copied safely while the app is idle. For a hot copy, use
`sqlite3 output/learning.db ".backup /backup/learning.db"` to avoid torn
writes during an in-flight verification.

## Smoke test after deploy

```bash
source .venv/bin/activate
python -c "from bobbytailor.web.app import create_app; create_app()" && echo "boot OK"
curl -sf http://127.0.0.1:5050/login >/dev/null && echo "login page OK"
python3 -m pytest tests/ -q -m "not golden"     # full offline suite (~5 min)
```
