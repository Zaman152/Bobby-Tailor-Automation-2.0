# INV-C — What must change before Bobby Tailor can be deployed safely

Read-only investigation, 2026-08-13, branch `accuracy/flag-dont-guess-coincidental-detections`.
Scope: **deployability only** (Job C). Accuracy is Jobs A/B.
Target scenario: ONE operator, ONE box, plans-only PDF upload + optional manifest, small
projects (Bob's 7pp, Crow 4pp). No paid API was spent producing this document.

---

## TL;DR — the blunt verdict

**The app is much closer to deployable than Phase 27's scope implies, but it will fail on
day one if you follow your own deployment docs.** Five things are genuinely broken for a
real deploy; four of them are one-line fixes and none of them are in Phase 27's stated
scope. Meanwhile **three of Phase 27's seven stated items are already done, stale, or
irrelevant to your deployment** and should not cost you a single hour.

The single worst finding: **`docs/DEPLOYMENT.md:13`, `README.md:169` and the systemd unit
at `README.md:192` all prescribe `gunicorn -w 2`, and every piece of live run state —
uploads, jobs, manifests, the single-active-job lock — is a module-level dict in
`bobbytailor/web/jobs_runtime.py:21-28`.** With two workers the upload→run→poll flow
breaks roughly half the time with "Upload not found or expired" and 404 job polls, and the
WR-06 concurrency guard that exists specifically to stop two runs corrupting each other's
learned context becomes per-worker, i.e. absent. Nobody has ever run this app under the
command the docs tell you to run it under.

Second worst, and proven with live output below: **`load_dotenv(..., override=True)` at
`src/bobbytailor/config.py:10` silently discards every deployment environment variable
whose name appears in `.env`, and mutates `os.environ` while doing it.** A `docker run -e`
or systemd `Environment=` setting is not "lower priority" — it is erased. That is an
unfixable-by-the-operator support nightmare.

Phase 27 as written is a ~2-week refactor phase. **You need about one focused day of it.**
Do the five blockers, ship, and leave the 5,859-line module split, the StackCT front-door
parity, and the data-root abstraction alone until a second operator or a second box exists.

Do **not** wait for Phase 27 to be "complete" before deploying. It is not on the critical
path; five specific lines of it are.

---

## Answers to the four questions you asked directly

### (a) Does the app crash-fail at import on a missing env var? — YES. Verified.

`src/bobbytailor/config.py:140` calls `validate_required_env()` **at module import**, and
the required set at `config.py:117-124` includes `STACKCT_EMAIL` and `STACKCT_PASSWORD`.

Simulating a container with no `.env` file present:

```
$ python3 -c "... pop the six vars; neutralize load_dotenv ...; import bobbytailor.config"
IMPORT FAILED: ValueError
Missing required environment variables: STACKCT_EMAIL, STACKCT_PASSWORD,
ANTHROPIC_API_KEY, SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH
Please set them in .env file at project root.
```

For **your** deployment this is worse than "confusing container failure". You are shipping
a plans-only product. StackCT is not part of it. A plans-only operator is nevertheless
required to invent two fake StackCT credentials before the Python package will import at
all — including for a pure offline deterministic run with zero API calls. The blast radius
is already visible in the code: `takeoff_pipeline.py` carries "config stubbed (tests)"
guards that exist only to survive this import.

### (b) Is `debug=True` still live? — YES, unchanged.

`app.py:5` — `app.run(debug=True, port=5050, use_reloader=False)`.

Honest severity: **not reachable under the documented production command.** `gunicorn
app:app` imports the module without executing `__main__`, and Flask's default host is
`127.0.0.1`. It bites in exactly one scenario, which is a realistic one: an operator ssh's
in and runs `python3 app.py` (which `docs/DEPLOYMENT.md:14` itself lists as a supported
entry point) while nginx is proxying port 5050 — then the PIN-protected Werkzeug console is
on the public internet. MAJOR, not BLOCKER, and the fix is one line so just do it.

### (c) What happens to uploads/output when CWD differs from the repo root? — Proven.

Run from an arbitrary directory:

```
cwd                        = .../scratchpad
config.OUTPUT_DIR (raw)    = ./output
resolved OUTPUT_DIR        = .../scratchpad/output
web upload dir would be    = .../scratchpad/uploads
create_app makedirs target = .../scratchpad/output/screenshots
main.py FileHandler target = .../scratchpad/output/run.log
```

Every piece of durable state follows CWD: reports, `learning.db`, `stackct.db`, uploads.
`web/app.py:64-65` hardcodes `"output/screenshots"` and `"uploads"` as relative literals
that **ignore `OUTPUT_DIR` entirely**; `runs.py:134,233,290` save uploads to relative
`"uploads/..."`.

**But**: the documented systemd unit pins `WorkingDirectory=/home/ubuntu/bobby-tailor`
(`README.md:190`), so on the path you are actually going to deploy, this works. It is a
latent hazard, not a live one. DEFER the abstraction; mitigate in `.env` instead.

The real, non-latent consequence is the one below.

### (d) Is there a secret-leak path in the settings UI? — No leak. But there is silent config corruption.

Leak: **clean.** `web/settings.py:20,40-51` redacts `STACKCT_PASSWORD` to bullets and
`ANTHROPIC_API_KEY` to first-7 (`sk-ant-`) + last-4. `SECRET_KEY` and `ADMIN_PASSWORD_HASH`
are not in `ALLOWED_FIELDS` (`settings.py:26-37`) so they are never read or returned.
Empty updates to sensitive fields are ignored. The global auth gate covers `/api/settings`
(verified live: `GET /api/reports -> 401` unauthenticated). No leak path found.

Corruption: **real, and it silently breaks paid runs.** `web/settings.py:24` still ships
`VALID_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]` and
`templates/settings.html:91-94` hardcodes those same three as the only `<option>`s for
`CLAUDE_MODEL_SCHEDULES` — but `.env.example:26` ships `CLAUDE_MODEL_SCHEDULES=claude-sonnet-5`.

Verified server-side:

```
validate empty  -> True []
validate shipped-> False ['CLAUDE_MODEL_SCHEDULES must be one of: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-7']
```

`static/settings.js:38` does `el.value = value` on the `<select>`. A value with no matching
option sets the select to `""`. `collectFormData` then PUTs `""`, `validate_settings` passes
it (`if model and model not in VALID_MODELS`), and `update_settings` writes it. Reproduced
end-to-end:

```
CLAUDE_MODEL_SCHEDULES=''
resolved CLAUDE_MODEL_SCHEDULES = ''
```

`config.py:25` uses `os.getenv(key, CLAUDE_MODEL)` — a key that is *set but empty* does not
fall back. `sheet_pass_matrix.py:84-85` routes `("floor_plan","count")` and
`("floor_plan","measure")` through that variable. **One visit to Settings + Save, and every
floor-plan vision pass on the next run calls the API with `model=""`.** For a takeoff engine
that is the whole product.

Related, cheap, and worth fixing in the same commit: `run_settings` in the saved paid
evidence records `deterministic_enabled / ensemble_n / learning_enabled / budget_usd /
verify_retry_enabled / raster_force` and **not the model slugs** — so "which model produced
this number" is unanswerable from the artifact, which is the exact class of question
24-RESEARCH Open Question 1 already got burned by.

---

## BLOCKERS — fix these before the first real deploy

**B1. `gunicorn -w 2` destroys all run state.** `jobs_runtime.py:21-28` holds `jobs`,
`uploads`, `object_manifests`, `job_lock` as per-process dicts; `runs.py:167` looks up
`uploads[upload_id]` and `blueprints/jobs.py:18` looks up `jobs[job_id]`. Two workers = ~50%
404s on `/api/pdf/run` and `/api/status/<id>`, and `register_job`'s single-active-job guard
(whose own docstring says two overlapping jobs "swap each other's learned context mid-run")
is enforced per-worker.
→ **Fix:** change `-w 2` to `-w 1 --threads 4` in `README.md:169`, `README.md:192`
(systemd `ExecStart`) and `docs/DEPLOYMENT.md:13`.

**B2. `.env` silently erases deployment environment variables.** `config.py:10`
`load_dotenv(..., override=True)`. Proven:

```
os.environ BEFORE import: OUTPUT_DIR= /srv/bobby/data   MAX_UPLOAD_MB= 42
config.OUTPUT_DIR       = ./output      <-- the real env var was DISCARDED
config.MAX_UPLOAD_MB    = 42            <-- survived only because .env omits it
os.environ AFTER  import: OUTPUT_DIR= ./output   <-- os.environ itself was mutated
```

Any variable named in `.env` cannot be overridden by the deployment, and every later
`os.getenv` in the process sees the `.env` value too.
→ **Fix:** `config.py:10` → `load_dotenv(dotenv_path=_env_path, override=False)`.

**B3. Import-time `validate_required_env()` forces fake StackCT credentials on a
plans-only install.** `config.py:140`, required set at `config.py:117-124`.
→ **Fix:** delete the `validate_required_env()` call at `config.py:140` and call it from
`create_app()` (`web/app.py:39`) against a web-only required set
(`SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH`), with `ANTHROPIC_API_KEY` checked at first
vision call and `STACKCT_*` checked only inside `scrape/`.

**B4. HTTPS is documented as optional but `SESSION_COOKIE_SECURE` is `True` by default —
plain-HTTP login is impossible, with no error message.** `web/app.py:42`
`SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") != "development"`; verified live on a booted
app: `SESSION_COOKIE_SECURE = True`. `README.md` heads the nginx section "Nginx reverse
proxy (**optional**)" and puts Let's Encrypt after it. Follow the README literally, serve on
port 80, and the browser never returns the session cookie: `/login` succeeds, then every
request redirects back to `/login` forever. The only escape hatch is an env var named
`FLASK_ENV=development`, which no operator will guess and which nobody should set in prod.
→ **Fix:** add `SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower()
not in ("0","false","no")` at `web/app.py:42`, and make TLS non-optional in the README
runbook.

**B5. Opening Settings and clicking Save blanks `CLAUDE_MODEL_SCHEDULES`, which routes every
floor-plan count and measure pass.** Full chain proven in (d) above. `web/settings.py:24`,
`templates/settings.html:91-94`, `static/settings.js:38`, `config.py:25`,
`sheet_pass_matrix.py:84-85`.
→ **Fix:** build `VALID_MODELS` and the two `<select>` option lists from the `config.py`
defaults (or an explicit `MODEL_CHOICES` constant in `config.py`), and in
`update_settings` refuse an empty value for any non-sensitive allowlisted field instead of
writing it. Same commit: add the four `CLAUDE_MODEL_*` slugs to
`TakeoffPipeline.settings.to_dict()` so `run_settings` in `takeoff.json` records them.

---

## MAJOR — do these in the same day if you can, but they will not stop a launch

- **M1. `debug=True` at `app.py:5`.** → `app.run(debug=os.getenv("FLASK_ENV")=="development", port=5050, use_reloader=False)`.
- **M2. `gunicorn` is not in `requirements.txt`** (verified — 15 packages, no gunicorn) while
  both deployment docs and the systemd unit invoke it. → add `gunicorn>=21.2`.
- **M3. No `ProxyFix`** (verified: zero references in `src/`). Behind the documented nginx
  proxy, `get_remote_address` (`web/auth.py:30`) sees `127.0.0.1` for every client, so the
  `5 per minute;20 per hour` login limit at `blueprints/auth.py:14` is **global**: one
  attacker (or one fat-fingered password) locks the sole operator out. Flask-Login's
  `session_protection="strong"` is likewise degraded. → wrap `app.wsgi_app` in
  `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1, x_proto=1)`.
- **M4. Boot-time StackCT work on a plans-only install.** `web/app.py:75`
  `prefetch_in_background()` spawns a Playwright/Chromium StackCT login whenever the catalog
  DB is empty (`stores/project_cache.py:96-103`), and `web/app.py:82-90` schedules it every
  24 h. With the fake credentials B3 forces, that is a recurring failed third-party login
  from the operator's box, plus a mandatory `playwright install chromium` (`DEPLOYMENT.md:24`)
  on an install that never scrapes. → gate both on `STACKCT_EMAIL` being non-empty.
- **M5. nginx `client_max_body_size 100M` (`README.md`) vs `MAX_UPLOAD_MB=500`
  (`config.py:89`, verified live `MAX_CONTENT_LENGTH = 524288000`).** Irrelevant for Bob's
  (4.6 MB) and Crow (1.1 MB); a silent 413 the moment anyone tries Moxy (87 MB) or Chelsea
  (67 MB) with a slightly different nginx default. → set both to the same number.

---

## DEFER — genuinely not deployment risks for this scenario

| Phase 27 item | Verdict | Why |
|---|---|---|
| **V4-PROD-01 front-door parity (StackCT skips the vocabulary/naming pass)** | **DEFER — and the roadmap text is stale** | Two facts. (1) Your deployment is plans-only; `pdf_analyzer.py` calls `pipeline.run_project(...)` directly, so the front door you are shipping has full parity by construction. (2) `_build_project_vocabulary` has **zero call sites anywhere in `src/`** — Phase 24 deliberately made it dead code on cost grounds and pinned that with `tests/test_phase24_acceptance.py:633` (`assert "self._build_project_vocabulary(" not in pipeline_src`). The live pass is `_build_naming_conventions`, called only from `run_project` (`takeoff_pipeline.py:5262`). So "the scraper skips the vocabulary pass" describes a pass neither door runs. Rewrite the roadmap item; do not schedule work. |
| **V4-PROD-02 `takeoff_pipeline.py` split** | **DEFER hard** | It is now **5,859 LOC**, not the 3,209 the roadmap records. A refactor of that size against ~14 patch-by-module-path test files is the single most expensive and most regression-prone item in Phase 27, and it fixes zero deployment risks. Not before a paying customer. |
| **V4-PROD-06 data root** | **DEFER (mitigate in config)** | Proven CWD-relative, but the documented systemd unit pins `WorkingDirectory`. Put an **absolute** `OUTPUT_DIR=/home/ubuntu/bobby-tailor/output` in `.env` and note in the runbook that `uploads/` follows CWD. Revisit if you containerize. |
| **V4-PROD-07 magic-byte sniffing** | **DEFER** | `runs.py:130,286` is extension-only, but the whole app is behind a single-admin login (`web/app.py:110-117`, verified `401` on `/api/reports`) with CSRF (`CSRFProtect`, `web/app.py:51`) and a 500 MB body cap. A non-PDF gets a `fitz` exception and a generic 500. There is no untrusted uploader in this deployment. |
| **V4-PROD-07 rate limiting beyond login** | **DEFER** | Login is already limited. Fix M3 (ProxyFix) instead — that is the part that is actually wrong. |
| **V4-PROD-05 30 ft wall height / `PLAN_TITLE_RE` / ≤900 SF** | **DEFER out of Phase 27 — it is Job A/B** | These are accuracy ceilings, not deployment risks, and two of the three have already moved: `room_fill.py:28` now documents that a region above `MAX_REGION_SF` is **kept and flagged** (23-09) rather than silently dropped, and `PLAN_TITLE_RE` was extended with an uncoded-title branch after the Crow A-101 `plan_titles: 0` defect. `_WALL_HEIGHT_DEFAULT_FT = 30.0` (`takeoff_pipeline.py:1482`) is still live and still wrong for retail/hotel — hand it to whoever owns accuracy. |
| Excel export lives only in `scripts/` (CONCERNS M8) | **DEFER** | No `openpyxl` anywhere in `src/`, and it is not in `requirements.txt` either. The operator can download `takeoff_summary.csv` / `calculations.csv` / `raw_items.csv` through `reports.py:241`. CSV is a shippable deliverable. |
| No `/health` endpoint | **DEFER** | `curl -sf http://127.0.0.1:5050/login` is already the documented smoke test and works (verified `GET /login -> 200`). |
| CONCERNS L5 (missing `@login_required` on two report routes) | **CLOSED — no action** | Verified live: unauthenticated `GET /api/reports` returns **401** via the global `before_request` gate. Cosmetic only. |
| CONCERNS L2/L3 (`_diag_chelsea.json`, `MagicMock/`) | **CLOSED** | Both gone from the tree. |
| Answer-key take-off PDFs sitting in `uploads/` next to the plans | **No action needed** | `uploads/` and `output/` are both in `.gitignore`; a clone-based deploy carries no answer keys. Auto-discovery is locked out at `pdf_analyzer.py:477` and `scraper.py:580,1162` (`allow_discovery=False`). The residual risk is the operator hand-picking `"...-Take offs.pdf"` in the file dialog — a UX guard (warn on a filename matching `take[ -]?off`), not a security hole. Worth 10 minutes, not a blocker. |

---

## Recommended order of work

Everything below is a small, local edit. There is no refactor on this list.

1. `README.md:169`, `README.md:192`, `docs/DEPLOYMENT.md:13` — `-w 2` → `-w 1 --threads 4`. (B1)
2. `src/bobbytailor/config.py:10` — `override=True` → `override=False`. (B2)
3. `src/bobbytailor/config.py:140` — delete the import-time call; call a web-scoped
   `validate_required_env()` from `create_app()` in `src/bobbytailor/web/app.py:39`. (B3)
4. `src/bobbytailor/web/app.py:42` — env-overridable `SESSION_COOKIE_SECURE`; make TLS
   mandatory in the README runbook. (B4)
5. `src/bobbytailor/web/settings.py:24` + `templates/settings.html:91-94` — generate the
   model list from `config.py`; refuse empty writes for allowlisted non-sensitive fields in
   `update_settings`. Add the `CLAUDE_MODEL_*` slugs to `run_settings`. (B5)
6. `app.py:5` — gate `debug` on `FLASK_ENV`. (M1)
7. `requirements.txt` — add `gunicorn>=21.2`. (M2)
8. `src/bobbytailor/web/app.py` — `ProxyFix(x_for=1, x_proto=1)`. (M3)
9. `src/bobbytailor/web/app.py:75,82-90` — skip prefetch + scheduler when `STACKCT_EMAIL` is
   empty. (M4)
10. `.env` on the box — absolute `OUTPUT_DIR`; align nginx `client_max_body_size` with
    `MAX_UPLOAD_MB`. (M5, and the V4-PROD-06 mitigation)
11. Re-run the offline suite (`pytest tests/ -q -m "not golden"`), then **one** paid Crow run
    driven entirely through the real web UI — upload PDF, attach manifest, poll, download CSV
    — as the acceptance test. That is the only way the B1/B3/B5 fixes get proved on the path
    the operator will actually use.

---

## Risks

- **Flipping `override=False` (B2) changes the Settings page's semantics.** If a variable is
  also set in the process environment, an edit made through Settings will not take effect
  after restart. Today's systemd unit sets only `PATH`, so this is safe now — but say so in
  the runbook, or the next person will lose an afternoon.
- **`-w 1` makes the app single-request-blocking for the length of a takeoff.** `--threads 4`
  covers it because the job already runs in its own daemon thread and the request returns a
  `job_id` immediately. Do not "fix" throughput later by raising `-w` without first moving
  `jobs`/`uploads` into `job_store`.
- **B3 splits the required-env set.** A missing `ANTHROPIC_API_KEY` will now surface as a
  failed vision call mid-run instead of a refusal to start. Check it in `create_app()` too,
  with a warning rather than a hard fail, so the offline deterministic path still boots.
- **B5's fix must not silently re-point the model.** The live `.env` currently resolves
  `CLAUDE_MODEL_SCHEDULES` to `claude-sonnet-4-6` while `.env.example` documents
  `claude-sonnet-5`. The two saved paid Crow runs succeeded on whatever the live `.env`
  holds. When you regenerate the allowlist, keep the existing value working and record it in
  `run_settings` — do not "correct" it to the documented slug without a paid smoke run.
- **None of this improves accuracy.** ~40-50% overall on Crow plans-only is unchanged by
  every item above. Deploying safely and deploying usefully are different questions; this
  document only answers the first.
- **The test suite will not catch any of this — it is already green.** The web-surface
  subset was run for this report and passes clean:

  ```
  $ python3 -m pytest tests/ -q -m "not golden" -k "web or settings or auth or runs or upload"
  123 passed, 2251 deselected, 5 warnings in 383.90s
  ```

  123 tests over the web surface, and none of them notices that the settings `<select>`
  cannot hold the shipped model slug (B5), that `SESSION_COOKIE_SECURE` makes plain-HTTP
  login impossible (B4), or that the documented `-w 2` command breaks every in-memory job
  lookup (B1). The gap is structural: every one of these defects lives in the seam between
  the code and the *deployment instructions*, and nothing in the suite reads the
  README/systemd unit or exercises a second worker process. Add pins with the fixes —
  cheapest three are (i) assert the settings model options equal the `config.py` choices,
  (ii) assert no doc string in `README.md`/`docs/DEPLOYMENT.md` contains `-w ` with a value
  above 1 while `jobs_runtime` state is in-process, (iii) assert `update_settings` refuses an
  empty value for a non-sensitive allowlisted field.
- Every behavioural claim in this document is backed by pasted output from a direct module
  call or a live `create_app()` boot. Run the **full** offline suite (`-m "not golden"`,
  ~2350 tests) after the ten edits, before shipping.
