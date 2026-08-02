# Web Layer Map (Flask + templates + static)

> Audit date: 2026-08-02 · branch `accuracy/flag-dont-guess-coincidental-detections` (post-checkpoint `92c48cc`)
> Scope: `src/bobbytailor/web/`, `templates/` (repo root), `static/` (repo root), `design-system/`.

## TL;DR

- The Flask side is in good shape: a clean app factory (`src/bobbytailor/web/app.py`, 131 lines), 7 blueprints, deny-by-default auth, global CSRF, solid path-traversal guards. The blueprint split is enforced by `tests/test_blueprint_parity.py` (35-route inventory).
- The frontend is the weak half: **`static/app.js` is an 81 KB / 2,223-line non-module monolith** driven by 13 inline `onclick=` globals in `templates/index.html`, coexisting with a *separate* ES-module world (`static/js/reports-workspace.js`, 57 KB) that talks to it through `window.reportWorkspace` / `window.uiMotion` bridges.
- **6 of 12 static JS files are dead or loaded-but-unused** (~21 KB): `js/ui/drawer.js`, `js/ui/modal.js`, `js/ui/toast.js`, `js/ui/focus-trap.js` are never loaded by any template and never imported by any loaded module; `js/ui/icons.js` and `js/data-grid.js` are loaded by `index.html` but their exports (`lucideIcon`, `mountGrid`) have zero importers.
- The CSRF-token helper is **triplicated** (`app.js:14`, `settings.js:8`, `reports-workspace.js:1205`) and the HTML-escape helper likewise (`app.js:1861`, `settings.js:174`, `reports-workspace.js:1373`).
- **6 files hard-import `motion@11.13.5` from cdn.jsdelivr.net** (no SRI, no vendoring); `js/ui/icons.js` fetches SVGs from unpkg at runtime; all three templates pull Google Fonts. The report workspace module fails entirely without internet.
- The root-path quirk is real: `create_app` points `template_folder`/`static_folder` at `parents[3]` (repo root) while `app.root_path` stays `src/bobbytailor/web/` — the freshly committed `_output_root()` in `reports.py:21-23` exists precisely because relative `send_file` paths resolve against `root_path`, not CWD. Recommendation: **move `templates/` and `static/` under `src/bobbytailor/web/`** and delete the explicit folder args.

---

## (a) Route inventory — blueprint → consumer

Entrypoint: repo-root `app.py` (`app = create_app(); app.run(port=5050)`). All blueprints registered in `src/bobbytailor/web/app.py:123-129`. 35 unique URL rules (verified against `tests/test_blueprint_parity.py` EXPECTED_PATHS).

### auth_bp — `src/bobbytailor/web/blueprints/auth.py` (55 lines)

| Route | Methods | Consumer |
|---|---|---|
| `/login` | GET, POST | `templates/login.html` (classic form POST; rate-limited `5/min;20/hour` at auth.py:14) |
| `/logout` | POST | logout `<form>` in `templates/index.html:62` and `templates/settings.html` header |

### projects_bp — `blueprints/projects.py` (169 lines)

| Route | Methods | Consumer |
|---|---|---|
| `/` | GET | renders `templates/index.html` (the SPA shell) |
| `/api/projects` | GET | `static/app.js:263,280` (incl. `?refresh=1`) |
| `/api/projects/refresh` | POST | **no in-repo consumer** (JS uses GET `?refresh=1` instead; only `tests/test_blueprint_parity.py`) |
| `/api/projects/sheet-counts` | GET | `static/app.js:191` |
| `/api/projects/<id>/sync-plan-sets` | POST | **no in-repo consumer** (grep of static/, templates/, scripts/, docs/ = 0 hits) |
| `/api/projects/<id>/plan-sets` | GET | `static/app.js:263,280,1406` |
| `/api/projects/<id>/plan-sets/<folder_id>/plans` | GET | `static/app.js:1512` |
| `/api/projects/<id>/sheet-previews` | GET | `static/app.js:1611` |
| `/api/projects/<id>/sheet-preview/<page_id>` | GET | indirect — URL emitted by `src/bobbytailor/scrape/sheet_preview.py:126` into the sheet-previews payload, rendered as `<img>` by app.js |
| `/api/projects/<id>/sync-plans` | POST | **no in-repo consumer** |
| `/api/projects/<id>/plans` | GET | **legacy, no in-repo consumer** (route docstring says so; JS uses the plan-sets nested route) |

### runs_bp — `blueprints/runs.py` (315 lines)

| Route | Methods | Consumer |
|---|---|---|
| `/api/run/stackct` | POST | `static/app.js:341,1774` |
| `/api/pdf/upload` | POST | `static/app.js:384` |
| `/api/pdf/run` | POST | `static/app.js:493` |
| `/api/pdf/manifest/template` | GET | plain `<a href>` links, `templates/index.html:197,266` |
| `/api/pdf/manifest/upload` | POST | `static/app.js:422` |
| `/api/run/pdf` | POST | **legacy single-step upload+run, no in-repo consumer** (docstring marks it legacy) |

### jobs_bp — `blueprints/jobs.py` (117 lines)

| Route | Methods | Consumer |
|---|---|---|
| `/api/status/<job_id>` | GET | `static/app.js:618` (monitor poll), `:2197` (history re-open) |
| `/api/cancel/<job_id>` | POST | `static/app.js:835` |
| `/api/jobs/active` | GET | `static/app.js:1228,1273` (sidebar mini-card poll) |
| `/api/jobs/history` | GET | `static/app.js:1984` |
| `/api/jobs/history/<job_id>` | GET | `static/app.js:2142` |

### reports_bp — `blueprints/reports.py` (318 lines)

| Route | Methods | Consumer |
|---|---|---|
| `/api/reports` | GET | `static/app.js:868` (reports grid) |
| `/api/reports/<run_folder>` | GET | `static/js/reports-workspace.js:61` |
| `/api/reports/<run_folder>/<filename>` | GET | download links `static/app.js:1034-1066`, workspace download buttons |
| `/api/reports/<run_folder>/preview/<filename>` | GET | `static/js/reports-workspace.js:300,1248,1256,1270,1278` |
| `/api/reports/<run_folder>/sheet-image/<path:relpath>` | GET | `static/js/reports-workspace.js:523,775,994` (lightbox, scale view, measure editor) |

(The shadowed legacy flat-download route was removed in WR-03 — see note at reports.py:312-317.)

### verify_bp — `blueprints/verify.py` (822 lines — the largest blueprint)

All under the `/api/reports/<run_folder>/…` prefix despite living in a different blueprint than reports_bp:

| Route | Methods | Consumer |
|---|---|---|
| `…/scale` | GET, POST | `static/js/reports-workspace.js:325,719,906` |
| `…/measurements` | GET, POST | `static/js/reports-workspace.js:972,1213` |
| `…/verify` | POST | `static/js/reports-workspace.js:610` |
| `…/verify-batch` | POST | `static/js/reports-workspace.js:628` |
| `…/calibrate` | POST | `static/js/reports-workspace.js:1138` |

### settings_bp — `blueprints/settings.py` (41 lines)

| Route | Methods | Consumer |
|---|---|---|
| `/settings` | GET | renders `templates/settings.html` |
| `/api/settings` | GET, PUT | `static/settings.js:15,120` |

**Dead/unconsumed routes (candidates to deprecate, pending user confirmation they are not curl-only operator tools):** `POST /api/projects/refresh`, `POST /api/projects/<id>/sync-plan-sets`, `POST /api/projects/<id>/sync-plans`, `GET /api/projects/<id>/plans`, `POST /api/run/pdf`. Zero hits outside `tests/test_blueprint_parity.py`.

---

## (b) Static asset inventory (sizes + loaders + dead assets)

`static/` totals 256 KB (of which `static/js/` 84 KB). Loader evidence = `<script>`/`<link>` grep across all three templates.

| Asset | Size | Lines | Loaded by | Status |
|---|---|---|---|---|
| `static/app.js` | 81,911 B | 2,223 | `index.html:416` (classic script) | **live — the monolith** |
| `static/js/reports-workspace.js` | 57,133 B | 1,389 | `index.html:15` (module) | live; exposes `window.reportWorkspace` (line 1389) |
| `static/style.css` | 50,423 B | 2,054 | all 3 templates | live |
| `static/ui-polish.css` | 28,381 B | 1,388 | `index.html:12`, `settings.html:12` (not login) | live — override layer on style.css |
| `static/settings.js` | 4,848 B | 181 | `settings.html:151` | live |
| `static/js/data-grid.js` | 4,271 B | 131 | `index.html:14` (module) | **loaded but dead** — exports `mountGrid`; zero importers/callers (grep: only its own file) |
| `static/js/ui/toast.js` | 4,062 B | 123 | nothing | **dead** — never loaded, never imported |
| `static/js/ui/modal.js` | 3,740 B | 132 | nothing | **dead** |
| `static/js/ui/icons.js` | 3,627 B | 101 | `index.html:13` (module) | **loaded but dead** — exports `lucideIcon`; zero importers; fetches unpkg CDN at runtime |
| `static/ui-motion.js` | 3,378 B | 143 | `index.html:415` (module) | live but bloated — exposes 11 functions on `window.uiMotion`; only `pageEnter` (app.js:98) and `staggerChildren` (app.js:897) are used |
| `static/js/ui/drawer.js` | 3,221 B | 108 | nothing | **dead** |
| `static/js/ui/focus-trap.js` | 2,303 B | 98 | nothing directly | **dead** — only imported by dead drawer.js/modal.js |

Supporting evidence for the dead set: `grep -rn "lucideIcon\|mountGrid" static templates` → hits only inside the defining files; `grep -rn "ui-modal-root\|ui-toast-root" static` → 0 hits (the mount `<div>`s at `index.html:20-21` are orphaned too); no `import(` dynamic imports anywhere.

**External-origin dependencies (no SRI, no vendoring):**
- `https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm` — imported by `reports-workspace.js:12`, `ui-motion.js:5`, and all four dead `js/ui/*` files. `reports-workspace.js` (the whole verify/measure UI) **fails to load offline** because a static ES import that errors kills the module.
- `https://unpkg.com/lucide-static@latest/icons` — runtime fetch in dead `icons.js` (`@latest` = unpinned).
- Google Fonts `<link>`s — `index.html:8-10`, `settings.html:8-10`.
- `https://go.stackct.com/app/#/Takeoff/` in app.js is a legitimate deep-link, not an asset.

`design-system/` (24 KB) is documentation, not served assets: `bobby-tailor/MASTER.md` (251 lines, dark-industrial token sheet) + `pages/projects.md` (239) + `pages/reports.md` (182). Referenced by app.js/index.html section comments ("Master §8.3" etc.). Keep, but it belongs with docs/design contracts, not at repo root.

---

## (c) JS organization

**Yes, `app.js` is a monolith.** Its own section headers map its 10 concerns (line refs): CSRF & fetch helpers (8), state (42), navigation (56), mode (119), projects list (133), run StackCT (320), PDF upload/page-selection (360), object manifest (413), job polling/monitor (568), reports (861), active-job mini-card (1225), plan selection (1287), utilities (1860), init (1950), job history (1957). It is a *classic* script — everything global — because `index.html` wires 13 inline `onclick="…"` handlers (e.g. `navigateTo`, `setMode` at index.html:36-114) to its top-level functions.

**Two module systems coexist.** `reports-workspace.js`, `ui-motion.js`, `icons.js`, `data-grid.js` are ES modules; app.js and settings.js are globals. The worlds talk through window bridges: `window.reportWorkspace = {…}` (reports-workspace.js:1389) consumed at app.js:905,2172-2185; `window.uiMotion` (ui-motion.js:127-140) consumed at app.js:98,897.

**Confirmed duplication:**
- CSRF token read ×3: `getCsrfToken()` app.js:14, `getCsrfToken()` settings.js:8-9 (the phase-12 decision), `csrfToken()` reports-workspace.js:1205 **plus** a fourth inline `csrfMeta` lookup at reports-workspace.js:905.
- HTML escaping ×3: `escHtml` app.js:1861 (+`escAttr`:1865), `escHtml` settings.js:174, `escapeHtml` reports-workspace.js:1373.
- Fetch discipline is inconsistent inside app.js itself: 12 `apiFetch(` calls vs 9 raw `fetch('` calls (raw ones hand-roll `credentials: 'same-origin'`).
- `settings.js` does not use `apiFetch` at all — hand-built headers at settings.js:124.

**A professional `static/` layout** (post-move, see (d)):

```
src/bobbytailor/web/static/
  css/
    style.css          # base tokens + layout (from design-system MASTER)
    ui-polish.css      # or merged into style.css
    login.css          # extracted from login.html <style> (~200 inline lines)
    settings.css       # extracted from settings.html <style>
  js/
    core/api.js        # ONE csrfToken() + apiFetch() — imported everywhere
    core/dom.js        # ONE escapeHtml/escAttr, fmt helpers, debounce
    core/motion.js     # slimmed ui-motion (2 used fns) importing vendored motion
    vendor/motion-11.13.5.js  # vendored, SRI-irrelevant, works offline
    pages/projects.js  # split of app.js §projects + plan selection
    pages/pdf.js       # §PDF upload + object manifest
    pages/jobs.js      # §polling, monitor, mini-card, history
    pages/reports.js   # §reports grid
    workspace/…        # reports-workspace.js split (worksheet / scale / measure editor)
    main.js            # entry module; addEventListener instead of inline onclick
```

Everything an ES module, one `<script type="module" src="js/main.js">` per page, no `window.*` bridges, no inline `onclick` (which also unblocks a future CSP). No bundler needed at this size; native modules are fine.

---

## (d) The Flask root-path quirk

Facts (`src/bobbytailor/web/app.py:32-37`):

```python
repo_root = Path(__file__).resolve().parents[3]
app = Flask(__name__,
    template_folder=str(repo_root / "templates"),
    static_folder=str(repo_root / "static"))
```

- `app.root_path` remains `src/bobbytailor/web/` (derived from `__name__`), so **relative paths given to `flask.send_file` resolve against the package dir, not the repo root or CWD**. That is exactly why the just-committed `_output_root()` helper exists (`reports.py:21-23`, commit `92c48cc` "reports served from absolute OUTPUT_DIR"): `config.OUTPUT_DIR` defaults to `"./output"` (`src/bobbytailor/config.py:73`) and every `send_file` in reports.py now goes through `Path(config.OUTPUT_DIR).resolve()`.
- The same `parents[3]` reach-up is repeated in `web/settings.py:16` and `web/seed_admin.py:31` (both to find repo-root `.env`), and `verify.py` still builds paths from raw `Path(config.OUTPUT_DIR)` (works only because those are opened, not `send_file`'d).
- Separately, the app is CWD-dependent regardless: `create_app` does `os.makedirs("output/screenshots")`, `os.makedirs("uploads")` (app.py:67-69) and `runs.py` saves uploads to CWD-relative `"uploads/…"` (runs.py:134,233,290). Running `python app.py` from anywhere but repo root would scatter directories.

**Assessment — move `templates/` and `static/` under `src/bobbytailor/web/`.** Reasons:
1. Flask's defaults (`templates`/`static` next to the package) then apply — the two explicit folder args and the `parents[3]` computation in app.py are deleted, not patched.
2. The package becomes self-contained and wheel-installable (today a non-editable install has no templates at all — `web/settings.py:17-18` even carries a fallback comment admitting this).
3. It eliminates a whole class of "which root?" bugs of which `_output_root()` was the latest instance.
4. Cost is low: `git mv` + two-line factory change; templates reference assets only via `url_for('static', …)` so nothing inside them changes. The only other references to repo-root `templates|static` to re-check are in docs and `.claude` tooling, not code.

What should NOT move: `output/`, `uploads/`, `.env` — those are runtime data. Instead, make `OUTPUT_DIR`/`UPLOADS_DIR` absolute once in `config.py` (anchored to an env-overridable data root), and have `create_app`/`runs.py` consume them, removing the CWD dependence; `_output_root()` then collapses into config.

---

## (e) Auth/security posture (brief — deep dive owned by another agent)

- **Auth model:** single admin from env (`ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH`, bcrypt) — `web/auth.py`; seeding via `web/seed_admin.py` (bcrypt rounds=12, plaintext never persisted).
- **Deny-by-default:** global `before_request` (app.py:114-121) requires login for every endpoint except `PUBLIC_ENDPOINTS = {auth.login, auth.logout, static}`; `/api/*` gets 401 JSON, pages get 302. `@login_required` decorators are applied inconsistently (present on reports detail/download/sheet-image, jobs history, all verify routes; absent on `/api/reports` list, previews, projects, runs, settings) — harmless today because the global guard covers all, but the inconsistency invites a false sense that decorator-less routes were deliberately public.
- **CSRF:** `CSRFProtect(app)` global (app.py:55), 1h token limit; meta tag + hidden inputs in all three templates; JS sends `X-CSRFToken` (in the three duplicated helpers).
- **Session:** HTTPOnly, `Secure` unless `FLASK_ENV=development`, SameSite=Lax, 12h lifetime, `session_protection="strong"` (app.py:43-58).
- **Rate limiting:** only `/login` (`5 per minute;20 per hour`, auth.py:14); `default_limits=[]` and `memory://` storage (auth.py:30-34) — no API-wide limits, resets on restart, not multi-worker-safe.
- **Path traversal:** consistent `".."`/`"/"` fast-fail + `resolve()` + `relative_to()` containment in `reports.py:26-79` and the sheet-image route (:293-309); verify.py checks `run_folder` on every route. Extension allow-list for previews (`{'.csv','.json','.txt'}`).
- **Uploads:** `secure_filename` wrapper (runs.py:32-39), `.pdf`-suffix check (extension only, no magic-byte sniff), `MAX_CONTENT_LENGTH` = 500 MB default (app.py:52, config.py:89).
- **Open-redirect guard** on login `next` (auth.py:38-41); timing-safe user enumeration defense (auth.py:27-33); POST-only logout.
- **Secrets:** `os.environ["SECRET_KEY"]` etc. raise KeyError at boot if missing (loud fail, good). `PUT /api/settings` writes `ANTHROPIC_API_KEY`/passwords into `.env` (web/settings.py:119-164) — session+CSRF protected, secrets redacted on read, but it is the highest-value endpoint in the app.
- **Weak spots for the security agent:** third-party CDN script imports without SRI (jsdelivr/unpkg/Google Fonts) and 13 inline `onclick` handlers mean no meaningful CSP is currently possible; no security headers (CSP/HSTS/X-Frame-Options) are set anywhere in `create_app`.

---

## (f) Verdict — moves/renames/merges for a professional web layer

Ordered by value/effort:

1. **Relocate** `templates/` → `src/bobbytailor/web/templates/` and `static/` → `src/bobbytailor/web/static/`; delete the explicit folder args + `parents[3]` from `create_app`. Absolutize `OUTPUT_DIR`/`UPLOADS_DIR` in `config.py` and remove CWD-relative `os.makedirs`/`"uploads/…"` in app.py/runs.py; `_output_root()` collapses into config.
2. **Delete dead JS** (after user confirmation): `static/js/ui/{drawer,modal,toast,focus-trap}.js`, plus `static/js/ui/icons.js` and `static/js/data-grid.js` together with their two `<script>` tags (`index.html:13-14`) and the orphaned `#ui-modal-root`/`#ui-toast-root` divs (`index.html:20-21`).
3. **Vendor `motion@11.13.5`** locally (or drop it — only 2 of 11 ui-motion functions are used) so `reports-workspace.js` works offline; pin/self-host fonts.
4. **Extract one `core/api.js`** (csrfToken + apiFetch) and one `core/dom.js` (escapeHtml/escAttr/fmt) — kills the ×3 CSRF and ×3 escape duplication; make settings.js and reports-workspace.js consume them.
5. **Split `app.js`** along its own section headers into page modules (projects / pdf / jobs / reports / plan-select) with a `main.js` entry; replace the 13 inline `onclick=` globals with `addEventListener` wiring. This is the prerequisite for any CSP.
6. **Templates:** introduce `base.html` (head, fonts, CSRF meta, sidebar) with Jinja inheritance; extract the ~200-line inline `<style>` blocks from `login.html` and `settings.html` into CSS files.
7. **Blueprint hygiene:** move business logic out of `verify.py` (822 lines — learning capture, `_rebuild_summary`, plausibility checks) into a service module (e.g. `bobbytailor/services/verification.py`), leaving the blueprint as thin route handlers; either merge verify_bp into reports_bp (it already lives entirely under `/api/reports/<run_folder>/…`) or rename for clarity. Also either standardize on the global auth guard (drop scattered `@login_required`) or decorate every route — not the current mix.
8. **Deprecate unconsumed routes** after confirming no out-of-repo callers: `POST /api/run/pdf`, `GET /api/projects/<id>/plans`, `POST /api/projects/refresh`, `POST …/sync-plan-sets`, `POST …/sync-plans` (update `tests/test_blueprint_parity.py` inventory in the same change).
9. **Relocate `design-system/`** under `docs/` (it is a design contract, not a served asset); keep `pages/*.md` next to it.
10. Fix the empty `src/bobbytailor/web/__init__.py` docstring-less file only if package metadata is added — cosmetic.

Non-goals: no bundler/framework needed at this size (12 files, 256 KB); native ES modules + Jinja are appropriate for a single-admin internal tool.
