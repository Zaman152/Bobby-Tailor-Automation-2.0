"""Layer-1 tests for the Recipe C room polygonize + footprint engine."""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.rooms import (
    RoomPolygon,
    building_footprint,
    extract_rooms,
    rooms_to_legend,
)
from bobbytailor.deterministic.walls import extract_walls

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC_DIR = FIXTURES / "synthetic"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"

# Crow p0 main-plan viewport (unrotated PDF points) and dims-anchored truth.
CROW_MAIN_BBOX = (303.12, 957.24, 2691.0, 2105.88)
CROW_FOOTPRINT_SF = 397_600.0  # 1136' x 350' overall dims (proven anchor)


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
def floorplan_rooms():
    """(rooms, walls, truth, fpp, doc) for the synthetic floor plan."""
    truth = _floorplan_truth()
    fpp = truth["fpp"]
    doc = fitz.open(SYNTHETIC_DIR / truth["pdf"])
    page = doc[0]
    walls = extract_walls(page, fpp)
    rooms = extract_rooms(page, walls, (0, 0, 1000, 800), fpp)
    fp = building_footprint(rooms, fpp, walls=walls, page=page)
    doc.close()
    return rooms, walls, truth, fpp, fp


# ── Synthetic: face count and areas ───────────────────────────────────────────


def test_synthetic_room_count_exact(floorplan_rooms):
    rooms, _, truth, _, _ = floorplan_rooms
    # Slivers, the exterior face, and the arc dangle must all be discarded:
    # exactly the four drawn rooms remain.
    assert len(rooms) == truth["room_count"] == 4


def test_synthetic_room_areas_within_2pct(floorplan_rooms):
    rooms, _, truth, fpp, _ = floorplan_rooms
    got = sorted(r.area_pt2 * fpp * fpp for r in rooms)
    expected = sorted(truth["room_areas_sf"].values())
    for g, e in zip(got, expected):
        assert g == pytest.approx(e, rel=0.02)


def test_synthetic_labels_bound_correctly(floorplan_rooms):
    rooms, _, truth, fpp, _ = floorplan_rooms
    by_label = {r.label: r.area_pt2 * fpp * fpp for r in rooms}
    for name, expected_sf in truth["room_areas_sf"].items():
        assert name in by_label, f"room label {name!r} not bound"
        assert by_label[name] == pytest.approx(expected_sf, rel=0.02)
    for room in rooms:
        assert room.label_source == "text_in_polygon"
        assert room.confidence == "high"
        assert room.candidate_id.startswith("ROOM-")


def test_synthetic_candidate_ids_by_area_desc(floorplan_rooms):
    rooms, _, _, _, _ = floorplan_rooms
    areas = [r.area_pt2 for r in rooms]
    assert areas == sorted(areas, reverse=True)
    assert [r.candidate_id for r in rooms] == [
        "ROOM-%d" % i for i in range(1, len(rooms) + 1)
    ]


# ── Synthetic: footprint + dims cross-check ───────────────────────────────────


def test_synthetic_footprint_within_2pct_and_crosscheck(floorplan_rooms):
    _, _, truth, _, fp = floorplan_rooms
    assert fp["area_sf"] == pytest.approx(truth["footprint_sf"], rel=0.02)
    # Both deterministic methods agree: delta <= 2%, no review flag.
    assert fp["dims_area_sf"] == pytest.approx(truth["footprint_sf"], rel=0.001)
    assert fp["dims_crosscheck"] is not None
    assert fp["dims_crosscheck"] <= 0.02
    assert fp["needs_review"] is False


def test_footprint_disagreement_flags_review(floorplan_rooms):
    rooms, walls, truth, fpp, _ = floorplan_rooms
    # Same page geometry at a WRONG scale: dims text no longer matches the
    # polygon footprint — must flag, never silently pick a winner.
    doc = fitz.open(SYNTHETIC_DIR / truth["pdf"])
    wrong_fpp = fpp * 1.5
    fp = building_footprint(rooms, wrong_fpp, walls=walls, page=doc[0])
    doc.close()
    assert fp["needs_review"] is True
    assert fp["review_reason"] == "footprint methods disagree"
    assert fp["dims_crosscheck"] > 0.02


# ── Legend handoff ────────────────────────────────────────────────────────────


def test_rooms_to_legend_shape(floorplan_rooms):
    rooms, _, truth, fpp, _ = floorplan_rooms
    legend = rooms_to_legend(rooms, fpp)
    assert legend is not None
    assert legend["table_purpose"] == "takeoff_legend"
    assert legend["use_for_takeoff"] is True
    assert legend["_provenance"] == "geometry"
    assert legend["_confidence"] == "high"
    assert len(legend["rows"]) == 4
    for row in legend["rows"]:
        assert row["UNIT"] == "SF"
        assert float(row["QTY"]) > 0
        assert row["ITEM"] in truth["room_areas_sf"]
    assert rooms_to_legend([], fpp) is None


# ── Degenerate guards ─────────────────────────────────────────────────────────


def test_no_walls_page_returns_empty():
    doc = fitz.open()
    page = doc.new_page()
    assert extract_rooms(page, [], (0, 0, 612, 792), 0.1) == []
    assert extract_rooms(page, extract_walls(page, 0.1), None, 0.1) == []
    doc.close()


def test_missing_scale_returns_empty():
    doc = fitz.open()
    page = doc.new_page()
    assert extract_rooms(page, [], (0, 0, 612, 792), 0) == []
    doc.close()
    fp = building_footprint([], 0)
    assert fp["area_sf"] is None
    assert fp["needs_review"] is True


def test_room_polygon_to_dict_roundtrip(floorplan_rooms):
    rooms, _, _, _, _ = floorplan_rooms
    d = rooms[0].to_dict()
    assert set(d) == {
        "polygon_wkt", "area_pt2", "label", "label_source",
        "candidate_id", "confidence",
    }
    json.dumps(d)  # report-serializable


# ── Crow Cass anchor ──────────────────────────────────────────────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page0_footprint_within_5pct_of_anchor():
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
    rooms = extract_rooms(page, walls, CROW_MAIN_BBOX, fpp)
    fp = building_footprint(rooms, fpp, walls=walls, page=page)
    doc.close()

    assert rooms, "Crow p0 must yield room polygons"
    assert any(r.label_source == "text_in_polygon" for r in rooms)
    assert fp["area_sf"] == pytest.approx(CROW_FOOTPRINT_SF, rel=0.05)
    # Honest cross-check: agree within 2% OR carry the review flag.
    assert (
        fp["dims_crosscheck"] is not None and fp["dims_crosscheck"] <= 0.02
    ) or fp["needs_review"] is True
