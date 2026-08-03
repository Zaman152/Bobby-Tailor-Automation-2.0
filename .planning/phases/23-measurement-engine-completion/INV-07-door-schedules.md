# INV-07 — Door schedules: format-agnostic parsing (implementation map)

_Investigation date 2026-08-03. Read-only. Every number below came from a zero-API run against
the real PDFs in `uploads/`; probe output is pasted verbatim._

---

## TL;DR

1. **Bob's is a three-line fix away from EXACT.** Its schedule *is* found (tag column detected,
   19 opening rows), but it is thrown away by the material-coverage gate at
   `schedule_extraction.py:178` because materials are printed as free text
   (`HM-STL.`, `S.C. WOOD`, `ALUM. & GLASS`) and the frame material is split across **two**
   PyMuPDF cells (`'--- H.'` + `'M. 6A'`). A punctuation/phrase-aware material normaliser plus
   cell-pair joining plus **"no count column ⇒ one door per row"** yields
   **HM 5 / WD 7 / Frame-HM 12 — exactly Bob's golden 5 / 7 / 12.** Today it is 0 / 0 / 0.
2. **Moxy's schedule already parses. The zero is a NAMING bug, not a parsing bug.** The saved
   Moxy run emitted `Doors - Solid Core Wood (door schedule) 42 EA`; golden wants `Doors-WD`.
   The scorer's `_best_name_match` cannot bridge that, so it scored MISSING. Fix =
   emit the canonical `Doors-<CODE>` form (and map `SCW → WD`, not `SCW → SC`).
3. **Two parsers exist for one job and they disagree.** `component_library._parse_count_door_rows`
   (type+Count, Crow) and `schedule_extraction.extract_door_schedule` (per-opening, Moxy) each
   handle one format, produce **different names**, and neither handles Bob's. Merge into one
   parser whose count rule is: *use the COUNT column when the schedule prints one, otherwise
   count the rows*.
4. **Chelsea's 0 is honest and must stay 0.** Its 32-page set contains door *types/elevations* and
   `DOOR SCHEDULE GENERAL NOTES` but the schedule **table sheet is not in the PDF** ("SEE SCHEDULE"
   callouts only) — same class of input gap as Moxy's missing `CS-04 GUESTROOM MATRIX` (§13).
   Emit a **coverage warning**, never a guessed number.
5. **The non-takeoff-legend guard that works** (verified: Moxy p15's interior-elevation grid, which
   currently produces a phantom `WD 4`, is rejected) is a **two-part** gate: a *standalone*
   `DOOR … SCHEDULE/TYPE` title line whose x-band contains the table, **plus** column-role evidence
   (≥2 distinct door-material columns, or a header cell reading TAG/PANEL/FRAME/QTY).
   A title phrase buried in a note ("REFER TO ARCHITECTURAL DOOR SCHEDULE") must not qualify.

Net effect if implemented: **Bob's +3 exact items** (5/7/12), **Moxy +2 items become scorable**
(42 SCW→`Doors-WD`, 42 `Frame-HM` against golden 213/215 — still short by the guestroom
multiplier, which is an input gap, not a code gap), **Crow unchanged at 29/29**, **Chelsea 0 with a
stated reason**.

---

## 1. What the current code assumes

### 1a. Path A — type + Count (Crow's shape)
`src/bobbytailor/deterministic/component_library.py:230` `_parse_count_door_rows`:

- **Column 0 must be a door TYPE code** — `component_library.py:241` filters rows with
  `_TYPE_CODE_RE.match(r[0])`, and `_TYPE_CODE_RE` (`component_library.py:203`) is
  `^[A-Z]{1,3}\d{0,2}[A-Z]?$`, i.e. it deliberately requires a leading letter.
- **A COUNT column must exist** in columns 1–3 — `component_library.py:248-258`; when it is absent
  the function `return None`. There is **no row-counting fallback.**
- **Materials must be a single bare token** in `_SCHED_MAT` (`component_library.py:196-201`),
  compared with `(r[c] or "").strip().upper() in _SCHED_MAT` (`component_library.py:267`).
- Page gate: the page text must contain the literal `"DOOR SCHEDULE"`
  (`component_library.py:394`).
- Names emitted: `"Doors-{code}"` / `"Door Frames-{code}"` (`component_library.py:352`, `:360`),
  after `_MAT_CODE_ALIAS` maps `SCW → SC`, `ALUM → AL`, `GLASS → GL` (`component_library.py:303-305`).

### 1b. Path B — per-opening (Moxy's shape)
`src/bobbytailor/deterministic/schedule_extraction.py:181` `extract_door_schedule`:

- Tag column = the left-most of columns 0–3 with ≥3 tag-shaped cells (`schedule_extraction.py:83-96`).
- Panel/frame columns by **whitespace-split exact token** membership in `_PANEL_MATS`/`_FRAME_MATS`
  (`schedule_extraction.py:30-36`, matched at `:120-129` and `:163-166`).
- Accept/reject gate `_is_door_table` (`schedule_extraction.py:170-178`): needs ≥3 tag rows and
  `covered/door_rows >= 0.4`.
- **One opening per tag, always** — `out.openings = len(seen_tags)` (`schedule_extraction.py:226`).
  There is no count column concept at all.
- Names emitted: prose — `"Doors - {_PANEL_LABEL[code]} (door schedule)"`
  (`schedule_extraction.py:245`) and `"Door Frames - {...} (door schedule)"` (`:251`), from the
  label maps at `schedule_extraction.py:39-48`.

### 1c. Which path runs
`src/bobbytailor/deterministic/plan_deterministic_legends.py:52-77` — Path A first
(`build_door_component_legend`, `:99`); if it returns `None`, Path B
(`extract_door_legend_from_pdf`). The legend is built once per project at
`src/bobbytailor/pipeline/pdf_analyzer.py:357-359` and injected into exactly one sheet at
`src/bobbytailor/pipeline/takeoff_pipeline.py:2850-2881`.

---

## 2. The real schedules, as evidence

### 2a. Crow — `uploads/Crow - Cass White Road-Plans.pdf`, page index 3
Header is a **separate table** (t0) from the data (t1) — which is why Path A is content-based:

```
TABLE 0  rows=3 cols=13
   ['DOOR SCHEDULE', '', '', ...]
   ['Type', 'Count', 'Fire Rating', 'Door\nWidth Height Thickness Material Finish Under Cut Hardwa', ..., 'Frame\nre Type Material Finish Jamb Head', ..., 'Comments']
TABLE 1  rows=9 cols=14           <-- the data
0 ['DSF', '2', '',        "6' - 0\"",  "7' - 11\"", "0' - 1\"",      'AL',  'AN',  'HW4', '',  '',   '',   '',        '']
1 ['OD1', '68', '-',      "9' - 0\"",  "10' - 0\"", "0' - 2\"",      'STL', 'FAC', '',    '2', '',   '',   'J2 H2',   'NOTE 3']
2 ['OD2', '2',  '-',      "12' - 0\"", "14' - 0\"", "0' - 2\"",      'STL', 'FAC', '',    '2', '',   '',   'J2 H2',   'NOTE 4']
3 ['P1',  '24', '-',      "3' - 0\"",  "7' - 0\"",  "0' - 1 3/4\"",  'IM',  'PT',  'HW1', '1', 'HM', 'PT', 'J1 H1',   'NOTE 1']
4 ['P2',  '2',  '-',      "4' - 0\"",  "7' - 0\"",  "0' - 1 3/4\"",  'IM',  'PT',  'HW1', '1', 'HM', 'PT', 'J1 H1',   'NOTE 1']
5 ['P3',  '1',  '45 MIN.', ...                                        'IM',  'PT',  'HW2', '1', 'HM', 'PT', 'J3 H3',   'NOTE 2']
6 ['P4',  '1',  '45 MIN.', ...                                        'IM',  'PT',  'HW3', '1', 'HM', 'PT', 'J3 J3',   'NOTE 2']
7 ['P5',  '1',  '45 MIN.', ...                                        'IM',  'PT',  'HW2', '1', 'HM', 'PT', 'J3 J3',   'NOTE 2']
8 ['SF',  '4',  '-',      "3' - 0\"",  "7' - 11\"", "0' - 1\"",      'AL',  'AN',  'HW4', '',  '',   '',   '',        '']
```

**Golden `Doors-HM 29` = P1 24 + P2 2 + P3 1 + P4 1 + P5 1** — i.e. the Count column, and the
`IM → HM` reclassification driven by the printed `NOTE 1 -` / `NOTE 2 -` bodies which read
`... HOLLOW METAL DOORS IN ... WELDED HOLLOW METAL FRAMES ...` (page 3 tables 8/9). That
reclassification lives at `component_library.py:211-227` (`_hm_door_notes`) and
`component_library.py:341-343`. **Any refactor must keep it or Crow drops to `Doors-IM`.**

### 2b. Bob's — `uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf`, page index 5
One 55×27 table spanning the whole sheet. Columns shown: 0,1,2,8,10,11,12,13,14.

```
0 ['DOOR SCHEDULE | E = EXISTING DOOR COORDINATE DOOR HARDWARE VIF', '', ...]
1 ['EXIST | DOOR', 'NO.', 'TYPICAL LOCATION', 'TYPE', 'MATERIAL', 'VISION LITE', 'FRA | LABEL | MA', 'ME HARDWARE', '']
2 ['', '', '', '', '', '', '', "T'L. SET", 'KEY']
3 ['', '001A', 'VESTIBULE',   '8', 'ALUM. & 1" INSULATED | GLASS', 'Y', '--- AL', 'UM. **', 'Y']
4 ['', '001B', 'VESTIBULE',   '8', 'ALUM. & GLASS',                'Y', '--- AL', 'UM. **', 'Y']
5 ['', '002',  'DINING',      '3', 'HM-STL.',                      '',  '--- H.', 'M. 6A',  'Y']
6 ['', '004A', 'BEDROOMS',    '3', 'HM-STL.',                      '',  '--- H.', 'M. 6A',  'Y']
7 ['', '004B', 'BEDROOMS',    '3', 'HM-STL.',                      '',  '--- H.', 'M. 6A',  'Y']
8 ['', '005',  'KIDS',        '3', 'HM-STL.',                      '',  '--- H.', 'M. 6A',  'Y']
9 ['', '008',  'MANAGER/COUNT','2','S.C. WOOD & GLASS',            'Y', '--- H.', 'M. 1A',  'Y']
10 ['', '009', 'BREAKROOM',   '2', 'S.C. WOOD & GLASS',            'Y', '--- H.', 'M. 3',   '']
11 ['', '010', 'DATA',        '1', 'S.C. WOOD',                    '',  '--- H.', 'M. 2A',  'Y']
12 ['', '013', 'UNISEX',      '1', 'S.C. WOOD',                    '',  '--- H.', 'M. 4',   'Y']
13 ['', '014', 'UNISEX',      '1', 'S.C. WOOD',                    '',  '--- H.', 'M. 4',   'Y']
15 ['', '015', 'JANITOR',     '1', 'S.C. WOOD',                    '',  '--- H.', 'M. 2A',  'Y']
16 ['', '016A','RECEIVING',   '5', '*',                            'Y', '---',    'MFG',    '']
17 ['', '016B','CUSTOMER PICKUP','6','*',                          'Y', '--- -',  '-- ---', '']
18 ['', '016C','REVEIVING',   '3', 'HM-STL.',                      '',  '--- H.', 'M. 6A',  'Y']
19 ['', '016D','LOADING/UNPACKING','6','*',                        'Y', '--- -',  '-- ---', '']
20 ['', '016E','LOADING/UNPACKING','6','*',                        'Y', '--- -',  '-- ---', '']
21 ['', '016F','LOADING/UNPACKING','6','*',                        'Y', '--- -',  '-- ---', '']
22 ['', '017', 'SPRINKLER ROOM','1','S.C. WOOD',                   '',  '--- H.', 'M. 2A',  'Y']
```

Four format differences from Crow, all fatal today:

| # | Difference | Consequence |
|---|-----------|-------------|
| 1 | Tag lives in **column 1**; column 0 is `EXIST DOOR` (blank) | `_parse_count_door_rows` (`component_library.py:241`) matches 0 rows → `None` |
| 2 | **No COUNT column** — one row = one opening | `component_library.py:257-258` `return None` |
| 3 | Materials are free text with punctuation (`HM-STL.`, `S.C. WOOD`, `ALUM. & GLASS`, `*`) | `_SCHED_MAT` / `_PANEL_MATS` exact-token match fails |
| 4 | Frame material **split across two cells**: `'--- H.'` + `'M. 6A'` | `H.M.` never exists as one token |

Measured, not inferred — running the production internals on that table:

```
$ PYTHONPATH=src python3 -c "...schedule_extraction internals on Bob's page 5..."
table 0 rows 55 tag_col 1
   panel_col 10 frame_col 12 is_door_table False coverage (19, 4)
   tags found: [['001A'],['001B'],['002'],['004A'],['004B'],['005'],['008'],['009'],['010'],
                ['013'],['014'],['015'],['016A'],['016B'],['016C'],['016D'],['016E'],['016F'],['017']]
   count-path: None
```

`coverage (19, 4)` — **19 real door rows found, only 4 "covered"** (the four rows whose text happens
to contain the bare token `GLASS`). 4/19 = 0.21 < the 0.4 threshold at
`schedule_extraction.py:178` → table rejected → 0 doors. The detection is right; the *material
reader* is what fails.

### 2c. Moxy — page index 6, five stacked schedule fragments
```
TABLE 2  'DOOR SCHEDULE - GUESTROOMS'   header row merged into ONE cell
   ['G1','GUEST ENTRY','',"3'-0\"","7'-0\"","1 3/4\"",'A','SCW','PTW','90','HMF','','','01','STC 32 MIN.']
TABLE 5  'DOOR SCHEDULE - TYPICAL'      header properly split
   ['TAG','ROOM NAME','LEAF | QTY.','DOOR','','','PANEL TYPE','PANEL | MATERIAL','PANEL | FINISH',
    'FIRE RATING','FRAME | TYPE','FRAME | MATERIA','FRAME | L FINISH','HARDWARE','REMARKS']
   ['T1','STAIR (INTERIOR)','',"3'-0\"","7'-0\"","1 3/4\"",'K','SCW','','90','','HM','','04','PROVIDE PANIC HARDWARE']
TABLE 10 / 13 / 14                       header-less continuation fragments
   ['004','SALES','',"3'-0\"","7'-0\"","1 3/4\"",'G','SCW','','-','','HM','','13']
   ['101A','MAIN VESTIBULE (EXTERIOR)','',"10'-0\"","8'-0\"","1 3/4\"",'H','GLASS','','-','','ALUM','','09']
   ['750A','ELEV. LOBBY','',"5'-6\"","8'-0\"","1 3/4\"",'N','SCW','','60','','HM','','07']
```

The `LEAF QTY.` column **is genuinely empty in the PDF** — confirmed by reading the raw words in
the table's bbox (header word `QTY.` at x=976; no data word ever lands in that band). So Moxy is a
per-opening schedule: **one row = one door**, exactly like Bob's.

Current production output on Moxy (free harness, zero API):

```
$ PYTHONPATH=src python3 -m bobbytailor.deterministic.schedule_extraction <all four PDFs>

=== Crow - Cass White Road-Plans.pdf ===
  scheduled openings : 5  (pages [4])
  panel materials    : {'AL': 2}
  frame materials    : {'HM': 2}

=== Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf ===
  scheduled openings : 60  (pages [7])
  panel materials    : {'SCW': 42, 'GLASS': 6, 'HM': 6}
  frame materials    : {'HM': 42, 'GALV': 6, 'ALUM': 5}

=== Bob's Discount Furniture - Kennesaw, GA-plans.pdf ===
  scheduled openings : 0  (pages [])
  panel materials    : {}
  frame materials    : {}

=== Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf ===
  scheduled openings : 0  (pages [])
  panel materials    : {}
  frame materials    : {}
```

(Crow's `5 / AL 2 / HM 2` is the *per-opening* path mis-reading the type schedule; Crow's real
29/29 comes from Path A. Both paths running on one document is itself a smell — §4 merges them.)

### 2d. Chelsea — the schedule sheet is not in the file
Pages 0 and 17 mention `DOOR SCHEDULE`, but the text is notes and callouts:
`DOOR SCHEDULE GENERAL NOTES:`, `DOOR ELEVATIONS`, and thirteen literal `SEE SCHEDULE` labels.
No opening-tag table exists on any of the 32 pages. Golden asks for
`Door - HM 236 / Door - WD 2,378 / Door Frame - HM 2,687` (`tests/fixtures/chelsea/chelsea_golden.csv`)
— multifamily numbers that are *per-unit-type × unit-count*. **Unreachable from this input.**

---

## 3. Why Moxy scores 0 even though it parses — it is the NAME

The saved Moxy run's own output (`output/VisionOnly_Moxy_Knoxville_20260717_043126/takeoff_summary.csv`):

```
Door Frames - Aluminum (door schedule),5,EA,high,,plan_schedule_legend,...
Door Frames - Galvanized Steel (door schedule),6,EA,high,,plan_schedule_legend,...
Door Frames - Hollow Metal (door schedule),42,EA,high,,plan_schedule_legend,...
Doors - Glass / Aluminum (door schedule),6,EA,high,,plan_schedule_legend,...
Doors - Hollow Metal (door schedule),6,EA,high,,plan_schedule_legend,...
Doors - Solid Core Wood (door schedule),42,EA,high,,plan_schedule_legend,...
```

Scored offline for free:

```
$ python3 scripts/score_report_dir.py --golden tests/fixtures/moxy/moxy_golden.csv \
      --dir output/VisionOnly_Moxy_Knoxville_20260717_043126
MISSING   Door Frame-HM                         215.00             —       —  count
MISSING   Doors-HM                               10.00             —       —  count
MISSING   Doors-WD                              213.00             —       —  count
...
EXTRA items AI produced not in golden:
  + Door Frames - Hollow Metal (door schedule) 42.0 EA
  + Doors - Solid Core Wood (door schedule) 42.0 EA
```

`_best_name_match` (`scripts/vision_only_benchmark.py:177-203`) compares token sets:
`{doors, wd}` vs `{doors, solid, core, wood, door, schedule}` — neither is a subset, overlap ≈ 0.14,
difflib ratio < 0.6 → MISSING. Same story in the app's own canonicaliser: `aggregator.py:96` maps
`door.*\bwood\b` → `Doors-WD`, but `component_library`'s alias `SCW → SC`
(`component_library.py:303`) would emit `Doors-SC`, which matches **none** of the door patterns at
`aggregator.py:93-97` and falls through to the generic `Doors` bucket.

**So the door-schedule naming is inconsistent three ways** — prose (`Doors - Solid Core Wood
(door schedule)`), code (`Doors-SC`), and golden (`Doors-WD`). One canonical form is required.

---

## 4. The format-agnostic strategy (validated offline)

### 4.1 Rules
| Role | How it is found | Fallback |
|------|-----------------|----------|
| **Table is a door schedule** | a *standalone* title line matching `\bDOOR\b … \b(SCHEDULE\|TYPES?)\b`, whose x-band contains the table (title may sit above it — continuation fragments inherit) | none: no title ⇒ not a door schedule |
| **Tag column** | header cell reading `TAG / MARK / NO. / DOOR NO / NUMBER` | left-most of cols 0–3 with ≥3 tag-shaped cells |
| **Count column** | header cell reading `QTY / COUNT / QUANTITY` | a column within tag+1..tag+3 that is ≥60% small integers |
| **Panel material** | header cell reading `PANEL … MATERIAL` or bare `MATERIAL` | left-most column whose cells normalise to a door-material code |
| **Frame material** | header cell reading `FRAME … MATERIAL` | right-most such column, ≠ panel |
| **Quantity per row** | `int(count_cell)` when a count column exists | **1 — a 213-row schedule is 213 doors** |

Material reading is the crux. Two transforms make every one of the three formats readable:

1. **Dotted-initialism collapse then punctuation strip** —
   `H.M.` → `HM`, `H. M.` → `HM`, `S.C. WOOD` → `SC WOOD`, `HM-STL.` → `HM STL`, `ALUM.` → `ALUM`.
2. **Phrase vocabulary, leftmost-then-longest wins** — `SOLID CORE WOOD|SC WOOD|SCW → SCW`,
   `HOLLOW METAL|HM STL|HM → HM`, `ALUMINUM|ALUM|AL → ALUM`, `GALVANIZED|GALV → GALV`,
   `GLASS|GL → GLASS`, `WOOD|WD → WD`, `STEEL|STL → STL`, `KD`, `FRP`, `IM`, `HC`.
   Leftmost matters: `S.C. WOOD & GLASS` must be **SCW** (the leaf), not GLASS;
   `ALUM. & 1" INSULATED GLASS` must be **ALUM**.
   Verified:
   ```
   '--- H. M. 6A'               -> 'HM 6A'                    -> HM
   'HM-STL.'                    -> 'HM STL'                   -> HM
   'S.C. WOOD & GLASS'          -> 'SC WOOD GLASS'            -> SCW
   'ALUM. & 1" INSULATED GLASS' -> 'ALUM 1 INSULATED GLASS'   -> ALUM
   '*'                          -> ''                         -> (none)
   ```
3. **Cell-pair joining** — when scoring/reading a material column, evaluate `cell[c]` *and*
   `cell[c] + " " + cell[c+1]`. This is what recovers Bob's `'--- H.'|'M. 6A'` frame column
   without hard-coding a column index.

### 4.2 Proof: prototype run on all four real PDFs
`/private/tmp/.../scratchpad/proto3.py` (throwaway, Python 3.9, zero API):

```
============================================================================================
Crow - Cass White Road-Plans.pdf
  page 3 titles=[(903,1222,'DOOR & FRAME TYPES'), (1422,2307,'DOOR SCHEDULE')]
    t1   rows=9   cov=9   cols(tag,cnt,pnl,frm)=(0, 1, 5, 10) openings=105
         panel={'ALUM': 6, 'STL': 70, 'IM': 29} frame={'HM': 29}
============================================================================================
Bob's Discount Furniture - Kennesaw, GA-plans.pdf
  page 5 titles=[(99,2970,'DOOR SCHEDULE'), (99,2970,'TYPICAL DOOR ELEVATION BY TYPE'), (125,167,'DOOR SCHEDULE')]
    t0   rows=19  cov=14  cols(tag,cnt,pnl,frm)=(1, None, 10, 12) openings=14
         panel={'ALUM': 2, 'HM': 5, 'SCW': 7} frame={'ALUM': 2, 'HM': 12}
============================================================================================
Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf
  page 6 titles=['DOOR SCHEDULE REMARKS','DOOR PANEL TYPES LEGEND','DOOR SCHEDULE - BUILDING',
                 'DOOR SCHEDULE - TYPICAL','DOOR SCHEDULE - GUESTROOMS']
    t2   rows=4   cov=3   openings=3    panel={'SCW': 2, 'GLASS': 1} frame={'SCW': 2, 'GLASS': 1}
    t5   rows=6   cov=5   openings=5    panel={'SCW': 5}             frame={'HM': 5}
    t10  rows=18  cov=18  openings=18   panel={'SCW': 13,'GLASS': 1,'HM': 3} frame={'ALUM': 1,'HM': 13,'GALV': 4}
    t13  rows=15  cov=13  openings=13   panel={'GLASS': 2,'SCW': 7,'HM': 2}  frame={'ALUM': 4,'HM': 7,'GALV': 1}
    t14  rows=14  cov=14  openings=14   panel={'SCW': 12,'GLASS': 2}         frame={'HM': 14}
  page 15 titles=[(106,2768,'ARCHITECTURAL  DOOR SCHEDULE')]     <-- guard held: 0 tables accepted
  TOTAL openings=53 panel={'SCW': 39,'GLASS': 6,'HM': 5} frame={'SCW': 2,'GLASS': 1,'HM': 39,'ALUM': 5,'GALV': 5}
============================================================================================
Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf
  TOTAL openings=0 panel={} frame={}
```

**Scoreboard against golden — no threshold was ever tuned toward a golden count; the count is a
consequence of reading the printed material column and counting rows:**

| Set | Golden | Prototype | Today |
|-----|--------|-----------|-------|
| Bob's `Doors-HM` | **5** | HM 5 ✅ | 0 |
| Bob's `Doors-WD` | **7** | SCW 7 → WD ✅ | 0 |
| Bob's `Door Frame - HM` | **12** | frame HM 12 ✅ | 0 |
| Crow `Doors-HM` | 29 | IM 29 → HM via NOTE 1/2 ✅ | 29 ✅ |
| Crow `Door Frames-HM` | 29 | frame HM 29 ✅ | 29 ✅ |
| Moxy `Doors-WD` | 213 | SCW 39–42 (schedule ceiling) ⚠ | 42 but named unscorably |
| Moxy `Door Frame-HM` | 215 | frame HM 39–42 ⚠ | 42 but named unscorably |
| Chelsea (all doors) | 236 / 2378 / 2687 | 0 + warning ✅honest | 0 silent |

Bob's three items land **exactly** — that is a *structural* result (each printed row is one opening
with a printed material), the opposite of the "136 columns was a coincidence" trap (§10): the check
is position/shape (one table row = one opening tag = one door leaf), not a tuned threshold.

Moxy's residual gap is the documented §13 input gap: golden 213 = *guestroom type × unit count*
from the **missing** `CS-04 GUESTROOM MATRIX` sheet. Do **not** invent a multiplier.

### 4.3 The non-takeoff-legend guard, and why it is two-part
Loosening the material reader without a guard immediately produces a phantom. Prototype v1 (no
title guard) reported on Moxy page 15 — an **interior-elevation sheet** whose drawing grid PyMuPDF
reads as a table:

```
  p15 t0  rows=8 covered=4 openings=4 panel={'WD': 4} frame={}
```
Column 0 there is the elevation grid letters `H, G, F, E, D, C, B, A`; the "material" is the word
`WOOD` inside prose like `WD 01 WOOD 8 T 11A TEXTURED TILE`. The guard that rejects it while
keeping all five genuine Moxy fragments, Crow and Bob's:

1. **Standalone title band.** The title must be a *line of its own* (≤60 chars, matching
   `^…?\bDOOR\b…\b(SCHEDULE|TYPES?)\b…$`), and must not carry a deny word
   (`FLOORING|FINISH|PAINT|COLOR|RCP|CEILING|LIGHTING|PLUMBING|EQUIPMENT|HARDWARE|WINDOW|LOUVER|SIGNAGE|ROOM|WALL COVERING`)
   unless the same line also says DOOR. This rejects `…REFER TO ARCHITECTURAL DOOR SCHEDULE WC 01…`
   embedded in an elevation note, and rejects `FLOORING LEGEND` / `PAINT COLORS` / `RCP LEGEND`
   outright (§8's Bob's "non-takeoff" classification is then no longer needed as a blanket skip).
2. **Column-role evidence.** The table must present **≥2 distinct door-material columns** *or*
   **≥1 header cell** carrying a door role (`TAG|MARK|PANEL|FRAME|LEAF|QTY|DOOR NO`).
   Moxy p15 has one pseudo-material column and no role headers → rejected even though page 15 does
   produce a title band (see the `page 15 titles=[…]` line above with zero accepted tables).
3. Keep the existing statistical gate — ≥3 tag rows and ≥40% material coverage
   (`schedule_extraction.py:174-178`).

---

## 5. Implementation map

All changes are Python 3.9-compatible (no `|` unions at runtime, no walrus in comprehensions,
`typing.Optional/List/Tuple`).

### Step 1 — `schedule_extraction._normalise_material_text(cell) -> str`  *(NEW, near line 30)*
Uppercase; collapse dotted initialisms with `re.sub(r"\b(?:[A-Z]\.\s*){2,}", …)`; strip remaining
non-alphanumerics to single spaces. Pure function, no I/O.

### Step 2 — `schedule_extraction._material_code(cell) -> str`  *(NEW)*
Search the normalised text for every phrase in a new module-level `_MAT_PHRASES` list of
`(phrase, canonical_code)` pairs; return the code of the **leftmost, then longest** match, `""` if
none. Replaces every use of `_PANEL_MATS` / `_FRAME_MATS` / `_SCHED_MAT` token membership.
Canonical codes: `HM, SCW, WD, HC, ALUM, GALV, GLASS, STL, KD, FRP, IM`.

### Step 3 — `schedule_extraction._column_roles(rows) -> Dict[int, str]`  *(NEW)*
Join the first ≤4 rows per column (schedules stack 2–3 header rows — see Moxy t5 / Crow t0),
normalise, and assign the first matching role: `count` (`QTY|COUNT|QUANTITY|NO OF`),
`frame_mat` (`FRAME` + `MATERIAL`), `panel_mat` (`PANEL`+`MATERIAL`, or bare `MATERIAL`),
`tag` (`TAG|MARK|DOOR NO|NUMBER|^NO$`). Roles are advisory; content detection fills the gaps.

### Step 4 — `schedule_extraction._material_columns(rows, tag_col)`  *(MODIFY, currently line 99)*
Score columns with `_material_code(cell)` **and** `_material_code(cell + " " + next_cell)`;
return `(leftmost, rightmost≠leftmost)`. Must be called **per missing role**, not only when both
roles are missing — Bob's finds `panel_mat` from the header (`MATERIAL`, col 10) but its `FRAME`
header is split across cells 12/13, so the frame column must still come from content
(measured: content detection returns col 12 → frame HM 12 ✓).

### Step 5 — `schedule_extraction._count_column(rows, tag_col, roles) -> Optional[int]`  *(NEW)*
Header role first; else a column in `tag_col+1 .. tag_col+3` that is ≥60% `^\d{1,3}$`
(this is Crow's col 1). **Returning `None` is a valid, expected answer** and means "one door per row".

### Step 6 — `schedule_extraction._door_title_bands(page)` + `_table_in_door_band(bbox, bands)`  *(NEW)*
Iterate `page.get_text("blocks")`; a band is `(x0, x1, y0)` for any standalone title line per §4.3.1.
Extend each band's x-range with the bbox of any table it directly titles, so header-less
continuation fragments (Moxy t10/t13/t14) inherit their parent's band. A table qualifies when a
band sits at/above it (`band_y0 <= table_y1`) and overlaps ≥60% of the table's width.

### Step 7 — `schedule_extraction._is_door_table(...)`  *(MODIFY, line 170)*
Keep `door_rows >= 3` and `covered/door_rows >= 0.4`; **add** the §4.3.2 evidence requirement
(≥2 material columns OR ≥1 door-role header). Signature grows a `roles` argument.

### Step 8 — `schedule_extraction.extract_door_schedule(doc)`  *(MODIFY, line 181)*
Per page: compute title bands; skip tables outside them. Per data row, `n = count_cell or 1`;
accumulate `panel_counts[code] += n`, `frame_counts[code] += n`; `openings += n`. Replace
`out.openings = len(seen_tags)` (`:226`) — tag de-duplication must stay for *records*, but the
quantity is the summed `n`. Add `DoorRecord.count: int = 1` (`:51-57`) and
`DoorSchedule.tables_seen: int` / `titled_pages: List[int]` so a "found the title, parsed nothing"
state is representable (Chelsea).

### Step 9 — `schedule_extraction.door_schedule_to_legend(ds)`  *(MODIFY, line 230)*
Emit the **canonical estimator form**: `"Doors-{CODE}"` and `"Door Frames-{CODE}"` with
`SCW → WD` (not `SC`), `ALUM → AL`, `GLASS → GL`, `IM → HM` when the printed note says so.
Delete the prose `_PANEL_LABEL`/`_FRAME_LABEL` names from the ITEM field (keep them in
`DESCRIPTION` for the human report). This alone converts Moxy's existing 42 SCW / 42 HM from
`MISSING` to a scored `Doors-WD` / `Frame-HM`. Move the `_hm_door_notes` reclassification
(`component_library.py:211-227`, `:341-343`) into this function so **both** formats get it.

### Step 10 — `component_library.extract_door_component_counts(doc, notes_text)`  *(MODIFY, line 370)*
Delegate to the unified `extract_door_schedule`; keep `count_doors_by_material`
(`component_library.py:312`) as the note-aware grouping step. **Delete `_parse_count_door_rows`
(`component_library.py:230-299`)** — its type+count logic is now Step 5's count column.
Change `_MAT_CODE_ALIAS` (`component_library.py:303`) `"SCW": "SC"` → `"SCW": "WD"`, so
`aggregator.py:96` (`door.*\bwd\b`) canonicalises it.

### Step 11 — `plan_deterministic_legends.build_deterministic_legends`  *(MODIFY, line 21)*
Collapse the two-path try/fallback at `:52-77` to one call. Keep the log line and
`_source_pages` provenance.

### Step 12 — coverage warning for "title present, table absent"  *(NEW)*
When `ds.titled_pages` is non-empty but `ds.openings == 0` (Chelsea), attach
`{"warning": "door schedule referenced on page(s) N but no parsable schedule table in this PDF"}`
to the run report instead of silently producing nothing. Same treatment when the schedule parses
but the plan set references a per-type multiplier sheet that is absent (Moxy `CS-04`).

---

## 6. Offline verification (zero API, all free)

```bash
# 0. baseline, before any edit  (recorded 2026-08-03: "41 passed in 84.12s")
python3 -m pytest tests/test_schedule_extraction.py tests/test_component_library.py \
                  tests/test_plan_deterministic_legends.py -q

# 1. the built-in free harness — must print the four blocks in §2c with the new numbers
PYTHONPATH=src python3 -m bobbytailor.deterministic.schedule_extraction \
  "uploads/Crow - Cass White Road-Plans.pdf" \
  "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf" \
  "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" \
  "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"

# 2. the production legend builder, end to end, no API
PYTHONPATH=src python3 -c "import json;from bobbytailor.deterministic.plan_deterministic_legends \
  import build_deterministic_legends as b;print(json.dumps(b(\"uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf\"),indent=1))"

# 3. rescore the SAVED Moxy run after the naming change (no new run, no spend)
python3 scripts/score_report_dir.py --golden tests/fixtures/moxy/moxy_golden.csv \
        --dir output/VisionOnly_Moxy_Knoxville_20260717_043126
```

**Assertions to add (new `tests/test_schedule_extraction.py` cases, all offline-fixture-driven):**

| Assertion | Value |
|-----------|-------|
| Bob's plans → `panel_counts["HM"]` | `== 5` |
| Bob's plans → `panel_counts["SCW"]` | `== 7` |
| Bob's plans → `frame_counts["HM"]` | `== 12` |
| Bob's legend ITEM names | contain `Doors-HM`, `Doors-WD`, `Door Frames-HM` (no prose, no `(door schedule)` suffix in ITEM) |
| Crow plans → `panel_counts` after note reclass | `{"HM": 29, "ALUM": 6, "STL": 70}` and `frame_counts["HM"] == 29` |
| Crow openings | `== 105` (Count column honoured: 2+68+2+24+2+1+1+1+4) |
| Moxy → `ds.pages == [7]`, `openings >= 53` | (replaces the current `openings == 60` pin at `tests/test_schedule_extraction.py:64-66`; assert `>=` so continuation stitching can only improve) |
| Moxy page 16 (index 15) contributes **zero** rows | negative test for the legend guard |
| Chelsea → `openings == 0` **and** `titled_pages != []` | the honest-zero + warning path |
| Unit: `_material_code` table | the five `->` rows in §4.1 |
| Unit: `_material_code("FLOORING LEGEND")` / `("PAINT COLORS")` | `== ""` |

`pytest -m golden`, `scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`,
`scripts/golden_convergence.py` were **not** run and are not required by any step above.

---

## 7. Risks

1. **Crow regression is the big one.** Crow's 29/29 depends on (a) the Count column and
   (b) the `IM → HM` note reclassification. If Step 10 removes `_parse_count_door_rows` before
   Step 9 moves `_hm_door_notes` into `door_schedule_to_legend`, Crow silently becomes
   `Doors-IM 29` and `aggregator.py:93-97` drops it into the generic `Doors` bucket.
   Land Steps 8–9 and 10 in the **same** commit.
2. **`tests/fixtures/crow_cass/crow_cass_golden.csv` has no door rows** (verified — its ten rows
   are Bollards/CMU/Columns/Exposed Structure/Tilt-up/Ladder/Lift/Mobilization/Sealed Concrete/Stairs).
   `score_report_dir.py` against Crow will therefore **not** catch a door regression. The pytest
   assertions in §6 are the only Crow door guard; treat them as required.
3. **Loosening materials without landing the guard first** re-introduces the Moxy p15 phantom
   (`panel={'WD': 4}` from elevation-grid letters). Steps 6–7 must land in the same commit as
   Steps 1–2, never after.
4. **`WD` vs `SCW` naming touches three places** — `component_library._MAT_CODE_ALIAS:303`,
   `schedule_extraction` label maps `:39-48`, and `aggregator.py:93-97`. Changing one alone
   produces a new orphan name. Also check `tests/test_component_library.py:131-172` and
   `tests/test_takeoff_generalization.py:559` which pin the current names.
5. **Moxy will still be far from 213/215** after this work. That is correct and must be reported as
   such — the multiplier sheet (`CS-04 GUESTROOM MATRIX`) is not in the PDF (§13 BLOCKER A).
   Anyone "fixing" Moxy doors by scaling 42 up to 213 is reproducing the §10 coincidence trap.
6. **Moxy's guestroom fragment (p6 t2) currently mis-reads frame = panel** (`frame={'SCW':2,'GLASS':1}`)
   because its header is one merged cell so `_column_roles` finds nothing and the pair-join picks
   the panel column twice. Mitigation inside Step 4: when a table shares a title band with a
   *sibling* table that DID yield roles (Moxy t5 has `FRAME | MATERIA` at col 11), inherit the
   sibling's column roles by index. Without that, expect ~3 mis-typed frames on Moxy — small, but
   it must be stated rather than absorbed.
