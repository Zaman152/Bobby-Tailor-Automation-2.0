# INV-D — Would switching the vision model help, and what would the A/B cost?

Investigator D. Read-only. Zero paid API calls. All behavioural claims below are re-scored
from the two saved paid Crow runs
(`.planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_194607` and `_195704`)
using the FREE `scripts/score_report_dir.py`, plus direct reads of `takeoff.json`.

---

## TL;DR — VERDICT: KEEP CLAUDE. DO NOT A/B NOW. A MIGRATION BUYS ZERO POINTS ON CROW.

**The measured upside of switching vision models on Crow's 10-item golden is 0 items — not
"small", not "uncertain", zero.** I checked every one of the ten items against the two
saved runs and asked, per item, "did a vision label decide this number?" The answer is no
for all ten:

| Golden item | Saved-run result | Who decided it | Would a better VLM change it? |
|---|---|---|---|
| Bollards 28 EA | **56 EA (FAIL)** | geometry count; label came from the *deterministic* naming library — the run note literally says **"vision label unavailable"** | **No.** No model was asked. The 2× is a geometry dedup defect. |
| CMU Wall 2,204 SF | **11,286 SF (FAIL, 412%)** | wall-class area from geometry; vision *did* answer, and fusion **rejected it** | **No.** See `fusion_rejected` below — printed-thickness outranks the vision reading by design. |
| Columns-H-35' 132 EA | **NOT MEASURED** | geometry never isolates the cluster | **No.** Nothing was rendered, nothing was asked. |
| Exposed Structure | **397,600 SF (PASS, 0.5%)** | `plan_schedule_legend` — a *text-centric* read | **No.** Already right; all frontier models score ~0.95 here. Switching can only regress it. |
| Internal Tilt-up | **106,992 SF (PASS, 1.3%)** | naming library "hint bind" (deterministic) | No. |
| Ladder-H-20' 1 EA | **NOT MEASURED** | geometry | No. |
| Lift 1 EA | **0 / 1 (flips)** | manifest bind | No — this is a determinism defect, and §5 of the evidence file says temperature can't fix it on *any* hosted API. |
| Mobilization 1 EA | **PASS** | standard item | No. |
| Sealed Concrete | **397,600 SF (PASS, 0.5%)** | `plan_schedule_legend` — text-centric | No. |
| Stairs 10 EA | **1–2 EA (FAIL)** | geometry | No. |

Re-scored, FREE, just now:

```
run 194607: Overall quantity accuracy: 40%   Counts(EA) n=6 qty_ok=17%   Measured n=4 qty_ok=75%
run 195704: Overall quantity accuracy: 50%   Counts(EA) n=6 qty_ok=33%   Measured n=4 qty_ok=75%
```

Every failure is in the **count** column, and every count failure is a **geometry
detection/dedup** failure, not a labelling failure. The measured (SF/LF) column — the one
vision could plausibly influence — is already at 75%, and its two misses are the same wall-class
binding, which fusion resolves deterministically *against* the vision answer.

**Hard proof that a better label changes nothing on the one item where vision actually
answered** — from `takeoff.json → fusion_rejected`, run 194607:

```json
{"candidate_id": "WALL-TC5", "source": "wall_class_labels",
 "answer": "tilt-up concrete panel",
 "reason": "wall_class_thickness_bind_outranks_label",
 "kept_label": "CMU Wall",
 "detail": "...a printed-thickness match is deterministic evidence and outranks a vision
            reading, so the reading 'tilt-up concrete panel' did not name this class"}
```

The architecture is working exactly as designed. Vision proposed; determinism overruled.
Upgrading the proposer is upgrading a voice that has already been outvoted.

**Spend the week on the deterministic symbol detector (evidence file §10.1 / §11 option 1),
not on a provider migration.**

---

## 1. Complete vision call-site inventory, and which passes are even model-sensitive

The Anthropic SDK appears in **exactly one file**: `src/bobbytailor/vision/claude_analyzer.py`
(`import anthropic` at :7, `client = anthropic.Anthropic(...)` at :33, and only three call
sites — `:373` stream, `:376` create, `:641` the legacy STACK-scraper navigation helper).
There is one public entry point, `analyze_drawing()` at `claude_analyzer.py:222`, and every
consumer injects it as a callable (`ensemble.py` docstring :32, `object_vocabulary.py:129`,
`verify_retry.py:241`, `takeoff_pipeline.py:1956`). That is a genuinely clean seam — see §3.

| Pass | Prompt | Schema | Routed model | Call site | Type | Model-sensitive? |
|---|---|---|---|---|---|---|
| `naming_conventions` | (built in `object_vocabulary`) | `schemas.py:412` | `CLAUDE_MODEL_DENSE` (`sheet_pass_matrix.py:117`) | `object_vocabulary.py:488` | **text-centric** — reads the plan's own notes/abbrevs/schedules | No — ~0.95 for all frontier models |
| `vocabulary` | — | `schemas.py:314` | DENSE (`:107`) | `object_vocabulary.py:155` | **text-centric** | No |
| `legend` | `prompts.py:310` | `schemas.py:237` | DENSE (`:118`) | pipeline legend pass | **text-centric** table structuring | No |
| `schedule` | `prompts.py:256` | `schemas.py:237` | DENSE (`:119`) | pipeline schedule pass | **text-centric** | No |
| `semantic` | `prompts.py:346` | `schemas.py:57` | DENSE (`:103`) | `takeoff_pipeline.py:4264` | **text-anchored by construction** — prompt: *"Use the legend's own wording"*; anchor text is supplied per marker | Marginal — and its answer is outranked by printed thickness |
| `symbol_gallery` | `prompts.py:380` | `schemas.py:194` | routes via the `semantic` row (`claude_analyzer.py:316`) | `takeoff_pipeline.py:4369` | **text-anchored, hard-gated** — *"The drawn shape ALONE is not sufficient"* (`prompts.py:404`) | See §2 — mostly never fires |
| `verify_retry` | `prompts.py:413` | `schemas.py:290` | DENSE (`:120`) | `verify_retry.py:314` | **the one genuinely symbol/spatial call** — one crop, one narrow "ladder or stair?" arbitration | Yes in principle; decides ≤1 golden item, and that item currently dies upstream as NOT MEASURED |
| `measure` (raster) | `prompts.py:42` | `schemas.py:503` — the **only** numeric schema | routed | `takeoff_pipeline.py:4681` | raster **fallback only** (scanned plans) | N/A on Crow/Bob's — both are vector |
| `count` (tiled) | `prompts.py:204` | — | routed | `takeoff_pipeline.py:5782` | targeted tile counting for manifest-missing items | Counting — evidence file §3 says *no* vendor is usable here |
| `classify` | — | — | `CLAUDE_MODEL_CLASSIFY` (`:92`) | **no call site** | dead routing row — classification is deterministic keyword matching (`sheet_pass_matrix.py:277`) | N/A |

**Score-keeping:** 4 of the 8 live passes are pure text-centric OCR/QA — the regime where the
evidence file records ~0.95 for every frontier model and a switch is statistical noise. 2 are
text-anchored by prompt contract and by candidate-ID enum. 1 is symbol-shaped
(`verify_retry`) and answers a binary question about a zoomed crop. 1 is a raster fallback
that never runs on our two target projects.

**There is no pass in this engine where Gemini's benchmark edge (0.51 vs 0.42 on floor-plan
object counting) can express itself, because no pass asks a model to count or to localise.**
The schemas forbid it: `schemas.py:19-22` — zero numeric properties on every vector-path
schema, enforced by a recursive test.

---

## 2. The 21 symbol groups nobody is asking any model about

This is the finding that ends the debate. From `takeoff.json → unnamed_geometry`, both runs:

```
run 194607 (34 candidates)          run 195704 (35 candidates)
 11  symbol_group  label_is_drafting_noise      12  symbol_group  label_is_drafting_noise
 10  symbol_group  no_name_source               10  symbol_group  no_name_source
  7  wall_class    wall_class_unlabeled          7  wall_class    wall_class_unlabeled
  6  room          (unlabeled / token-run / …)   6  room          (…)
```

Example: `SYM-6`, 36 EA, reason `no_name_source`, detail: *"36 repeated marks were measured,
but no vision label, no naming-library bind, no deterministic geometry name and no text anchor
identifies them; the anchor pass recorded no plan text within reach."*

Those 21 symbol groups (190 EA of real, measured objects) were **never sent to any model**.
`takeoff_pipeline.py:4322-4344` excludes any candidate with a recorded text-anchor absence
from the request, and `:4395` skips the pass entirely when the sheet yields no legend labels:

```python
if cid in anchor_absences:
    unanchored.append(cid)
    continue
...
"run_sheet: %r — %d symbol group(s) carry no text anchor and are not presented to the
 model; they stay flagged unlabeled"
```

That gate is Phase 24/28 doing precisely what the evidence file §3 prescribes: never ask a
model to name a bare shape (the 0.03–0.39 regime). **Swapping the model behind a gate that
never opens changes nothing.** And opening the gate so Gemini can guess would be a direct
regression of the "flag, don't guess" work on the current branch — you would be trading a
truthful blank for a confident wrong name in front of a bidder.

Of the 51 published rows, exactly **8 carry `source == vision`**, and not one of them is a
golden item: Building Perimeter, Electrical Panels, Fire riser, Mobilization, and the four
OVERALL elevation areas (all NEEDS REVIEW except Electrical Panels).

---

## 3. How hard is a provider swap? (Cheaper than you'd think — and still not worth doing)

**The seam is already almost there.** Cost is small; that is not the reason to say no.

Anthropic-specific surface, all in `claude_analyzer.py`:

| Thing | Line | Portable? |
|---|---|---|
| `import anthropic` / module-level `client` | 7, 33 | trivially |
| `PRICING` table keyed to Claude slugs | 37–47 | needs a per-provider table |
| `system=[{... "cache_control": {"type":"ephemeral"}}]` | 338–344 | **No direct equivalent.** Gemini uses explicit/implicit context caching with minimum-token thresholds; OpenAI caches prefixes automatically. Cost-only, not correctness — and at 18,934 input tokens for a whole Crow run, irrelevant. |
| `output_config={"format":{"type":"json_schema","schema":…}}` | 363–365 | see contract note below |
| `_response_text()` block scanning (thinking blocks etc.) | 93–121 | per-provider response shape |
| `client.messages.stream(...).get_final_message()` for >20k-token passes | 372–376 | per-provider |
| base64 image blocks + 5 MB/image guard | 141–143, 210–219 | per-provider |
| `make_navigation_decision` (legacy STACK scraper) | 621–656 | dead for the plans-only path |

Test coupling is **4 assertions in one file** (`tests/test_vision_schemas.py:909-934`, which
pins `output_config` and `cache_control`), plus 16 files referencing model slugs — almost all
of those are `MODEL_ROUTING` table tests that would just gain a second table.

**Structured-output contract — does the guarantee survive?**

Our contract (`schemas.py:1-24`): `additionalProperties: false` at every object level, every
property listed in `required`, candidate IDs as `enum`, zero numeric fields, dependency-ordered
topology (`semantic_labeling_schema`, `schemas.py:57`).

- **OpenAI strict Structured Outputs: exact match.** Strict mode *requires* `additionalProperties:
  false` and every property in `required` — the same two rules we already satisfy. `enum`,
  nested objects and arrays are supported. Our schemas would port essentially unchanged.
- **Gemini `responseSchema`: partial.** It accepts an OpenAPI-3.0 subset — `type`, `enum`,
  `required`, `properties`, `items`, `propertyOrdering` — but **not `additionalProperties`.**
  Generation is still schema-constrained, so extra keys are unlikely in practice; but our
  *declared* "unexpressible rather than merely flagged" guarantee (`schemas.py:14-16`) becomes a
  vendor-behaviour assumption instead of a stated contract. That is a real, if narrow, weakening.
- **The zero-numeric-field guarantee survives everywhere**, because it is enforced by *our*
  recursive schema test, not by the provider.
- Enum sizes are fine on both (symbol IDs 20–60, legend labels a few dozen).
- The DPI worry from evidence file §6 (Gemini caps at 3072 px) **does not bind us**:
  `config.py:48` sets `RENDER_TARGET_PX = 1568` and `overlay.py:246` defaults `target_px=1568`.
  We are already well under every provider's cap. Be honest about this — it is not an argument
  against Gemini.

**Estimated seam cost: 1.5–2.5 days** for a `VisionProvider` protocol, two adapters, a Gemini
schema translator (strip `additionalProperties`, add `propertyOrdering`), a per-provider
pricing table, and fixing 4 test assertions. Cheap. Just pointed at nothing.

---

## 4. The cheapest honest A/B, if you want it anyway

Do **not** run a whole-pipeline A/B — an end-to-end score can't attribute a delta to the model,
because the deterministic layer overrides most labels anyway (§1). Compare **labels to labels**.

**Phase 0 — capture the exact requests. FREE, zero API.**
`scripts/author_replay_fixtures.py` already drives the real deterministic pipeline over the
real Crow PDF with a *responder* analyzer that answers each structured request from the saved
paid runs' own observed names — no credential is read, no call is made. Extend that responder
to also dump each request's `(pass_type, model, system prompt, user message, JSON schema,
images as PNG)` to `.planning/vision-ab/requests/`. Reusing the existing responder is essential:
`author_replay_fixtures.py` documents that the naming pass's *answer* becomes the *next*
request's enum, so a stubbed answer would produce a request set the real run never issues.
**~3 hours.**

**Phase 1 — replay. PAID, small.**
A standalone script (never in the pipeline) that POSTs each captured payload to
(a) the routed Claude model — control, N=3; (b) Gemini 3 Pro — N=3; (c) GPT-5.2 — N=3, and
writes raw JSON answers. Needs the Gemini schema translator from §3.
Measured token volume for a whole Crow run is **18,934 in / 14,866 out** (identical in both
saved runs — prompt sizes are deterministic). At any frontier price in the $2–$5 in / $12–$25
out per-M range that is **$0.20–$0.50 per full-project replay per model**. Actual Anthropic
cost was $0.768 (run 1, uncached) and $0.389 (run 2, cached).
→ 3 repeats × 2 challengers × 2 projects (Crow + Bob's) ≈ **$3–$6; budget $15 with headroom.**
**~1 day** including the translator.

**Phase 2 — score. FREE.** Three metrics, none of them a takeoff score:
1. **Self-agreement** — across a model's own 3 samples, per `(pass, candidate_id)`. This is the
   run-to-run flipping metric that actually hurts us (§5 of the evidence file).
2. **Printed-text agreement** — does the chosen label match the plan's own text, using the
   `evidence_texts` already recorded per candidate in `unnamed_geometry`? Validate against the
   drawing, never against the golden count (the §10 coincidence trap).
3. **Refusal discipline** — how often each model correctly answers `"unknown"`
   (`schemas.py:33`) on a genuinely unanchored candidate. A model that names more shapes is
   *worse*, not better.

**Total: ~$6 in credits and ~1.5 days of engineering — to measure a variable that the saved
evidence already shows moves zero golden items.** Run it only if the trigger in §5 fires.

---

## 5. Recommendation

**KEEP CLAUDE. Do not build the seam, do not run the A/B, this month.**

Grounded in the evidence file §8 ("keep Claude for the reading/labeling passes… A vendor A/B
is worth one cheap experiment but is not the lever — the architecture is") and, more
importantly, in what the two paid runs actually did:

- The two items vision *is* good at (`plan_schedule_legend` text reads) are already at **0.5%
  error**. There is no headroom there; a switch is pure downside risk.
- The one item vision answered on (WALL-TC5) was **rejected by design** in favour of printed
  thickness.
- The 21 unnamed symbol groups are **never sent to a model**, by deliberate design.
- Every remaining failure — Bollards 56-vs-28, Columns/Ladder NOT MEASURED, Stairs 1-vs-10 —
  is a **vector-geometry detection/dedup** problem in the deterministic half.

**Realistic upside on Crow's 10-item golden from a perfect vision model: 0 of 10 items.**
Not "1–2 maybe". Zero — I checked each row's `source`, `review_notes` and `fusion_rejected`
entry individually.

**The trigger that would make this worth revisiting** (write it down, don't guess later):
after the deterministic 2-D symbol detector lands and Columns/Bollards/Stairs are being
*detected*, re-score. If the residual failures then read `vision label X, expected Y` in
`review_notes` — i.e. geometry is finding the right objects and the *label* is wrong — the
A/B in §4 becomes the right $6 to spend. Until then it is a week spent moving a variable that
is pinned at zero.

**What to do with that week instead:** evidence file §11 option 1 — coordinate-based 2-D
lattice detection over our own already-extracted vector primitives, validated by position and
shape, never by the golden count. That is the only route in the record that turns
"NOT MEASURED × 3" into numbers.

---

### Appendix — commands used (all FREE, all read-only)

```
python3 scripts/score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
        --dir .planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_194607
python3 scripts/score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
        --dir .planning/paid-run-evidence/VisionOnly_P24DET_Crow_20260806_195704
# plus direct json/csv reads of takeoff.json (api_usage, sheet_log, unnamed_geometry,
# fusion_rejected) and takeoff_summary.csv in both evidence dirs.
```

No `pytest -m golden`, no `accuracy_gate.sh`, no `vision_only_benchmark.py`,
no `golden_convergence.py`, no `.env` read, no network call. $0.00 spent.
