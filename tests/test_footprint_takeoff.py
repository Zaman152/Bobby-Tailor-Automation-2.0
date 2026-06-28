"""Tests for deterministic building-footprint extraction from overall dims."""
import os

import pytest

from footprint_takeoff import (
    Footprint,
    _parse_feet,
    _axis_dims,
    footprint_from_page,
    extract_building_footprint,
)


# ── Dimension parsing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("1136' - 0\"", 1136.0),
    ("350'-0", 350.0),
    ("55' - 6\"", 55.5),
    ("60'", 60.0),
    ("100' - 3\"", 100.25),
])
def test_parse_feet_valid(text, expected):
    assert _parse_feet(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [
    "12' - 0\"",      # below MIN_OVERALL_FT (a room/bay dim)
    "3000' - 0\"",    # above MAX_OVERALL_FT (site/property)
    "1136' - 14\"",   # invalid inches
    "TYP.",
    "A-101",
    "",
])
def test_parse_feet_rejected(text):
    assert _parse_feet(text) is None


# ── Synthetic page (axis separation via dir vector) ─────────────────────────────

class _FakePage:
    """Minimal page exposing get_text('dict') and ('text') like PyMuPDF."""
    def __init__(self, spans, title="OVERALL FLOOR PLAN"):
        # spans: list of (text, dir) where dir=(cos, sin)
        self._spans = spans
        self._title = title

    def get_text(self, kind="text"):
        if kind == "dict":
            return {
                "blocks": [
                    {"lines": [
                        {"dir": dir_, "spans": [{"text": txt, "bbox": (0, 0, 1, 1)}]}
                        for txt, dir_ in self._spans
                    ]}
                ]
            }
        return self._title + "\n"


def test_axis_separation_horizontal_vs_vertical():
    page = _FakePage([
        ("1136' - 0\"", (1.0, 0.0)),   # horizontal overall length
        ("350' - 0\"", (0.0, -1.0)),    # vertical overall depth
        ("54' - 0\"", (1.0, 0.0)),      # bay dims
        ("60' - 0\"", (0.0, -1.0)),
    ])
    horiz, vert = _axis_dims(page)
    assert max(horiz) == pytest.approx(1136.0)
    assert max(vert) == pytest.approx(350.0)


def test_footprint_from_synthetic_page():
    page = _FakePage([
        ("1136' - 0\"", (1.0, 0.0)),
        ("350' - 0\"", (0.0, -1.0)),
        ("54' - 0\"", (1.0, 0.0)),
        ("60' - 0\"", (0.0, -1.0)),
    ])
    fp = footprint_from_page(page)
    assert fp is not None
    assert fp.width_ft == pytest.approx(1136.0)
    assert fp.depth_ft == pytest.approx(350.0)
    assert fp.area_sf == pytest.approx(397600.0)
    assert fp.perimeter_lf == pytest.approx(2 * (1136 + 350))
    assert fp.confidence == "high"
    assert fp.needs_review is False


def test_footprint_none_when_single_axis():
    page = _FakePage([("1136' - 0\"", (1.0, 0.0))])  # no vertical dim
    assert footprint_from_page(page) is None


def test_footprint_medium_conf_when_not_dominant():
    # Overall dim does not clearly exceed the bay dims → flag for review.
    page = _FakePage([
        ("120' - 0\"", (1.0, 0.0)),
        ("110' - 0\"", (1.0, 0.0)),
        ("100' - 0\"", (0.0, -1.0)),
        ("95' - 0\"", (0.0, -1.0)),
    ])
    fp = footprint_from_page(page)
    assert fp is not None
    assert fp.confidence == "medium"
    assert fp.needs_review is True


# ── Crow regression (real PDF) ──────────────────────────────────────────────────

CROW = "tests/fixtures/crow_cass/crow_cass_plans.pdf"


@pytest.mark.skipif(not os.path.isfile(CROW), reason="Crow plans fixture not present")
def test_crow_footprint_matches_golden():
    """Golden Exposed Structure / Sealed Concrete footprint = 395,673 SF."""
    fp = extract_building_footprint(CROW)
    assert fp is not None
    # 1136 x 350 = 397,600 → within 2% of golden.
    assert fp.area_sf == pytest.approx(395673.0, rel=0.02)
    assert fp.confidence == "high"


# ── Legend conversion + authoritative override ──────────────────────────────────

from footprint_takeoff import footprint_to_legend
from object_manifest import Manifest, ManifestEntry
from aggregator import aggregate_takeoff


def _crow_manifest():
    return Manifest([
        ManifestEntry(name="Exposed Structure", unit="SF", measure="area",
                      aliases=["exposed deck", "open web joist", "bar joist"]),
        ManifestEntry(name="Sealed Concrete", unit="SF", measure="area",
                      aliases=["slab on grade", "concrete floor"]),
        ManifestEntry(name="CMU Wall", unit="SF", measure="area",
                      aliases=["cmu", "masonry"], assumptions={"height_ft": 35}),
        ManifestEntry(name="Internal Tilt up walls", unit="SF", measure="area",
                      aliases=["interior tilt up"], assumptions={"height_ft": 35}),
    ])


def test_legend_targets_floor_roof_not_walls():
    fp = Footprint(width_ft=1136, depth_ft=350, area_sf=397600.0,
                   perimeter_lf=2972.0, confidence="high", page_index=0)
    leg = footprint_to_legend(fp, _crow_manifest())
    names = {r["ITEM"] for r in leg["rows"]}
    assert names == {"Exposed Structure", "Sealed Concrete"}  # walls excluded
    assert leg["table_purpose"] == "takeoff_legend"
    assert all(r["UNIT"] == "SF" for r in leg["rows"])


def test_legend_none_without_manifest():
    fp = Footprint(width_ft=1136, depth_ft=350, area_sf=397600.0,
                   perimeter_lf=2972.0, confidence="high", page_index=0)
    assert footprint_to_legend(fp, None) is None


def test_footprint_overrides_unstable_vision_area():
    """The measured footprint suppresses the vision-guessed area for the item."""
    m = _crow_manifest()
    items = [
        # Authoritative footprint-derived legend row (what our legend becomes).
        {"description": "Exposed Structure", "item_type": "exposed_structure",
         "quantity": 397600.0, "unit": "SF",
         "qty_source": "companion_takeoff_legend", "confidence": "high"},
        # Unstable vision read of the same item — must be suppressed, not summed.
        {"description": "Exposed Structure", "item_type": "exposed_structure",
         "calculated_quantity": 440180.0, "calculated_unit": "SF",
         "qty_source": "measurement", "confidence": "medium"},
    ]
    summary = aggregate_takeoff(items, manifest=m)
    rows = [r for r in summary if r["item"] == "Exposed Structure"]
    assert len(rows) == 1, rows
    assert rows[0]["quantity"] == pytest.approx(397600.0)  # not 440180, not summed
