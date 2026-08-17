# Bobby Tailor — Operator Guide

Everything one estimator needs to deploy this, run it, and trust what it prints.

---

## 1. What this app promises, and what it does not

**It promises: no confidently wrong numbers.**

Every row is either a quantity the app measured off the drawing, or a visible blank that says
why it is blank. The app will leave a cell empty rather than guess it. A blank costs you thirty
seconds; a confident wrong number costs you a bid.

**It does not promise a complete take-off.** On a typical plan set the app measures roughly half
the line items unassisted. The rest come back flagged, and you fill them in — which is the
workflow, not a failure of it.

> **The one rule that matters when reading a report:** a blank is **not** a zero. If a row shows
> *"no measurement path"*, the app had no way to measure that item on these drawings. It is not
> saying the building has none.

---

## 2. Deploying

Prerequisites: Ubuntu box, Python 3.9, **one operator, one instance**. This is single-tenant by
design (see §8).

> **Sized for small and medium sets — roughly 4 to 15 sheets.** That is the range the accuracy
> work targets and the range the app is measured on. Larger sets still run, but they exercise
> paths that carry no accuracy evidence, so treat their output as unvalidated.

```bash
git clone <repo> && cd Bobby-Tailor-Automation-2.0
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 -c "import gunicorn, bobbytailor; print('ok')"     # must print: ok
```

Skip `playwright install chromium` — that is StackCT-only and you are running plans-only.

### 2.1 Environment

```bash
cp .env.example .env
```

Set the three the app **refuses to start without** (it names all missing ones at once):

| Variable | Notes |
|---|---|
| `SECRET_KEY` | any long random string |
| `ADMIN_EMAIL` | your login |
| `ADMIN_PASSWORD_HASH` | bcrypt, starts `$2b$` |

Then:

- `ANTHROPIC_API_KEY` — **missing is a warning, not a refusal.** The deterministic path still
  runs; a missing key surfaces as a failed vision pass mid-run.
- `OUTPUT_DIR` — use an **absolute** path.
- **Leave `STACKCT_EMAIL` / `STACKCT_PASSWORD` unset.** With them empty the app skips the catalog
  prefetch and the 24 h scheduler and logs that it did. **Do not invent fake StackCT credentials.**

**Precedence:** a variable set in the process environment (systemd `Environment=`, `docker run -e`)
**beats `.env`**, and is therefore read-only from the Settings page.

### 2.2 TLS — required, and the failure is silent

⚠️ **`.env.example` does not ship a `SESSION_COOKIE_SECURE` line. Add it yourself:**

```bash
# Leave UNSET behind nginx+TLS. Set false ONLY if you control the network path
# (SSH tunnel to 127.0.0.1, or a local box).
# SESSION_COOKIE_SECURE=false
```

Get this wrong and the symptom is: **`/login` reports success, and every request redirects back to
`/login`, forever, with nothing in the log and nothing on screen.** If you see that loop, this is
why.

nginx also needs `client_max_body_size 500M` (must match `MAX_UPLOAD_MB`) and must forward
`X-Forwarded-For` / `X-Forwarded-Proto`. The app trusts **exactly one** hop.

### 2.3 Start it

```bash
gunicorn -w 1 --threads 4 -b 127.0.0.1:5050 app:app --timeout 300
```

**`-w 1` is mandatory, not a tuning preference.** `jobs`, `uploads`, `object_manifests` and the
single-active-job lock are module-level dicts in one process. With two workers, an upload handled
by worker A returns 404 when the follow-up run lands on worker B, and status polls 404 while a
paid run completes invisibly.

Do **not** run `python3 app.py` in production — it serves the Werkzeug console when
`FLASK_ENV=development`.

### 2.4 Smoke test — 60 seconds, free

```bash
curl -sk https://<host>/login | head -c 200                              # HTML, 200
curl -sk -o /dev/null -w '%{http_code}\n' https://<host>/api/reports     # 401
curl -sk -o /dev/null -w '%{http_code} %{redirect_url}\n' https://<host>/ # 302 -> /login?next=/
```

If `/api/reports` returns **200, stop** — your report data is public.

---

## 3. The manifest — the highest-leverage 30 seconds in the workflow

The manifest is **your standard item catalog**: the names you bid with, and the words the drawings
use for them. It is optional, reusable on every project forever, and it is what makes the app
speak your vocabulary instead of the drafter's.

### 3.1 Format

**JSON** — a list, or `{"objects": [...]}`:

```json
[
  {"name": "CMU Wall", "unit": "SF", "measure": "area",
   "aliases": ["concrete masonry", "cmu", "block wall"]},
  {"name": "Doors-STL", "unit": "EA", "measure": "count",
   "aliases": ["Doors - Steel", "steel door", "STL door"]},
  {"name": "Bollards", "unit": "EA", "measure": "count",
   "aliases": ["bollard", "pipe bollard", "concrete bollard"]}
]
```

**CSV** — header with at least `name` and `unit`; aliases separated by `;` or `|`:

```
name,unit,aliases,measure
CMU Wall,SF,concrete masonry;cmu,area
Doors-STL,EA,Doors - Steel;steel door,count
Bollards,EA,bollard;pipe bollard,count
```

### 3.2 Fields

| Field | Required | What to put |
|---|---|---|
| `name` | **yes** | the name you want printed in your take-off |
| `unit` | **yes** | `EA` `SF` `LF` `CY` `CF` `GAL` |
| `measure` | no | `count` `area` `length` `volume` — inferred from `unit` if omitted |
| `aliases` | no | **the drawing's words.** This field does the work |
| `assumptions` | no | `height_ft`, `thickness_in` |
| `keywords` | no | extra hints for targeted extraction |

### 3.3 What to add — and what will hurt you

**Aliases are the whole game.** The app measured the doors correctly and still published a blank
under `Doors-STL`, because the drawing says *"Doors - Steel"*. One alias fixes that permanently.
Put in every way a drafter might write the item: abbreviations (`HM`, `STL`, `AL`), the spelled-out
form, and the plural.

**Rules, learned the hard way:**

1. **Put in your WHOLE catalog, not this building's items.** The test is mechanical: *the same file
   must run unchanged on every project.* If you rewrite it per job, you have handed the app the
   answer key and its accuracy numbers stop meaning anything.
2. **Never put quantities in it.** It is not a take-off.
3. **Be careful with one-word aliases.** A bare `"panel"` on *Electrical Panels* caused a
   **tilt-up concrete panel** to be priced as an electrical panel. If an alias is a common noun,
   qualify it (`"electrical panel"`, not `"panel"`).
4. **Do not put a number in `assumptions` you got from a take-off.** If the drawings print 36 ft
   and 48 ft, do not assert 35.

A starter catalog of 91 industry-standard items ships at
`tests/fixtures/generic_catalog_manifest.json` — copy it and replace the names with yours.

---

## 4. Running a take-off

1. **Log in.** If you land back on the login form, re-read §2.2.
2. **Upload a PDF of PLANS — not a completed take-off.** A take-off-shaped filename warns you and
   holds the Analyze button until you tick the confirmation, and the warning is written into the
   run's own log.
   - If the upload returns **400** with *"could not be opened"* or *"password-protected"*, that is
     your file, not the server. Re-export it or save an unprotected copy.
3. **Confirm the page picker lists your sheets by name.**
4. **Attach your manifest** (§3). Optional, and the single highest-value step.
5. **Watch the progress bar.** If polling fails three times you get a banner and polling stops; a
   401 stops immediately. A frozen bar with **no** banner means the run is genuinely slow.
6. **Read the banner first:** *"N% of the expected line items were measured"*, taken verbatim from
   the run's own `coverage.json`. It is a coverage figure — **never quote it as accuracy.**

---

## 5. Reading the report — the six row states

| Badge | Means | Can you type a number in? |
|---|---|---|
| ✓ **Measured** | the app measured it; no human has confirmed it | yes — that confirms it |
| ! **Needs review** | measured **but flagged**. Confirm before you bid it | yes |
| ∅ **Not measured** | **the app had NO way to measure this.** A blank, not a zero | **yes — and you should** |
| – **Not applicable** | the set genuinely contains none of these | rarely |
| ≡ **Standard item** | a convention the app injects (e.g. Mobilization) | yes |
| ✎ **Human input** | you typed it. Labelled as yours, permanently | yes |

Always download **`coverage.json`** and **`summary.txt`** with the CSV. They are the record of what
the run did *not* do, and they are what makes your number defensible to whoever you are bidding
against.

---

## 6. Calibration — turning flags into a finished take-off

This is the workflow the accuracy target actually depends on.

1. **Filter to flagged rows.** The worksheet has a *needs review* toggle.
2. **Click any quantity cell** — including a `∅ Not measured` one — and type your number. It
   publishes as **HUMAN INPUT** and is labelled as yours forever.
3. **Read the review reason before you overwrite anything.** The app tells you *why* it flagged the
   row, and the reason usually tells you exactly what to check:
   - *"NOT reconciled by name"* → the app measured this under a different name. **Add an alias to
     your manifest** and it never recurs.
   - *"no measurement path"* → nothing on these sheets states this quantity.
   - *"NOT_IN_UPLOADED_SET"* → the sheet that would answer it **is not in your PDF.** Upload it.
   - *"this row's NAME is a hypothesis"* → the number is real, the name is a guess.
   - a **derived-quantity** blank → quotes the general note that governs the item and names what it
     could not count. Usually a two-minute manual count.
4. **Confirm the good rows too.** A confirmed row is worth more than an unconfirmed one when you
   are defending the bid.

**Expect roughly half the items to need a touch.** Items that are drawn get measured; items that
are *specified in a note* or drawn on a sheet you did not upload need you.

---

## 6a. How the app works, in one page

Read this once and the review reasons stop being cryptic.

**1 — Route.** Each sheet is classified. A title sheet runs nothing and costs nothing; unknown
types fall back to "measure" so no sheet is silently dropped.

**2 — Measure deterministically (free, no API).** For vector sheets this does the real work, in
order: dimensions → viewports → printed scale → scale solve → walls, rooms, symbols, grid
lattices, schedules, keynotes. **Everything is measured from the PDF's vector geometry at the
drawing's own printed scale.** This is why the large areas land within about 1%, and why no
vision model can match it — every AI provider rasterises a PDF before looking at it.

**3 — Label, never count.** The model is *never* asked "how many". It sees marked-up crops and
answers "which of these candidates is which named thing". A candidate with no text near it is not
even shown to it — asking a model to name a bare shape is where accuracy collapses.

**4 — Arbitrate the name.** One ladder decides what a row is called:

```
the drawing's printed schedule  >  your manifest  >  your past corrections
      >  the built-in library   >  AI-learned names  >  the vision label
```

**5 — Calculate**, applying estimating formulas and waste — except printed schedule quantities,
which pass through verbatim.

**6 — Aggregate, and refuse.** A series of guards each turn a doubtful number into a visible
blank: a volume reading that would publish as a count, a count read off a *detail* sheet, a name
that is only a hypothesis, a count nothing corroborates.

**7 — Reason across sheets.** A question raised on one sheet is answered by evidence on another,
repeating until nothing new resolves. Two possible answers means the app picks **neither** and
tells you both. Anything it still cannot answer becomes an **INPUT GAPS** entry — including a
cited sheet you did not upload, listed with the questions it would have answered.

**8 — Report** with a per-row state and a reason for every blank.

---

## 6b. Repeat runs, and the learning store

### Will the same plans give the same answer twice?

**The deterministic half: yes, exactly.** Vector geometry, printed scales, schedule tables and
keynote text are pure functions of the PDF. Same file in, identical numbers out.

**The vision half: nearly, and it is measured rather than assumed.** Hosted AI APIs are not
bit-reproducible even at temperature zero — the cause is GPU batching inside the provider, not a
setting anyone can switch off. The app's answer to that is to *take decisions away from the model*
rather than to ask it more nicely: names now come from printed schedules and legends wherever one
exists, and a count nothing corroborates is flagged rather than published.

`summary.txt` names the specific rows a repeat run may answer differently. Those are the rows to
confirm first.

### The learning store — on by default

`output/learning.db` accumulates across runs and is loaded once at the start of each:

| What it stores | Effect on the next run |
|---|---|
| **Vocabulary** | a name you corrected is used automatically; the correction never recurs |
| **Corrections** | your edits, captured from the worksheet |
| **Project vocabulary** | a repeat run reuses the object list the first run derived, instead of paying to re-derive it |

It sits **below** the drawing's own printed legend and **above** the built-in guesses: the sheet
outranks a past correction, and a past correction outranks a guess. An anti-amplification guard
stops it compounding its own mistakes.

**This is why calibration pays twice** — once for this bid, and again on every future job.

---

## 7. Getting the most accuracy out of it

| Do | Why |
|---|---|
| **Upload every referenced sheet** | the app tells you which cited sheets are missing; those are usually pure loss |
| **Grow your manifest aliases after each job** | every *"NOT reconciled by name"* is a permanent fix, once |
| **Prefer vector PDFs** | measurement comes from vector geometry. A scan drops to the weakest path |
| **Do not upload completed take-offs** | the app is designed to read plans |
| **Re-check rows the report says may move** | `summary.txt` names the rows a repeat run may answer differently |

---

## 8. Known limits — say these out loud

- **Single operator, single instance.** Do not raise `-w` without moving job state to a shared
  store first.
- **A count that is only stated in prose** (e.g. *"provide bollards at all drive-in door jambs"*)
  comes back as a blank quoting the note. The app refuses to derive a compound rule.
- **Symbols with no text anchor** (e.g. column markers on a grid) are counted but cannot be
  *named* by the app. They publish flagged, with hypotheses for you to confirm.
- **Scanned/raster sheets** fall back to a much weaker path.
- **Accuracy figures are per-project.** Anyone quoting a single percentage without naming the plan
  set is quoting nothing.

---

## 9. Do not

- Do not raise `-w` above 1.
- Do not read a blank as a zero.
- Do not quote a coverage percentage as an accuracy percentage.
- Do not upload a completed take-off as plans.
- Do not run the golden/paid scripts (`scripts/accuracy_gate.sh`,
  `scripts/vision_only_benchmark.py`, `scripts/golden_convergence.py`, `pytest -m golden`) unless
  you intend to spend money.
