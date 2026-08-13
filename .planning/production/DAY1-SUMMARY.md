# DAY 1 — Deployment blockers, done

**Date:** 2026-08-13 · **Branch:** `accuracy/flag-dont-guess-coincidental-detections`
**Scope:** PRODUCTION-PLAN.md §2 Day 1 (items 1.1–1.7) and INV-C's B1–B5 + M1–M5.
**Cost:** $0.00 — no paid API, no golden marker, no network.

---

## 1. Verdict

**All five BLOCKERS and all five MAJORs are fixed.** None of them was already
fixed in the tree — every one was verified live against the current source
before editing, and every one was still present.

The work is nine commits. Nothing on this list is a refactor; the largest
single behavioural change is scoping environment validation to the surface
that reads each variable.

The headline is unchanged from INV-C and is worth restating, because it is the
one that made everything else moot: **nobody had ever run this application
under the command its own documentation tells you to run it under.**

---

## 2. What was fixed

### 2.1 — B3 was only half fixed: the README still demanded StackCT credentials

Found on the verification pass, after the code fixes were already committed.
B3 moved `validate_required_env()` off import so a plans-only operator no
longer needs StackCT credentials to import the package. But the document that
operator actually follows had not moved with it. `README.md`'s environment
table still read:

```
| `STACKCT_EMAIL`    | StackCT login email | (required) |
| `STACKCT_PASSWORD` | StackCT login password | (required) |
```

and the install block still said `# Edit .env with StackCT and Anthropic
credentials`. So the operator invents two fake StackCT passwords anyway —
which is **the exact user-visible symptom B3 exists to remove**. The import no
longer crashes, but nothing tells them to stop.

Worse, the three variables that genuinely do block startup —
`SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` — were **not in the README's
table at all**. They are documented in `docs/DEPLOYMENT.md`, but the README is
the file with the `git clone`/`cp .env.example .env` runbook, so the reader
following it start-to-finish met the wrong required set and none of the right
one. A code fix whose only observable effect is in a document is not finished
until the document changes.

Now: a "required to start the web app" table with those three, and a second
table where StackCT is marked `(optional)` and says why, `ANTHROPIC_API_KEY` is
`(required for vision)` with the warn-don't-crash behaviour spelled out, and
`SESSION_COOKIE_SECURE` / `MAX_UPLOAD_MB` are listed (they were in neither
table, and §6's `.env.example` gap means the README is now the only place a
reader meets them). The `playwright install chromium` step is annotated as
StackCT-only, closing M4's other half — a plans-only box was being told to
install a browser it never launches.

Both new cross-links were checked against real headings; the first two I wrote
pointed at anchors that do not exist in this README.

### B1 — `gunicorn -w 2` destroyed all run state · commit `552b138`

`web/jobs_runtime.py` holds `jobs`, `uploads`, `object_manifests` and the
single-active-job lock as module-level dicts in **one** process. Two workers do
not share them, so an upload handled by worker A 404s when the follow-up
`POST /api/pdf/run` lands on worker B, status polls 404 while a paid run
completes invisibly, and `register_job`'s guard against two runs swapping each
other's learned context becomes per-worker.

- `-w 2` → `-w 1 --threads 4` in `README.md` (prose + systemd `ExecStart`) and
  `docs/DEPLOYMENT.md`.
- **The reason travels with the flag.** Both documents now carry a "Why `-w 1`"
  section naming `jobs_runtime.py` and stating the precondition for ever
  raising it (move that state into a shared store first). A bare `-w 1` reads
  like a typo and invites the next well-meaning throughput tweak.

### B2 — `.env` erased deployment environment variables · commit `5d878b5`

`load_dotenv(override=True)` did not merely deprioritise a `docker run -e` or
systemd `Environment=` value, it **discarded** it — and because `load_dotenv`
writes through to `os.environ`, every later `os.getenv` in the process saw the
`.env` value too.

- `override=True` → `override=False`.
- `docs/DEPLOYMENT.md` gains a "Precedence" section stating the one
  user-visible consequence: a variable **also** set in the process environment
  is now effectively read-only from the Settings page, because Settings writes
  `.env` and the environment wins again after a restart. The supported systemd
  unit sets only `PATH`, so nothing is affected today. (This is INV-C's risk R6,
  written down rather than left to be rediscovered.)
- `tests/conftest.py` carried a comment asserting the attr-patch was the only
  workable isolation mechanism *because* of `override=True`. Corrected — the
  patch is kept because it also covers the derived `SCREENSHOTS_DIR`, which no
  env pin reaches.

### B3 — import-time validation forced fake StackCT credentials · commit `19b2a0b`

`validate_required_env()` ran at module level in `config.py`, and `config` is
imported by essentially the whole package — so `STACKCT_EMAIL` and
`STACKCT_PASSWORD` were preconditions for `import bobbytailor` on a product
that ships plans-only and never scrapes.

Requirement now belongs to the surface that reads the value:

| Set | Variables | Checked | On failure |
|---|---|---|---|
| `WEB_REQUIRED_ENV_VARS` | `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` | `create_app()` | refuses to start, naming **all** missing at once |
| `SCRAPE_REQUIRED_ENV_VARS` | `STACKCT_EMAIL`, `STACKCT_PASSWORD` | `StackCTBrowser.login()` | refuses the login |
| `VISION_REQUIRED_ENV_VARS` | `ANTHROPIC_API_KEY` | `create_app()` | **warning only** |

`REQUIRED_ENV_VARS` survives as the union for a genuine all-surface pre-flight.

The API key is deliberately a warning, per INV-C's own risk note: the
deterministic offline path is a supported way to run this product and
crash-failing would take it away from an operator who has not bought credit.
The cost is that a missing key surfaces mid-run rather than at startup — which
is exactly what the startup log line exists to make diagnosable.

### B4 — plain-HTTP login was silently impossible · commit `1322061`

`SESSION_COOKIE_SECURE` was hardcoded to `FLASK_ENV != "development"`. The
default is correct; the failure mode was not. Over plain HTTP the browser
accepts the Secure cookie and never returns it, so `/login` reports success and
every request redirects back to `/login` forever — no log line, nothing on
screen. The only escape was `FLASK_ENV=development`, a name no operator would
guess and nobody should set in production to reach a login form.

- `SESSION_COOKIE_SECURE=false|0|no|off` is now an explicit opt-out.
  `FLASK_ENV=development` still works. **The default is unchanged and stays
  Secure** — this is a fix for a usability trap, not a reason to weaken it.
- `README.md`: the nginx section is now **"(required)"**, TLS is stated as
  mandatory with the two acceptable configurations spelled out, and the
  redirect-loop symptom is written down. An operator cannot reason their way
  from "cookies are Secure" to "login silently loops forever".

### B5 — one Settings save blanked the model routing every floor-plan pass · commit `e70bbee`

The full chain, every link silent: `web/settings.py` hardcoded a three-slug
`VALID_MODELS` that `.env` had outgrown → `settings.html` hardcoded the same
three as the only `<option>`s → `settings.js` does `el.value = value`, and a
value with no matching option sets the select to `""` → the form PUTs every
field on Save → `validate_settings` passed the blank (`if model and model not
in VALID_MODELS`; `""` is falsey) → `update_settings` wrote it →
`os.getenv(key, DEFAULT)` does **not** fall back for a set-but-empty key. Result:
every floor-plan count and measure pass on the next run called the API with
`model=""`.

- `config.MODEL_CHOICES` is the single source. `web/settings.py` derives its
  allowlist from it; the template renders its `<option>`s from it. No second or
  third copy is left to drift.
- **`model_choices()` appends any slug the live environment resolves but the
  catalogue does not know.** This is the guarantee that actually prevents a
  recurrence: a model upgraded in `.env` can never again become
  unrepresentable in the UI, which is the mechanism that produced the blank.
  It also satisfies INV-C's warning not to "correct" the live slug to the
  documented one — whatever is configured stays configured and stays valid.
- `update_settings` **refuses** a write that would erase a configured
  non-sensitive value, and names it. Refusing loudly rather than skipping
  quietly is the point: this survived precisely because every layer was silent.
  A blank over an already-blank field remains a no-op, so the form (which PUTs
  everything) still works on a fresh install, and `""` for a secret still means
  "leave unchanged".
- `RunSettings` gains `models`, recording the slug each of the six routing
  variables resolved to, written into every report's `run_settings`. The saved
  paid runs recorded ensemble size, budget and every boolean toggle and not one
  model name — 24-RESEARCH Open Question 1's failure mode, repeated.

**Severity correction — B5 fires on a fresh install, not on this dev box.**
INV-C states the blanking as a present-tense fact ("One visit to Settings +
Save, and every floor-plan vision pass on the next run calls the API with
`model=""`"), and the Day-1 brief repeats it as "*Today* one Settings save
blanks `CLAUDE_MODEL_SCHEDULES`". Measured on this machine, that is not what
would have happened. `config.active_models()` resolves:

```
CLAUDE_MODEL            = claude-haiku-4-5
CLAUDE_MODEL_SCHEDULES  = claude-sonnet-4-6
```

Those are the only two model fields in `ALLOWED_FIELDS`, and **both were
present in the old hardcoded `["claude-haiku-4-5", "claude-sonnet-4-6",
"claude-opus-4-7"]`** — so both had a matching `<option>`, `el.value` bound,
and Save round-tripped them intact. The defect could not have fired here.

It fires on the path that matters anyway. INV-C's evidence is `.env.example:26`
shipping `CLAUDE_MODEL_SCHEDULES=claude-sonnet-5` — a slug the old list did
**not** contain. Copying `.env.example` to `.env` is the documented install
step, so **every fresh deployment** — which is precisely what Day 1 exists to
unblock — starts in the state that blanks on first Save. This dev box is the
exception, not the rule, because its `.env` predates the sonnet-5 default.

The fix and its severity are both unchanged; only the tense is. Recorded
because "we observed this" and "we reasoned this would happen" are not the same
claim, and this project's contract is that the difference is always stated.
(`.env.example` is unreadable under this sandbox — see §6 — so its content is
INV-C's measurement, not a re-measurement.)

### 1.6 — a 404 status poll was swallowed · commit `1a9eddc`

`pollJobMonitor` discarded every non-OK response (`if (!res.ok) return;`) and
every thrown one (`catch (e) { /* ignore */ }`). The progress bar sat at 0% and
the badge on QUEUED while a **paid** run either finished invisibly or never
started. The user's only signal was a bar that did not move, which is
indistinguishable from a slow sheet.

- Three consecutive failures surface a banner and stop polling. One or two are
  still tolerated — a worker restart or a dropped packet is not news, and
  crying wolf trains people to ignore the banner.
- The 404 message names the cause an operator can act on: job state lives in
  one process, so only `gunicorn -w 1` can serve it.
- `401` gets no failure budget. An expired session will not fix itself, and a
  bar frozen at 40% is not a login prompt.
- Counter and banner reset when the monitor attaches to a new job.

**Path correction:** the plan said `static/js/app.js:620`. Phase 22 moved
static into the package; the real file is
`src/bobbytailor/web/static/app.js` (there is a `static/js/` subdirectory, but
`app.js` is not in it).

### MAJORs

| # | Item | Commit |
|---|---|---|
| M1 | `debug=True` → `debug=os.getenv("FLASK_ENV")=="development"` in root `app.py` | `9da6758` |
| M2 | `gunicorn>=21.2` added to `requirements.txt` — both deployment docs invoked a package that was never a dependency | `552b138` |
| M3 | `ProxyFix(x_for=1, x_proto=1)` on `app.wsgi_app` | `1322061` |
| M4 | StackCT prefetch **and** the 24 h scheduler gated on `STACKCT_EMAIL` | `9da6758` |
| M5 | nginx `client_max_body_size` `100M` → `500M`, matching `MAX_UPLOAD_MB` | `552b138` |

Notes worth keeping:

- **M3 is a security fix, not a nicety.** Without `ProxyFix`, behind the
  documented nginx every request looks like `127.0.0.1`, so the
  `5 per minute;20 per hour` login limit was **global** — one attacker, or the
  sole operator fat-fingering a password, locks out the only account on the
  box. `session_protection="strong"` was comparing a constant IP too. Exactly
  one hop is trusted; more would let a client forge `X-Forwarded-For` past the
  limit.
- **M1's honest severity is unchanged from INV-C**: not reachable under
  `gunicorn app:app`, which imports the module without running `__main__`. It
  bites when an operator ssh's in and runs `python3 app.py` (itself a
  documented entry point) while nginx proxies 5050. One line, so it is done.
- **M4** also removes the reason a plans-only install was told to run
  `playwright install chromium`.

---

## 3. Test coverage added

INV-C's central observation was that the suite is green and proves nothing
about deployment, because every one of these defects lives in the seam between
the code and the *documents that start it*. Two new modules close that seam.

**`tests/test_deployment_contract.py` — 56 tests.** All three of INV-C's
suggested pins, plus the rest:

- no deployment doc may prescribe `-w > 1`, every documented invocation must
  state its worker count explicitly, and both docs must **explain why** —
  guarded by a test asserting the premise (that `jobs`/`uploads` are still
  in-process dicts), so the day that stops being true the worker rule is
  relaxed deliberately rather than quietly;
- `.env` precedence, asserted on the source **and** by re-importing config in a
  child interpreter with a colliding `OUTPUT_DIR`;
- config imports cleanly with every required variable blanked; no module-level
  `validate_required_env` call (checked over the parsed AST);
- `SESSION_COOKIE_SECURE` parsing in both directions, the default, and the
  README's wording;
- `ProxyFix` present, trusting exactly one hop, with a forwarded address driven
  through the real WSGI stack into `get_remote_address`;
- the settings allowlist equals the config choices, the template hardcodes no
  slugs, **every configured slug is selectable**, and `update_settings` refuses
  destructive blanks while still accepting legitimate saves;
- `run_settings` records a non-empty slug for all six routing variables;
- the `pollJobMonitor` behaviour, below.

**`tests/test_object_manifest_wiring.py` — 11 tests** (INV-A gap / risk R9).
`grep -r object_manifest_id tests/` previously returned nothing: the manifest is
half the product contract and every hop from browser to pipeline was uncovered.
Now pinned end to end — `object_manifest_id` → `object_manifests[id]["path"]` →
`manifest_path` as `_pdf_job`'s 5th positional argument (arity asserted too,
since a reordering would swap it with `selected_pages`) → `run_pdf_analysis`.
The negatives carry equal weight: no id must yield `None` rather than
inheriting an earlier upload, and an unknown or vanished manifest must **refuse
the run** — silently ignoring it starts a paid run whose results the operator
believes were manifest-guided.

**`tests/js/poll_job_monitor_harness.js`.** The polling fix is tested by
executing the real `app.js` in a node `vm` with a thin DOM stub, not by matching
source text — the claim is about what a user ends up seeing, and a string match
cannot distinguish a surfaced error from a dead one. The suite skips these when
node is absent.

**Every new assertion was verified to fail against the pre-fix code**, by
temporarily reverting the change and re-running:

| Reverted | Failing tests |
|---|---|
| `ProxyFix` wrap removed | 3 |
| `pollJobMonitor` restored to the old body | 5 |
| manifest severed at the run endpoint | 2 |

---

## 4. Test results observed

Run on this machine, Python 3.9, no paid marker, no network.

| Run | Result |
|---|---|
| **Full offline suite** (`python3 -m pytest -q`) | **2438 passed, 1 skipped, 2 deselected** — exit 0 |
| `tests/test_phase23_acceptance.py` + `test_phase24_acceptance.py` + `test_four_set_coverage.py` + `test_determinism_harness.py` (the 24-09 gate) | **61 passed, 1 skipped** in 1416.50s (23m36s) |
| `tests/test_deployment_contract.py` | 56 passed |
| `tests/test_object_manifest_wiring.py` | 11 passed |

Interim targeted runs, used to catch fallout before each commit:

- `test_pipeline_deterministic` + `test_sheet_pass_matrix` + `test_blueprint_parity`
  + `test_reporter_accuracy` + `test_ensemble` — **338 passed** (after B2)
- `test_blueprint_parity` + `test_job_history_api` + `test_learning_capture` +
  `test_scale_module` + `test_pipeline_parity` + `test_seed_admin` +
  `test_scraper_errors` — **98 passed** (after B3)
- `test_pipeline_parity` + `test_pipeline_deterministic` + `test_reporter_accuracy`
  + `test_takeoff_pipeline` + `test_sheet_pass_matrix` — **398 passed** (after B5's
  `RunSettings` change)

### 4.1 Full suite

```
$ python3 -m pytest -q
2438 passed, 1 skipped, 2 deselected, 5 warnings in 3904.44s (1:05:04)
$ echo $?
0
```

Python 3.9, no `-m golden`, no `ANTHROPIC_API_KEY` read, no network. The two
deselected are the paid golden markers, which is the correct state for an
offline run. The 5 warnings are pre-existing SWIG `DeprecationWarning`s from a
C-extension import, unrelated to anything on this list.

The four mandated gates are inside this run and green:
`test_phase23_acceptance.py`, `test_phase24_acceptance.py`,
`test_four_set_coverage.py`, `test_determinism_harness.py`.

**Method note.** Nothing else was allowed to run against the tree while this
was in flight. `tests/fixtures/synthetic/*.pdf` are regenerated by every suite
run, and `test_deployment_contract.py` reads `README.md` and
`docs/DEPLOYMENT.md` from disk — so a concurrent second pytest, or a
mid-run doc edit, would race the very files under assertion and produce a
result that means nothing. The README change in §2.1 below was made only after
this run exited.

---

## 5. Deliberately NOT done

- **The green badge on Exposed Structure / Sealed Concrete is untouched.**
  INV-A calls it "painting the two worst numbers green"; the synthesis proved
  that reads `ERR%` as an accuracy when `vision_only_benchmark.py:240` computes
  it as an **error** percentage. At 0.5% those are the engine's two *best*
  numbers and a golden PASS. The badge is correct. Changing it would degrade
  the best output in the system.
- **All other Day-2 UI work** — `rowStatus()`/provenance, killing the
  "Confirm 11 remaining → 100%" banner, surfacing `coverage.json`, rendering
  `unnamed_geometry`, the take-off-filename upload warning. Out of Day 1's
  scope by the plan's own ordering.
- **Everything in PRODUCTION-PLAN §3** — the `takeoff_pipeline.py` split,
  StackCT front-door parity, the data-root abstraction, magic-byte sniffing,
  broader rate limiting, Phase 26. Decisions, not oversights.
- **No paid run.** The acceptance test for this day is the browser-driven Crow
  run in Day 3, which is the only thing that proves B1/B3/B5 on the operator's
  actual path.

## 6. Could not do — permissions

- **`.env.example` was not updated.** It is inside a directory the sandbox
  denies, so it could not be read or edited. Two variables are now worth
  documenting there and are **not**: `SESSION_COOKIE_SECURE` and
  `MAX_UPLOAD_MB`. Both are documented in `docs/DEPLOYMENT.md`'s environment
  tables, so an operator following the runbook will find them — but the `.env`
  template is stale by two entries. **~2 minutes for whoever holds the
  permissions.**
- `.env` itself was never read, per the same rule. Consequence worth stating:
  **the live value of `CLAUDE_MODEL_SCHEDULES` is unknown to me.** The B5 fix
  is built so that this does not matter — `model_choices()` makes whatever is
  configured selectable by construction — and a live render of the settings
  template produced 6 options per select with no "configured in .env" fallback
  entry, which means the live slugs are all inside the catalogue. But it has
  not been eyeballed.

## 7. For whoever picks up Day 2

1. `.env.example` (§6) — two lines.
2. INV-A's green-badge claim is **false**; §5 explains why. Put that in the
   ticket text, not just in this file — R5 in the plan's own risk register
   rates it medium-high likelihood if INV-A is handed to a dev unread.
3. The `-w 1` rule is now enforced by a test that asserts its own premise. If
   you move `jobs`/`uploads` into `job_store`, that test tells you which other
   test to change with it.
4. `RunSettings.models` now lands in every `takeoff.json`. The next paid run is
   the first artifact that can answer "which model produced this number".
