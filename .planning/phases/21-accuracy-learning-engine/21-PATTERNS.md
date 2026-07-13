# Phase 21: Accuracy & Learning Engine (v3) - Pattern Map

**Mapped:** 2026-07-13
**Files analyzed:** 27 new/modified files
**Analogs found:** 22 / 27 (5 with no close analog — see final section)

All analog paths are current flat-root paths. After the V3-STRUCT-01 package move they relocate under `src/bobbytailor/` — the excerpts and line numbers below refer to the pre-move files, which the move commit preserves byte-identical (`git mv` only, no content edits).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `deterministic/dimensions.py` (NEW — Recipe A dimension-line association) | extraction utility | file-I/O (PDF text+geometry) | `footprint_takeoff.py` + `scale_extraction.py` | exact |
| `deterministic/viewports.py` (NEW — viewport segmentation) | extraction utility | transform | `geometry_takeoff.py` `_measure_viewports` | role-match |
| `deterministic/scale_solver.py` (NEW — RANSAC per-viewport solve, resolve_scale v2) | service | transform | `scale_extraction.py` + `geometry_takeoff.resolve_scale` | exact |
| `deterministic/walls.py` (NEW — Recipe B parallel-pair walls) | extraction utility | transform | `geometry_takeoff.py` `_segments`/`RawGeometry` | role-match |
| `deterministic/rooms.py` (NEW — Recipe C polygonize rooms) | extraction utility | transform | `footprint_takeoff.py` (measure → legend conversion) | role-match |
| `deterministic/symbols.py` (NEW — Recipe D block clustering) | extraction utility | transform | `geometry_takeoff._segments` (primitives only) | partial |
| `deterministic/tables.py` (NEW — generalize schedule reader beyond doors) | extraction utility | file-I/O | `schedule_extraction.py` | exact |
| `vision/ensemble.py` (NEW — N-run voting + tiled counting dedup) | service | request-response (API fan-out) | `claude_analyzer.analyze_drawing` (call/cost pattern) | partial |
| `vision/fusion.py` (NEW — geometry-proposes/vision-disposes, provenance merge) | service | transform | `claude_analyzer.merge_passes` + `apply_accuracy_rules` | role-match |
| `vision/prompts.py` + structured outputs (REFACTOR of claude_analyzer prompts) | config/service | request-response | `claude_analyzer.py` prompt constants + `_build_user_message` | exact |
| `sheet_pass_matrix.py` MODEL_ROUTING v2 (MODIFY — config-driven slugs) | config | n/a | `sheet_pass_matrix.py` + `config.py` env pattern | exact |
| `learning/store.py` (NEW — corrections/vocabulary/assumptions/manifests tables) | model/store | CRUD | `stackct_store.py` (schema versioning) + `job_store.py` (lazy init) | exact |
| `learning/distill.py` (NEW — rebuild distilled tables from append-only log) | service | batch | `stackct_store.migrate_from_json_caches` (idempotent import) | role-match |
| `learning/retrieval.py` (NEW — LearnedContext bundle + prompt injection) | service | CRUD read | `stackct_store.get_plans` + `takeoff_pipeline._build_count_hint` | role-match |
| `web/app.py` `create_app()` factory (NEW) | config/bootstrap | request-response | `app.py` (flat module — no factory exists) | partial |
| `web/blueprints/verify.py` (MOVE+MODIFY — verify/scale endpoints feed learning store) | controller | request-response | `app.py` lines 1329–1619 | exact |
| `web/blueprints/{auth,projects,runs,reports,settings,jobs}.py` (MOVE) | controller | request-response | `app.py` route groups (same endpoint pattern as verify) | exact |
| `web/jobs_runtime.py` (NEW — owns in-memory jobs dict + Playwright threads) | service | event-driven | `app.py` jobs dict (primitive-payload thread rule) | role-match |
| `takeoff_pipeline.py` (MODIFY — verify-retry real impl, provenance, RunSettings) | orchestrator | pipeline | itself (`QuantityVerifier`, analyzer injection) | exact |
| `aggregator.py` (MODIFY — learned vocabulary before ITEM_NAME_MAP) | service | transform | `aggregator.normalize_item_name` | exact |
| `calculator.py` (MODIFY — learning assumptions for wall height etc.) | service | transform | `takeoff_pipeline._manifest_wall_height` | exact |
| `scraper.py` (MODIFY — parity: drop `companion_present=False` hardcode :787) | entry point | pipeline | `pdf_analyzer.py` (the other entry point) | exact |
| `pyproject.toml` + root import shims (NEW) | config | n/a | none (no pyproject exists; sys.path insert in `scripts/`) | none |
| `tests/test_dimensions.py`, `test_walls.py`, `test_rooms.py`, `test_symbols.py` (NEW) | test | n/a | `tests/test_takeoff_generalization.py` fixture pattern | exact |
| `tests/fixtures/*/scale_truth.json` + scale-solver gate tests (NEW) | test | n/a | `tests/test_takeoff_generalization.py` expected-constraints pattern | role-match |
| `tests/` record/replay analyzer for fusion (NEW) | test | n/a | `TakeoffPipeline(analyzer=...)` injection + conftest | exact |
| `scripts/vision_only_benchmark.py` (MODIFY — provenance split, reproducibility gate) | benchmark | batch | itself | exact |

## Pattern Assignments

### `deterministic/dimensions.py` (extraction utility, file-I/O)

**Analog:** `footprint_takeoff.py` (dimension parsing + rotation) and `scale_extraction.py` (char-level rawdict)

**Dimension-token regex + plausibility-bounds pattern** (`footprint_takeoff.py` lines 29–65):

```python
# Feet-inch dimension token: "1136' - 0\"", "350'-0", "55' - 6\"", "60'".
_DIM_RE = re.compile(r"^\s*(\d{2,4})\s*'\s*[-–]?\s*(\d{1,2})?\s*\"?\s*$")

MIN_OVERALL_FT = 50.0
MAX_OVERALL_FT = 2000.0

def _parse_feet(text: str) -> Optional[float]:
    m = _DIM_RE.match(text or "")
    if not m:
        return None
    feet = int(m.group(1))
    inches = int(m.group(2)) if m.group(2) else 0
    if inches >= 12:
        return None
    val = feet + inches / 12.0
    if not (MIN_OVERALL_FT <= val <= MAX_OVERALL_FT):
        return None
    return val
```

Extend the regex per RESEARCH Recipe A to fractions (`25'-4 1/2"`) and reuse the stacked-fraction char-split from `scale_extraction._paper_inches_from_chars` (below).

**Text-rotation (`line["dir"]`) handling** (`footprint_takeoff.py` lines 68–94) — the pattern for orienting dimension strings; the new module extends the axis split to full corridor geometry:

```python
def _axis_dims(page) -> Tuple[List[float], List[float]]:
    data = page.get_text("dict")
    ...
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            dir_ = line.get("dir", (1.0, 0.0)) or (1.0, 0.0)
            dx, dy = dir_[0], dir_[1]
            for span in line.get("spans", []):
                ft = _parse_feet(span.get("text", ""))
                if ft is None:
                    continue
                if abs(dx) >= abs(dy):
                    horiz.append(ft)
                else:
                    vert.append(ft)
```

**Stacked-fraction char recovery** (`scale_extraction.py` lines 102–119) — reuse for fractional inches in dim strings:

```python
    digits = [(x, y, c) for x, y, c in kept if c.isdigit()]
    ...
    ys = [y for _, y, _ in digits]
    y_min, y_max = min(ys), max(ys)
    # Stacked fraction: a meaningful vertical split between numerator/denominator.
    if (y_max - y_min) >= 1.5:
        mid = (y_min + y_max) / 2.0
        top = [(x, c) for x, y, c in digits if y < mid]      # numerator (higher)
        bot = [(x, c) for x, y, c in digits if y >= mid]     # denominator (lower)
        if top and bot:
            num = int("".join(c for _, c in sorted(top)))
            den = int("".join(c for _, c in sorted(bot)))
            if den:
                return num / den
```

**Result-dataclass + confidence + needs_review pattern** (`footprint_takeoff.py` lines 38–51) — every deterministic extractor returns this shape:

```python
@dataclass
class Footprint:
    width_ft: float
    depth_ft: float
    area_sf: float
    perimeter_lf: float
    confidence: str          # "high" | "medium" | "low"
    page_index: int
    sheet_name: str = ""
    needs_review: bool = False
    review_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
```

New `DimensionSample(feet, points, text_bbox, line_bbox, rotation, score)` should follow this exact shape (dataclass, `to_dict` via `asdict`).

**Lazy fitz import + open/close pattern** (`footprint_takeoff.py` lines 221–264):

```python
def extract_building_footprint(pdf_path: str) -> Optional[Footprint]:
    import fitz  # PyMuPDF — imported lazily so importing this module is cheap
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Footprint: cannot open %s: %s", pdf_path, exc)
        return None
    try:
        ...
    finally:
        doc.close()
```

What the analog does NOT provide: STRtree corridor search and terminator verification (arrowheads/extension lines). That is new code — but note the anti-pattern it replaces: `geometry_takeoff._calibrate_from_dimensions` (lines 124–159) is the brute-force nearest-segment loop whose mispairing caused the 1"=24' failure. Do not copy that loop; replace it.

---

### `deterministic/scale_solver.py` (service, transform)

**Analog:** `scale_extraction.py` (ladder philosophy) + `geometry_takeoff.resolve_scale` (priority/confidence contract)

**Ladder snap as cross-check** (`scale_extraction.py` lines 35–58) — keep intact; v2 demotes it from primary source to cross-check per RESEARCH §2:

```python
_ARCH_PAPER_IN = [1/32, 1/16, 3/32, 1/8, 3/16, 1/4, 3/8, 1/2, 3/4, 1.0, 1.5, 3.0]
ARCH_FPI = sorted({round(1.0 / p, 6) for p in _ARCH_PAPER_IN})
ENG_FPI = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 200.0]
_ALL_FPI = sorted(set(ARCH_FPI) | set(ENG_FPI))
_SNAP_TOL = 0.04

def snap_fpi(fpi: Optional[float]) -> Optional[float]:
    """Snap *fpi* to the nearest standard scale within tolerance, else None."""
    if not fpi or fpi <= 0:
        return None
    best, best_err = None, 1e9
    for cand in _ALL_FPI:
        err = abs(fpi - cand) / cand
        if err < best_err:
            best, best_err = cand, err
    return best if best_err <= _SNAP_TOL else None
```

**ScaleResult contract to preserve** (`geometry_takeoff.py` lines 39–47) — downstream (`scale_recalc`, calibration UI, reporter) consumes this dict shape; v2 adds methods like `dimension_solve` but keeps the fields:

```python
@dataclass
class ScaleResult:
    feet_per_point: Optional[float]
    confidence: str            # high | medium | low | none
    method: str                # override | printed_scale | dimension_calibration | none
    detail: str = ""
```

**Priority-chain structure** (`geometry_takeoff.resolve_scale`, lines 75–111) — copy the shape, reorder per RESEARCH pitfall 11 to: override > dimension-solved > printed (cross-check) > learned prior:

```python
def resolve_scale(page, scale_text=None, override_feet_per_inch=None) -> ScaleResult:
    # (1) Explicit override — most reliable.
    if override_feet_per_inch and override_feet_per_inch > 0:
        return ScaleResult(
            feet_per_point=override_feet_per_inch / POINTS_PER_INCH,
            confidence="high", method="override",
            detail=f"{override_feet_per_inch} ft per inch (supplied)",
        )
    # (2) ... each tier returns a ScaleResult with method + confidence + detail
```

**Positioned callout anchors for viewport binding** (`scale_extraction.extract_scale_callouts`, lines 162–188) — returns `[{feet_per_inch, x, y}]`; the viewport module consumes these as title-anchor signals.

---

### `deterministic/viewports.py` (extraction utility, transform)

**Analog:** `geometry_takeoff._measure_viewports` (lines 259–331)

**Per-viewport bucketing + dominant selection** — the existing nearest-anchor bucketing is the fallback tier; the new module adds clip-rect/gutter detection above it. The dominant-viewport selection and confidence math are directly reusable:

```python
    dom = max(viewports, key=lambda v: (v["footprint_sf"] or 0.0,
                                        v["total_linework_lf"] or 0.0))
    dom["dominant"] = True
    ...
    scale_segs = sum(v["segment_count"] for v in viewports
                     if v["feet_per_inch"] == fpi)
    share = scale_segs / total_segs if total_segs else 0
    n_scales = len({v["feet_per_inch"] for v in viewports})
    conf = "high" if (n_scales == 1 or share >= 0.6) else "medium"
```

Note the required change: dominance must be by *real* area after each viewport's own solved scale (RESEARCH §2 "main-plan selection"), which this code already approximates via `footprint_sf` — keep that, replace the scale source with the dimension solve.

**Viewport record shape to keep** (`geometry_takeoff.py` lines 286–295) — persisted in `scale_calibration.json`, consumed by the UI:

```python
        viewports.append({
            "feet_per_inch": fpi,
            "anchor": {"x": round(c["x"], 1), "y": round(c["y"], 1)},
            "segment_count": len(vsegs),
            "raw": raw.to_dict(),
            "footprint_sf": vals["footprint_sf"],
            ...
            "dominant": False,
        })
```

---

### `deterministic/walls.py`, `deterministic/rooms.py`, `deterministic/symbols.py` (extraction utilities, transform)

**Analog:** `geometry_takeoff.py` `_segments` (primitive harvest) + `RawGeometry` (points-until-scale-bound) + `footprint_takeoff.footprint_to_legend` (quantity → legend handoff)

**Segment harvest from get_drawings()** (`geometry_takeoff.py` lines 50–66) — the shared primitive reader all three modules build on (extend with `"c"` Bézier flattening and `"qu"` quads per RESEARCH pitfall 6):

```python
def _segments(page) -> List[Tuple[float, float, float, float]]:
    """All straight line segments on the page as (x0,y0,x1,y1) in PDF points."""
    out = []
    for path in page.get_drawings():
        for it in path["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                out.append((a.x, a.y, b.x, b.y))
            elif it[0] == "re":
                r = it[1]
                out.extend([...four rect edges...])
    return out
```

**Keep-everything-in-points-until-scale-bound pattern** (`geometry_takeoff.py` lines 164–178) — `WallSegment`/room polygons must mirror `RawGeometry`: store point measures, convert via `scale_recalc.recompute`-style pure math so human scale corrections rescale instantly without re-extraction:

```python
@dataclass
class RawGeometry:
    """Scale-INDEPENDENT geometry measures in PDF points.

    These are captured once; multiplying by the (scale/72) factor recomputes exact
    real-world quantities for ANY scale the user later verifies — no vision re-run.
    """
    footprint_pt2: float
    total_linework_pt: float
    ...
```

**Pure conversion math** (`scale_recalc.py` lines 25–45) — the recompute contract every new measurer feeds:

```python
def recompute(raw: Dict, feet_per_inch: Optional[float]) -> Dict:
    if not feet_per_inch or feet_per_inch <= 0 or not raw:
        return {"footprint_sf": None, "total_linework_lf": None, "long_run_lf": None}
    fpp = feet_per_point(feet_per_inch)
    ...
    return {
        "footprint_sf": round(fp2 * fpp * fpp, 1),
        "total_linework_lf": round(tot * fpp, 1),
        ...
    }
```

**Deterministic quantity → authoritative legend handoff** (`footprint_takeoff.footprint_to_legend`, lines 169–212) — how a deterministic measurement enters the pipeline as an authoritative row (wall LF-by-class and room SF should emit the same structure, with a provenance field added):

```python
    return {
        "name": "Building Footprint (measured from overall dimensions)",
        "table_purpose": "takeoff_legend",
        "schedule_type": "area",
        "use_for_takeoff": True,
        "description": note,
        "rows": rows,                      # [{"ITEM", "QTY", "UNIT"}]
        "_source_pages": [footprint.page_index + 1],
        "_confidence": footprint.confidence,
    }
```

`symbols.py` has no clustering analog in the codebase (see No Analog section) — but its *output* must be this same legend/row shape plus a candidate registry (`{candidate_id: bbox_pt}`) for the fusion layer.

---

### `deterministic/tables.py` (extraction utility, file-I/O)

**Analog:** `schedule_extraction.py` — generalize, don't fork (RESEARCH "Don't Hand-Roll")

**find_tables loop + content-based column detection** (`schedule_extraction.py` lines 181–201) — the page/table iteration skeleton to parameterize by schedule kind:

```python
def extract_door_schedule(doc) -> DoorSchedule:
    out = DoorSchedule()
    seen_tags = set()
    for i in range(doc.page_count):
        page = doc[i]
        try:
            tables = list(page.find_tables().tables)
        except Exception:
            tables = []
        for t in tables:
            rows = [_cells(r) for r in t.extract()]
            tag_col = _tag_column(rows)
            if tag_col is None:
                continue
            panel_col, frame_col = _material_columns(rows, tag_col)
            if not _is_door_table(rows, tag_col, panel_col, frame_col):
                continue
```

**Order-independent column identification by token density** (`schedule_extraction._tag_column`, lines 83–96) — the generalization seed: per schedule kind, define token vocabularies and score columns by hit density, exactly as done for door tags:

```python
def _tag_column(rows: List[List[str]]) -> Optional[int]:
    """The column whose cells most consistently look like door tags."""
    width = max(len(r) for r in rows)
    best_col, best_hits = None, 0
    for c in range(min(width, 4)):  # tag is always near the left
        hits = sum(1 for r in rows if c < len(r) and _tag_tokens(r[c]))
        if hits > best_hits:
            best_col, best_hits = c, hits
    return best_col if best_hits >= 3 else None
```

**Coverage gate against false positives** (`_is_door_table`, lines 170–178) — every new schedule kind needs the equivalent "most rows carry the expected token" gate:

```python
    door_rows, covered = _material_coverage(rows, tag_col, panel_col, frame_col)
    if door_rows < 3:
        return False
    return covered >= 3 and (covered / door_rows) >= 0.4
```

Also preserve the schedule-counts-are-lower-bounds honesty from the module docstring (lines 11–17) — RESEARCH pitfall 10 (WC-1 hotel duplication) depends on it.

---

### `vision/prompts.py` + structured outputs (config/service, request-response)

**Analog:** `claude_analyzer.py`

**API call with prompt caching + usage/cost capture** (`claude_analyzer.analyze_drawing`, lines 458–532) — the request skeleton to keep; swap freeform-JSON parsing for `output_config.format` structured outputs per RESEARCH §3:

```python
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media_type,
                                             "data": image_data}},
                {"type": "text", "text": _build_user_message(...)},
            ]}],
        )
        usage = response.usage
        p = PRICING.get(model, {"in": 3.0, "out": 15.0})
        cost_usd = (usage.input_tokens * p["in"] + usage.output_tokens * p["out"]) / 1_000_000
```

**Result-metadata convention** (lines 520–526) — every vision response dict carries these underscore fields; ensemble members and fusion outputs must too:

```python
        extracted["_tokens_in"] = input_tokens
        extracted["_tokens_out"] = output_tokens
        extracted["_cost_usd"] = round(cost_usd, 6)
        extracted["_model_used"] = model
        extracted["_pass_type"] = pass_type
        extracted["_source_sheet"] = sheet_name
```

**Graceful error-dict return** (lines 563–573) — extraction never raises; errors return `{"error": ..., "_pass_type": ..., "_cost_usd": 0}` so the pipeline degrades per-sheet, not per-run.

**Pass-scoped system prompts + user-hint injection** (lines 448–456 and `_build_user_message` lines 576–590) — the prompt-selection switch and the hint slot where `learning/retrieval.py`'s LearnedContext block plugs in (same slot `_build_count_hint` uses today).

---

### `vision/fusion.py` (service, transform)

**Analog:** `claude_analyzer.merge_passes` (lines 628–684) + `apply_accuracy_rules` (lines 702–738)

**Normalized-name dedup with precedence rule** (lines 656–678) — the merge skeleton; fusion replaces "count-pass wins on confidence" with "provenance rank wins" (`geometry > text_layer > schedule_table > learned > vision_ensemble`):

```python
    merged: dict = dict(measure_result)
    seen: dict[str, dict] = {
        c["name"].strip().lower(): c
        for c in merged.get("components", [])
        if isinstance(c, dict) and c.get("name")
    }
    for c in count_result.get("components", []):
        key = c["name"].strip().lower()
        if key not in seen:
            merged.setdefault("components", []).append(c)
            seen[key] = c
        else:
            existing = seen[key]
            if c.get("confidence") == "high" and existing.get("quantity") is None:
                existing["quantity"] = c["quantity"]
                existing["_count_pass_upgrade"] = True
```

**Authoritative-source suppression precedent** (`apply_accuracy_rules`, lines 702–712) — "when a legend exists, drop conflicting room-derived items" is the existing single-source-of-truth rule; fusion generalizes it to per-item provenance. Also see the aggregator's `legend_names` suppression set (`aggregator.py` lines 220–237 and 267–280) — that is where vision duplicates of authoritative rows are already silenced; provenance enum should replace the string-matching heuristics there.

---

### `vision/ensemble.py` (service, request-response fan-out)

**Analog (partial):** `claude_analyzer.analyze_drawing` for the per-call mechanics; no voting analog exists.

Copy: the API-call skeleton, PRICING/cost capture, and error-dict convention from `vision/prompts.py` assignment above. The `COUNT_TILING` machinery referenced in `takeoff_pipeline.py` (imports `count_tiling_enabled`, `count_tiling_grid` from `accuracy_config.py`) is the existing tiling entry point to integrate as one ensemble member. Voting/median/NMS-dedup logic is new (RESEARCH §4 gives thresholds). Budget guard: reuse the run-level cost accumulation the benchmark already reads (`result["api_usage"]["total_cost_usd"]` — see `scripts/vision_only_benchmark.py` line 243).

---

### `sheet_pass_matrix.py` MODEL_ROUTING v2 (config)

**Analog:** itself + `config.py`

**Routing-table shape to keep** (`sheet_pass_matrix.py` lines 54–69) — extend keys, source slugs from config:

```python
MODEL_ROUTING: dict[tuple[str, str], str] = {
    ("elevation",  "measure"):   CLAUDE_MODEL_SCHEDULES,
    ("schedule",   "schedule"):  CLAUDE_MODEL_SCHEDULES,
    ...
}
```

**Env-driven slug pattern** (`config.py` lines 22–25) — add `CLAUDE_MODEL_SEMANTIC`, `CLAUDE_MODEL_DENSE`, `CLAUDE_MODEL_ESCALATION` etc. the same way; never hardcode slugs (user decision, CONTEXT):

```python
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
CLAUDE_MODEL_SCHEDULES = os.getenv("CLAUDE_MODEL_SCHEDULES", CLAUDE_MODEL)
```

Also update `PRICING` in `claude_analyzer.py` (lines 20–24) with the July 2026 table from RESEARCH §5. Note `tests/conftest.py` lines 32–33 pin these env vars for deterministic routing tests — new model env vars need the same conftest defaults.

---

### `learning/store.py` (model/store, CRUD)

**Analog:** `stackct_store.py` (schema versioning, WAL, write lock) + `job_store.py` (lazy double-checked init)

**Connection + write-lock pattern** (`stackct_store.py` lines 20–21, 81–86):

```python
_write_lock = threading.Lock()
_initialized = False

def get_connection() -> sqlite3.Connection:
    STACKCT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STACKCT_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

**Schema-version migration precedent** (`stackct_store.init_schema`, lines 89–149) — the v1→v2 pattern to follow when adding `learning_*` tables (RESEARCH proposes schema in §6; whether to extend `stackct.db` v2→v3 or use the version key `learning_schema_version` is planner's call, but this is the mechanism):

```python
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cache_metadata'"
    ).fetchone()
    if not table_check:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO cache_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("schema_version", "2", now),
        )
        ...
    row = conn.execute(
        "SELECT value FROM cache_metadata WHERE key = 'schema_version'"
    ).fetchone()
    current_version = row["value"] if row else None
    if current_version == "1":
        # ... targeted ALTERs / drops, then executescript(SCHEMA_SQL) again
```

**Lazy double-checked schema init** (`job_store.py` lines 57–70) — simpler variant for a module whose callers can't be relied on to call init first:

```python
def _ensure_schema() -> None:
    global _initialized
    if _initialized:
        return
    with _write_lock:
        if _initialized:
            return
        conn = _get_connection()
        try:
            conn.executescript(JOB_RUNS_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True
```

**Weighted upsert pattern** (`stackct_store.set_metadata`, lines 180–192) — `ON CONFLICT ... DO UPDATE` is the shape for `learning_vocabulary` weight increments:

```python
            conn.execute(
                """
                INSERT INTO cache_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
```

**Named-parameter insert for wide rows** (`job_store.save_job_run`, lines 148–167) — use for `learning_corrections` (many nullable JSON columns).

---

### `learning/distill.py` (service, batch)

**Analog:** `stackct_store.migrate_from_json_caches` (lines 540–572) — the idempotent, re-runnable, guarded-by-metadata-flag batch job:

```python
def migrate_from_json_caches() -> dict[str, int]:
    """Import legacy JSON caches into SQLite (idempotent)."""
    stats = {"projects_imported": 0, "plans_files_imported": 0}
    if project_count() > 0:
        logger.info("Projects table already populated — skipping JSON project import")
    ...
    return stats
```

and its invocation guard (`init_db`, lines 575–585): run once, record a metadata flag, return stats dict. Distill differs in that it re-runs after every correction batch, but the "rebuildable from the append-only log, returns stats" contract is the same.

---

### `learning/retrieval.py` (service, CRUD read + prompt injection)

**Analog:** `stackct_store.get_plans` (row → dict list, lines 448–486) for the query side; `takeoff_pipeline._build_count_hint` (lines 50–71) for the injection side.

**Hint-block construction to imitate** — LearnedContext renders "expected items / known naming" text into the same `user_hint` slot the manifest hints use today:

```python
def _build_count_hint(manifest) -> Optional[str]:
    if not manifest:
        return None
    lines = []
    for e in manifest.entries:
        if e.measure not in ("count", "each"):
            continue
        names = [e.name, *[a for a in e.aliases if a]]
        lines.append("  - " + " / ".join(dict.fromkeys(names)))
    if not lines:
        return None
    return (
        "TARGETED COUNT — the estimator expects these discrete (EA) objects in this "
        "project. ... Objects to look for:\n" + "\n".join(lines)
    )
```

**Assumption-consumption pattern** (`takeoff_pipeline._manifest_wall_height`, lines 124–141) — the exact seam where `learning_assumptions` (wall heights) plugs in, keeping the 9 ft cold-start default flagged:

```python
def _manifest_wall_height(manifest) -> float:
    default = 9.0
    if not manifest:
        return default
    heights = [...from entries' assumptions...]
    return max(heights) if heights else default
```

**Aggregation-consumption seam** (`aggregator.normalize_item_name`, lines 141–150) — learned vocabulary is consulted *before* this loop; ITEM_NAME_MAP stays as the cold-start floor (V3-LEARN-02):

```python
def normalize_item_name(description: str, item_type: str, unit: str) -> tuple:
    d = (description or "").lower()
    for pattern, name, default_unit in ITEM_NAME_MAP:
        if re.search(pattern, d, re.IGNORECASE):
            ...
            return name, default_unit
    canonical = item_type.replace("_", " ").title() if item_type else (description or "")[:40]
    return canonical, unit or "EA"
```

---

### `web/blueprints/verify.py` (controller, request-response) — the learning-capture rewire

**Analog:** `app.py` lines 1329–1619 (exact — these endpoints move into the blueprint and gain learning-store INSERTs)

**Endpoint skeleton: path-traversal guard, JSON body validation, persist, rebuild** (`app.py` lines 1560–1619, `/verify`):

```python
@app.route("/api/reports/<run_folder>/verify", methods=["POST"])
@login_required
def verify_item(run_folder: str):
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    sub = Path(OUTPUT_DIR) / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    data = request.json or {}
    item = (data.get("item") or "").strip()
    if not item:
        return jsonify({"error": "item required"}), 400
    ...
    store[key] = {
        "item": item, "quantity": qty, "unit": data.get("unit") or "",
        "verified": bool(data.get("verified", True)), "note": data.get("note") or "",
    }
    p.write_text(json.dumps({"run_folder": run_folder, "overrides": store}, indent=2), ...)
    summary = _rebuild_summary(run_folder)
    return jsonify({"run_folder": run_folder, "takeoff_summary": summary, ...})
```

The Phase-21 change: after `p.write_text(...)`, also `learning_store.record_correction(scope="item", ...)` in the same request (per CONTEXT: capture surfaces must feed the learning store instead of dying with the run folder). Same for the scale endpoint (lines 1329–1364, `scope="scale"`) and measurements endpoint (lines 1518–1557, `scope="wall_height"`/measurement).

**Layered rebuild with explicit precedence** (`app.py` `_rebuild_summary`, lines 1424–1503) — the provenance-layering precedent (base vision < measurements < human overrides) that fusion's provenance enum formalizes:

```python
    # Layer 2 — measurements
    agg = tm.aggregate_measurements(_load_measurements(run_folder))
    for entry in agg.values():
        row.update({..., "source": "measured_auto" if is_auto else "measured_verified", ...})

    # Layer 3 — manual verified overrides (win over everything)
    overrides = _load_verify_overrides(run_folder)
    for key, ov in overrides.items():
        if not ov.get("verified"):
            continue
        ...
        row["source"] = "user_verified"
```

All other blueprints copy the same decorator + guard + jsonify conventions from their respective `app.py` route groups.

---

### `takeoff_pipeline.py` modifications (orchestrator)

**Analog:** itself

**Analyzer injection for testability** (lines 260–272) — preserve exactly; the fusion/ensemble layers must be injectable the same way (record/replay tests depend on it):

```python
    def __init__(self, analyzer: Optional[Callable] = None) -> None:
        if analyzer is not None:
            self._analyzer = analyzer
        else:
            # Use the module-level name so it can be patched by tests
            import takeoff_pipeline as _self_module
            self._analyzer = _self_module.analyze_drawing
```

**QuantityVerifier flag shape + the retry stub being replaced** (lines 181–236) — flags feed the new targeted crop verify-retry (RESEARCH §3 handoff 3); keep the "flag, never suppress" rule:

```python
            if q < rule["min"] or q > rule["max"]:
                flags.append({"sheet": sheet_name, "item": item_name,
                              "qty": qty, "unit": unit_key, "rule": rule})
        ...
            if os.environ.get("ENABLE_VERIFY_RETRY") == "1":
                logger.info(
                    "QuantityVerifier: ENABLE_VERIFY_RETRY=1 set — "
                    "%d item(s) flagged on %r (log only, no re-query in this build)", ...)
```

**Patchability convention** (lines 37–45) — module-level re-imports exist so tests can `unittest.mock.patch("takeoff_pipeline.analyze_drawing", ...)`; new deterministic/learning call-sites need the same module-level import style.

---

### `scraper.py` / `pdf_analyzer.py` parity (entry points)

**Analog:** each other. The asymmetry to remove is at `scraper.py` lines 782–794:

```python
        from plan_deterministic_legends import (
            build_deterministic_legends_from_run_dir,
            inject_project_legends,
        )
        det_legends = build_deterministic_legends_from_run_dir(
            screenshots_dir, object_manifest, companion_present=False,
        )
```

The `companion_present=False` hardcode (line 787) plus the fact that the StackCT path feeds *rasterized screenshots* while `pdf_analyzer._page_to_image` renders from the vector PDF is the parity gap: the shared `RunSettings` dataclass (deterministic flags, ensemble N, learning on/off) must be constructed identically in both, and the StackCT path must retain per-page PDF blobs for the deterministic engine (RESEARCH §7 / open question 1). `tests/test_pipeline_parity.py` is the existing parity test to extend.

Also note `pdf_analyzer.py` lines 22–31: the 7900 px render clamp — RESEARCH §5 says retarget renders to ≈1568 px long edge for whole-sheet passes and use clip crops for detail; this is where that changes.

---

### Tests: geometry engine, scale truth tables, fusion replay

**Analog:** `tests/test_takeoff_generalization.py` + `tests/conftest.py`

**Fixture-file + expected-constraints pattern** (`test_takeoff_generalization.py` lines 24–36, 79–90):

```python
FIXTURES = Path(__file__).parent / "fixtures" / "generalization"
EXPECTED = FIXTURES / "expected"

def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())

def test_floor_plan_retail_expected_constraints():
    exp = _load_expected("floor_plan_retail.json")
    if not exp:
        pytest.skip("No expected file for floor_plan_retail")
    raw = apply_estimation_tables(_load_fixture("floor_plan_retail.json"))
    types = _item_types(raw)
    for required in exp.get("required_item_types", []):
        assert required in types, f"Expected item_type '{required}' not found in {types}"
    for qty_type, min_q in exp.get("min_quantities", {}).items():
        total = sum(it["quantity"] for it in raw if it.get("item_type") == qty_type)
        assert total >= min_q, ...
```

`tests/fixtures/*/scale_truth.json` follows the same expected-constraints idea (page → viewport → fpi truth table). Pinned exact assertions (e.g. Crow 1136'×350', 20 ft/in ±2%, ≥28 bollard clusters) mirror `test_floor_plan_industrial_bollard_count` (lines 104–110).

**Env pinning + real-module pre-registration** (`tests/conftest.py` lines 25–33, 36–59) — any new env-driven config (ensemble N, model slugs, learning toggle) needs `os.environ.setdefault` here so routing is deterministic under any collection order; any module that parity tests stub via `sys.modules.setdefault` needs `_ensure_real(...)` pre-registration.

**Record/replay fusion tests** — inject via `TakeoffPipeline(analyzer=fake)` (constructor excerpt above); the recorded-response cache extends the existing `{page_id}_analysis.json` reuse pattern noted in RESEARCH §8 layer 3.

---

### `scripts/vision_only_benchmark.py` modifications (accuracy gate)

**Analog:** itself

**Isolation + scoring skeleton to extend** (lines 221–246, 103–172): the temp-dir isolation guaranteeing plans-only, and the `score()` dict (`overall_qty`, `name_found_rate`, `count_qty`, `measured_qty`) that gains per-provenance splits (geometry/text-layer ≥97%, vision-provenance ≈0 on vector fixtures) and a two-run reproducibility check (±5%):

```python
    with tempfile.TemporaryDirectory(prefix="vision_only_") as tmp:
        isolated = Path(tmp) / plans.name
        shutil.copy2(plans, isolated)
        companion = find_companion_takeoff_pdf(str(isolated))
        assert companion is None, f"Expected NO companion take-off, found: {companion}"
        ...
        result = run_pdf_analysis(str(isolated), project_name=f"VisionOnly {name}", **kwargs)
```

Per-run cost is already surfaced (line 243: `(result.get("api_usage") or {}).get("total_cost_usd", 0)`) — the cost-regression warning hooks there.

## Shared Patterns

### Result dataclass + `to_dict` + confidence flag
**Source:** `footprint_takeoff.Footprint` (lines 38–51), `geometry_takeoff.ScaleResult` (lines 39–47)
**Apply to:** every new deterministic module (`DimensionSample`, `WallSegment`, `RoomPolygon`, `SymbolGroup`, viewport records)

```python
@dataclass
class Footprint:
    ...
    confidence: str          # "high" | "medium" | "low"
    needs_review: bool = False
    review_reason: str = ""
    def to_dict(self) -> dict:
        return asdict(self)
```

### Flag-don't-guess / reject-what-you-can't-verify
**Source:** `scale_extraction.snap_fpi` (reject off-ladder), `geometry_takeoff._measure_single` needs_review logic (lines 246–256), `aggregator` manifest-missing injection (lines 315–329)
**Apply to:** all extraction and fusion code — an unverifiable value is emitted flagged, never silently guessed or dropped (CONTEXT accuracy strategy, honest-framing decision).

### Lazy imports to break cycles
**Source:** `geometry_takeoff.py` lines 94, 240, 266 (`from scale_extraction import ...` / `from scale_recalc import recompute  # local import avoids cycle`); `claude_analyzer._pick_model` deferred `sheet_pass_matrix` import (lines 44–52)
**Apply to:** all package-move work — RESEARCH §7 explicitly says preserve lazy imports during the move; new deterministic↔learning↔pipeline edges should use the same style when a cycle threatens.

### SQLite: module lock + Row factory + ON CONFLICT upserts
**Source:** `stackct_store.py` lines 20–21, 81–86, 180–192; `job_store.py` lines 57–70
**Apply to:** `learning/store.py` exclusively (one store module owns the `learning_*` tables; endpoints call it, never raw SQL).

### Flask endpoint hygiene
**Source:** `app.py` verify/scale endpoints (lines 1329–1364, 1560–1619)
**Apply to:** every blueprint route

```python
@app.route("/api/reports/<run_folder>/verify", methods=["POST"])
@login_required
def verify_item(run_folder: str):
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    ...
    return jsonify({"error": "Failed to save"}), 500   # OSError branch
```

### Vision-call cost accounting + prompt caching
**Source:** `claude_analyzer.analyze_drawing` (lines 471–509: `cache_control: ephemeral` system block, PRICING lookup, `_cost_usd` stamping)
**Apply to:** `vision/ensemble.py`, verify-retry crops, crop-gallery calls — every API call must stamp cost metadata so the per-run budget guard (V3-PROD-02) can total it.

### Test injection over network mocking
**Source:** `TakeoffPipeline(analyzer=...)` (lines 260–272) + module-level re-export for patching (lines 37–45)
**Apply to:** fusion, ensemble, learning retrieval — construct with injectable callables; keep module-level names patchable.

## No Analog Found

Files with no close match in the codebase (planner should lean on RESEARCH.md recipes and the shared patterns above):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `deterministic/symbols.py` clustering core | extraction utility | transform | No connected-component/shape-hash code exists anywhere; Recipe D in RESEARCH is the spec. Output shape follows `footprint_to_legend`. |
| `vision/ensemble.py` voting core | service | fan-out | No multi-sample voting exists; `COUNT_TILING` machinery is the only adjacent code. RESEARCH §4 supplies N/thresholds. |
| `web/app.py` `create_app()` factory | bootstrap | request-response | `app.py` is a flat 1,817-line module with module-level `app`; no factory or blueprint exists. Follow the standard Flask factory pattern (project rule file also mandates it); `main.py` entry becomes `app = create_app()`. |
| `web/jobs_runtime.py` | service | event-driven | Jobs dict + Playwright thread launch live inline in `app.py`; extracting them is a move, but the "owned module, primitive payloads only" boundary is new. |
| `pyproject.toml` + root import shims | config | n/a | No pyproject exists; `scripts/` use `sys.path.insert(0, str(ROOT))` (`vision_only_benchmark.py` lines 46–47). RESEARCH §7 migration steps are the spec (src-layout, `pip install -e .`, shim-per-old-module). |

## Metadata

**Analog search scope:** repo root (30 flat modules), `tests/`, `scripts/`
**Files read for excerpts:** `footprint_takeoff.py`, `scale_extraction.py`, `geometry_takeoff.py`, `schedule_extraction.py`, `scale_recalc.py`, `stackct_store.py`, `job_store.py`, `sheet_pass_matrix.py`, `config.py`, `takeoff_pipeline.py` (1–280), `claude_analyzer.py` (1–160, 415–745), `app.py` (1320–1620), `aggregator.py`, `scraper.py` (755–825), `pdf_analyzer.py` (1–80), `main.py`, `tests/conftest.py`, `tests/test_takeoff_generalization.py` (1–130), `scripts/vision_only_benchmark.py`
**Pattern extraction date:** 2026-07-13
