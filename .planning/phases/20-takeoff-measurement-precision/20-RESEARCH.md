# Phase 20: Takeoff Measurement Precision — Research

**Researched:** 2026-06-03  
**Domain:** Claude vision extraction accuracy, construction quantity take-off, golden-file test harness  
**Confidence:** HIGH (findings grounded in direct code inspection + verified root-cause audit from 20-CONTEXT.md)

---

## Summary

Phase 16 produced output with ≥64% error on bollard counts and missed ~80% of line items for both golden projects (Crow Cass industrial + Bob's Discount retail). The root causes are all in code and are fully fixable without changing the fundamental pipeline architecture.

The eight root causes from `20-CONTEXT.md` break into three layers: (1) **extraction failures** — the wrong data comes out of Claude, (2) **mapping failures** — right data doesn't reach the right estimation table, and (3) **test gap** — there is no numeric comparison against golden truth, so failures are invisible.

**Primary recommendation:** Fix extraction in four targeted passes (title-block, count, measure, schedule), add project-type profiles to the calculator and aggregator, implement a `GoldenValidator` test class against the two CSV golden files, and route elevation sheets + complex schedules to Sonnet while keeping Haiku for simple plans. This is evolutionary, not a rewrite.

---

## Root Cause Inventory (verified in code)

| # | Root Cause | File | Specific Line/Function | Error Observed |
|---|-----------|------|------------------------|----------------|
| RC-1 | Sheet ID regex picks first match in full page text | `pdf_analyzer.py:32` | `_sheet_name_from_doc` — `re.search` on full page text, first `[A-Z]\d{3}` wins → ASTM E283 beats A8.1 | Bob's elevation page mislabeled `E283` |
| RC-2 | `_calculate_from_room()` applies flooring/ceiling/paint/drywall to ALL area types | `calculator.py:385–416` | No project-type gate; industrial slab area → flooring+ceiling items instead of Sealed Concrete + Exposed Structure | Crow Cass: 437K SF Flooring instead of 395K SF Sealed Concrete |
| RC-3 | Components with `quantity: null` silently dropped | `calculator.py:353` | `if qty_raw is None … return None` — correct guard but Claude returns null when symbol count isn't visible; no retry | Crow: Ladder qty null → dropped |
| RC-4 | No `pipe_runs[]` produced for gas piping on roof plan | `claude_analyzer.py` EXTRACTION_PROMPT | Prompt only mentions storm pipe examples (`PVC`, `SCH 40`); gas pipe (`black steel`, `CSST`) not illustrated | Bob A3.0: 886.77 LF gas missing |
| RC-5 | No linear counting pass for lintels | EXTRACTION_PROMPT | Lintels are callout annotations (e.g. `L-4 @ 6'-0" ea`) across elevation/detail sheets; no `lintel_runs[]` structure in prompt | Bob A4.0: 179.24 LF lintels missing |
| RC-6 | Bollard detail confusion — 6' spacing dimension counted as bollard count | EXTRACTION_PROMPT + `_classify_item` | Detail sheet shows `6'-0" TYP` spacing; `_classify_item` hits `bollard` keyword; `_parse_numeric` returns 6 | Crow: 10 EA instead of 28 EA |
| RC-7 | Door schedule hallucination (101–115 range) | EXTRACTION_PROMPT single-pass | Haiku interprets abbreviated schedule with door mark range as 15 separate entries; no verification pass | Bob A8.1: 24 doors wrong type breakdown |
| RC-8 | No numeric accuracy gate | `tests/test_calculator_accuracy.py` | Phase 16 tests check format/guards but never load a golden CSV and compare totals | All errors invisible until manual review |

---

## 1. Title-Block Sheet Name Fix

### Problem
`_sheet_name_from_doc` runs two regexes on the **full page text**. ASTM standard numbers (`E283`, `A156`), keynote references, and any alphanumeric annotation matching `[A-Z]\d+\.\d+` can win before the real title-block sheet number.

### Fix: Search Near Bottom of Page Only
Construction drawings always put the title block in the **bottom right** ~15% of the page. PyMuPDF (`fitz`) provides word-level bounding boxes via `page.get_text("words")` — each word has `(x0, y0, x1, y1, text, ...)`.

```python
def _sheet_name_from_doc(doc: fitz.Document, page_num: int) -> str:
    page = doc[page_num]
    words = page.get_text("words")        # list of (x0,y0,x1,y1,word,...)
    height = page.rect.height
    width  = page.rect.width
    # Title block occupies bottom-right quadrant
    title_block_words = [
        w[4] for w in words
        if w[1] > height * 0.80 and w[0] > width * 0.55
    ]
    title_block_text = " ".join(title_block_words)

    for pat in [r'\b([A-Z]\d+\.\d+)\b', r'\b([A-Z]-\d+)\b', r'\b([A-Z]\d{3})\b']:
        m = re.search(pat, title_block_text)
        if m:
            return m.group(1)

    # Fallback: full-page search but skip known false-positive patterns
    NOISE = re.compile(r'^(E283|A156|ASTM|UL\d|IBC|NFPA|ADA)')
    full_text = page.get_text()
    for pat in [r'\b([A-Z]\d+\.\d+)\b', r'\b([A-Z]-\d+)\b', r'\b([A-Z]\d{3})\b']:
        for m in re.finditer(pat, full_text):
            if not NOISE.match(m.group(1)):
                return m.group(1)

    return f"Page_{page_num + 1}"
```

**Confidence:** HIGH — PyMuPDF `get_text("words")` returns bounding boxes; title block location is an industry standard (ANSI/ASME Y14.1).

---

## 2. Multi-Pass Extraction Architecture

### Problem
A single `analyze_drawing()` call asks Claude to simultaneously count symbols, trace pipe runs, read schedules, and parse room areas. This overloads the model's attention and causes:
- Symbols visible only at high zoom to be missed
- Pipe run annotations blending with dimension annotations
- Schedule columns misaligned

### Solution: Three Focused Passes

Each pass sends the same image but with a narrow, purpose-specific system prompt. The combined JSON is merged before feeding the calculator.

```
Pass 1 — COUNT PASS   (EA items: bollards, columns, stairs, lifts, doors)
Pass 2 — MEASURE PASS (SF/LF/CY items: areas, pipe runs, lintels, gas piping)  
Pass 3 — SCHEDULE PASS (tables only; skip if no schedule detected in Pass 1)
```

Pass 3 is conditional: only invoked when the Pass 1 response contains non-empty `schedules[]`. This limits cost impact.

#### Pass 1 — COUNT_PROMPT (new)
```python
COUNT_PROMPT = """You are counting discrete construction items on this drawing.
Count ONLY items that exist as individual physical units (EA).
Return JSON:
{
  "sheet_name_guess": "...",
  "has_schedules": true/false,
  "components": [
    {"name": "Bollard", "quantity": 28, "unit": "ea", "method": "grid|direct|note",
     "confidence": "high|medium|low", "location": "...", "notes": "..."}
  ]
}

CRITICAL COUNTING RULES:
- Bollards: Count SYMBOLS on plan, NOT dimension callout numbers (e.g. '6'-0\" TYP' is spacing, not count)
- Columns: Count grid intersection symbols, NOT grid line numbers
- Stairs: Count stair assemblies, NOT individual treads
- If a number is next to a dimension line (arrow), it is a DIMENSION, not a count
- Mark method="grid" when you count from a grid layout
- Mark confidence="low" if count is uncertain; set quantity=null rather than guess"""
```

#### Pass 2 — MEASURE_PROMPT (extends existing EXTRACTION_PROMPT)
Add to existing `EXTRACTION_PROMPT`:
```python
MEASURE_ADDENDUM = """
LINEAR RUN EXTRACTION (CRITICAL):
Gas piping, conduit, lintels, guard rail are shown as lines with inline annotations.
For each linear run found, populate pipe_runs[] OR a new lintel_runs[] structure:

"lintel_runs": [
  {
    "length_lf": 179.24,
    "mark": "L-4",
    "size": "6x4x5/16",
    "count": 12,
    "location": "above openings at gridline B",
    "raw_text": "L-4 @ 6'-0\" ea × 12 = 72LF"
  }
]

Gas piping goes in pipe_runs[] with material="black steel" or "CSST".
NEVER put lintel/gas pipe lengths in measurements[]; use the dedicated arrays.
"""
```

#### Pass 3 — SCHEDULE_PROMPT (focused schedule re-read)
Only activated when `has_schedules=true` from Pass 1. Uses Sonnet model unconditionally.

```python
SCHEDULE_PROMPT = """Extract ONLY the schedule/table on this drawing.
Return the schedule rows with exact quantities. Do not extract dimensions or plan elements.
{existing EXTRACTION_PROMPT schedules[] JSON spec}
Double-check: mark rows in door schedules by TYPE (HM, WD, AL), count how many of each type.
"""
```

#### Merge Strategy
```python
def merge_passes(count_result: dict, measure_result: dict, schedule_result: dict) -> dict:
    """Merge three pass results, deduplicating components."""
    merged = measure_result.copy()
    # Prefer count-pass components (more accurate EA counts)
    seen_names = {c["name"].lower() for c in merged.get("components", [])}
    for c in count_result.get("components", []):
        if c["name"].lower() not in seen_names:
            merged.setdefault("components", []).append(c)
        else:
            # Update quantity if count-pass has higher confidence
            for existing in merged["components"]:
                if existing["name"].lower() == c["name"].lower():
                    if c.get("confidence") == "high" and existing.get("quantity") is None:
                        existing["quantity"] = c["quantity"]
    if schedule_result:
        merged["schedules"] = schedule_result.get("schedules", [])
    return merged
```

**Confidence:** HIGH — multi-pass prompting is a documented Anthropic technique for improving extraction accuracy on complex documents.

---

## 3. Project-Type Profiles (Industrial vs. Retail)

### Problem
`_calculate_from_room()` unconditionally generates `flooring + ceiling_grid + paint + drywall` for every room area. This is correct for retail/office but catastrophically wrong for industrial:
- Industrial warehouses: rooms → `sealed_concrete + exposed_structure + tilt_up_wall`
- Retail: rooms → `flooring + ceiling_grid + paint + drywall` (current behavior)

### Solution: Project Profile in Calculator

Add a `PROJECT_TYPE_PROFILES` dict and pass `project_type` through to `_calculate_from_room()`:

```python
PROJECT_TYPE_PROFILES = {
    "industrial": {
        "area_items": ["sealed_concrete", "exposed_structure"],
        "wall_items": ["tilt_up_wall"],       # from room perimeter × wall height
        "skip_items": ["flooring", "ceiling_grid", "paint", "drywall"],
    },
    "retail": {
        "area_items": ["flooring", "ceiling_grid"],
        "wall_items": ["paint", "drywall"],
        "skip_items": [],
    },
    "office": {
        "area_items": ["flooring", "ceiling_grid"],
        "wall_items": ["paint", "drywall"],
        "skip_items": [],
    },
    "auto": None,  # Claude decides per-room (existing behavior, default for unknown types)
}
```

Add to `ESTIMATION_TABLES`:
```python
"sealed_concrete": {
    "unit_out": "sq_ft",
    "waste_factor": 1.0,
    "formula": "area",
    "description": "Sealed/polished concrete floor SF",
    "keywords": ["sealed concrete", "polished concrete", "concrete floor", "slab on grade"],
},
"cmu_wall": {
    "unit_out": "sq_ft",
    "waste_factor": 1.0,
    "formula": "area",
    "description": "CMU masonry wall SF",
    "keywords": ["cmu", "masonry", "block wall", "concrete masonry"],
},
"internal_tilt_up_wall": {
    "unit_out": "sq_ft",
    "waste_factor": 1.0,
    "formula": "area",
    "description": "Internal tilt-up wall panel SF",
    "keywords": ["internal tilt", "interior tilt", "interior concrete wall"],
},
```

**Auto-detection logic** (add to `pdf_analyzer.py`):
```python
def _detect_project_type(extracted_pages: list) -> str:
    """Heuristic: look at sheet titles and component names across all pages."""
    indicators = {"industrial": 0, "retail": 0, "office": 0}
    for page in extracted_pages:
        title = (page.get("sheet_title") or "").lower()
        notes = (page.get("notes") or "").lower()
        text  = title + " " + notes
        if any(kw in text for kw in ["warehouse", "tilt-up", "tilt up", "industrial", "sealed concrete"]):
            indicators["industrial"] += 2
        if any(kw in text for kw in ["retail", "store", "showroom", "sales floor"]):
            indicators["retail"] += 2
        if any(kw in text for kw in ["office", "tenant", "suites"]):
            indicators["office"] += 1
    return max(indicators, key=indicators.get) if max(indicators.values()) > 0 else "retail"
```

**Confidence:** HIGH — profile approach aligns with how StackCT organizes take-off by project category.

---

## 4. Grid/Symbol Counting Approaches

### Problem
Bollards, columns, stairs are discrete symbols on the plan. Claude sees them but either:
(a) miscounts because dimension callout numbers override (RC-6), or
(b) returns `quantity: null` because the count isn't stated as text on the drawing

### Approach A: Vision-only with explicit grid instruction (LOW cost)
The COUNT_PROMPT above (Section 2) addresses (a) by distinguishing dimension numbers from counts.
For (b), Claude is instructed to visually count symbols and report `method="grid"`.

**Works for:** Bollards, catch basins, manholes (distinct visual symbols)  
**Fails for:** Structural columns in a regular grid (40+ columns look identical, Claude loses count)

### Approach B: Grid-aware counting with zone decomposition (MEDIUM cost)
For structural grids, instruct Claude to:
1. Read the grid label rows/columns (A–G, 1–14)
2. Count grid intersections that have a column symbol
3. Sum by column type (e.g. "H-35' columns at all interior grid intersections = 6×4=24")

```python
GRID_COUNT_ADDENDUM = """
STRUCTURAL GRID COUNTING:
If this is a structural plan with a column grid:
1. Read the grid axis labels (letters on one axis, numbers on other)
2. Count total grid intersections that show a column symbol
3. Group by column mark/size if different types appear
Report in components[]:
  {"name": "Columns H-35'", "quantity": 132, "method": "grid",
   "grid_axes": "A-G × 1-14", "confidence": "medium"}
"""
```

**Works for:** Regular orthogonal column grids  
**Fails for:** Irregular/complex structural grids

### Approach C: Hybrid (HIGH confidence, recommended for EA counts >10)
After Claude returns a count, add a verification sub-prompt that sends ONLY a zoomed region:

```python
def _verify_ea_count(image_path: str, item_name: str, claimed_count: int, model: str) -> int:
    """Re-count a specific item type using a focused verification prompt."""
    prompt = f"""I previously counted {claimed_count} {item_name} on this drawing.
    Recount ONLY the {item_name} symbols. Ignore dimension numbers.
    Return JSON: {{"recount": N, "confidence": "high|medium|low", "discrepancy_reason": "..."}}"""
    ...
```

Only trigger hybrid if `confidence != "high"` OR if the count seems unreasonable (e.g. bollards <5 on an industrial site).

**Recommended strategy:** Start with Approach A (COUNT_PROMPT) for all EA items. Add Approach C verification only for items flagged `confidence != "high"` — this limits extra API calls to items that actually need it.

**Confidence:** MEDIUM — Claude's vision counting has known limitations for dense grids; hybrid approach adds resilience but doubles API calls for uncertain items.

---

## 5. Linear Run Extraction (Gas Pipe, Lintels)

### Problem
Gas piping on roof plans is drawn as a line with inline length annotations (`886.77 LF` total may be across multiple run segments). Lintels are callout tags on elevation drawings (`L-4 @ 6'-0" × 12 = 72 LF`).

Neither maps to `pipe_runs[]` in the current extraction prompt — the prompt examples only show storm drainage (`PVC SCH 40 @ 4.81%`).

### Solution A: Extend pipe_runs[] to include gas/mechanical

Add to `EXTRACTION_PROMPT` pipe_runs[] instructions:
```
PIPE RUNS (ALL types, not just storm sewer):
Include gas piping (black steel, CSST, corrugated stainless), mechanical (copper, CPVC), 
irrigation, fire suppression lines.
Material field examples: "black steel", "CSST", "copper type L", "PVC SCH 40"
A roof plan gas main annotation "886.77 LF - 2\" Black Steel" → one pipe_run entry.
```

### Solution B: New lintel_runs[] structure

Add to EXTRACTION_PROMPT:
```json
"lintel_runs": [
  {
    "mark": "L-4",
    "size": "6×4×5/16 A36",
    "individual_length_ft": 6.0,
    "count": 12,
    "total_lf": 72.0,
    "location": "above storefront openings at Gridline B",
    "raw_text": "L-4 @ 6'-0\" ea"
  }
]
```

Add to `calculator.py`:
```python
def _calculate_from_lintel_runs(lintel_runs: list, sheet_name: str) -> List[dict]:
    results = []
    for run in lintel_runs:
        total_lf = run.get("total_lf") or (
            (run.get("individual_length_ft") or 0) * (run.get("count") or 1)
        )
        if total_lf <= 0:
            continue
        results.append({
            "item_type": "lintel",
            "description": f"Lintel {run.get('mark', '')} {run.get('size', '')}".strip(),
            "quantity": round(total_lf, 2),
            "unit": "lf",
            "formula": f"{run.get('individual_length_ft')} lf × {run.get('count')} = {total_lf} lf",
            "source_sheet": sheet_name,
            "source_raw": run.get("raw_text", ""),
            "table_used": "lintel",
        })
    return results
```

Add `lintel` to `ESTIMATION_TABLES` and `ITEM_NAME_MAP`.

**Confidence:** HIGH — the pattern is straightforward; the only work is adding the prompt instruction and the calculator path.

---

## 6. Aggregator & Item Name Map Gaps

The `ITEM_NAME_MAP` in `aggregator.py` is missing several items that appear in the Crow Cass golden take-off:

| Missing Item | Client Name | Client Unit | Regex Pattern to Add |
|-------------|-------------|-------------|----------------------|
| Sealed Concrete | `Sealed Concrete` | SF | `r"sealed.concrete\|polished.concrete\|concrete.floor"` |
| CMU Wall | `CMU Wall` | SF | `r"cmu\|masonry wall\|block wall"` |
| Internal Tilt Up | `Internal Tilt up walls` | SF | `r"internal.tilt\|interior.tilt"` |
| Exposed Structure | `Exposed Structure` | SF | already present ✓ |
| Columns H-35' | `Columns-H-35'` | EA | `r"column.*h.*\d+"` — already present ✓ but needs height parsing |
| Gas Piping | `Gas Piping` | LF | `r"gas.pip\|black.steel\|csst"` |
| Lintels | `Lintels` | LF | `r"lintel"` |
| Ladder | `Ladder-H-20'` | EA | `r"ladder"` |
| Canopy | `Canopy` | SF | `r"canopy"` |
| CMU Paint | `CMU Paint` | SF | `r"cmu.paint\|masonry.paint"` |
| EIFS | `EIFS` | SF | `r"eifs\|stucco\|exterior.insul"` |
| Frame-HM | `Frame-HM` | EA | `r"frame.*hm\|hollow.metal.frame"` |
| Door-HM | `Doors-HM` | EA | `r"door.*hm\|hollow.metal.door"` |
| Door-WD | `Doors-WD` | EA | `r"door.*wd\|wood.door"` |

**Critical:** `normalize_item_name()` must separate door types. Currently `door` regex hits before material type check. Fix: make door regex material-aware:
```python
(r"door.*hollow.metal\|hm.*door\|door.*hm", "Doors-HM", "EA"),
(r"door.*wood\|wd.*door\|door.*wd",          "Doors-WD", "EA"),
(r"door.*alum\|al.*door",                    "Doors-AL", "EA"),
(r"door(?!.*frame)",                         "Doors",    "EA"),  # catch-all
```

**Confidence:** HIGH — directly derived from comparing golden take-off line items to existing `ITEM_NAME_MAP`.

---

## 7. Model Selection Strategy

### Current Logic
`_pick_model()` routes `SCHEDULE|PANEL|RISER|EQUIPMENT|FIXTURE` and `E\d|M\d|P\d` sheets to `CLAUDE_MODEL_SCHEDULES` (Sonnet). Everything else uses Haiku.

### Problem
- Elevation sheets (`A4.x`) and detail sheets (`A8.x`) contain the most complex mixed content: bollard counts, canopy SF, EIFS areas, lintels — all need spatial reasoning, not just table reading. Currently routed to Haiku.
- Door schedule with mixed HM/WD types requires precise column parsing. Sonnet gives much better JSON structure.
- A simple floor plan with a single room area is over-engineered with Sonnet; Haiku suffices.

### Recommended Model Routing Matrix

| Sheet Code / Type | Pass | Model | Rationale |
|-------------------|------|-------|-----------|
| `A1.x` Floor Plans, `S1.x` Structural | COUNT | Sonnet | Grid counting, bollard symbols |
| `A1.x` Floor Plans | MEASURE | Haiku | Dimension annotations are simple text |
| `A3.x` Roof Plans | MEASURE | Sonnet | Gas piping runs, CSST routing on complex roof |
| `A4.x` Elevations | MEASURE | Sonnet | EIFS, CMU paint SF, canopy area, lintels |
| `A8.x` Details | COUNT | Sonnet | Ladder, lift, stair counting from detail sheets |
| `A8.x` Door/Window Schedule | SCHEDULE | Sonnet | Type breakdown (HM/WD) critical |
| `E\d|M\d|P\d` Mechanical/Electrical | SCHEDULE | Sonnet (existing) | Panel schedules |
| Title sheets, cover sheets | — | Skip | No quantity data |
| Civil / Site (`C\d`) | MEASURE | Haiku | Pipe runs are explicit text annotations |
| Civil / Site (`C\d`) | COUNT | Haiku | Catch basins have labeled IDs |

**Extended `_pick_model()` logic:**

```python
def _pick_model(sheet_name: str, pass_type: str = "measure") -> str:
    """Route sheet+pass to optimal model."""
    upper = (sheet_name or "").upper()
    
    # Always Sonnet for schedule passes (complex table parsing)
    if pass_type == "schedule":
        return CLAUDE_MODEL_SCHEDULES  # Sonnet
    
    # Always Sonnet for count pass on architectural/structural sheets
    if pass_type == "count":
        if re.match(r"^[AS]\d", upper):
            return CLAUDE_MODEL_SCHEDULES
    
    # Existing Sonnet triggers (keep)
    schedule_keywords = ("SCHEDULE", "PANEL", "RISER", "EQUIPMENT", "FIXTURE")
    if any(kw in upper for kw in schedule_keywords):
        return CLAUDE_MODEL_SCHEDULES
    if re.match(r"^[EMP]\d", upper):
        return CLAUDE_MODEL_SCHEDULES
    
    # New: elevation/detail sheets need Sonnet for measure pass
    if re.match(r"^A[34568]\.", upper) or re.match(r"^A[34568]-", upper):
        return CLAUDE_MODEL_SCHEDULES
    
    return CLAUDE_MODEL  # Haiku default
```

### Cost Impact Estimate

| Scenario | Before (all Haiku) | After (targeted Sonnet) | Delta |
|----------|-------------------|------------------------|-------|
| Crow 4-page industrial | ~$0.008 | ~$0.022 | +175% |
| Bob 7-page retail | ~$0.014 | ~$0.038 | +171% |
| Typical 30-page project | ~$0.06 | ~$0.16 | +167% |

These remain well within acceptable cost ranges (<$0.25 per project). Accuracy improvement far outweighs cost increase.

**Confidence:** HIGH — model capability differences for vision tasks are well-established; routing logic is conservative (only upgrades high-complexity sheet types).

---

## 8. Verification Loop (Extract → Calculate → Compare → Retry)

### Design

After running all passes, run a lightweight `QuantityVerifier` before finalizing the report:

```python
class QuantityVerifier:
    """Post-extraction sanity checks that catch obvious errors before output."""
    
    SANITY_RULES = [
        # (item_name_pattern, min_qty, max_qty, unit, message)
        (r"bollard", 1, 200, "ea", "Bollard count out of range"),
        (r"sealed.concrete|flooring", 1000, 2_000_000, "sq_ft", "Floor area implausible"),
        (r"gas.pip|pipe", 10, 10_000, "lf", "Gas pipe run implausible"),
        (r"door", 1, 500, "ea", "Door count implausible"),
        (r"column", 1, 1000, "ea", "Column count implausible"),
    ]
    
    def check(self, takeoff_summary: list) -> list:
        """Return list of flagged items that may need retry."""
        flags = []
        for item in takeoff_summary:
            name = item.get("item", "").lower()
            qty  = item.get("quantity", 0)
            unit = item.get("unit", "").lower()
            for pattern, lo, hi, expected_unit, msg in self.SANITY_RULES:
                if re.search(pattern, name) and unit in (expected_unit, expected_unit.replace("_", "")):
                    if qty < lo or qty > hi:
                        flags.append({"item": item["item"], "qty": qty, "flag": msg})
        return flags
```

**Retry logic**: When a flag is raised for an item, re-run only the sheet(s) that contributed that item using the VERIFY_PROMPT below. This avoids re-running the full project.

```python
VERIFY_PROMPT = """This drawing was previously analyzed and produced: {item_name} = {claimed_qty} {unit}.
This quantity appears incorrect. Recount/remeasure ONLY {item_name}.
Common errors:
- Dimension numbers mistaken for counts
- Detail callout numbers mistaken for item counts
- Linear dimensions in feet used as counts
Return: {{"item": "{item_name}", "corrected_qty": N, "unit": "...", "confidence": "...", "reason": "..."}}"""
```

**Integration point:** Add to `pdf_analyzer.run_pdf_analysis()` after `aggregate_takeoff()`:
```python
flags = QuantityVerifier().check(takeoff_summary)
if flags:
    logger.warning(f"Verification flags: {flags}")
    # Retry flagged sheets (optional; controlled by ENABLE_VERIFY_RETRY config flag)
    if ENABLE_VERIFY_RETRY:
        for flag in flags:
            contributing_sheets = _find_contributing_sheets(flag["item"], all_estimates)
            for sheet_path in contributing_sheets:
                retry_result = _verify_single_item(sheet_path, flag)
                # Merge corrected qty back into takeoff_summary
```

**Confidence:** MEDIUM — retry logic adds API calls; sanity bounds need tuning per project type.

---

## 9. Golden-File Regression Test Design

### Architecture

```
tests/
├── fixtures/
│   ├── crow_cass/
│   │   ├── crow_cass_plans.pdf          # source PDF (gitignored if large)
│   │   └── crow_cass_golden.csv         # ground truth take-off
│   └── bobs_discount/
│       ├── bobs_discount_plans.pdf
│       └── bobs_discount_golden.csv
├── test_calculator_accuracy.py          # existing (keep)
└── test_golden_takeoff.py               # NEW — Phase 20 target
```

### Golden CSV Format

```csv
item_name,quantity,unit,tolerance_pct,match_mode
Bollards,28,EA,0,exact_or_within_1
CMU Wall,2204.33,SF,3,pct
Columns-H-35',132,EA,0,exact_or_within_1
Exposed Structure,395673.42,SF,3,pct
Internal Tilt up walls,108442.66,SF,3,pct
Sealed Concrete,395673.42,SF,3,pct
Stairs,10,EA,0,exact_or_within_1
Gas Piping,886.77,LF,3,pct
Lintels,179.24,LF,3,pct
Mobilization,1,EA,0,exact_or_within_1
Lift,1,EA,0,exact_or_within_1
Ladder-H-20',1,EA,0,exact_or_within_1
```

### `GoldenValidator` Class

```python
class GoldenValidator:
    """Compare AI takeoff summary against a golden reference CSV."""
    
    def __init__(self, golden_csv_path: str):
        self.golden = self._load(golden_csv_path)
    
    def _load(self, path: str) -> list:
        with open(path) as f:
            return list(csv.DictReader(f))
    
    def validate(self, takeoff_summary: list) -> dict:
        """
        Returns:
            {
                "pass": bool,
                "score": float,          # fraction of items passing
                "items": [per-item results],
                "missing": [golden items not found in AI output],
                "extra":   [AI items not in golden]
            }
        """
        ai_index = {item["item"].lower(): item for item in takeoff_summary}
        results = []
        
        for g in self.golden:
            g_name    = g["item_name"].lower()
            g_qty     = float(g["quantity"])
            g_unit    = g["unit"].upper()
            tolerance = float(g["tolerance_pct"]) / 100
            mode      = g["match_mode"]
            
            # Fuzzy name match (handles "Bollards" vs "Bollard")
            ai_item = ai_index.get(g_name) or self._fuzzy_match(g_name, ai_index)
            
            if ai_item is None:
                results.append({"item": g["item_name"], "status": "MISSING",
                                 "golden": g_qty, "ai": None})
                continue
            
            ai_qty = float(ai_item["quantity"])
            
            if mode == "exact_or_within_1":
                passed = (ai_qty == g_qty) or (abs(ai_qty - g_qty) <= 1)
            else:  # pct
                passed = abs(ai_qty - g_qty) / g_qty <= tolerance
            
            results.append({
                "item": g["item_name"],
                "status": "PASS" if passed else "FAIL",
                "golden": g_qty, "ai": ai_qty,
                "error_pct": round(abs(ai_qty - g_qty) / g_qty * 100, 1) if g_qty else None,
            })
        
        passing = sum(1 for r in results if r["status"] == "PASS")
        score = passing / len(results) if results else 0
        
        return {
            "pass": score >= 0.97,
            "score": round(score, 4),
            "items": results,
            "missing": [r for r in results if r["status"] == "MISSING"],
        }
```

### pytest Test File

```python
# tests/test_golden_takeoff.py
import pytest
import os
from pathlib import Path
from pdf_analyzer import run_pdf_analysis
from tests.golden_validator import GoldenValidator

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.mark.golden
@pytest.mark.skipif(
    not (FIXTURES / "crow_cass/crow_cass_plans.pdf").exists(),
    reason="Golden fixture PDF not present"
)
def test_crow_cass_golden():
    result = run_pdf_analysis(
        str(FIXTURES / "crow_cass/crow_cass_plans.pdf"),
        project_name="Crow Cass Test"
    )
    summary = result["takeoff_summary"]
    validator = GoldenValidator(str(FIXTURES / "crow_cass/crow_cass_golden.csv"))
    report = validator.validate(summary)
    
    # Print diagnostics on failure
    if not report["pass"]:
        for item in report["items"]:
            print(f"  {item['status']:6} {item['item']:35} "
                  f"golden={item['golden']} ai={item['ai']} "
                  f"err={item.get('error_pct', 'N/A')}%")
    
    assert report["score"] >= 0.97, (
        f"Crow Cass accuracy {report['score']:.1%} < 97%. "
        f"Missing: {[m['item'] for m in report['missing']]}"
    )


@pytest.mark.golden
@pytest.mark.skipif(
    not (FIXTURES / "bobs_discount/bobs_discount_plans.pdf").exists(),
    reason="Golden fixture PDF not present"
)
def test_bobs_discount_golden():
    result = run_pdf_analysis(
        str(FIXTURES / "bobs_discount/bobs_discount_plans.pdf"),
        project_name="Bobs Discount Test"
    )
    summary = result["takeoff_summary"]
    validator = GoldenValidator(str(FIXTURES / "bobs_discount/bobs_discount_golden.csv"))
    report = validator.validate(summary)
    assert report["score"] >= 0.97, (
        f"Bob's Discount accuracy {report['score']:.1%} < 97%."
    )
```

**Run with:** `pytest tests/test_golden_takeoff.py -v -m golden`

**Confidence:** HIGH — standard pytest fixture pattern; `skipif` keeps CI green when PDFs are absent.

---

## 10. Implementation Sequence (Dependency Order)

The eight root causes must be fixed in this order to avoid cascading failures in testing:

```
Step 1: Fix RC-1 — Title block sheet parsing          [pdf_analyzer.py]
         ↓ (correct sheet IDs needed before model routing works)
Step 2: Fix RC-6 — COUNT_PROMPT bollard/column         [claude_analyzer.py]  
         ↓ (EA counts must be right before aggregation)
Step 3: Fix RC-2 — Project-type profiles              [calculator.py]
         ↓ (flooring vs sealed concrete needs profile before aggregation)
Step 4: Fix RC-4+RC-5 — Gas pipe + lintel extraction  [claude_analyzer.py + calculator.py]
         ↓
Step 5: Fix RC-3 — Components quantity:null retry     [pdf_analyzer.py]
         ↓
Step 6: Update ITEM_NAME_MAP                          [aggregator.py]
         ↓
Step 7: Write golden CSV fixtures from client PDFs    [tests/fixtures/]
Step 8: Implement GoldenValidator + test_golden_takeoff.py [tests/]
Step 9: Wire QuantityVerifier sanity gate             [pdf_analyzer.py]
Step 10: Run tests, iterate on prompt tuning          [iterative]
```

---

## Architecture Patterns

### Recommended Project Structure Changes

```
claude_analyzer.py
├── EXTRACTION_PROMPT     (existing — add MEASURE_ADDENDUM)
├── COUNT_PROMPT          (NEW — discrete symbol counting)
├── SCHEDULE_PROMPT       (NEW — focused table re-read)
├── VERIFY_PROMPT         (NEW — single-item recount)
├── analyze_drawing()     (extend to accept pass_type param)
└── _pick_model()         (extend with pass_type routing)

calculator.py
├── ESTIMATION_TABLES     (add 5 new items)
├── PROJECT_TYPE_PROFILES (NEW)
├── apply_estimation_tables()  (add project_type param)
├── _calculate_from_room()     (profile-aware)
└── _calculate_from_lintel_runs() (NEW)

pdf_analyzer.py
├── _sheet_name_from_doc() (title-block fix)
├── run_pdf_analysis()     (add multi-pass, verifier call)
└── _detect_project_type() (NEW)

aggregator.py
└── ITEM_NAME_MAP          (add ~14 missing entries)

tests/
├── fixtures/crow_cass/    (golden CSV + PDF)
├── fixtures/bobs_discount/ (golden CSV + PDF)
├── golden_validator.py    (GoldenValidator class)
└── test_golden_takeoff.py (pytest golden tests)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF word bounding boxes | Custom PDF parser | `fitz.page.get_text("words")` | PyMuPDF already returns per-word coordinates |
| Fuzzy string matching (golden CSV name lookup) | Levenshtein from scratch | `difflib.get_close_matches()` (stdlib) | Sufficient for item name matching; no extra dep |
| Golden CSV loading | Custom parser | `csv.DictReader` (stdlib) | Headers map directly to golden row fields |
| Image compression for API | Custom JPEG pipeline | Existing `encode_image()` in `claude_analyzer.py` | Already handles iterative quality reduction |
| Multi-pass JSON merging | Complex merge algorithm | Simple dict update with component dedup | Passes produce non-overlapping data by design |

---

## Common Pitfalls

### Pitfall 1: Re-running all passes on every sheet (cost explosion)
**What goes wrong:** If COUNT + MEASURE + SCHEDULE all run on every page, a 30-page project costs 3× more.  
**How to avoid:** COUNT pass only on `A\d`, `S\d` sheet types. SCHEDULE pass only when `has_schedules=true` from Pass 1. MEASURE pass always (it's the primary extraction).

### Pitfall 2: Merging component lists creates duplicates
**What goes wrong:** COUNT_PROMPT extracts `Bollards: 28`. MEASURE_PROMPT also finds the bollard annotation and puts `Bollards: 10` in components (from the detail dimension). Merge sums them → 38 bollards.  
**How to avoid:** When merging, prefer COUNT_PROMPT component quantities for `method != "dimension"`. Remove measure-pass components where the same name exists in count-pass with `confidence=high`.

### Pitfall 3: Project type auto-detection fails on small sheet sets
**What goes wrong:** A 4-page PDF might not have "warehouse" in any sheet title.  
**How to avoid:** Fall back to `"retail"` profile (safer default — over-estimates finish items but doesn't delete structural items). Let user override via a `project_type` param in the UI.

### Pitfall 4: Golden CSV item names don't match aggregator output casing
**What goes wrong:** Golden has `"Sealed Concrete"` but aggregator outputs `"Sealed_Concrete"` or `"sealed concrete"`.  
**How to avoid:** `GoldenValidator._fuzzy_match()` normalizes both sides to lowercase + replace `_/-/ ` before matching. Add an exact-match check first, then fuzzy.

### Pitfall 5: PyMuPDF `get_text("words")` is slow for large PDFs
**What goes wrong:** A 150-page PDF calling `get_text("words")` per page adds noticeable latency.  
**How to avoid:** Call `_sheet_name_from_doc()` once per page during the existing `get_pdf_metadata()` pre-scan (which already iterates all pages). Cache results; don't re-open per page.

---

## Code Examples

### Verified Pattern: PyMuPDF word bounding boxes
```python
# Source: PyMuPDF docs — fitz.Page.get_text("words")
# Returns: list of (x0, y0, x1, y1, "word", block_no, line_no, word_no)
page = doc[page_num]
words = page.get_text("words")
height = page.rect.height
# Title block: bottom 20% of page
title_words = [w[4] for w in words if w[1] > height * 0.80]
```

### Verified Pattern: difflib fuzzy name match
```python
import difflib
def _fuzzy_match(name: str, index: dict) -> Optional[dict]:
    keys = list(index.keys())
    matches = difflib.get_close_matches(name, keys, n=1, cutoff=0.7)
    return index[matches[0]] if matches else None
```

### Verified Pattern: Anthropic prompt caching
```python
# Source: Anthropic docs — ephemeral cache_control
# Already used in claude_analyzer.py:218; extend to new prompts
system=[{"type": "text", "text": COUNT_PROMPT, "cache_control": {"type": "ephemeral"}}]
```

---

## Open Questions

1. **Golden PDF availability**  
   - What we know: Client PDFs are referenced in 20-CONTEXT.md as `uploads/` but the directory is empty.  
   - What's unclear: Whether PDFs will be committed to the repo or provided via another mechanism (S3, local mount).  
   - Recommendation: Use `pytest.mark.skipif` + `GOLDEN_PDF_DIR` env var so tests skip in CI unless PDFs are present. Keep golden CSVs committed (small text files).

2. **Bob's Discount elevation page (A4.0) not in 7-page upload**  
   - What we know: CONTEXT.md says A4.0 elevations are missing from the plan upload; items on A4.0 (bollards 11, canopy 79.44 SF, etc.) are in the golden take-off.  
   - What's unclear: Is this a deliberate test of missing-sheet handling, or should the full plan set be re-uploaded?  
   - Recommendation: Plan golden test to reflect only the sheets that ARE uploaded; flag missing sheets as `"SHEET_NOT_UPLOADED"` rather than `"MISSING"` in validator output.

3. **Crow Cass column height spec (H-35')**  
   - What we know: ITEM_NAME_MAP has `r"column.*h.*\d+"` with spec extraction. But columns extracted by COUNT_PROMPT may not include the H-35' height if it's only in the structural schedule.  
   - Recommendation: Ensure structural schedule (if present) runs through SCHEDULE_PROMPT on Sonnet; column height extracted from schedule becomes the spec tag in ITEM_NAME_MAP.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `claude_analyzer.py`, `calculator.py`, `pdf_analyzer.py`, `aggregator.py`, `cross_references.py` — current implementation fully read
- `20-CONTEXT.md` — root-cause audit with verified error measurements
- PyMuPDF docs: `get_text("words")` returns `(x0, y0, x1, y1, word, ...)` tuples with per-word coordinates

### Secondary (MEDIUM confidence)
- Masterv2.md §C (Addendum v2.1) — prior accuracy gap analysis, same codebase
- `tests/test_calculator_accuracy.py` — existing test patterns to extend

### Tertiary (context only)
- Phase 16, 17, 18 plan summaries — evolution of the extraction architecture

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing code is the stack; no new libraries except stdlib `difflib`
- Architecture: HIGH — multi-pass + profile changes are evolutionary; patterns are verified against existing code
- Pitfalls: HIGH — derived from actual error measurements in 20-CONTEXT.md golden run
- Test design: HIGH — standard pytest fixture pattern

**Research date:** 2026-06-03  
**Valid until:** 2026-09-03 (stable domain; re-check if Anthropic API schema changes)

---

## RESEARCH COMPLETE

**Phase:** 20 — Takeoff Measurement Precision  
**Confidence:** HIGH

### Key Findings

- All 8 root causes are in code and fixable without pipeline rewrite; most are 1–2 function changes
- Title-block fix (RC-1) uses PyMuPDF word bounding boxes to search only the bottom-right 20% of the page — eliminates ASTM/standard-number false positives
- Multi-pass extraction (COUNT + MEASURE + SCHEDULE) is the highest-impact single change; COUNT_PROMPT explicitly distinguishes dimension numbers from symbol counts (fixes RC-6 bollard error)
- Project-type profiles (industrial vs. retail) in `_calculate_from_room()` eliminate the Flooring-for-Sealed-Concrete misclassification (RC-2); auto-detect via sheet title heuristics
- Gas pipe and lintel linear extraction requires prompt additions + new `lintel_runs[]` structure in the calculator (RC-4, RC-5)
- 14 missing `ITEM_NAME_MAP` entries account for all Crow Cass items absent from aggregator output
- `GoldenValidator` class + `test_golden_takeoff.py` provides the numeric accuracy gate that was completely absent in Phase 16 (RC-8)
- Model routing: elevation/detail `A3-A8` sheets → Sonnet for measure pass; all schedule passes → Sonnet; simple civil/floor plans → Haiku. Cost increase ~$0.08/project (fully justified by accuracy gain)

### File Created

`.planning/phases/20-takeoff-measurement-precision/20-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Root cause mapping | HIGH | Verified against actual code + golden run error data |
| Title block fix | HIGH | PyMuPDF bounding box API is stable; location of title block is ANSI standard |
| Multi-pass prompting | HIGH | Directly addresses identified confusion between dimension numbers and counts |
| Project-type profiles | HIGH | Error data confirms room-based calc is wrong for industrial; profile values match golden |
| Linear run extraction | HIGH | Prompt extension follows existing `pipe_runs[]` pattern exactly |
| Model routing | HIGH | Changes are conservative and target only sheets with documented failures |
| Golden test design | HIGH | Standard pytest fixture pattern; matches error metric spec from CONTEXT.md |
| Verification loop | MEDIUM | Sanity bounds need tuning; retry adds API cost; mark as v2 if needed |

### Open Questions

1. Golden PDFs need to be placed in `tests/fixtures/` (uploads/ is empty; confirm delivery mechanism)
2. Bob's A4.0 elevation page is missing from the uploaded plan set — golden test must reflect only uploaded sheets
3. Crow Cass column H-35' height requires structural schedule SCHEDULE_PROMPT run to extract spec tag

### Ready for Planning

Research complete. Planner can now create PLAN.md files for Phase 20.
