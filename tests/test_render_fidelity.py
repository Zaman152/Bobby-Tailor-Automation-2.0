"""
tests/test_render_fidelity.py — Render retarget + clip-crop primitives (21-05).

Pins the adaptive-fidelity contract from 21-RESEARCH.md §5:
  - Whole-sheet renders target RENDER_TARGET_PX (≈1568 px) long edge instead
    of the old 7900 px clamp (model downscales to ~1568 anyway — oversized
    renders waste tokens).
  - render_clip_crop() zooms INTO a region at native detail — the shared
    primitive for verify-retry crops (21-14), crop galleries (21-08), and
    ensemble tiles (21-11).
  - The 8000 px API hard cap is never exceeded.

Uses the crow_cass vector fixture (3024×2160 pt arch sheets). No API calls.
"""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from PIL import Image

from bobbytailor.pipeline import pdf_analyzer
from bobbytailor.pipeline.pdf_analyzer import (
    _MAX_IMAGE_LONG_SIDE_PX,
    _effective_render_scale,
    _page_to_image,
    _target_render_scale,
    render_clip_crop,
)

FIXTURE_PDF = str(
    Path(__file__).parent / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
)


@pytest.fixture(scope="module")
def crow_page():
    doc = fitz.open(FIXTURE_PDF)
    yield doc[0]
    doc.close()


# ---------------------------------------------------------------------------
# Whole-sheet render retarget
# ---------------------------------------------------------------------------

class TestPageToImage:
    def test_default_long_edge_targets_render_target_px(self, tmp_path):
        """Default whole-sheet render lands at ≈1568 px long edge."""
        path = _page_to_image(FIXTURE_PDF, 0, str(tmp_path))
        with Image.open(path) as img:
            long_edge = max(img.size)
        assert 1500 <= long_edge <= 1600, (
            f"long edge {long_edge} outside [1500, 1600] — render retarget broken"
        )

    def test_explicit_target_px_is_honored(self, tmp_path):
        path = _page_to_image(FIXTURE_PDF, 0, str(tmp_path), target_px=1000)
        with Image.open(path) as img:
            long_edge = max(img.size)
        assert 980 <= long_edge <= 1020

    def test_returns_png_path_with_page_numbering(self, tmp_path):
        path = _page_to_image(FIXTURE_PDF, 0, str(tmp_path))
        assert path.endswith("page_0001.png")
        assert Path(path).is_file()

    def test_oversized_target_capped_at_api_limit(self, tmp_path):
        """Even an absurd target never renders past the 8000 px API cap."""
        path = _page_to_image(FIXTURE_PDF, 0, str(tmp_path), target_px=50_000)
        with Image.open(path) as img:
            long_edge = max(img.size)
        assert long_edge <= _MAX_IMAGE_LONG_SIDE_PX + 1


# ---------------------------------------------------------------------------
# render_clip_crop — the shared zoom primitive
# ---------------------------------------------------------------------------

class TestRenderClipCrop:
    def test_square_rect_hits_target(self, crow_page):
        crop = render_clip_crop(crow_page, (100, 100, 200, 200), target_px=800)
        assert 780 <= max(crop.size) <= 820

    def test_accepts_fitz_rect(self, crow_page):
        crop = render_clip_crop(crow_page, fitz.Rect(0, 0, 400, 200), target_px=800)
        assert 780 <= max(crop.size) <= 820

    def test_default_target_is_1568(self, crow_page):
        crop = render_clip_crop(crow_page, (0, 0, 500, 250))
        assert 1540 <= max(crop.size) <= 1590

    def test_long_edge_drives_zoom_not_short_edge(self, crow_page):
        """A 2:1 rect at target 800 → 800 × 400, not 1600 × 800."""
        crop = render_clip_crop(crow_page, (0, 0, 200, 100), target_px=800)
        w, h = crop.size
        assert 780 <= w <= 820
        assert 380 <= h <= 420

    def test_returns_rgb_pil_image(self, crow_page):
        crop = render_clip_crop(crow_page, (0, 0, 100, 100), target_px=200)
        assert isinstance(crop, Image.Image)
        assert crop.mode == "RGB"

    def test_safety_cap_at_8000px(self, crow_page):
        """Tiny rect + huge target must clamp at the API hard cap."""
        crop = render_clip_crop(crow_page, (0, 0, 10, 10), target_px=999_999)
        assert max(crop.size) <= _MAX_IMAGE_LONG_SIDE_PX + 1

    def test_empty_rect_raises(self, crow_page):
        with pytest.raises(ValueError):
            render_clip_crop(crow_page, (100, 100, 100, 100), target_px=800)

    def test_inverted_rect_raises(self, crow_page):
        with pytest.raises(ValueError):
            render_clip_crop(crow_page, (200, 200, 100, 100), target_px=800)


# ---------------------------------------------------------------------------
# Scale helpers — contract for takeoff_pipeline's crop/tile renderers
# ---------------------------------------------------------------------------

class TestScaleHelpers:
    def test_effective_render_scale_clamps_to_api_cap(self, crow_page):
        longest = max(crow_page.rect.width, crow_page.rect.height)
        scale = _effective_render_scale(crow_page, 1_000.0)
        assert scale * longest <= _MAX_IMAGE_LONG_SIDE_PX + 1e-6

    def test_effective_render_scale_passes_small_scales_through(self, crow_page):
        assert _effective_render_scale(crow_page, 0.5) == 0.5

    def test_target_render_scale_lands_on_target(self, crow_page):
        longest = max(crow_page.rect.width, crow_page.rect.height)
        scale = _target_render_scale(crow_page, 1568)
        assert abs(scale * longest - 1568) < 1.0

    def test_api_cap_constant_is_8000(self):
        """RESEARCH §5: the hard API limit is 8000 px — the old 7900 clamp
        (used as a render TARGET) is gone."""
        assert _MAX_IMAGE_LONG_SIDE_PX == 8000
        source = Path(pdf_analyzer.__file__).read_text()
        assert "7900" not in source
