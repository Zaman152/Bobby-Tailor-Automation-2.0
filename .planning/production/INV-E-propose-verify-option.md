# INV-E — The propose→verify harness option (orchestrator note, 2026-08-07)

Raised by the user during the production swarm: *"why not build the right harness and use the most
accurate model currently available? We should teach and build the right harness, and I'm pretty sure
we are very near to that."*

This note exists so the sequencing does not dismiss that argument with "the research says vendors
don't matter." The user is pointing at something real. Here is the precise version.

---

## 1. Why a model swap alone cannot fix Crow's last three items

The vision layer is **label-only by construction**: schemas carry candidate-ID enums and zero numeric
fields, so the model picks from a list the geometry engine already produced.

Crow's `Columns` (golden 132) does not fail because a model looked at the columns and answered wrong.
It fails because **no candidate for them exists**. The unnamed-geometry ledger from the last paid run
holds `SYM-6=36`, `SYM-7=32`, `SYM-9/10/11=14` — the 132 columns were never isolated as a cluster.
Ground truth §10/§11 proved a 2-D lattice search (both spans > 300 pt, count 30–250) returns **zero**
candidates, and that the celebrated "136 cluster" was collinear dimension ticks at `yspan=0`.

Hand that same candidate list to Gemini 3 Pro and it answers the same way. **The better model never
gets to see the problem.** That — not vendor loyalty — is why the A/B is scoped as an experiment on
the *labelling* passes rather than as a migration.

## 2. The harness change that WOULD make a better model matter

Today the flow is one-directional:

```
geometry  ->  candidates  ->  vision labels them
```

The missing direction is:

```
vision proposes regions on the raster  ->  geometry verifies and measures them
```

This inverts *who finds things*. Frontier VLMs are measurably decent at "there is a repeating element
here" while being poor at *counting* it (the verified evidence: symbol counting plateaus 0.40–0.55,
item localization is every general VLM's worst subtask at 56–64). A proposal is not a count, and that
distinction is what makes this safe.

**The safety property survives intact.** A vision proposal is a HYPOTHESIS about where to look;
the deterministic layer still produces every number. A wrong proposal costs a flagged candidate, not
a wrong quantity on an invoice. This is categorically different from asking a model "how many columns
are there", which the architecture rightly forbids and must continue to forbid.

## 3. What this implies for sequencing

The cost split depends on Job B's finding:

- **If the 132 columns exist as vector primitives but the style-class partition loses them** → this is
  a *clusterer* fix. Cheap, deterministic, no model involved, Phase 25 as scoped.
- **If they are genuinely not separable in the vector data** (merged into the wall network, or drawn
  as grid furniture) → no deterministic clusterer will recover them, and the propose→verify loop is
  the honest path. That is a real architectural addition, not a tuning exercise.
- **Either way**, a text/schedule route may beat both: the project's own verified research puts
  text-anchored recognition at 0.65–0.92 against 0.03–0.39 for symbol-shaped. If Crow prints a column
  schedule or grid callouts implying the lattice, that is the cheapest and most reliable route of all.

## 4. Guardrails if propose→verify is built

1. A proposal NEVER carries a quantity. It carries a region; geometry measures it.
2. A proposed region that geometry cannot measure becomes a **flagged candidate**, never a number.
3. Proposals are validated by POSITION/SHAPE against the drawing — never by whether the resulting
   count matches golden. The §10 coincidence trap applies with full force here; a proposal loop is
   *more* susceptible to it, not less, because it can be steered.
4. The four-plan-set no-regression gate applies: a proposal strategy that helps Crow and hurts
   Chelsea is rejected, exactly as the title-block window was.
5. Provider-agnostic seam first, model choice second — otherwise the A/B is unrepeatable.

## 5. Honest bottom line

The user's instinct is right that the harness is unfinished, and wrong only in the implied order:
**the model is the last variable to change, not the first**, because until a candidate exists no model
can help. Build the candidate-generation path (clusterer fix, schedule/text route, or propose→verify
in that order of preference), *then* A/B the model on the passes that actually decide something.

---

## 6. MEASURED 2026-08-07 — the premise "no candidate exists" is FALSE

Direct probe of Crow **page 0** (the OVERALL FLOOR PLAN @1"=40', per §11.0 — page 1 is elevations
and analysing it has misled this project before). Free, zero API.

**Confirming the prior evidence:** `cluster_symbols` yields 19 groups. `SYM-1` is 136 marks at
**yspan = 0.0** — collinear dimension ticks, exactly as §10 proved, NOT columns. `SYM-2` (56, 2.59 x
2.81 ft) is the bollard cluster and the only 2-D group in count range [30,250]. **No cluster
resembling 132 exists.** So far, prior evidence reproduced exactly.

**But the raw vector data tells a different story.** Scanning all 33,499 drawing paths for
column-sized square-ish closed shapes (0.8–2.6 ft, near-square):

```
column-sized square-ish paths: 277
spatial span: x = 2223 pt, y = 1860 pt   -> genuinely 2-D distributed
top style signatures (w_ft, h_ft, type, fill, stroke_width):
   (2.47, 2.53, 's', None, 1.44)  x 41
   (2.53, 2.47, 's', None, 1.44)  x 41
   (2.53, 2.53, 's', None, 1.44)  x 39
   (2.47, 2.47, 's', None, 1.44)  x 39
   (1.87, 1.87, 's', None, 1.44)  x 36
```

**The first four signatures are the SAME square**, differing by 0.06 ft — about 0.11 pt, i.e.
rounding jitter — yet they occupy four separate signature buckets. That is a plausible mechanism for
the clusterer losing a lattice it can physically see.

**Do NOT over-read this.** Isolating the ~2.5 ft set (stroke width > 1.0) gives 160 marks, no
co-located duplicates at 3 pt, across 33 X-gridlines and 16 Y-gridlines — but with **row occupancy
`[4,6,6,8,4,44,8,4,4,4,4,4,4,8,44,4]`**. Two dense rows of 44 among rows of 4–8 is **not** a clean
structural column lattice, and 160 is not 132. This probe does **not** establish that these are the
columns, and no work should assume it.

### What this does and does not change

- **DOES change:** the claim "no candidate exists, so a better model cannot help" is too strong as
  stated. Column-sized, 2-D-distributed primitives are present in the vector data. The candidate
  *generation* path — signature quantization in `cluster_symbols`, and whatever merges these into the
  wall network — is a real, cheap, deterministic thing to fix, and it must be investigated BEFORE any
  propose->verify loop or model swap. §3's ordering holds and is now evidence-backed.
- **DOES NOT change:** the coincidence-trap guardrail. 160 -> 132 must never be reached by filtering
  until the number matches. Validation is by POSITION and SHAPE — occupancy regularity, spacing
  consistency, agreement with printed grid callouts — and by the drawing's own text, never by the count.
- **Still open, for Job B's rigorous pass:** are the ~2.5 ft squares columns, pilasters, footings, or
  something else entirely? What are the two 44-mark rows? Does the plan print a column schedule or
  grid bubbles that name the lattice independently (the text route, which our verified research rates
  0.65–0.92 against 0.03–0.39 for symbol-shaped recognition)?
