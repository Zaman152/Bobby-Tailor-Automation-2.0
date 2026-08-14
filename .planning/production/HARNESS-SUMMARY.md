# HARNESS — what the detector finds, what it refuses to find, and why

**Days 4-5 · 2026-08-14 · Cost: $0.00** (every number below is offline, zero API)

Scope: the candidate-generation harness INV-B and INV-E pointed at — a grid-lattice
column detector, the keynote/Ladder route, and honest flagging for what is not in
the uploaded file.

---

## 1. Headline

| Item | Golden | What the engine now publishes | Status |
|------|--------|-------------------------------|--------|
| **Columns-H-35'** | 132 EA | **120 EA measured**, with 120 cell ids, 100% grid occupancy, and three flagged completion hypotheses (132 / 160 / 176) of which **none is published as a number** | MEASURED + FLAGGED |
| **Ladder-H-20'** | 1 EA | **1 placed callout** of keynote 1, "ACCESS LADDER TO CONCRETE ROOF OF ELECTRICAL ROOM" | MEASURED |
| **Bollards** | 28 EA | the false **56** is gone — it was 56 column markers, not bollards | DEFECT REMOVED |
| **Stairs** | 10 EA | `not_in_uploaded_set`, naming A-111 / A-112 / A-113 | FLAGGED, correctly |

Ceiling on Crow **with the file the user actually uploads**: 9 of 10 items. Say so
to the user now rather than after another week of detector work.

---

## 2. The detector, per plan set

`src/bobbytailor/deterministic/grid_lattice.py` (~470 LOC incl. docs). Additive:
`symbols.py` is untouched.

Recipe, unchanged from INV-B: closed-rect census → grid axes from printed bubble
text → 2-D lattice requiring `n >= 12`, `>= 2` distinct X **and** `>= 2` distinct
Y, occupancy `>= 0.9`, no duplicate cell.

### Four-plan-set result — 83 pages, 11 drawing scales, 913 trials

| Set | Pages | Fires | False positives |
|-----|-------|-------|-----------------|
| **Crow** | 4 | **1** (page 0, n=120, 20×6, occupancy 1.000, marker 1.44×1.56 pt = 9.6"×10.4") | 0 |
| Bob's | 7 | 0 | 0 |
| Chelsea | 32 | 0 | 0 |
| Moxy | 40 | 0 | 0 |

**One fire, on the right page, with the right answer. 82 clean negatives.**

This is a stronger check than INV-B's: INV-B swept 23 pages of three sets at one
assumed scale each. This sweeps all four sets, every page, at eleven plausible
drawing scales from 1/2"=1' to 1"=60' — because the live pipeline gets `fpp` from
the scale solver, not from a constant. The count is scale-invariant: only the
reported marker size in inches changes.

### The false positive that was found and killed at the root

The first draft **fired on Chelsea page 17** — twelve roof-pitch triangles at 100%
occupancy on a 6×2 "lattice". Chelsea prints pitch callouts reading `3 2 4 / 3 2 4
/ ...` across the sheet, and those repeated glyphs formed a bogus axis.

Per the four-plan-set rule this is a rejection, not something to filter away. The
structural fix: **a gridline axis names every line uniquely, in one alphabet, in
sequence.** `1..22` and `A..H` qualify; `3 2 4 3 2 4` does not. No threshold moved.

### Section 10's trap, encoded permanently

The 136-mark class at `(1.80, 0.72)` and the 40-mark class at `(1.32, 1.32)` are
both still present on Crow page 0 and both are rejected for having **one distinct
Y** — by construction, not by a count filter. Make the tick row 1,000 marks long
and it is still rejected. `tests/test_grid_lattice.py` asserts this.

### One page the detector cannot see, measured rather than assumed

Crow page 3 carries 249,608 primitives, over the 200,000 cap `grid_lattice` shares
with `symbols.py`, so it is skipped. **Measured with the cap lifted: still zero
lattices at every scale.** Nothing is hidden there.

---

## 3. Columns: 120 is the honest number, and the gap stays open

The sheet draws **120**: rows B..G × columns 2..21, one marker per cell, no cell
empty, no marker off-grid. Both grid axes reconcile to the sheet's own printed
overall dimensions (1136'-0" and 350'-0"), so the drawing validates itself.

**INV-B's completion rule is not supported by the drawing, and I did not implement
it.**

INV-B proposed extending the six detected rows across the full 22-line number axis
(6 × 22 = 132) and was candid that the rule was chosen *after* seeing that golden
is 132. Re-measured here:

* the occupied block is missing **exactly the two end positions on BOTH axes** —
  rows B..G of A..H, and columns 2..21 of 1..22;
* all four footprint edges carry the same continuous panel geometry
  (2,758 / 2,636 / 9,795 / 9,194 pt of long-line stroke at x=439, x=2481, y=1200,
  y=1828). There is no asymmetry to appeal to;
* the take-off PDF carries **no per-column markup** — its only page-0 annotation is
  a 21-point footprint polygon. The 132 was entered as grid arithmetic.

Extending the numbers gives 132, the letters 160, both 176. Exactly one matches the
answer key, and picking it *because* it matches is §10's coincidence trap.

So `LatticeGroup.completion_candidate` is populated **only when a single axis
qualifies** — when the drawing itself picks. On Crow it is `None`, all three
hypotheses are published as flagged and unconfirmed, `needs_review` is True, and
the run asks a human. **120 measured, 12 unknown, nothing invented.**

---

## 4. The Bollards defect was the same bug

`SYM-2` (56 instances, named "Bollards" by the semantic pass) is 56 of these column
markers. `cluster_symbols` shatters the lattice because the marker edges share a
style class with the gridlines and a gridline dash endpoint lands 0.805 pt from a
marker corner — inside `ENDPOINT_EPS_PT` — so the dash unions in and the signature
depends on dash phase.

With the lattice wired in, four fragments (`SYM-2`, `SYM-26`, `SYM-27`, `SYM-32`)
are recognised as lattice markers and dropped, so the same drawn objects are not
published twice. The 136-mark tick row `SYM-1` is **not** suppressed — it is not a
lattice marker, and removing it would be a different and wrong claim.

Crow's real bollard count is text-anchored anyway: general note 13 says "PROVIDE
BOLLARDS AT ALL DRIVE-IN OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS...". Bollards
are a derived quantity from a door schedule, not a countable glyph at 1"=40'.

---

## 5. Ladder: a two-character regex, and two defects it was hiding

`_KEYNOTE_NUM_RE` was `^(\d{2})\.?$`. Keynotes 1-9 were structurally invisible to
`keynote_legend()` and `keynote_tags()`. Crow page 0 read **3 of its 12** keynotes,
and keynote 1 — the whole evidence for the Ladder — never entered the pipeline.

Widening to `\d{1,2}` is purely additive across all four sets: 24 legend blocks →
25, +49 entries, **zero lost, zero changed**. It also exposed three latent defects,
each of which publishes a confidently wrong LABEL, all fixed structurally:

1. **No vertical bound on the header search.** Crow page 1's four
   "1 OVERALL NORTH ELEVATION" view titles, up to 1,900 pt below the header, became
   keynotes 1-4; Bob's page 3 absorbed three roof detail titles. The header-to-entry
   *gap* cannot separate these (a real Moxy entry sits 918 pt below its header; a
   spurious Bob's title sits 890 pt below). The *step from the previous element of
   the stack* can, and it is sharply bimodal: **394 real entries step ≤ 92.8 pt, all
   8 spurious ones step ≥ 298.1 pt.** The constant sits in that measured empty band.
2. **Two adjacent lists merged.** Bob's KEYED NOTES runs 01..16, and an unheaded
   paint-colour list restarts at 1, 2 just 93 pt below. A legend numbers upward, so
   a restart ends the stack — no constant needed.
A third fix was **built, measured and REJECTED** — recorded here because the
measurement is the useful part. Wrapped notes return only the one line level with
the number block (Crow keynote 2 comes back as its second line, "CONCRETE ROOF AT
ELECTRICAL ROOF BELOW. G.C. TO", turning a note about a roof *hatch* into a note
about a roof). Reassembling by splitting the note column at the midpoint between
consecutive entry centres fixed all of Crow — 260 entries across the four sets
gained their full text, 130 unchanged, none replaced — **but the midpoint is only
the true boundary when adjacent notes have the same line count.** On Bob's page 4
it moved one wrapped line across the 07/08 boundary, so note 07 ended "...DO NOT
INSTALL TO THE STOREFRONT" and note 08 began "SYSTEM/GLAZING MULLIONS.". That put
the word STOREFRONT into an awning note, flipped the front facade's dominant
material from CMU to Storefront, and cost a real published quantity.

Helped one plan set, hurt another → rejected, exactly like the title-block window.
Doing it properly means grouping note lines into **contiguous blocks** first and
matching each block to the nearest number centre, rather than slicing the column by
number positions alone. That is its own piece of work with its own four-set
measurement. Until then the reader returns *less* text rather than *wrong* text,
and `tests/test_keynote_callouts.py` asserts the current truncation out loud so the
limitation stays visible.

`keynote_callout_counts()` then converts a keynote into a count: the bubble group is
identified as the one enclosing the most of the legend's own number blocks, and each
entry's own legend bubble is subtracted. Crow keynote 1 is drawn exactly twice —
legend plus one plan callout — so **Ladder = 1**.

One more thing the widening broke and the four-set gate caught: `keynote_tags()`
shares the regex, and a *tag* has none of the header/stack/ordering context that
makes a legend entry recognisable — it is just a lone number in a drawing. Bob's
page 4 started returning twenty bare `1` tags that are general-note indices and
dimension text, and the front facade lost its CMU row. The two-digit regex had been
supplying that constraint by accident. It is now stated: **a keynote tag is a number
the sheet's own legend defines.** Bob's tag census is byte-identical to before;
Crow's single-digit keynotes now resolve.

Keynotes 1 **and** 2 both contain "ACCESS LADDER" on the sheet (2 is a roof hatch).
The count is
deterministic; which keynote *is* the Ladder stays a head-noun judgement for the
semantic pass, and a test pins the ambiguity so nobody "fixes" it with a substring
match. Zero numeric fields entered any vision schema.

---

## 6. Stairs: not an engine failure, an input gap

**Correcting INV-B on a point of fact.** INV-B places the stairs on "A-401 details
and the A-111/112/113 enlarged plans, which are not in the uploaded PDF". **A-401
IS in the uploaded PDF — it is page 2, MISC. DETAILS**, and it draws a STAIR PLAN, a
STAIR SECTION and a STAIR RAIL.

Measured: the upload contains A-101, A-201, A-401, A-601 and cites five sheets it
does not contain — **A-002, A-111, A-112, A-113, A-501**. Page 0 defers three times,
`SEE 1/A-111 / A-112 / A-113`, to enlarged plans that are absent.

So the set shows *what a stair looks like*; it never says *how many are installed*.
INV-B's conclusion is unchanged and its reason is now accurate.

`missing_referenced_sheets()` reads this deterministically from title blocks and page
text; `run_pdf_analysis` records it on the ledger **before any measurement**; the
ledger warns that the quantity is UNKNOWN not zero and that the gap closes by
uploading the sheet, never by more detector work. `NOT_IN_UPLOADED_SET` distinguishes
it from "we skipped it" and from "we measured zero".

The 10 stairs remain unreachable, and that is the correct outcome.

---

## 7. What is still unmeasurable, and exactly why

| Thing | Why | Closes by |
|-------|-----|-----------|
| Crow Stairs (10) | not drawn in the uploaded 4 pages; on A-111/112/113 | **uploading those sheets** |
| The 12 end-wall columns | the drawing does not distinguish concealed end-COLUMNS from concealed end-ROWS; 132/160/176 are equally supported | **one human confirmation** on the flagged hypotheses |
| The lattice's NAME | it has no text anchor — grid cell ids say where the markers are, not what they are | the semantic labelling pass, from the candidate registry |
| Crow Bollards (28) | text-anchored to a general note about door jambs and risers, not a countable glyph at 1"=40' | a door-schedule-derived route (not this job) |
| Anything on Crow p3 | 249,608 primitives, over the shared 200k cap | measured: nothing there anyway |

## 8. Two rules this work depended on, for whoever comes next

1. **A detector that fires on a second plan set is rejected.** It caught the Chelsea
   pitch-callout false positive, and the fix was structural. The gate is
   `tests/test_grid_lattice.py::test_no_lattice_anywhere_else_in_four_sets`.
2. **Never close a gap to a golden number.** 120 ≠ 132 and the tests assert 120.
   Every constant introduced here is either a shape property (uniquely-labelled
   axis, ≥2 distinct Y, occupancy) or a value read from the middle of a measured
   bimodal gap (the 150 pt keynote stack step). If one ever needs to move,
   **re-measure the distribution** — do not nudge it.
