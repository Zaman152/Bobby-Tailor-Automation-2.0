# PRODUCTION PLAN — shortest credible path to a small-project deployment

**Author:** sequencing investigator · **Date:** 2026-08-13 · **Cost to produce:** $0.00
**Inputs:** INV-A (real user path), INV-B (symbol detection), INV-C (deploy blockers),
INV-D (vision A/B), INV-E (propose→verify), ROADMAP phases 25–28, STATE.md.
**Scope:** ONE operator, ONE box, plans-only PDF + optional manifest, small projects
(Bob's Discount 7 pp, Crow Cass 4 pp).

---

## 1. VERDICT

**Yes — you can deploy for Crow in about 6 working days, at a cost of roughly $2.40 in API
credits. You cannot deploy for Bob's on the same evidence, because Bob's has never been
measured by the current engine at all.**

The honest shape of what ships:

> **Not "an accurate takeoff". A takeoff with zero confidently-wrong numbers, where roughly
> half the line items are measured correctly and the rest are explicitly flagged as "we could
> not measure this — you must supply it."** Under your human-in-the-loop contract that is a
> sellable product. It is not "near 100%", and nothing on any credible path this month makes
> it near 100%.

Three findings drive that verdict, and two of them contradict the briefing you gave me. I am
leading with them because they change what you should build first.

### Finding 1 — the 40–50% number is stale. Nobody has measured the current engine.

The saved paid evidence was written at **Aug 6, 20:06**. The first Phase-28 code commit
(`10026aa`) landed at **Aug 6, 20:58** — 52 minutes later. Plans 28-01 through 28-06 all
landed after the evidence was captured:

```
$ ls -la .planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_194607/takeoff.json
-rw-r--r--  399516 Aug  6 20:06 ...takeoff.json

$ git log --reverse | grep 28-01
10026aa 2026-08-06 20:58:13 test(28-01): the detail-sheet item-type list must exist once...

has quantity_route (the field 28-06 adds to every published row): False
```

So "Crow ~40–50%, 5 of 10 golden" describes an engine that is **six plans out of date**. Every
Phase-28 fix — uncorroborated counts may no longer publish MEASURED (28-03), a non-discriminating
thickness may no longer bind (28-04), one region may no longer fan out to three rows (28-05),
every quantity now states its route (28-06) — is unmeasured on a real drawing.

**Consequence for sequencing:** several of those fixes will *lower* the raw "correct" count while
*raising* "correct + honestly flagged" — Stairs will stop publishing a confident `1.00` and start
publishing a flagged blank, which scores as a FAIL but is the behaviour you built the phase to get.
**Planning accuracy work against the stale number will send you chasing regressions you deliberately
introduced.** The first paid run after the deploy fixes is not a nice-to-have; it is the
measurement everything else is planned against.

### Finding 2 — INV-A's headline UI severity claim is wrong, and acting on it would make the product worse.

INV-A states that the worksheet "paints the worst errors green", naming *Exposed Structure* and
*Sealed Concrete* as "the two ~0.5%-accurate items". That reads the scorer's `ERR%` column as an
accuracy. It is an **error** percentage — `scripts/vision_only_benchmark.py:240`:

```python
err = round(abs(ai_qty - g_qty) / g_qty * 100, 1) if g_qty else None
```

Re-scored free just now:

```
PASS      Exposed Structure     395,673.42    397,600.00     0.5  measured
PASS      Sealed Concrete       395,673.42    397,600.00     0.5  measured
PASS      Internal Tilt up walls 108,442.66   106,992.00     1.3  measured
```

`0.5` means **0.5% error — 99.5% correct, and a golden PASS.** Those two rows are the engine's
two best numbers. The UI marking them green ✓ Confirmed is **correct behaviour**, not a defect.
Note also that the golden itself lists Exposed Structure and Sealed Concrete at the *same*
395,673 SF — the two-way fan-out of one measured footprint into those two rows is what the
estimator did too. (28-05's fix was aimed at the *third* row, Concrete Pad.)

The rest of INV-A §4 stands and is serious: NOT MEASURED rendered as "Needs review · enter value",
the "Confirm 11 remaining estimates → 100%" button, `coverage.json` unreachable from the UI,
`unnamed_geometry` rendered nowhere. Fix those. **Do not "fix" the green badge on the two rows
that are right** — a developer following INV-A literally would flag the engine's best output and
leave the honest-blank problem untouched.

### Finding 3 — Bob's Discount is not validated. At all.

The deployment target is "Bob's and Crow". Every piece of evidence in this repository is Crow.
The only Bob's artifacts:

```
output/VisionOnly_Bobs_G3_20260715_182541   (July, pre-Phase-23/24)
  Overall quantity accuracy: 8%   1 of 12 golden items (Mobilization)

output/bobs_20260803_150552                  (Aug 3, deterministic-only, $0.00)
  published rows: 0        items_measured: 0        coverage_pct_items: 0.0
```

Bob's golden has **12** items, not 10 — so each is 8.3%, and the item mix is different from
Crow's (two door-count rows, a door-frame row, gas piping LF, lintels LF, two elevation paint
areas). Those route through parts of the engine Crow never exercises. **Shipping "for Bob's"
today means shipping on a guess.** One $0.60 baseline run converts that guess into a number; it
is the single highest-value dollar in this plan.

---

## 2. THE CRITICAL PATH

Six working days of engineering, two paid checkpoints, ~$2.40. Ordered. Anything not on this
list is deferred in §3 — deliberately.

### Day 1 — Make the documented deploy actually work · owner: **Phase 27 (scoped to 5 items)**

The highest-confidence work in the whole program: INV-A and INV-C found the same blocker
independently, from different directions, and both reproduced it live.

| # | Item | File:line | Effort |
|---|---|---|---|
| 1.1 | `gunicorn -w 2` → `-w 1 --threads 4` | `docs/DEPLOYMENT.md:13`, `README.md:169`, `README.md:192` (systemd `ExecStart`) | 15 min |
| 1.2 | `load_dotenv(override=True)` → `override=False` | `config.py:10` | 10 min |
| 1.3 | Move `validate_required_env()` out of import; web-scoped required set; `STACKCT_*` checked only in `scrape/` | `config.py:140`, `config.py:117-124`, `web/app.py:39` | 1 h |
| 1.4 | `SESSION_COOKIE_SECURE` env-overridable; make TLS non-optional in the runbook | `web/app.py:42`, `README.md` | 30 min |
| 1.5 | Settings `VALID_MODELS` generated from config; `update_settings` refuses empty writes; record `CLAUDE_MODEL_*` in `run_settings` | `web/settings.py:24`, `templates/settings.html:91-94`, `static/settings.js:38` | 1.5 h |
| 1.6 | `pollJobMonitor` must surface a non-OK status poll instead of `if (!res.ok) return;` | `static/js/app.js:620` | 30 min |
| 1.7 | MAJORs, same day: `debug` gated on `FLASK_ENV` (`app.py:5`); `gunicorn>=21.2` in `requirements.txt`; `ProxyFix(x_for=1,x_proto=1)`; skip StackCT prefetch + 24 h scheduler when `STACKCT_EMAIL` empty (`web/app.py:75,82-90`); align nginx `client_max_body_size` with `MAX_UPLOAD_MB` | various | 2 h |

**Why this is day 1 and not day 3:** 1.1 alone breaks roughly half of all real user clicks, and
1.3 means a plans-only operator cannot import the package without inventing two fake StackCT
passwords. There is no point measuring accuracy on a path the operator cannot reach.

**Add the three cheap pins with the fixes** (INV-C's suggestion, and it is right): assert the
settings model options equal the config choices; assert no deployment doc contains `-w ` above 1
while `jobs_runtime` state is in-process; assert `update_settings` refuses an empty non-sensitive
value. The existing 123-test web suite passes today and catches none of these.

### Day 2 — Make the report screen tell the truth · owner: **Phase 27 (new UI item) or Phase 28-07**

This is what makes the app *safe to put in front of an estimator*, which is a different question
from whether it boots.

| # | Item | Where | Effort |
|---|---|---|---|
| 2.1 | `rowStatus()` must read `provenance`. NOT MEASURED renders as its own third state — visually distinct from NEEDS REVIEW, cell text "no measurement path", never "enter value" | `static/js/reports-workspace.js:361-371` | 2 h |
| 2.2 | Kill "Confirm 11 remaining estimates → 100%". The banner reports `coverage_pct_items` from `coverage.json`, and there is no single control that converts 31 unmeasured rows into a verified takeoff | `reports-workspace.js:393-400` | 1.5 h |
| 2.3 | Surface `coverage.json`: add to the file lists and the Downloads panel | `web/blueprints/reports.py:125-131`, `:195-201` | 45 min |
| 2.4 | Render `unnamed_geometry` (34 entries on Crow) as a "measured but unnamed" panel — this is real geometry the operator can name, and naming it is the learning loop's raw material | `reports-workspace.js` | 1.5 h |
| 2.5 | Show `quantity_route` (28-06) per row, and reproduce `summary.txt`'s "a repeat run may move these" list on screen | `reports-workspace.js` | 1 h |
| 2.6 | Warn on upload when the filename matches `take[ -]?off` — the plans-only contract stated in the UI, not just in the docs | `web/blueprints/runs.py:130`, `index.html` | 30 min |

**Explicitly NOT on this list:** changing how Exposed Structure / Sealed Concrete are badged. See
Finding 2. They are correct and the green badge is correct.

### Day 3 (half) — PAID BASELINE #1 · ~$1.20 · **the measurement everything else depends on**

Two runs, both driven entirely through the real browser UI — upload PDF, attach manifest, poll,
download CSV. This is simultaneously (a) the acceptance test for days 1–2 on the operator's
actual path, and (b) the first honest measurement of the post-Phase-28 engine.

- **Crow** with `tests/fixtures/crow_cass/crow_cass_manifest.json` (10 objects) — ~$0.60
- **Bob's** with `tests/fixtures/bobs_discount/bobs_discount_manifest.json` (12 objects) — ~$0.60

Score both free with `scripts/score_report_dir.py`. **Record the result before writing any
accuracy code.** If Bob's comes back materially different from the forecast in §4, re-sequence
day 4–6 around what Bob's actually needs rather than around Crow's column problem.

### Days 4–6 — Accuracy: the three items INV-B proved are reachable · owner: **Phase 25 (scoped)**

Do not run Phase 25 as the roadmap scopes it. Run exactly this:

| # | Item | Effort | Confidence |
|---|---|---|---|
| 4.1 | **`src/bobbytailor/deterministic/grid_lattice.py`** (~250 LOC, additive, must not touch `symbols.py`): closed-rect census → grid axes from printed text → 2-D lattice accepting only `n≥12`, ≥2 distinct X **and** ≥2 distinct Y, occupancy ≥0.9, no duplicate cells. Emits `count`, per-instance cell IDs, marker size, occupancy, and `completion_candidate` as a **separate flagged field** | 1.5–2 d | **High** |
| 4.2 | Offline regression suite for 4.1 across Crow p0–3, Bob's p0–6, Chelsea p0–11 — 1 fire, 21 clean negatives. Plus the permanent §10 trap test: the 136×`(1.80,0.72)` and 40×`(1.32,1.32)` classes are rejected for having one distinct Y | included above | **High** |
| 4.3 | `room_fill.py:294` `^(\d{2})\.?$` → `^(\d{1,2})\.?$`; re-pin `keynote_legend`/`keynote_tags`; route keynote text → manifest alias, with the keynote-1-vs-2 head-noun call left to the semantic pass (zero numeric fields, as now) | 0.5–1 d | **High** |
| 4.4 | Stairs: **no detector code.** Wire `NOT IN UPLOADED SET` into the Phase-28 flag surface, quoting the drawing's own cross-references (`SEE 1/A-111`, `6/A-401`). Correct the ground-truth §10 second conclusion and the `symbols.py:13-17` docstring claim, both of which are now known false | 0.5 d | **Certain** |

I re-ran INV-B's central probe independently before committing to this:

```
closed-rect size census, Crow page 0:
  size (1.8, 0.72)   n= 136  xspan=1885.2  yspan=  0.0  distinctY=1   <- §10's ticks. CONFIRMED.
  size (1.44, 1.56)  n= 120  xspan=1846.8  yspan=435.0  distinctY=6   <- REAL COLUMNS
  size (1.32, 1.32)  n=  40  xspan=1846.9  yspan=  0.0  distinctY=1   <- panel-joint ticks
```

The 120 are real, 2-D, and structurally distinguishable from the tick rows that trapped §10.
This is the best-evidenced accuracy bet in the program.

**One caution INV-B did not flag.** The same census shows a `(15.84, 15.72) n=21, distinctY=20`
class — 21 larger squares, genuinely 2-D distributed. INV-B's `n≥12` + `occupancy≥0.9` +
no-duplicate-cells filter should reject it, but **that must be an assertion in 4.2, not an
assumption.** A detector that fires twice on Crow p0 is a new false-positive source.

### Day 6 (half) — PAID CONFIRM · ~$1.20

Re-run Crow and Bob's through the browser. Diff against baseline #1. Ship if nothing regressed.

**Total: 6 working days, ~$2.40. Allow 8 calendar days.**

---

## 3. WHAT WE ARE DEFERRING — and these are decisions, not oversights

Each of these was considered and rejected **for this deployment**. Say so out loud in standups,
or someone will re-discover them as "gaps" in three weeks.

| Deferred | Owning phase | Why it is a decision |
|---|---|---|
| **Vision-model A/B / provider migration** | — | INV-D checked all 10 Crow golden items individually against both saved runs: **zero** are decided by a vision label. A perfect VLM moves 0 of 10. See §6. |
| **propose→verify harness (INV-E)** | — | INV-E's own §3 says this is the honest path *only if* the columns are not separable in the vector data. INV-B proved they are, and I reproduced it. The expensive architectural answer is now unnecessary — build the cheap deterministic one. Revisit only if Bob's baseline shows a class of object with no vector signature. |
| **Phase 26 (Learning Loop & Autonomy) — entire phase** | 26 | Real value, wrong month. The manifest is 12 lines of CSV; re-supplying it per run costs the operator 30 seconds. Autonomy metrics are meaningless until the engine has a measured baseline to trend from. Day 2.4 (rendering `unnamed_geometry`) is the one piece worth pulling forward, because it collects the raw material. |
| **`takeoff_pipeline.py` split (V4-PROD-02)** | 27 | 5,859 LOC against ~14 patch-by-module-path test files. Most regression-prone item in the program; fixes zero deployment risks. Not before a paying customer. |
| **StackCT front-door parity (V4-PROD-01)** | 27 | The roadmap text is **stale**. You are shipping plans-only; `pdf_analyzer.py` calls `run_project` directly, so the door you ship has parity by construction. And `_build_project_vocabulary` has zero call sites — Phase 24 made it dead code and pinned that at `tests/test_phase24_acceptance.py:633`. Rewrite the roadmap item; schedule no work. |
| **Data-root abstraction (V4-PROD-06)** | 27 | Real, but the documented systemd unit pins `WorkingDirectory`. Mitigate with an absolute `OUTPUT_DIR` in `.env` plus one runbook line. Revisit on containerization. |
| **Upload magic-byte sniffing, broader rate limiting (V4-PROD-07)** | 27 | Single-admin login + CSRF + 500 MB cap. No untrusted uploader exists in this deployment. Do `ProxyFix` (day 1.7) instead — that is the part that is actually broken. |
| **Multi-worker / shared job store** | 27 | One operator, one box. `-w 1 --threads 4` is correct, not a workaround. Do not raise `-w` later without first moving `jobs`/`uploads` into a shared store. |
| **30 ft wall-height default (`takeoff_pipeline.py:1482`)** | 25/28 | Still live, still wrong for retail/hotel — but Crow *is* a warehouse and Bob's golden has no wall-height-derived item. Watch it in the Bob's baseline; fix only if it moves a Bob's number. |
| **Chasing Bollards 28 and Stairs 10** | 25 | INV-B: the "Bollards 56" is 56 mislabelled column markers, and Crow's real bollards are derived from a door-schedule note, not countable glyphs at 1"=40'. Stairs are physically absent. Both should **flag**, not resolve. Trying to hit those numbers is exactly the §10 coincidence trap. |
| **Excel export, `/health` endpoint** | 27 | CSV is a shippable deliverable; `curl /login` is a working smoke test. |

---

## 4. ACCURACY FORECAST — honest

### How to read this

Three buckets, and the third distinction is the whole product:

- **(a) MEASURED CORRECT** — engine produces the right number unassisted.
- **(b) HONESTLY FLAGGED** — engine cannot measure it and says so, with evidence. **This is a
  SUCCESS of the design, not a failure.** Under your human-in-the-loop contract the estimator
  resolves flags; a flagged blank costs 30 seconds and a wrong number costs a bid.
- **(c) MISSING / WRONG-AND-UNFLAGGED** — the only genuine failure mode.

The metric that should govern the ship decision is **(a) + (b) — "correct or honestly flagged"**,
with **(c) = 0** as a hard gate. Raw "% correct" against the golden CSV understates a
deliberately-flagging engine; the golden scorer marks a flagged blank FAIL, which is why the
scorer alone must never be your ship criterion.

### Crow — 10 items, each 10%

**Hard ceiling is 9 of 10, not 10 of 10.** Stairs (golden 10) are not in the uploaded 4-page PDF.
Page 0 has zero "STAIR" text; the E2 tag exists only in the legend and is marked "TYP."; a tread
search finds 0 runs in the plan. They live on A-401 and enlarged plans A-111/112/113, which the
sheet cross-references and does not contain. No detector — deterministic, ML, or vision — counts
objects that are not in the file.

| # | Item | Now (pre-28, measured) | After critical path | Bucket | Reasoning |
|---|---|---|---|---|---|
| 1 | Exposed Structure | PASS 0.5% err | PASS | **(a)** | `plan_schedule_legend`, text-centric. Already right. Only risk is a day-2 UI change touching it — don't. |
| 2 | Sealed Concrete | PASS 0.5% err | PASS | **(a)** | Same route. |
| 3 | Internal Tilt-up | PASS 1.3% err | PASS | **(a)** | Naming-library hint bind, deterministic. |
| 4 | Mobilization | PASS | PASS | **(a)** | Standard item. |
| 5 | Ladder-H-20' | NOT MEASURED | **PASS** | **(a)** | Highest-confidence *new* pass. Keynote 1 = "ACCESS LADDER…", appears exactly once on the plan + once in legend. Blocked only by `\d{2}` at `room_fill.py:294`. Text route — the engine's strongest regime (0.65–0.92 vs 0.03–0.39 for symbol-shaped). |
| 6 | Columns-H-35' | NOT MEASURED | **120 measured + 12 flagged** → PASS *after one click* | **(a)/(b)** | The sheet **draws 120**. 132 needs an explicit extrapolation rule INV-B honestly admits was derived *after* seeing the golden, unvalidated on a second building. Golden `match_mode` is `exact_or_within_1`, so **120 scores FAIL**. Ship it as 120 MEASURED + 12 INFERRED-CONFIRM. Correct after one human click; do **not** add a test asserting 132. |
| 7 | Bollards | 56 vs 28 (FAIL) | **flagged blank** | **(b)** | The 56 was never bollards — it is 56 of the 120 column markers mislabelled. Once the lattice consumes them the false 56 disappears. Real bollards are derived from a door-schedule note, not glyphs. Expect a flag, not 28. |
| 8 | CMU Wall | 11,286 vs 2,204 (FAIL 412%) | **flagged, probably** | **(b)** | 28-04 made a non-discriminating thickness refuse to bind. Unmeasured. Most likely outcome is a refusal + audit record rather than a corrected 2,204. |
| 9 | Lift | flips 0 ↔ 1 between runs | **flagged** | **(b)** | Manifest-bind determinism defect. INV-D §5: temperature cannot fix it on any hosted API. |
| 10 | Stairs | 1–2 vs 10 (FAIL, unflagged) | **NOT IN UPLOADED SET** | **(b)** | 28-03 already stops the confident `1.00`. Day 4.4 makes the reason legible. |

**Crow forecast:**
- **(a) correct unassisted: 5 of 10 (50%)** — was 4–5.
- **(a) after one confirmation click on the 12 end-wall columns: 6 of 10 (60%)**.
- **(b) honestly flagged: 4 of 10** — Bollards, CMU Wall, Lift, Stairs.
- **(c) wrong-and-unflagged: target 0.**
- **"Correct or honestly flagged": 10 of 10.**

**Say this to yourself before you say it to a customer: near-100% *correct* is not achievable on
Crow, this month or any month, from that 4-page PDF.** What IS achievable, and what I believe you
will actually reach, is 50–60% measured correctly and 100% either correct or explicitly flagged —
with a stated ceiling of 90% correct even if every remaining engineering problem were solved,
because the stairs are not in the file.

**Confidence:** medium-high on items 1–5 (four are already passing; item 5 is a two-character
regex on a text route). Medium on item 6 (detector is proven on the page, the +12 rule is not
validated on a second building). Low-confidence on the *exact* post-28 numbers for items 7–9 —
see Finding 1; nobody has run this engine.

### Bob's Discount — 12 items, each 8.3% — **forecast is a guess and should be treated as one**

There is no baseline. The July run scored 1/12 on an engine three phases old; the Aug-3
deterministic-only run published zero rows. I will not dress that up.

Reasoning by route, not by measurement:

| Route | Items | Expectation |
|---|---|---|
| Standard item | Mobilization | **(a)** — near-certain |
| Door **schedule** (text) | Doors-HM 5, Doors-WD 7, Door Frame-HM 12 | Plausible **(a)**. The schedule route is alive — the Crow run emitted "Doors - Hollow Metal (door schedule) 29.0" — and Bob's has a schedule sheet (A156.10). But Crow's door numbers were extras, never scored against a golden, so the route has **never been validated for correctness**. Call it 1–3 of 3. |
| Elevation facade silhouette (23-14) | Ext. Painting CMU 16,219 SF, EIFS-ALT 3,053 SF | Plausible. 23-14 was validated against Bob's own front (249.2 ft vs 250.0 depth). 0–2 of 2. |
| Run selectors (23-15) | Gas Piping 886 LF, Lintels 179 LF | Contested. 23-15 records a false schedule bbox on Bob's roof plan that "deleted every gas segment" — worked on, outcome unverified. 0–2 of 2. |
| Counts / small areas | Bollards 11, Canopy 79 SF, Ladder-H-24' 1, Lift 1 | Weak. Ladder benefits from the same keynote fix (4.3) if Bob's uses keynotes. 1–2 of 4. |

**Bob's forecast: 3–6 of 12 correct (25–50%), very wide error bars.** The critical-path work is
Crow-shaped: the column lattice almost certainly does **not** fire on Bob's (INV-B's detector
returned `None` for all 7 Bob's pages), so days 4–6 buy Bob's roughly **one** item (Ladder, and
only if it is keynoted).

**This is the plan's biggest open risk, and it is cheap to close.** $0.60 on day 3 converts the
whole table above from reasoning into measurement. If Bob's comes back at 2/12 you have a
different product problem than the one this plan solves, and you want to know that on day 3, not
after you ship.

---

## 5. THE REAL-USER-PATH GAPS — first-class work, days 1–2

Restating the good news first, because it removes the thing everyone feared: **a user CAN upload
a manifest through the browser, and it DOES reach the pipeline.** INV-A proved the id arrives as
`manifest_path` in `_pdf_job`; I confirmed the endpoint accepts both `.csv` and `.json`
(`runs.py:224-273`) and that the loader handles both (`devtools/object_manifest.py:266,273`).
Nothing needs building. Two residual gaps, both small: a manifest cannot be attached to a
*project* for reuse, and nothing tests the `object_manifest_id → manifest_path` hop
(`grep object_manifest_id tests/` returns nothing) — add that test on day 1, it is 20 minutes and
it protects the one thing that must not silently break.

Equally important: **the web path and the benchmark path are the same function.** Both
`scripts/vision_only_benchmark.py:753` and `web/jobs_runtime.py:362` call
`pdf_analyzer.run_pdf_analysis()`. There is no worse pipeline hiding behind the UI, and the
plans-only / no-discovery guards live *inside* that shared function (`pdf_analyzer.py:476-478`,
`allow_discovery=False`), pinned by `tests/test_pipeline_parity.py:972`/`:1015`. **The leakage
tripwire holds on the operator's path by construction.** The only residual is human: the app
accepted `Crow - Cass White Road-Take offs.pdf` with a 200 and no warning — day 2.6.

What actually blocks a real user, in priority order:

1. **`-w 2` 404s ~half of all uploads and status polls** (day 1.1). Reproduced twice, independently.
2. **A 404 status poll is swallowed and polls forever** — `app.js:620` `if (!res.ok) return;`.
   The bar sits at 0% while a paid run completes invisibly (day 1.6).
3. **A plans-only operator cannot import the package without fake StackCT credentials**
   (day 1.3), and boot spawns a real Playwright StackCT login (day 1.7).
4. **Plain-HTTP login is silently impossible** — `SESSION_COOKIE_SECURE=True` while the README
   calls nginx "optional" (day 1.4). Login succeeds, every request redirects to `/login` forever,
   no error anywhere.
5. **One visit to Settings + Save blanks `CLAUDE_MODEL_SCHEDULES`**, which routes every floor-plan
   count and measure pass. The next run calls the API with `model=""` (day 1.5).
6. **The report screen contradicts the honesty work the pipeline does** — 31 NOT MEASURED rows
   rendered as "Needs review · enter value", and a button that converts an 15.7%-coverage run into
   a "100% verified" takeoff in one click (day 2.1–2.2). This is the one that would cost a bid.

---

## 6. VISION-MODEL RECOMMENDATION

**KEEP CLAUDE. Do not build the provider seam. Do not run the A/B. Cost of this decision: $0 and
0 days — it is already made, it just needs recording.**

INV-D checked each of the 10 Crow golden items against both saved runs, asking per item "did a
vision label decide this number?" The answer is no, ten times:

- Bollards' own run note reads **"vision label unavailable"** — named by the deterministic naming
  library; the 56 came from geometry.
- Columns / Ladder / Lift are `manifest object not found in plans` — nothing rendered, nothing asked.
- Exposed Structure and Sealed Concrete pass via `plan_schedule_legend`, a text-centric read where
  every frontier model sits at ~0.95. Switching there is noise with regression risk on the only
  two items currently passing.
- The one item where vision *did* answer is overruled **by design** —
  `fusion_rejected: {candidate_id: WALL-TC5, answer: "tilt-up concrete panel",
  reason: "wall_class_thickness_bind_outranks_label", kept_label: "CMU Wall"}`. Upgrading a
  proposer that has already been outvoted buys nothing.
- 21 of 34 unnamed symbol groups (190 EA of real measured objects) are **never sent to any model**
  (`takeoff_pipeline.py:4333`, `:4395`). Swapping the model behind a gate that never opens changes
  nothing; opening the gate so a model can guess would directly regress the "flag, don't guess"
  branch you are on.

Two corrections worth carrying forward: the Gemini 3072 px raster cap is **not** an argument
against Gemini (we render at `RENDER_TARGET_PX=1568`), and Gemini's `responseSchema` does not
accept `additionalProperties`, which downgrades our "unexpressible rather than merely flagged"
guarantee to a vendor-behaviour assumption. OpenAI strict mode is an exact match to our contract.

**Write down the trigger** so this is not re-litigated from memory: *after the grid-lattice
detector lands and Columns/Bollards are being detected, re-score. If the residual failures then
read "vision label X, expected Y" in `review_notes` — geometry finding the right objects and the
label being wrong — the A/B becomes the right ~$6 to spend* (~1.5 days engineering, budget $15).
Until then it is a week moving a variable pinned at zero.

**The seam itself is cheap if you ever want it** — `import anthropic` appears in exactly one file
(`vision/claude_analyzer.py`), every consumer already injects the analyzer as a callable, and only
4 test assertions pin the Anthropic call shape (`tests/test_vision_schemas.py:909-934`).
1.5–2.5 days whenever the trigger fires. That cheapness is a reason not to pre-build it.

---

## 7. OPEN DECISIONS — only you can make these

1. **Ship at "zero confidently-wrong, ~50–60% auto-correct on Crow, remainder flagged"?**
   My recommendation: **yes.** Waiting for 90% means waiting for a full sheet set from the
   customer, which is their action, not yours. But it is your call whether that is a product you
   want in front of an estimator with your name on it.

2. **Approve ~$2.40 of paid runs** (2 baseline + 2 confirm, Crow + Bob's)? Without the baselines
   this plan is built on a six-plans-stale number (Finding 1) and a guess about Bob's (Finding 3).
   I consider this non-optional but it is your budget.

3. **The 12 end-wall columns: flag or publish?** Recommended: publish `120 MEASURED` +
   `12 INFERRED — end-wall grid lines 1 & 22, not drawn on A-101, typical for tilt-up. CONFIRM.`
   Alternative is publishing 132 silently, which hits the golden and hides an extrapolation rule
   that was derived from the answer key and is unvalidated on a second building. Your call on
   whether one extra click is worth the honesty.

4. **Deploy for Crow only first, or hold until Bob's is validated?** Depends entirely on day 3's
   Bob's number. Decide after, not now.

5. **When the uploaded set is missing cross-referenced sheets (Crow's A-111/112/113, A-401):
   refuse to run, or run and flag?** Recommended: run and flag prominently. A refusal on a
   4-page upload would block the deployment target itself.

6. **Is single-operator/single-worker acceptable as a standing constraint?** If yes, `-w 1` is a
   documentation fix and we are done. If you expect two concurrent users within 3 months, the
   `jobs`/`uploads` → shared-store refactor moves onto the critical path and adds ~2 days.

---

## 8. RISK REGISTER — the deployment itself

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Post-Phase-28 accuracy is materially worse than the stale 40–50%** — 28-03/04/05 convert confident numbers into flagged blanks, and the golden scorer marks those FAIL | **High** (by design) | Medium — looks like a regression in a spreadsheet, is actually the product working | Day-3 baseline **before** any accuracy work. Score on "(a)+(b) with (c)=0", not on raw %. Brief whoever reads the number. |
| R2 | **Bob's baseline comes back very low (≤2/12)** | Medium | **High** — invalidates "deploy for Bob's" | $0.60 on day 3. Re-sequence days 4–6 to Bob's routes if it fires. Fall back to Crow-only launch. |
| R3 | **The grid-lattice detector fires falsely** — the `(15.84,15.72) n=21 distinctY=20` class on Crow p0 is a live 2-D candidate | Medium | High — a new confidently-wrong number is the exact failure mode Phase 28 exists to kill | Assert single-fire on Crow p0 in the 4.2 suite. Keep the 21/21 clean-negative run across Bob's + Chelsea as a gate, not a one-off. |
| R4 | **The +12 column extrapolation is wrong on the next building** — rule derived after seeing golden=132, one degree of freedom, unvalidated | Medium | Medium | Ship as a flagged completion requiring confirmation, never a silent number. Test asserts `measured==120` and `completion_candidate==132` separately. |
| R5 | **Day-2 UI work "fixes" the two correct green rows** by following INV-A's mis-stated severity | **Medium-high** if INV-A is handed to a dev unread | High — degrades the engine's best output | Finding 2 is in this document for exactly that reason. Put it in the day-2 ticket text. |
| R6 | **`override=False` (1.2) changes Settings semantics** — a var also set in the process env can no longer be changed via Settings | Low today (systemd sets only `PATH`) | Medium confusion | One line in the runbook. Do it now, before a second env var exists. |
| R7 | **The offline suite stays green through all of this and proves nothing about deployment** — 123 web tests pass and catch none of B1–B5 | Certain | Medium | The three doc/settings pins on day 1. The paid browser run on day 3 is the only real acceptance test. |
| R8 | **Operator uploads a take-off PDF as plans** — accepted today with a 200 and no warning | Low-medium | **High** — a confident meaningless report, and the answer key entering the pipeline | Day 2.6 filename warning. Note the code-level guard already holds: no production module imports `companion_takeoff`, `allow_discovery=False`. |
| R9 | **Manifest wiring silently breaks in a refactor** — `object_manifest_id → manifest_path` has zero test coverage | Low | **Critical** — the manifest is half the product contract | 20-minute test on day 1. |
| R10 | **Scope creep back into Phase 26/27-as-written** | Medium | High — two weeks gone | §3 is the contract. Phase 27 as scoped is ~2 weeks and ~90% of it should not be done now. |
| R11 | **Single worker blocks under load** | Low (one operator) | Low | `--threads 4`; the job already runs in its own daemon thread and the request returns `job_id` immediately. Do not raise `-w` without the shared store. |
| R12 | **Crow's ceiling (9/10) is discovered by the customer rather than disclosed by you** | Medium | High — trust | State it in the delivery note: the stairs are on sheets not in the uploaded set. Encode it in the fixture so it is not re-discovered next month. |

---

## 9. ONE-PARAGRAPH SUMMARY

Spend one day making the documented deployment actually work — `gunicorn -w 2` breaks half of all
user clicks and a plans-only operator cannot even import the package without inventing StackCT
credentials. Spend a second day making the report screen stop describing 31 unmeasurable rows as
"needs review" with a button that converts them to "100% verified". Then spend $1.20 measuring
what you actually have, because the 40–50% figure everyone is planning against was captured 52
minutes before Phase 28's first commit and describes an engine that no longer exists — and because
Bob's Discount, one of your two launch projects, has never been measured by this engine at all.
Then spend three days on the one accuracy bet that is genuinely proven: 120 columns sit on a 20×6
grid at 100% occupancy with zero false positives across 22 pages, and the Ladder is blocked by a
two-character regex. Do not switch vision models — a perfect one moves zero of Crow's ten items.
What ships is a takeoff that gets about half its line items right, flags the rest honestly, and
publishes nothing confidently wrong — with a hard ceiling of 9 of 10 on Crow because the stairs
are on sheets the customer did not upload. That is worth shipping. "Near 100%" is not on offer,
and anyone who tells you otherwise has not read the PDF.
