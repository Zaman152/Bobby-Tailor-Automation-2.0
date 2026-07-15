"""Symbol-count binding: labeled counts reach the summary, unlabeled ones
still surface, and a conservative deterministic grid fallback names columns.

Offline only — drives the exact fusion → merge → report → aggregate path where
the symbol-count binding bug lived, with hand-built deterministic bundles and
stubbed vision label answers (no analyzer, no PDF, no API).
"""
from bobbytailor.vision.fusion import (
    deterministic_symbol_name,
    fuse_sheet,
    merge_with_provenance,
)
from bobbytailor.pipeline.calculator import apply_estimation_tables
from bobbytailor.pipeline.reporter import _normalize_calculated
from bobbytailor.pipeline.aggregator import aggregate_takeoff


def _summary_from_groups(symbol_groups, matches):
    """Full offline downstream path: fusion → merge → calc → normalize → aggregate."""
    bundle = {"sheet_name": "S-101", "symbol_groups": symbol_groups}
    fused = fuse_sheet(bundle, {"matches": matches})
    merged = merge_with_provenance([fused])
    merged["_source_sheet"] = "S-101"
    merged["sheet_type"] = "floor_plan"
    estimates = apply_estimation_tables(merged, project_type="commercial")
    calculated = _normalize_calculated(estimates)
    return aggregate_takeoff(calculated), fused


def _grid_bboxes(cols, rows, step=30.0, size=8.0, origin=(100.0, 100.0)):
    """cols×rows regular grid of identical instance bboxes."""
    ox, oy = origin
    boxes = []
    for r in range(rows):
        for c in range(cols):
            x0 = ox + c * step
            y0 = oy + r * step
            boxes.append((x0, y0, x0 + size, y0 + size))
    return boxes


def _row_for(summary, item):
    for row in summary:
        if row.get("item") == item:
            return row
    return None


# ── THE regression: labeled symbol count reaches the named summary line ───────


def test_labeled_symbol_count_reaches_summary_columns_136_ea():
    groups = [
        {
            "candidate_id": "SYM-1",
            "count": 136,
            "representative_bbox_pt": (100.0, 100.0, 140.0, 140.0),
            "instance_bboxes_pt": [(100.0, 100.0, 108.0, 108.0)],
            "contained_texts": [],
            "confidence": "high",
        }
    ]
    matches = [{"symbol_id": "SYM-1", "label": "Columns", "confidence": "high"}]
    summary, _ = _summary_from_groups(groups, matches)

    columns = _row_for(summary, "Columns")
    assert columns is not None, "labeled symbol count dropped out of the summary"
    assert float(columns["quantity"]) == 136.0
    assert (columns.get("unit") or "").upper() == "EA"


def test_labeled_bollards_also_bind():
    groups = [
        {
            "candidate_id": "SYM-2",
            "count": 56,
            "representative_bbox_pt": (200.0, 200.0, 220.0, 220.0),
            "instance_bboxes_pt": [(200.0, 200.0, 208.0, 208.0)],
            "contained_texts": [],
            "confidence": "high",
        }
    ]
    matches = [{"symbol_id": "SYM-2", "label": "Bollards", "confidence": "high"}]
    summary, _ = _summary_from_groups(groups, matches)

    bollards = _row_for(summary, "Bollards")
    assert bollards is not None
    assert float(bollards["quantity"]) == 56.0
    assert (bollards.get("unit") or "").upper() == "EA"


# ── Nothing skipped: unlabeled, non-grid group still surfaces flagged ─────────


def test_unlabeled_non_grid_group_surfaces_flagged_with_its_count():
    # 40 instances scattered irregularly → NOT a regular grid, vision unknown.
    scattered = [
        (x, y, x + 6.0, y + 6.0)
        for x, y in [
            (13.0, 91.0), (77.0, 12.0), (140.0, 205.0), (22.0, 260.0),
            (301.0, 44.0), (188.0, 330.0), (255.0, 118.0), (67.0, 402.0),
            (410.0, 233.0), (95.0, 155.0), (349.0, 288.0), (44.0, 377.0),
            (270.0, 61.0), (162.0, 96.0), (388.0, 401.0), (118.0, 318.0),
            (233.0, 244.0), (301.0, 355.0), (56.0, 210.0), (417.0, 133.0),
            (29.0, 47.0), (203.0, 411.0), (144.0, 27.0), (360.0, 190.0),
            (88.0, 289.0), (255.0, 399.0), (399.0, 72.0), (176.0, 168.0),
            (311.0, 251.0), (63.0, 344.0), (222.0, 118.0), (401.0, 322.0),
            (127.0, 235.0), (289.0, 41.0), (74.0, 383.0), (345.0, 156.0),
            (198.0, 300.0), (36.0, 129.0), (267.0, 213.0), (159.0, 366.0),
        ]
    ]
    groups = [
        {
            "candidate_id": "SYM-9",
            "count": 40,
            "representative_bbox_pt": (13.0, 91.0, 19.0, 97.0),
            "instance_bboxes_pt": scattered,
            "contained_texts": [],
            "confidence": "medium",
        }
    ]
    summary, fused = _summary_from_groups(groups, matches=[])

    # It must NOT be named "Columns" (weak signal stays unnamed).
    assert _row_for(summary, "Columns") is None
    # Its count of 40 must still be present as a flagged EA row (never dropped).
    flagged = [r for r in summary if float(r.get("quantity") or 0) == 40.0]
    assert flagged, "unlabeled symbol group of 40 was silently dropped"
    assert any(r.get("needs_review") for r in flagged)
    assert any((r.get("unit") or "").upper() == "EA" for r in flagged)
    # And the fused component kept its deterministic count, flagged for review.
    comp = next(c for c in fused["components"] if c.get("candidate_id") == "SYM-9")
    assert comp["quantity"] == 40 and comp["unit"] == "EA"
    assert comp["needs_review"] is True


# ── Deterministic grid fallback: conservative ────────────────────────────────


def test_deterministic_symbol_name_regular_grid_is_columns():
    group = {
        "candidate_id": "SYM-5",
        "count": 132,
        "instance_bboxes_pt": _grid_bboxes(cols=12, rows=11),
    }
    assert deterministic_symbol_name(group) == "Columns"


def test_deterministic_symbol_name_scattered_small_is_none():
    group = {
        "candidate_id": "SYM-6",
        "count": 3,
        "instance_bboxes_pt": [
            (10.0, 10.0, 18.0, 18.0),
            (300.0, 55.0, 308.0, 63.0),
            (140.0, 410.0, 148.0, 418.0),
        ],
    }
    assert deterministic_symbol_name(group) is None


def test_deterministic_symbol_name_high_count_but_no_instances_is_none():
    # High count but instances not populated → conservative: cannot verify grid.
    group = {"candidate_id": "SYM-7", "count": 200, "instance_bboxes_pt": []}
    assert deterministic_symbol_name(group) is None


def test_deterministic_grid_fallback_flows_to_summary_columns():
    groups = [
        {
            "candidate_id": "SYM-5",
            "count": 132,
            "representative_bbox_pt": (100.0, 100.0, 108.0, 108.0),
            "instance_bboxes_pt": _grid_bboxes(cols=12, rows=11),
            "contained_texts": [],
            "confidence": "medium",
        }
    ]
    # Vision returns nothing → deterministic geometry names it.
    summary, _ = _summary_from_groups(groups, matches=[])
    columns = _row_for(summary, "Columns")
    assert columns is not None
    assert float(columns["quantity"]) == 132.0
    assert (columns.get("unit") or "").upper() == "EA"
    assert columns.get("needs_review") is True


# ── No double-counting: one symbol group → one summary line ──────────────────


def test_no_double_count_one_group_one_line():
    groups = [
        {
            "candidate_id": "SYM-1",
            "count": 136,
            "representative_bbox_pt": (100.0, 100.0, 140.0, 140.0),
            "instance_bboxes_pt": [(100.0, 100.0, 108.0, 108.0)],
            "contained_texts": [],
            "confidence": "high",
        }
    ]
    matches = [{"symbol_id": "SYM-1", "label": "Columns", "confidence": "high"}]
    _, fused = _summary_from_groups(groups, matches)
    col_components = [c for c in fused["components"] if c.get("candidate_id") == "SYM-1"]
    assert len(col_components) == 1, "a symbol group produced more than one component"
    summary, _ = _summary_from_groups(groups, matches)
    columns_rows = [r for r in summary if r.get("item") == "Columns"]
    assert len(columns_rows) == 1
