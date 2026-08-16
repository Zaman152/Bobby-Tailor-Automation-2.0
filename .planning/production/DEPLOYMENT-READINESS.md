# DEPLOYMENT READINESS — the honest go / no-go

**Date:** 2026-08-14 · **Branch:** `accuracy/flag-dont-guess-coincidental-detections`
**Author:** integration / deployment-readiness pass — the fifth agent on this program, and the
first to check that the four preceding tracks compose.
**Cost to produce:** $0.00. No paid API, no golden marker, no `ANTHROPIC_API_KEY` read,
no network except one isolated `pip install gunicorn` into a scratch directory (§3.1).

---

## 1. VERDICT

**GO — conditionally — for one operator, one box, plans-only, Crow-shaped small projects.
NO-GO for Bob's Discount and for anything retail-shaped, on any timeline, until $0.60 of API
credit has been spent measuring it.**

Three conditions, all of them hard:

1. **TLS in front, or `SESSION_COOKIE_SECURE=false` set deliberately.** Neither is optional and
   getting it wrong produces a silent infinite redirect at the login form (§7, B4).
2. **`gunicorn -w 1 --threads 4`.** Not a tuning preference. Two workers 404 roughly half of all
   uploads and status polls (§7, B1).
3. **The paid baseline run in §8 happens BEFORE a customer sees a report.** Nobody has ever run
   the current engine on a real drawing. Every accuracy number anyone can quote today describes
   an engine that is fourteen code commits out of date.

What ships is **not "an accurate takeoff"**. It is **a takeoff with zero confidently-wrong
numbers**: what can be measured is measured, and everything else is a flagged blank that says so
in the row, in the banner, in `coverage.json` and in `summary.txt`. As of this pass that contract
is enforced end to end on the operator's real path, and it is now pinned by a test that drives
the actual HTTP routes rather than by inspection.

The one thing I will not write is a percentage. §6 gives the expected line-item outcome and its
ceiling; it is a forecast, and it is labelled as one.

---

## 2. WHAT THIS PASS ACTUALLY DID

Four agents committed ahead of this one — deploy blockers (Day 1), UI honesty (Day 2), the
detection harness (Days 4-5), and the phase-28 closeout. Each verified its own track. **Nobody
had verified that they compose**, and three of the seams between them were untested by anything
in a 2,500-test suite:

| Seam | Why no existing test could see it |
|---|---|
| `config` → `create_app` | Day 1 moved env validation off import and onto the surface that reads each variable. Every web test in the suite runs with a full environment. Nothing asserted the app boots on a box with **no StackCT credentials at all** — which is the shipping configuration. |
| blueprint → `/static` → browser ES module | Day 2 put the honesty rules in `report-provenance.js`, which `reports-workspace.js` imports by relative path. `test_report_honesty.py` executes that module against rows read off **disk**. If the file stops being *served*, or `index.html` stops loading the workspace as `type="module"`, all 40 of those tests stay green and the screen renders nothing. |
| HTTP → classification | The 31 NOT MEASURED rows have to survive the round trip through `/api/reports/<run>/preview/takeoff.json` — the route the browser actually fetches — and still classify as the third state. Nothing joined those two halves. |

All three are now closed by `tests/test_production_user_path.py` (20 tests, §9).

One real defect was found by driving the path rather than by reading it, and is fixed (§4.1).

---

## 3. VERIFIED BY TEST vs VERIFIED BY READING

This distinction is the point of the document. The project's rule is that "we observed this" and
"we reasoned this" are never written as the same claim.

### 3.1 Verified by EXECUTION (this pass, on this machine)

| # | Claim | How |
|---|---|---|
| 1 | The four mandated gates pass **standalone** | `pytest -q test_phase23_acceptance test_phase24_acceptance test_four_set_coverage test_determinism_harness` → **62 passed, 1 skipped** in 23:16 |
| 2 | The full offline suite passes | §9 |
| 3 | `create_app()` builds on a box with **no** StackCT credentials, and logs the plans-only path | test + live gunicorn boot log |
| 4 | **The documented gunicorn command actually serves.** `gunicorn -w 1 --threads 4 -b 127.0.0.1:5099 app:app --timeout 300`, isolated CWD, isolated `OUTPUT_DIR` | booted; `GET /login` → 200 (7,162 bytes); `GET /` → 302 `/login?next=/`; `GET /api/reports` → 401 |
| 5 | **B1's fix holds under real gunicorn.** Login → `POST /api/pdf/upload` (real Crow plans, multipart) → a **second** request resolves that `upload_id` | upload returned 4 pages `A-101, A-201, A-401, A-601`; the follow-up `/api/pdf/run` failed on the *manifest*, not with `Upload not found or expired` |
| 6 | Every report route refuses an unauthenticated client | 401 on `/api/reports`, `/api/reports/<run>`, both previews, the CSV download |
| 7 | The **real login form** authenticates — CSRF token parsed from the page, posted back — and `POST /logout` really ends the session | test + live gunicorn |
| 8 | `report-provenance.js`, `reports-workspace.js`, `app.js`, `style.css` are all served 200, the workspace still imports the provenance module by the path that resolved, and `index.html` loads it as `type="module"` | test |
| 9 | A plan-set PDF uploads and returns the page picker; a take-off-named file uploads **with** the warning | test |
| 10 | A corrupt PDF and a password-protected PDF are each refused **400** with the right message, and leave no orphan in `uploads/` | test (§4.1) |
| 11 | The object manifest uploads over HTTP and returns a usable id | test |
| 12 | `/api/pdf/run` **refuses** a missing upload_id, an unknown upload, and a vanished manifest | test — refusal paths only; the success path spends money |
| 13 | `coverage.json` is a listed artifact on **both** report endpoints, and every listed artifact downloads at its advertised byte size | test |
| 14 | Path traversal and non-previewable extensions are refused | test |
| 15 | **NOT MEASURED renders as a distinct third state over the rows the SERVER sent** — own badge class, cell text `no measurement path`, never `enter value`, never counted among the lines awaiting a human | test, via the shipped classifier under node |
| 16 | The banner reproduces the run's ledger verbatim: `pct == coverage_pct_items` (15.7), 31 not-measured, 11 needs-review — screen count equals ledger count for both | test |
| 17 | A run with no ledger gets **no invented percentage** | test |

### 3.2 Verified by READING ONLY — believed, not observed

State these as beliefs when anyone asks.

| Claim | Why it is only reading |
|---|---|
| **Columns publish as 120 MEASURED with three flagged hypotheses; Ladder publishes as 1.** | The detectors and their offline gates are green (`test_grid_lattice.py`, `test_keynote_callouts.py`). **No paid run has produced a published report from them.** The harness measured the detector; nobody has seen the row. |
| **`ProxyFix` fixes the rate-limit-and-session behaviour behind nginx.** | Driven through the real WSGI stack in `test_deployment_contract.py`, never behind an actual nginx. |
| **The systemd unit, the nginx config, `client_max_body_size 500M`.** | Documents. Asserted for internal consistency by `test_deployment_contract.py`; never executed. |
| **TLS termination.** | Never exercised. The gunicorn smoke above ran plain HTTP with `SESSION_COOKIE_SECURE=false`, which is exactly the escape hatch B4 added. |
| **`.env` precedence on a real deployment.** | Asserted in a child interpreter; `.env` itself is unreadable under this sandbox. |
| **Whatever `.env` actually contains.** | Deny-ruled. `CLAUDE_MODEL_SCHEDULES`' live value is still unknown to every agent on this program. The B5 fix is built so it does not matter (`model_choices()` appends any configured slug), but it has not been eyeballed. |

### 3.3 NOT VERIFIED AT ALL

- **Any paid run of the post-phase-28 engine.** This is the single largest gap in the program and
  §8 exists to close it.
- **Bob's Discount, on any engine anyone would ship.** §7.
- **A second concurrent operator, a restart mid-run, a >500 MB upload, a scanned (raster) plan
  set.** Out of scope for this deployment by decision, not oversight.

---

## 4. WHAT IS FIXED

### 4.1 Found and fixed by THIS pass

**A corrupt or password-protected PDF returned `Error: Internal server error`.**

`POST /api/pdf/upload` saved the file, called `get_pdf_metadata`, and let the exception escape to
the app's catch-all 500 handler. The estimator saw a server fault; the actual remedy is to
re-export the drawing set. The unreadable file stayed in `uploads/` forever with no registry
entry, because the handler that would have recorded it never ran.

Both are normal things for an estimator to be holding — a scan that came off a copier wrong, a
set the architect password-protected before emailing it — and neither is a server fault.

- `upload_pdf` now returns **400** with a message naming the remedy, and deletes the file it
  could not read.
- The two causes get **different words**, because they have different remedies. Which one applies
  is *measured*, not inferred from the exception: on this PyMuPDF a corrupt file raises
  `FileDataError` from `fitz.open`, while an encrypted one opens fine and raises
  `ValueError: document closed or encrypted` on first page access — so the exception type alone
  cannot tell the operator which they have. `_unreadable_pdf_error()` asks the document, and
  degrades to the generic message if that fails. **Naming the wrong cause is worse than naming
  none.**
- The browser already renders `data.error` verbatim (`app.js:418`), so the message reaches the
  screen with no JS change.

Found by driving the path end to end. It could not have been found by a unit test: every existing
test of `/api/pdf/upload` mocks `get_pdf_metadata` and so never meets a real unreadable file.
The three new assertions were confirmed to **fail** against the pre-fix code before being kept.

This was recorded as a known papercut in DAY2-SUMMARY §9.3 and left unfixed. It is a
first-session, first-file failure on the operator's actual path, so it is fixed here.

### 4.2 Fixed by the four preceding tracks — composed and re-verified here

| Track | What it fixed | Confirmed composed |
|---|---|---|
| **Day 1** — deploy blockers | `-w 1`; `.env` `override=False`; import-time env validation scoped to the surface that reads it; `SESSION_COOKIE_SECURE` opt-out; Settings no longer blanks the model routing; `ProxyFix`; `debug` gated; `gunicorn` added to requirements; StackCT prefetch + scheduler gated; nginx body size; a swallowed status poll now surfaces | §3.1 items 3, 4, 5, 7 |
| **Day 2** — UI honesty | NOT MEASURED as a third state; the banner reports `coverage_pct_items` instead of counting to 100%; `coverage.json` listed; unnamed geometry rendered; `quantity_route` per row; the plans-only upload guard | §3.1 items 8, 9, 13, 15, 16, 17 |
| **Days 4-5** — detection harness | grid-lattice columns (1 fire in 913 trials across 83 pages of four plan sets); keynote regex widened `\d{2}` → `\d{1,2}` with three latent label defects fixed structurally; a cited-but-absent sheet recorded as `NOT_IN_UPLOADED_SET`; the false 56 "Bollards" removed | `test_four_set_coverage.py` green **standalone** — the new detector does not perturb the coverage gate |
| **28-07** — phase closeout | The acceptance gate, with V4-FIX-01 and V4-FIX-03 deliberately **not** ticked | `test_phase28_acceptance.py` inside the full suite |

**The correction that must not be undone.** INV-A claims the report UI "paints the two worst
numbers green". It is false. `vision_only_benchmark.py:240` computes `ERR%` as an **error**
percentage, so *Exposed Structure* and *Sealed Concrete* at 0.5% are the engine's two **best**
numbers and a golden PASS. The green badge is correct, `test_the_engines_best_rows_keep_their_green_badge`
asserts it stays, and anyone "fixing" it would degrade the best output in the system.

---

## 5. WHAT REMAINS UNMEASURABLE, AND EXACTLY WHY

Not a backlog. These are the blanks the product is designed to produce, each with the only thing
that closes it.

| Thing | Why it cannot be measured | Closes by |
|---|---|---|
| **Crow Stairs (golden 10)** | Not drawn in the uploaded 4 pages. The set contains A-101, A-201, A-401, A-601 and *cites* five sheets it does not contain — A-002, **A-111, A-112, A-113**, A-501. Page 0 defers three times (`SEE 1/A-111 / A-112 / A-113`). A-401 draws *what a stair looks like*; it never says how many are installed. | **Uploading those sheets.** No detector — deterministic, ML or vision — counts objects that are not in the file. |
| **Crow's 12 end-wall columns (120 vs golden 132)** | The occupied block is missing exactly the two end positions on **both** axes (rows B..G of A..H, columns 2..21 of 1..22) and all four footprint edges carry the same continuous panel geometry. Extending the numbers gives 132, the letters 160, both 176. Exactly one matches the answer key, and picking it *because* it matches is the coincidence trap that has cost this project real time twice. | **One human confirmation** on the three flagged hypotheses. Never by a rule chosen after seeing the golden. |
| **Crow Bollards (golden 28)** | Text-anchored to general note 13 — "PROVIDE BOLLARDS AT ALL DRIVE-IN OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS…" — i.e. derived from a door schedule, not a countable glyph at 1"=40'. The old **56** was 56 column markers and is gone. | A door-schedule-derived route. Not this job. |
| **The lattice's NAME** | 120 grid cell ids say *where* the markers are, not *what* they are. There is no text anchor on the marker. | The semantic labelling pass, from the candidate registry. |
| **Wrapped keynote text** | The reader returns the one line level with the number block. A midpoint-split reassembly was **built, measured and rejected**: it fixed all of Crow (260 entries gained full text) and broke Bob's page 4, moving "STOREFRONT" into an awning note and flipping a facade's dominant material. Helped one plan set, hurt another → rejected. | Grouping note lines into contiguous blocks first. Its own piece of work, with its own four-set measurement. |
| **Extraction-pass stability** | Three of 51 quantities differed between two identical paid runs (`Door Frames-HM` 4.0→None, `Lift` None→1.0, `Stairs` 1.0→2.0), all traced to the per-sheet vision extraction reading different descriptions off the same pixels. It is **disclosed**, not stabilised — every published row states its `quantity_route` and `summary.txt` names the rows a repeat run may move. | Repeated sampling of a paid pass. A spend decision, not an engineering one. |
| **Crow page 3** | 249,608 primitives, over the 200k cap `grid_lattice` shares with `symbols.py`. | Measured with the cap lifted: **still zero lattices at every scale.** Nothing is hidden there. |

---

## 6. EXPECTED CROW LINE-ITEM OUTCOME

**The ceiling is 9 of 10, and it is a hard ceiling. The Stairs are not in the uploaded PDF.**

Say that to the customer before the first run, not after it. Ten golden items, 10% each:

| # | Item | Golden | Expected | Bucket |
|---|---|---|---|---|
| 1 | Exposed Structure | 395,673.42 SF | PASS (0.5% err today) | correct |
| 2 | Sealed Concrete | 395,673.42 SF | PASS (0.5% err today) | correct |
| 3 | Internal Tilt-up walls | 108,442.66 SF | PASS (1.3% err today) | correct |
| 4 | Mobilization | 1 EA | PASS — injected convention, publishes with **no route**, deliberately | correct |
| 5 | Ladder-H-20' | 1 EA | **PASS expected.** Keynote 1 = "ACCESS LADDER TO CONCRETE ROOF OF ELECTRICAL ROOM", drawn exactly twice (legend + one plan callout). Was structurally invisible to a `\d{2}` regex. | correct, **unproven on a paid run** |
| 6 | Columns-H-35' | 132 EA | **120 MEASURED + 12 flagged.** Golden `match_mode` is `exact_or_within_1`, so **120 scores FAIL** and that is the correct behaviour. Correct after one human click. **Do not add a test asserting 132.** | correct-after-confirmation |
| 7 | Bollards | 28 EA | **flagged blank.** The false 56 is gone. 28 is not reachable from glyphs. | honestly flagged |
| 8 | CMU Wall | 2,204.33 SF | **flagged, probably.** 28-04 stopped a non-discriminating thickness from binding; the masonry object still falls through to a non-confident hint bind (V4-FIX-03, deliberately not ticked). | honestly flagged |
| 9 | Lift | 1 EA | **flagged.** Flipped None↔1.0 between two identical paid runs. | honestly flagged |
| 10 | Stairs | 10 EA | **`NOT_IN_UPLOADED_SET`,** naming A-111 / A-112 / A-113. 28-03 stopped the confident `1.00`. | honestly flagged — correctly |

**Forecast:** 5 of 10 measured correctly unassisted (6 after one confirmation click), 4 honestly
flagged, **target 0 wrong-and-unflagged**. "Correct or honestly flagged" = 10 of 10; raw golden
score ≈ 50-60%.

**Read the scorer with care.** `score_report_dir.py` marks a flagged blank FAIL. A deliberately
flagging engine is *penalised* by it. It is the right tool for detecting regressions between two
runs and the wrong tool for a ship decision. **The ship gate is: zero wrong-and-unflagged rows.**

**Confidence:** high on 1-4 (three already pass, one is a convention). Medium-high on 5 (text
route, the engine's strongest regime). Medium on 6 (the detector is proven on the page; the
+12 rule is not, and is not implemented). **Low on the exact post-28 numbers for 7-9 — nobody has
run this engine on a drawing.**

---

## 7. BOB'S DISCOUNT IS UNVALIDATED — say it out loud

**Every piece of accuracy evidence in this repository is Crow.** The only Bob's artifacts are a
July run on an engine three phases old that scored **1 of 12** (Mobilization), and an Aug-3
deterministic-only run that published **zero rows**.

Bob's golden has **12** items, not 10, and the mix routes through parts of the engine Crow never
exercises: two door-count rows, a door-frame row, gas piping LF, lintels LF, and two elevation
paint areas. The critical-path work of the last week is Crow-shaped — the column lattice returns
**zero** on all 7 Bob's pages, by design and by measurement — so it buys Bob's at most **one**
item (the Ladder, and only if Bob's keynotes it).

**Forecast 3-6 of 12, with error bars so wide the forecast is not worth acting on.** Shipping
"for Bob's" today is shipping on a guess. **$0.60 converts the guess into a number**, and it is
the single highest-value dollar in this program. If Bob's comes back at 2 of 12, that is a
different product problem than the one this plan solves, and it should be discovered on the
baseline run and not after a customer has the report.

---

## 8. EXACT REMAINING STEPS BEFORE A PAID CONFIRMATION RUN

Everything below is free until step 5.

| # | Step | Who | Cost |
|---|---|---|---|
| 1 | **Add two lines to `.env.example`:** `SESSION_COOKIE_SECURE` and `MAX_UPLOAD_MB`. Both documented in `docs/DEPLOYMENT.md` and `README.md`, absent from the template an operator copies. Open since Day 1 — the file is inside a sandbox-denied directory and no agent on this program has been able to read or write it. | whoever holds the permissions | 2 min |
| 2 | **Eyeball the live `.env`** and confirm `CLAUDE_MODEL_SCHEDULES` resolves to a slug you meant. The B5 fix makes any configured slug selectable by construction, so this is confirmation, not repair. | human | 2 min |
| 3 | **`pip install -r requirements.txt` on the deployment box** and confirm `gunicorn` is present. It is declared but is **not installed on this development machine** — the smoke test in §3.1 needed an isolated scratch install to run at all. | operator | 5 min |
| 4 | **Stand the box up per §10 and complete the checklist**, including the TLS decision. Do not skip the `curl` steps; they are the whole smoke test. | operator | 30 min |
| 5 | **PAID BASELINE — Crow, through the browser, with `tests/fixtures/crow_cass/crow_cass_manifest.json`.** Upload → attach manifest → poll → download. ~$0.60. This is simultaneously the acceptance test for the last week of work on the operator's real path and the first honest measurement of the post-28 engine. | human spend decision | ~$0.60 |
| 6 | **PAID BASELINE — Bob's, same path**, with `tests/fixtures/bobs_discount/bobs_discount_manifest.json`. ~$0.60. | human spend decision | ~$0.60 |
| 7 | **Score both free:** `python3 scripts/score_report_dir.py --golden tests/fixtures/<set>/<set>_golden.csv --dir output/<run>`. Record the numbers **before** writing any accuracy code. | free | — |
| 8 | **Read the report as an estimator, not as a scorer.** Four things have never been seen with real data: the Route column, the REPRODUCIBILITY panel, the unnamed-geometry panel, and the `NOT_IN_UPLOADED_SET` Stairs blank. The saved Crow run predates 28-06 and carries no routes, so all four were verified against a synthetic run. | human | 20 min |
| 9 | **The ship gate:** zero wrong-and-unflagged rows. Not a percentage. A flagged blank costs the estimator 30 seconds; a confident wrong number costs a bid. | human | — |

**Two things to watch on the baseline, because they are the claims most likely to be false:**

- **`coverage_pct_items` is now the first number the customer reads**, taken verbatim from the
  ledger. If it comes back materially different from 15.7%, that is a real signal about the
  post-28 engine and **not** a UI artifact.
- **Columns.** Expect `120 MEASURED` plus three flagged hypotheses (132 / 160 / 176) and
  `needs_review: True`. If a single number is published there, something re-introduced the
  completion rule and it must be reverted, not tuned.

---

## 9. TEST RESULTS OBSERVED

Python 3.9.6, this machine, no paid marker, no `ANTHROPIC_API_KEY`, no network.

| Run | Result |
|---|---|
| **Full offline suite** — `python3 -m pytest -q` | **§9.1** |
| The four mandated gates, **standalone** | **62 passed, 1 skipped** in 1396.54s (23:16) |
| `tests/test_production_user_path.py` (new) | **20 passed** in 9.9s |
| Composition batch — deployment contract + report honesty + manifest wiring + blueprint parity + grid lattice + missing sheets + keynote callouts + user path + seed admin + job history | **204 passed** in 109.33s |
| Live `gunicorn -w 1 --threads 4` smoke, isolated CWD | login 200 · `/` → 302 · `/api/reports` → 401 · upload 4 pages · cross-request state survived |

### 9.1 Full suite

```
2557 passed, 1 skipped, 2 deselected, 5 warnings in 4453.64s (1:14:13)
```

Run on the FINAL tree — this readiness pass plus the phase-29 name-carry fix and the
fixture-pollution fix. An earlier run of this suite against the pre-phase-29 tree was killed at
36% and deliberately discarded rather than quoted: a green result that describes code we are not
shipping is worse than no result, because it reads as evidence.

The four mandated gates are inside that run and green. The two deselected are the paid golden
markers, which is the correct state for an offline run; the warnings are the pre-existing SWIG
`DeprecationWarning`s from a C-extension import.

`git status --porcelain .planning/paid-run-evidence/` → **0**, before and after.

### 9.2 The new module, and why it is worth its runtime

`tests/test_production_user_path.py` — 20 tests, ~10 seconds, zero cost. It is the only module in
the suite that drives the composed product: `create_app` → real login with real CSRF → static
assets → upload → manifest → the run endpoint's refusals → the report endpoints → the shipped
browser classifier, over the bytes the server actually returned.

Non-vacuity: the three upload-guard assertions were run against the pre-fix `runs.py` and all
three went red; the file was restored and re-verified at 20 passed.

Two deliberate constraints inside it:

- **`/api/pdf/run` is exercised only on refusal paths.** The success path starts a real analysis
  thread that would call the vision API. A deployment gate that can spend money is a trap for
  whoever runs it next, and `test_this_module_spends_no_money` asserts the module contains no
  paid token.
- **Every request carries its own `REMOTE_ADDR`.** Flask-Limiter is a session-wide singleton
  keyed on the client address, so a fixed address would make `5 per minute` a shared budget
  across the module and turn a real failure into a 429 flake.

---

## 10. DEPLOYMENT CHECKLIST — for the operator

Follow it in order. Every step has a check you can see fail.

**Before you start**

- [ ] Ubuntu box, Python 3.9, one operator, one instance. This is a single-tenant deployment by
      design — see §11 for what that means and what it forbids.
- [ ] `git clone`, `python3 -m venv .venv`, `. .venv/bin/activate`, `pip install -r requirements.txt`.
- [ ] `python3 -c "import gunicorn, bobbytailor; print('ok')"` → `ok`.
      **Skip `playwright install chromium`** — that is StackCT-only and this is a plans-only box.

**Environment**

- [ ] `cp .env.example .env`.
- [ ] Set the three variables the web app **requires**. It refuses to start without them and
      names all the missing ones at once:
      `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` (bcrypt, `$2b$…`).
- [ ] Set `ANTHROPIC_API_KEY`. **Missing is a warning, not a refusal** — the deterministic
      offline path still runs, and a missing key surfaces as a failed vision pass mid-run. The
      startup log line is what makes that diagnosable.
- [ ] **Leave `STACKCT_EMAIL` / `STACKCT_PASSWORD` unset.** You are plans-only. With
      `STACKCT_EMAIL` empty the app skips the catalog prefetch and the 24 h scheduler and logs
      that it did. **Do not invent fake StackCT credentials** — nothing needs them.
- [ ] Set `OUTPUT_DIR` to an **absolute** path. The documented systemd unit pins
      `WorkingDirectory`, but an absolute path removes the question.
- [ ] Know the precedence: a variable set in the process environment (systemd `Environment=`,
      `docker run -e`) **wins over `.env`**, and is therefore effectively read-only from the
      Settings page.

**TLS — required, and the failure is silent**

- [ ] Either put nginx with a certificate in front, **or** set `SESSION_COOKIE_SECURE=false`
      because you control the network path (an SSH tunnel to 127.0.0.1, a local box).
- [ ] If you get neither right, the symptom is: `/login` reports success and every request
      redirects back to `/login`, forever, with nothing in the log and nothing on screen. If you
      see that loop, this is why.
- [ ] nginx: `client_max_body_size 500M` (it must match `MAX_UPLOAD_MB`), and forward
      `X-Forwarded-For` / `X-Forwarded-Proto`. The app trusts **exactly one** hop.

**Start it**

- [ ] `gunicorn -w 1 --threads 4 -b 127.0.0.1:5050 app:app --timeout 300`
- [ ] **`-w 1` is mandatory.** `jobs`, `uploads`, `object_manifests` and the single-active-job
      lock are module-level dicts in one process. With two workers, an upload handled by worker A
      404s when the follow-up run lands on worker B, and status polls 404 while a paid run
      completes invisibly. Do not raise it without first moving that state into a shared store.
- [ ] Do **not** run `python3 app.py` in production. It is a documented entry point and it serves
      the Werkzeug console when `FLASK_ENV=development`.

**Smoke test — 60 seconds, all free**

- [ ] `curl -sk https://<host>/login | head -c 200` → HTML, status 200.
- [ ] `curl -sk -o /dev/null -w '%{http_code}\n' https://<host>/api/reports` → **401**.
      If this returns 200, stop: report data is public.
- [ ] `curl -sk -o /dev/null -w '%{http_code} %{redirect_url}\n' https://<host>/` → **302** to
      `/login?next=/`.
- [ ] Log in through the browser. If you land back on the login form, re-read the TLS step.
- [ ] Upload a **PDF of plans** — not a take-off. The form says so; a take-off-shaped filename
      warns and holds the Analyze button until you tick the confirmation, and the warning is
      written onto the run's own log.
- [ ] Confirm the page picker lists your sheets by name. If the upload returns 400 with "could
      not be opened" or "password-protected", that is the file, not the server.

**Your first real run**

- [ ] Attach an object manifest (CSV or JSON: name, unit, measure, aliases — **no quantities**).
      It is optional and it is the highest-leverage 30 seconds in the workflow.
- [ ] Watch the progress bar. If polling fails three times in a row you get a banner and polling
      stops; a 401 stops immediately. A frozen bar with no banner means the run is genuinely slow.
- [ ] When it finishes, read the banner **first**: `N% of the expected line items were measured`,
      taken from the run's own `coverage.json`.
- [ ] **Understand the four row states.** `✓ Measured` (the app measured it, no human has
      confirmed it) · `! Needs review` (measured but flagged) · `∅ Not measured / no measurement
      path` (**the app had NO way to measure this — the blank is a blank, not a zero, and no
      button on the screen can turn it into a quantity**) · `≡ Standard item` (a convention the
      app injects).
- [ ] Type your own numbers into the blanks you can supply. They publish as **HUMAN INPUT** and
      are labelled as such forever.
- [ ] Download `coverage.json` and `summary.txt` with the CSV. They are the record of what the
      run did **not** do, and they are what makes the number defensible to whoever you bid against.

**Do not**

- [ ] Do not raise `-w`. Do not upload a completed take-off. Do not read a blank as a zero. Do
      not quote a coverage percentage as an accuracy. Do not run the golden/paid scripts
      (`scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`,
      `scripts/golden_convergence.py`, `pytest -m golden`) unless you intend to spend money.

---

## 11. OPEN ITEMS THIS PASS DID NOT FIX — decisions, not oversights

| Item | Status |
|---|---|
| **`.env.example` short two entries** | Sandbox-denied for every agent on this program. §8 step 1. |
| **`verify.py`'s `_summary_counts` / `verified_count`** | Still computes the old 18%-shaped ratio. **No UI reads it** — the worksheet recomputes from the ledger. Left alone because changing a response shape nobody reads is churn. **If anything ever starts reading it, it will read the wrong number.** |
| **V4-FIX-01 and V4-FIX-03 remain open**, deliberately | Two calculator producers still emit EA counts with no verdict; the masonry object still falls through to a non-confident hint bind. Each has a tripwire that goes red the day it is fixed. Shorten those deliberately; never delete them. |
| **`takeoff_pipeline.py` split, StackCT front-door parity, data-root abstraction, magic-byte sniffing, broader rate limiting, Phase 26** | All deferred in PRODUCTION-PLAN §3 with reasons. Nothing this pass found changes any of those reasons. |
| **The GitNexus index is stale** (last indexed `5fab264`, ~30 commits behind) | `gitnexus_impact` was run on the two symbols this pass edits — `upload_pdf` (0 callers, **LOW**) and `get_pdf_metadata` (1 caller, **LOW**). No HIGH or CRITICAL finding. Re-run `npx gitnexus analyze` before the next plan that edits `fusion.py`, `aggregator.py` or `calculator.py`. |
| **Phase 25's scope fence has moved** | Its stated subjects were Columns, Ladder and Bollards detection. Two now have working deterministic routes that landed outside it. Re-plan it from what the harness measured, not from the ROADMAP text. |

---

## 12. THE ONE-PARAGRAPH ANSWER

The application boots under the command its own documentation prescribes — verified by executing
it, which had never been done before this pass. An estimator can log in, upload plans and a
manifest, and read a report in which a number the engine could not measure is visibly, separately
and unmistakably a blank rather than a zero or an oversight. A corrupt file now says so instead
of returning a server error. The four standing gates are green standalone and inside a full
offline suite. **What has never happened is a paid run of this engine on a real drawing** — so
every accuracy figure anyone quotes today, including the ones in this document, is a forecast.
Spend the $1.20, score it, read it as an estimator, and then ship for Crow-shaped work.
Bob's waits for its own $0.60.
