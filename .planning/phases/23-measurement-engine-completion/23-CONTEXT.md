# Phase 23: Measurement Engine Completion — Context

**Gathered:** 2026-08-03
**Status:** Ready for planning
**Source:** 8-investigator parallel study + synthesis (`23-RESEARCH.md`, `INV-00`…`INV-08`)

<domain>
## Phase Boundary

Make every quantity the drawing set actually contains measurable, on ANY sheet composition. The
engine is **not missing** — `23-RESEARCH.md` §1 establishes it is *unreachable* (18/40 Moxy pages
never run geometry), *unbound* (one frozenset drops every `wall_area`; basis `linear` has no
consumer at all), and *mis-scaled* (`_paper_inches` reads a leading drawing number as paper inches,
making every Bob's page 16–32× wrong linearly, 256–1024× by area).

IN scope: the four waves of `23-RESEARCH.md` §3 — foundations (coverage ledger, skip veto, scale +
rotation correctness), measurement primitives (region geometry, open-run chainer), binders
(primitive → line item), record & harness.

OUT of scope: run-to-run determinism and text-anchored Set-of-Mark (Phase 24), symbol/lattice
detection for columns & bollards (Phase 25), learning-loop capture (Phase 26), the RESTRUCTURE-SPEC
§7 hardening backlog (Phase 27). Do not start those here.
</domain>

<decisions>
## Locked decisions

### Evidence hierarchy (non-negotiable)
- `23-RESEARCH.md` + `INV-00`…`INV-08` supersede `docs/PIPELINE-GROUND-TRUTH.md` wherever they
  conflict. Three of the ground-truth doc's headline claims were **disproved** by probe:
  1. §14.2 "the clip leaks on ID-412/416" — FALSE. The fill matches the drawing's own printed
     dimensions to 0.7%; the ~2× is a wrong `unit_count` in `human_inputs/moxy_knoxville.json`.
  2. §9 "Bob's Gas Piping is civil linework" — FALSE. There is no civil sheet; it is an annotated
     CAD linetype on the A3.0 **roof plan**, already a plan sheet type.
  3. §13.3 / `:352` "BLOCKER A — the unit multiplier is not in the input" — FALSE. A blind census of
     the ID-001/ID-002 unit key plans yields 217 tags / 217 unique numbers → QQ A 90, KING A 26,
     K SUITE B 2, BUNK B 1 = **4/4 exact** vs golden.
  Correcting those three passages in `docs/PIPELINE-GROUND-TRUTH.md`, with citations, is a task in
  this phase. Also correct §14's implication that its 7.0% figure came from a run — it came from a
  probe calling the engine directly; a real run cannot reach those sheets.

### Wave order (locked — `23-RESEARCH.md` §3)
Wave A foundations → Wave B primitives → Wave C binders → Wave D record & harness.
**P1 (coverage ledger + skip veto) lands FIRST** — every other gap's honest-failure path terminates
in it, and without it we cannot tell "not measured" from "measured as zero".

### Build shared primitives ONCE (SP-1…SP-10)
Four INV docs independently proposed adding another frozenset beside `fusion.py:1601`; three
proposed a new open-run module; three proposed parameterising `MAX_REGION_SF`; three proposed the
same rotation helper; three reported `scripts/room_probe.py:82` broken. The planner MUST factor
these into the shared primitives of §2 rather than let each binder grow its own copy.

### Two independent causes of the silent sheet drop — fix BOTH
1. `sheet_pass_matrix.py:153` still matches bare `COVER` inside "LIGHT SWITCH COVER PLATE" (the §12
   whole-word fix did not cover this case).
2. `pdf_analyzer.get_title_block_text:178` takes `x > 55%` of page width, which on a 3024 pt sheet
   swallows the keynote column so 84 words of prose outvote the title (INV-00 §1c).
**Neither may be fixed by retuning a constant.** Sweeping the x-fraction to 0.88 fixes Moxy (18→2
skips) and BREAKS Chelsea (2→10, floor_plan 9→1). Identify the title block by STRUCTURE — field
labels (`SHEET NO.`, `SHEET TITLE`, `JOB NO.`), low prose density — and gate every change on the
four-plan-set no-regression check below.

### Mandatory four-set regression gate (free, no API)
Every classification/scale change is accepted only if, across Moxy/Crow/Bob's/Chelsea simultaneously:
Moxy skipped → ≈2, and **Crow (0), Bob's (1), Chelsea (2) do NOT increase**. This must live in the
test suite. Improving one fixture while regressing another is rejected — the documented
fixture-blindness trap.

### Numbers are allowed to get WORSE, deliberately
Rails go from "5.8 LF, confidently wrong" (a pipe DIAMETER in inches pushed through a unit-blind LF
formula, `calculator.py:1263-1266`) to "~53 LF per ramp, flagged, count unknown". Moxy will emit many
more `NEEDS REVIEW` rows. An honest flagged gap beats a confident wrong number — that is the point of
the phase. Do NOT protect a headline score by keeping a known-wrong quantity.

### Never tune to golden
Validate detection by POSITION/SHAPE and by each drawing's OWN printed dimensions (the technique
that falsified the clip theory). "Closer to golden" is not an acceptance test — §14.3's peeking trap
already cost this project hours, and correcting the four bad `unit_count`s will legitimately move the
Gyp Ceiling total AWAY from golden.

### Resolutions to `23-RESEARCH.md` §7 open questions (decided by the orchestrator)
1. **Shared-partition accounting** — determine it from DATA, not a guess: read the Moxy take-off's
   own legend/labels to establish whether Gyp Wall bills board faces (both sides) or wall length
   once. If the take-off is genuinely ambiguous, emit the quantity with an explicit
   `partition_convention` provenance note and flag it. Never try ratios until a total matches.
2. **Rail instance multiplier** — ship per-instance measurement, flagged, with the multiplier
   unknown. Do NOT hold the item back: a withheld item is a silent zero, which this phase exists to
   abolish.
3. **The four Moxy manifest `unit_count`s** — the in-plan unit-tag census (SP-10) **supersedes** the
   manifest once it reproduces 4/4, with the manifest retained as a cross-check that FLAGS
   disagreement rather than being overwritten silently. This is the autonomy direction: a number the
   drawing contains must never require a human. Correcting `human_inputs/moxy_knoxville.json` itself
   is out of scope for this phase — flag the disagreement, record `unit_count_source`.
4. **Bob's undrawn facades** — follow INV-03: `perimeter × datum height` stays a CROSS-CHECK that
   flags disagreement, never a second published quantity. Only 3 of 4 facades are drawn, so a
   silhouette sum cannot reach a whole-building golden; publishing a reconciled-looking number would
   be a fabrication.

### Claude's Discretion
- Exact module names/signatures for the shared primitives.
- How many plans per wave (2–4 tasks each per the research).
- Whether the ground-truth-doc corrections ride in Wave A or Wave D.
</decisions>

<canonical_refs>
## Canonical References

**Read before planning:**
- `.planning/phases/23-measurement-engine-completion/23-RESEARCH.md` — THE synthesis: §2 shared
  primitives, §3 plan sequence, §5 offline verification, Validation Architecture, §6 risks
- `INV-00-live-run-evidence.md` — free scoring of saved runs; the title-block root cause; the
  end-to-end proof (Gyp Ceiling 0 → 49,046 SF); my RETRACTED clip diagnosis
- `INV-01`…`INV-08` — per-gap implementation maps with file:line and probe output
- `docs/PIPELINE-GROUND-TRUTH.md` — historical log; **superseded where it conflicts** (see above)
- `.planning/research/VISION-MODEL-EVIDENCE-2026.md` — why quantities stay deterministic

**Free probes (zero API) — the iteration harness:**
`scripts/geom_probe.py`, `fusion_probe.py`, `scale_probe.py`, `room_probe.py` (fix `:82`),
`score_report_dir.py`, plus the new `coverage_probe.py`.
</canonical_refs>

<specifics>
## Specific Ideas

- Baseline to beat, measured free on saved artifacts: Moxy 8% overall / measured items **0%**;
  Crow 40% overall / measured 75% / counts 17%.
- `scripts/score_report_dir.py` works post-restructure and needs no changes.
- Paid validation runs are AUTHORIZED by the user and reserved for AFTER the code lands: Moxy
  (40pp, ~$1.90) and Bob's (7pp) exercise what changes; Crow (4pp, ~$0.35) is the cheap regression.
- Offline suite baseline: `python3 -m pytest -q` → 1132 passed, 2 deselected (~8 min).
</specifics>

<deferred>
## Deferred

Phase 24 (determinism + text-anchored labelling), Phase 25 (symbol detection), Phase 26 (learning
loop + autonomy metric), Phase 27 (hardening). The `one-area-one-item arbitration` primitive (SP-9)
is built here because five gaps need it, but the Crow footprint-bound-to-six-items symptom it fixes
is scored in Phase 24.
</deferred>

---

*Phase: 23-measurement-engine-completion*
*Context gathered: 2026-08-03 from an 8-investigator study*
