"""Layer-1 tests for the Recipe B parallel-pair wall extraction engine."""
from __future__ import annotations

import dataclasses
import json
import statistics
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.walls import (
    WallSegment,
    extract_walls,
    extract_walls_detailed,
    opening_gap_widths,
    wall_lf_by_class,
)

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC_DIR = FIXTURES / "synthetic"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"


def _ensure_floorplan_fixture() -> Path:
    pdf_path = SYNTHETIC_DIR / "floorplan_synthetic.pdf"
    if not pdf_path.exists():
        subprocess.run(
            [
                sys.executable,
                str(SYNTHETIC_DIR / "gen_synthetic.py"),
                "--out",
                str(SYNTHETIC_DIR),
            ],
            check=True,
        )
    return pdf_path


def _floorplan_truth() -> dict:
    _ensure_floorplan_fixture()
    payload = json.loads((SYNTHETIC_DIR / "truth.json").read_text())
    return payload["floorplan"]


@pytest.fixture(scope="module")
def floorplan_walls():
    """(walls, truth, fpp) for the synthetic floor plan."""
    truth = _floorplan_truth()
    fpp = truth["fpp"]
    doc = fitz.open(SYNTHETIC_DIR / truth["pdf"])
    walls = extract_walls(doc[0], fpp)
    doc.close()
    return walls, truth, fpp


# ── Synthetic: LF per thickness class ─────────────────────────────────────────


def test_synthetic_wall_lf_per_class_within_2pct(floorplan_walls):
    walls, truth, fpp = floorplan_walls
    lf = wall_lf_by_class(walls, fpp)

    # Map classes back to thickness bins (inches).
    class_thickness = {}
    for wall in walls:
        thickness_in = wall.thickness_pt * fpp * 12.0
        bin_in = round(thickness_in / 0.5) * 0.5
        class_thickness.setdefault(wall.thickness_class, bin_in)

    lf_by_bin = {}
    for cls, total in lf.items():
        lf_by_bin[class_thickness[cls]] = lf_by_bin.get(class_thickness[cls], 0.0) + total

    for bin_key, expected in truth["wall_lf_by_thickness_in"].items():
        bin_in = float(bin_key)
        assert bin_in in lf_by_bin, f"missing thickness class {bin_in}\""
        got = lf_by_bin[bin_in]
        assert got == pytest.approx(expected, rel=0.02), (
            f"{bin_in}\" class LF {got} vs truth {expected}"
        )


def test_synthetic_classes_ordered_by_lf_desc(floorplan_walls):
    walls, truth, fpp = floorplan_walls
    lf = wall_lf_by_class(walls, fpp)
    # Exactly the two drawn thickness classes — the hatch field must NOT
    # have produced a third class (Pitfall 2).
    assert set(lf) == {"TC1", "TC2"}
    assert lf["TC1"] >= lf["TC2"]
    # TC1 is the 8" exterior class (largest LF).
    tc1_walls = [w for w in walls if w.thickness_class == "TC1"]
    assert all(
        round(w.thickness_pt * fpp * 12.0 / 0.5) * 0.5 == 8.0 for w in tc1_walls
    )
    assert all(w.candidate_id == "WALL-TC1" for w in tc1_walls)


# ── Synthetic: door openings ──────────────────────────────────────────────────


def test_synthetic_two_openings_at_3ft(floorplan_walls):
    walls, truth, fpp = floorplan_walls
    gaps = opening_gap_widths(walls, fpp)
    assert len(gaps) == len(truth["opening_widths_ft"]) == 2
    for gap in gaps:
        assert gap == pytest.approx(3.0, abs=0.05)


# ── Synthetic: curved wall (Pitfall 6) ────────────────────────────────────────


def test_synthetic_curved_wall_lf_within_3pct(floorplan_walls):
    walls, truth, fpp = floorplan_walls
    curve_walls = [w for w in walls if len(w.centerline_pt) > 2]
    assert len(curve_walls) == 1, "the concentric quarter arcs must pair"
    got = curve_walls[0].length_pt * fpp
    assert got == pytest.approx(truth["curve_wall_lf"], rel=0.03)
    # 6" thickness class, like the interior partitions.
    thickness_in = curve_walls[0].thickness_pt * fpp * 12.0
    assert round(thickness_in / 0.5) * 0.5 == 6.0


# ── Synthetic: hatch fields must not create walls ─────────────────────────────


def test_synthetic_hatch_field_does_not_create_walls(floorplan_walls):
    walls, truth, fpp = floorplan_walls
    # Hatch bbox: x 600-710, y 150-180 — no wall centerline may live there.
    for wall in walls:
        xs = [p[0] for p in wall.centerline_pt]
        ys = [p[1] for p in wall.centerline_pt]
        inside = (
            595.0 <= min(xs) and max(xs) <= 715.0
            and 145.0 <= min(ys) and max(ys) <= 185.0
        )
        assert not inside, f"hatch stroke became a wall: {wall.centerline_pt}"


def test_synthetic_hatch_region_recorded(floorplan_walls):
    truth = _floorplan_truth()
    doc = fitz.open(SYNTHETIC_DIR / truth["pdf"])
    detailed = extract_walls_detailed(doc[0], truth["fpp"])
    doc.close()
    assert detailed["hatch_regions"], "collapsed hatch field must be recorded"
    region = detailed["hatch_regions"][0]
    assert region["count"] == truth["hatch_strokes"]


# ── WallSegment contract ──────────────────────────────────────────────────────


def test_wall_segment_stores_point_space_only():
    field_names = {f.name for f in dataclasses.fields(WallSegment)}
    assert not any(name.endswith("_ft") for name in field_names)
    assert {"centerline_pt", "length_pt", "thickness_pt", "openings_pt"} <= field_names


def test_wall_segment_to_dict_roundtrip(floorplan_walls):
    walls, _, _ = floorplan_walls
    d = walls[0].to_dict()
    assert d["candidate_id"].startswith("WALL-TC")
    assert d["confidence"] in ("high", "medium")
    json.dumps(d)  # report-serializable


# ── Curve-support review flag (Pitfall 6) ─────────────────────────────────────


def test_curve_share_flag_sets_needs_review():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Mostly curves: two long concentric arcs, one short straight pair.
    k = 0.5522847498307936
    for radius in (150.0, 155.0):
        page.draw_bezier(
            fitz.Point(300 + radius, 300),
            fitz.Point(300 + radius, 300 + k * radius),
            fitz.Point(300 + k * radius, 300 + radius),
            fitz.Point(300, 300 + radius),
        )
    page.draw_line(fitz.Point(50, 50), fitz.Point(100, 50))
    page.draw_line(fitz.Point(50, 55), fitz.Point(100, 55))
    detailed = extract_walls_detailed(page, 0.1)
    doc.close()
    assert detailed["needs_review"] is True
    assert "curve support verification" in detailed["review_reasons"]


def test_synthetic_floorplan_curve_share_below_flag():
    truth = _floorplan_truth()
    doc = fitz.open(SYNTHETIC_DIR / truth["pdf"])
    detailed = extract_walls_detailed(doc[0], truth["fpp"])
    doc.close()
    assert detailed["needs_review"] is False


# ── Degenerate guards ─────────────────────────────────────────────────────────


def test_blank_page_returns_no_walls():
    doc = fitz.open()
    page = doc.new_page()
    assert extract_walls(page, 0.1) == []
    doc.close()


def test_missing_scale_returns_no_walls():
    doc = fitz.open()
    page = doc.new_page()
    assert extract_walls(page, 0) == []
    assert extract_walls(page, None) == []
    doc.close()
    assert wall_lf_by_class([], 0) == {}
    assert opening_gap_widths([], 0) == []


# ── Crow Cass fixture smoke ───────────────────────────────────────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page0_wall_extraction_smoke():
    from bobbytailor.deterministic.dimensions import extract_dimension_samples

    doc = fitz.open(CROW_PDF)
    page = doc[0]
    samples = extract_dimension_samples(page, page_index=0, doc=doc)
    ratios = [s.feet / s.points for s in samples if s.points > 0]
    median = statistics.median(ratios)
    fpp = statistics.median(
        [r for r in ratios if abs(r - median) / median <= 0.02]
    )

    walls = extract_walls(page, fpp)
    doc.close()

    lf = wall_lf_by_class(walls, fpp)
    assert len(lf) >= 1
    assert max(lf.values()) > 100.0, "dominant wall class must exceed 100 LF"
    # Door-opening gaps feed the scale solver's door_check: the 3'-0" band
    # cluster must exist with a median inside 3.0 +/- 2" (RESEARCH §2).
    gaps = opening_gap_widths(walls, fpp)
    band = [g for g in gaps if 2.83 <= g <= 3.17]
    assert band, "no door-band opening gaps found"
    assert 2.83 <= statistics.median(band) <= 3.17
