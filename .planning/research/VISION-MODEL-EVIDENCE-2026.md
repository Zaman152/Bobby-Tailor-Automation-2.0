# Vision-model & architecture evidence for plan takeoff (deep research, 2026-08-03)

Deep-research run: 5 angles → 23 sources → 110 claims → 25 adversarially verified (3 independent
refuters each) → **18 confirmed, 3 refuted, 4 unverified**. The synthesis agent died at a session
limit; this document is the hand-written synthesis over the surviving verified claims.

Every claim below carries its primary source. Claims that FAILED verification are listed in §9 so
nobody resurrects them.

---

## 1. TL;DR — the four decisions this settles

1. **Our architecture is right, and it is what the literature independently recommends.** Quantity
   takeoff is the single weakest capability of every frontier VLM tested (best score 41.7/100, several
   near 0). Researchers explicitly recommend hybrid designs: dedicated detectors + geometric/
   connected-component algorithms + structured outputs, with the VLM confined to semantics. That is
   exactly the deterministic-geometry + vision-as-labeler design already built.
2. **Claude is NOT the best vision model for drawings — but the fix is not simply "switch to Gemini".**
   Claude ranks mid-pack on three independent drawing benchmarks. However the gap between the best and
   worst frontier model on symbol counting (0.42 → 0.51) is small compared to the gap to usable
   (needs ~1.0), and the weakness is *shared across all model families*. Switching vendors alone
   cannot close it.
3. **The real, actionable finding — text-anchored beats symbol-shaped.** Objects anchored by text
   labels are recognized at 0.65–0.92 accuracy; objects conveyed only by graphical symbol convention
   at 0.03–0.39. This is the *direct root cause* of our run-to-run flipping (CMU wall class, columns,
   bollards are all symbol-conveyed) and it prescribes the fix: never ask the model to recognize a
   shape — always give it the nearby text (keynote, tag, schedule row, abbreviation) and ask it to
   pick a candidate ID.
4. **No API parses vector PDF. Anthropic, Google, and OpenAI all rasterize.** Our deterministic
   vector extraction is a genuine structural advantage no VLM provider offers — it should be
   deepened, not replaced.

---

## 2. Model head-to-head on real drawings (Claude is mid-pack)

Three independent benchmarks, all confirmed 3-0:

| Benchmark | What it tests | Ranking |
|---|---|---|
| **DrawingVQA** — real "Issued for Construction" structural drawings | multi-depth visual-textual reasoning incl. a QTO category | Gemini-2.5-Pro **71.7** > Gemini-2.5-Flash 66.3 > o3 58.7 > **Claude-4.5-Sonnet 57.6** > Qwen3-VL-8B 53.3 > GPT-4o 48.9 |
| **AECV-Bench** — 120 real floor plans, object counting | doors/windows/bedrooms/toilets exact match | Gemini 3 Pro **0.51** (16.0% MAPE) > GPT-5.2 0.49 (19.4%) > **Claude Opus 4.5 0.42** (24.9%) |
| **MechVQA** — 3.3k drawings, 21K QA pairs | 10 fine-grained drawing tasks | GLM-4.6V **78.91** > Gemini-3-Pro 77.28 > Qwen3-VL-Plus 76.33 > GPT-5 75.44 > **Claude-Sonnet-4.5 71.20** |

Sources: `arxiv.org/html/2607.15418v1`, `arxiv.org/pdf/2601.04819` + `github.com/AECFoundry/AECV-Bench`
(raw CSVs re-aggregated by the extractor: Gemini 3 Pro 52.2%, GPT-5.2 48.7%, Claude Opus 4.6 44.0%,
Claude Opus 4.5 42.3%, Claude Sonnet 4.6 40.2%), `arxiv.org/html/2605.30794v2`.

**Caveats that matter:** no Claude *Opus* was in DrawingVQA or MechVQA; the AECV-Bench numbers do
include Opus 4.5/4.6. A separate ASCE study found the weakness "consistent across different VLM
architectures and frameworks" — i.e. vendor-independent.

---

## 3. Why our specific bugs happen (the highest-value finding)

**Confirmed 3-0:** classes anchored by *text* are counted far more reliably than classes conveyed by
*graphical symbol*:

| Class type | Example | Accuracy range across frontier models |
|---|---|---|
| Text-anchored | bedrooms | **0.65 – 0.91** |
| Text-anchored | toilets | 0.46 – 0.82 |
| Symbol-conveyed | doors | 0.09 – 0.39 |
| Symbol-conveyed | windows | 0.03 – 0.34 |

> "doors and windows are often conveyed primarily through graphical symbols and line-art conventions
> (swings, breaks in walls, façade notations) that vary across CAD standards and styles, making them
> harder to recognize and count consistently from rasterized drawings." — arxiv.org/pdf/2601.04819

**Direct mapping to our open defects** (see `docs/PIPELINE-GROUND-TRUTH.md` §10, §11):
- CMU-vs-tilt-up wall-class flip (8 ↔ 11,294 SF) — thickness classes are symbol/geometry-conveyed →
  predicted to be unstable. **Fix: bind by thickness + location deterministically, or by the nearest
  wall-type TAG text, never by asking vision "which class is CMU".**
- Columns / bollards label flipping — pure symbol shapes → predicted unstable. **Fix: require a text
  anchor (grid bubble text, keynote leader, schedule row) or flag; never name a bare cluster.**

Second mechanism, confirmed 3-0: counting failures are **visual-grounding** failures, not reasoning
failures — the model states the right strategy then "derails" while tracing, hallucinating grid
intersections. So better prompting/reasoning models will not fix counting; only removing counting
from the model's job does.

Third, confirmed 3-0: **Item Localization is the weakest subtask for every general VLM** — Claude
Sonnet 4.5 56.12, GPT-5 62.59, best general (Gemini-3-Pro) 64.03, vs 82.01 for a domain-fine-tuned
4B model. Never ask a general VLM where something is.

---

## 4. Specialized models — a real option, and they consume vector geometry

| Model | Backbone / input | Result | Relevance |
|---|---|---|---|
| **CADSpotting** | **vector CAD primitives** densely sampled as points (x,y,z=0), unified 3D point-cloud model; deliberately ignores primitive type/layer | panoptic symbol spotting | **Directly compatible with our extracted vector geometry** — this is the shape of a real column/bollard detector |
| **DPSS** | dual branch: raster (HRNetV2) + vector primitives (PointTransformerV2), adaptive fusion | panoptic symbol spotting | Independently validates raster+vector fusion over either alone |
| **MechVL-4B-RL** | Qwen3-VL-4B + SFT + DAPO RL | **84.85, beats Gemini-3-Pro by +7.57** | A 4B *locally runnable* model beating every frontier model on drawings |
| **FloorplanVLM** | Qwen2.5-VL-3B, 2.3M floorplans | 92.52% external-wall IoU, 96.10% output validity | Raster→vector room/wall extraction at 3B params (residential, not construction docs) |

**Transferable technique (confirmed 3-0):** FloorplanVLM enforces topological consistency *by output
schema* — define the wall skeleton first, then express rooms as references to those walls, so gaps
are structurally impossible. Our fusion schemas should adopt the same dependency-ordered pattern.

---

## 5. Determinism: temperature 0 is not enough

**Confirmed:** "LLM APIs are still not deterministic in practice." Root cause is batch-size-dependent
GPU reduction kernels (matmul, RMSNorm, attention) — i.e. *server-side batching*, not sampling
randomness. Source: `thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference`.

Consequence for us: **run-to-run flipping cannot be fixed by setting temperature=0 on a hosted API.**
The remedies are structural, in rough order of value for this codebase:
1. Remove the decision from the model (deterministic binding by geometry/thickness/position).
2. Text-anchor the decision (§3) so the model is reading, not recognizing.
3. Constrain the output space (candidate-ID enums, zero numeric fields — already done).
4. Ensemble/self-consistency voting (already built in `vision/ensemble.py` — wire it onto the
   remaining flipping passes).
5. Schema-enforced topological consistency (§4).

---

## 6. Native vector PDF: nobody does it — this is our moat

All three confirmed, from vendor primary docs:

| Provider | PDF handling |
|---|---|
| **Anthropic** | "converts each page of the document into an image" + extracts text layer; vector entities never exposed (~1,500–3,000 tokens/page, 100-page/32MB caps) |
| **Google Gemini** | rasterizes pages, max 3072×3072 px (min upscale 768×768) — effective DPI limited on large-format sheets |
| **OpenAI** | dual representation: embedded text layer + rasterized page images |

So no provider gives structured lines/polylines/hatches. Our PyMuPDF vector extraction + printed-scale
reading is a capability none of them have — and the large-format DPI cap is an argument *against*
leaning harder on whole-sheet vision.

---

## 7. Commercial reality check (calibrates "100% accuracy")

- **Togal.AI** — OCR + ML over plans; vendor-reported **97% at detecting spaces (rooms)**; produces
  exactly our target quantity set (footprint GSF, gross area per room incl. walls, net area excl.
  walls, wall linear footage). Third-party comparison blogs report 94–97% on commodity items but
  **87–91% on complex MEP**.
- **Beam AI** — the advertised "99% material accuracy / ±1%" is **human-in-the-loop QA service
  accuracy** (AI + human QA team verify before delivery), *not* autonomous model accuracy.
- **STACK** — symbol counting via one-shot **template matching** (Auto-Count), not a VLM.
- **Kreo** — CNN + transformer architectures described as industry standard for floor-plan recognition.

**Implication for the mission:** no shipping product claims autonomous 100%. The credible target is
deterministic-exact on everything the drawing states (schedules, dimensioned geometry, printed scales)
plus a learning loop for estimator-specific naming — which is precisely the current strategy. Treat
"100%" as *100% of what the document contains, with everything else explicitly flagged*, not as a
promise that no human ever looks.

---

## 8. Recommendation matrix per sub-task

| Sub-task | Today | Verdict | Action |
|---|---|---|---|
| (a) Label geometry candidates via Set-of-Mark + candidate-ID enums | Opus 4.8 | **Keep model, change the prompt contract** | Text-anchor every mark (§3): supply the nearest keynote/tag/schedule text with each candidate; forbid pure-shape naming → flag instead |
| (b) Read naming conventions / keynotes / abbreviations | Opus 4.8 (dense) | **Keep — this is Claude's strength** | Text-centric QA hits 0.95 across models; already routed to the dense model. No change |
| (c) Sheet / viewport discipline classification | Sonnet | **Keep** | Text-anchored (titles, viewport labels) → reliable class |
| (d) Room/region identification where vector is unclosed | raster flood-fill (`room_fill.py`) + vision | **Keep deterministic; do NOT hand to a VLM** | Localization is the weakest VLM subtask (§3). Consider FloorplanVLM-class local model only if flood-fill plateaus |
| (e) Schedule-table extraction in varied formats | Opus/Sonnet | **Keep, add per-format parsers** | Table reading is text-centric (model strength); the failure mode is format coverage, not model capability |
| **(f) Symbol detection / 2-D cluster isolation** (columns, bollards) | unsolved | **Augment with a specialized detector** | CADSpotting-style: point-sample our *already-extracted* vector primitives → detector. Never a general VLM |
| **Determinism across all passes** | partial ensemble | **Structural fixes, not temperature** | §5 ladder: deterministic-first → text-anchor → enum → ensemble → schema topology |

**Bottom line on the model question:** keep Claude for the reading/labeling passes (its strength is
text-centric extraction, where all models score ~0.95 and the differences are noise). Do **not** adopt
a VLM for counting, localization, or measurement under any vendor. Where we currently *want* vision to
detect symbols, build the CADSpotting-style detector over our vector data instead. A vendor A/B
(Gemini 3 Pro on the labeling passes) is worth one cheap experiment but is not the lever — the
architecture is.

---

## 9. Claims that FAILED verification — do not cite these

- ~~"CADSpotting sets SOTA on FloorPlanCAD, PQ 87.4 vs SymPoint 83.3…"~~ — refuted 1-2 (specific
  numbers not supported by the abstract).
- ~~"ArchPlanVQA: general VLMs achieve only 33.03–37.88% semantic understanding"~~ — refuted 1-2.
- ~~"Drawing-grounded doc QA: Gemini 3 0.854 > GPT-5.2 0.792 > Claude Opus 4.5 0.719"~~ — refuted 1-2.
- **Unverified (3 verifier agents errored at the session limit — treat as unconfirmed):** DPSS PQ
  numbers; "all 2025-era VLLMs failed outright at bounding-box localization"; "zero-shot VLLM counting
  ≈ trained YOLO"; the Claude-3.5-era head-to-head.

---

## 10. What this changes in the roadmap

1. **New capability — deterministic symbol detector over vector primitives** (CADSpotting pattern).
   This is the only credible path to real columns/bollards and it validates against *position/shape*,
   not against the golden count (avoiding the §10 coincidence trap).
2. **Prompt-contract change — text-anchored Set-of-Mark.** Cheap, high-value, directly targets the
   documented flipping mechanism.
3. **Determinism ladder** applied pass-by-pass to every binding that currently flips.
4. **Schema topology** (walls-first, rooms-as-references) for the fusion output.
5. **Keep Claude**; run one cheap Gemini-3-Pro A/B on labeling passes as a sanity check, not as a
   migration.

Sources are listed inline; full verified-claim payload with quotes:
`/private/tmp/claude-501/.../tasks/wgc3781mx.output` (session-local, copy anything needed before it ages out).

---

## 11. ⚠ This research contradicts a documented scope decision — needs a user call

`.planning/REQUIREMENTS.md` "Out of Scope" contains:

| Feature | Reason |
|---|---|
| Custom symbol training / ML pipeline | **Zero-shot Claude Vision is the differentiator** |

The evidence says the opposite: zero-shot VLM symbol recognition is *exactly* the capability that
does not work (doors 0.09–0.39, windows 0.03–0.34, localization worst-of-all-subtasks), and it is the
documented cause of our columns/bollards/CMU failures. Keeping this exclusion means accepting that
count items detected purely by symbol shape will never be reliable.

**Three options, cheapest first — recommendation is (1), escalating only on evidence:**

1. **Deterministic 2-D lattice detection over our own vector primitives (NO ML, honors the exclusion).**
   CADSpotting's transferable insight is its *representation* — densely sample points along vector
   primitives using coordinates only, ignoring primitive type and layer — not its neural net. Our
   current shape-signature clusterer never isolates the real 132 columns at all (ground truth §10/§11);
   a coordinate-based 2-D lattice search over sampled primitives is a plain geometry algorithm.
   Validate against **position/shape**, never against the golden count (the §10 coincidence trap).
2. **Text-anchored labeling for everything that has a tag** (§3) — no new model, immediate value,
   should land regardless of which option is chosen.
3. **A small local specialized detector** (CADSpotting/DPSS/MechVL-4B class, 3–4B params, runs
   locally) — only if (1) plateaus. This *would* cross the out-of-scope line and needs explicit
   user approval, plus training data we do not currently have.

Nothing in this program has been planned on the assumption that (3) is approved.
