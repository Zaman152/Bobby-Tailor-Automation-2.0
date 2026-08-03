"""
Unit tests for pdf_analyzer sheet-ID extraction.

Tests are discipline-agnostic: architectural, structural, civil, MEP, and
pure-noise cases are all exercised.  No real PDF is required — we mock the
PyMuPDF (fitz) page/document objects to control word bounding boxes exactly.
"""
import re
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal fitz stub so tests run without PyMuPDF installed in CI
# ---------------------------------------------------------------------------
if "fitz" not in sys.modules:
    fitz_stub = types.ModuleType("fitz")

    class _Rect:
        def __init__(self, width=816, height=1056):
            self.width = width
            self.height = height

    class _Page:
        def __init__(self, words, full_text, width=816, height=1056):
            self._words = words
            self._full_text = full_text
            self.rect = _Rect(width, height)

        def get_text(self, mode=None):
            if mode == "words":
                return self._words
            return self._full_text

    class _Document:
        def __init__(self, pages):
            self._pages = pages

        def __getitem__(self, idx):
            return self._pages[idx]

        def __len__(self):
            return len(self._pages)

    fitz_stub.Document = _Document
    fitz_stub.open = lambda *a, **kw: _Document([])
    sys.modules["fitz"] = fitz_stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(title_block_words=None, full_text="", width=816, height=1056):
    """Build a minimal fitz Document stub with one page."""
    import fitz  # noqa: PLC0415

    # Construct word tuples (x0, y0, x1, y1, word, ...)
    # Title-block region: x > width*0.55 and y > height*0.80
    tb_x = width * 0.60   # safely inside title block (x)
    tb_y = height * 0.85  # safely inside title block (y)
    body_x = width * 0.10  # outside title block (x)
    body_y = height * 0.30  # outside title block (y)

    words = []
    if title_block_words:
        for word in title_block_words:
            words.append((tb_x, tb_y, tb_x + 30, tb_y + 10, word, 0, 0, 0))

    # Any word not in the title block goes in the body region
    # (the full_text is returned for get_text() calls without "words" mode)

    page = fitz.Document.__new__(fitz.Document)  # type: ignore[call-arg]
    # Use the private stub implementation directly
    inner_page = type("_Page", (), {
        "rect": type("_Rect", (), {"width": width, "height": height})(),
        "_words": words,
        "_full_text": full_text,
        "get_text": lambda self, mode=None: self._words if mode == "words" else self._full_text,
    })()
    inner_page._words = words
    inner_page._full_text = full_text

    doc = type("_Doc", (), {
        "__getitem__": lambda self, i: inner_page,
        "__len__": lambda self: 1,
    })()
    return doc


# ---------------------------------------------------------------------------
# Import after potential fitz stub registration
# ---------------------------------------------------------------------------
from bobbytailor.pipeline.pdf_analyzer import (  # noqa: E402
    SHEET_ID_NOISE_PATTERNS,
    _is_noise_sheet_candidate,
    _sheet_name_from_doc,
    get_title_block_text,
)


# ---------------------------------------------------------------------------
# SHEET_ID_NOISE_PATTERNS structure tests
# ---------------------------------------------------------------------------

class TestNoisePatterns:
    def test_noise_patterns_is_list(self):
        assert isinstance(SHEET_ID_NOISE_PATTERNS, list)
        assert len(SHEET_ID_NOISE_PATTERNS) > 0

    def test_astm_pattern_present(self):
        combined = " ".join(SHEET_ID_NOISE_PATTERNS)
        assert "ASTM" in combined, "ASTM noise pattern must be present"

    def test_nfpa_pattern_present(self):
        combined = " ".join(SHEET_ID_NOISE_PATTERNS)
        assert "NFPA" in combined

    def test_no_hardcoded_e283(self):
        """Noise list must be generic — E283 must NOT appear as a literal."""
        for pat in SHEET_ID_NOISE_PATTERNS:
            assert "E283" not in pat, (
                "E283 must not be hardcoded; use generic ASTM pattern instead"
            )

    def test_no_hardcoded_a156(self):
        for pat in SHEET_ID_NOISE_PATTERNS:
            assert "A156" not in pat


# ---------------------------------------------------------------------------
# _is_noise_sheet_candidate
# ---------------------------------------------------------------------------

class TestIsNoiseSheetCandidate:
    def test_e283_in_astm_context_is_noise(self):
        page_text = "Glazing tested per ASTM E283 standard."
        assert _is_noise_sheet_candidate("E283", page_text) is True

    def test_nfpa13_number_is_noise(self):
        page_text = "Sprinkler system per NFPA 13."
        # "13" is not a sheet-ID candidate by regex anyway, but if it were
        assert _is_noise_sheet_candidate("13", page_text) is True

    def test_valid_sheet_id_a4_0_not_noise(self):
        page_text = "See sheet A4.0 for details. Also refer to ASTM E283."
        assert _is_noise_sheet_candidate("A4.0", page_text) is False

    def test_c4_not_noise(self):
        """C-4 (civil sheet) must not be classified as noise."""
        page_text = "Civil grading plan C-4."
        assert _is_noise_sheet_candidate("C-4", page_text) is False

    def test_a101_not_noise(self):
        page_text = "Floor plan sheet A-101."
        assert _is_noise_sheet_candidate("A-101", page_text) is False

    def test_s1_2_not_noise(self):
        page_text = "Structural framing plan S1.2."
        assert _is_noise_sheet_candidate("S1.2", page_text) is False

    def test_a36_in_astm_context_is_noise(self):
        page_text = "Structural steel ASTM A36 material."
        assert _is_noise_sheet_candidate("A36", page_text) is True


# ---------------------------------------------------------------------------
# _sheet_name_from_doc — title-block-first extraction
# ---------------------------------------------------------------------------

class TestSheetNameFromDoc:

    # --- Architectural ---

    def test_a4_0_wins_over_astm_e283(self):
        """A4.0 must be returned even when ASTM E283 appears on the same page."""
        doc = _make_doc(
            title_block_words=["ELEVATION", "A4.0"],
            full_text="Glazing per ASTM E283. See elevation A4.0.",
        )
        assert _sheet_name_from_doc(doc, 0) == "A4.0"

    def test_a_101_hyphenated(self):
        """A-101 with hyphen must parse correctly."""
        doc = _make_doc(
            title_block_words=["FLOOR", "PLAN", "A-101"],
            full_text="Floor plan A-101.",
        )
        assert _sheet_name_from_doc(doc, 0) == "A-101"

    # --- Structural ---

    def test_s1_2_from_title_block(self):
        """S1.2 in title block wins over NFPA 13 in body text."""
        doc = _make_doc(
            title_block_words=["FRAMING", "PLAN", "S1.2"],
            full_text="Structural framing per NFPA 13. Sheet S1.2.",
        )
        assert _sheet_name_from_doc(doc, 0) == "S1.2"

    # --- Civil ---

    def test_c4_civil_sheet(self):
        """C-4 civil sheet ID extracted from title block."""
        doc = _make_doc(
            title_block_words=["GRADING", "PLAN", "C-4"],
            full_text="Civil grading plan. See sheet C-4.",
        )
        assert _sheet_name_from_doc(doc, 0) == "C-4"

    # --- MEP ---

    def test_m3_1_mechanical_schedule(self):
        """M3.1 mechanical schedule sheet ID extracted."""
        doc = _make_doc(
            title_block_words=["MECH", "SCHED", "M3.1"],
            full_text="HVAC equipment schedule M3.1.",
        )
        assert _sheet_name_from_doc(doc, 0) == "M3.1"

    # --- Noise-only page → fallback ---

    def test_only_astm_references_returns_page_fallback(self):
        """When a page has only ASTM references and no real sheet ID, return Page_N."""
        doc = _make_doc(
            title_block_words=["ASTM", "E283", "ASTM", "A156"],
            full_text="All glazing tested per ASTM E283. Steel per ASTM A156.",
        )
        result = _sheet_name_from_doc(doc, 0)
        assert result == "Page_1"

    # --- Title-block boundary: words outside region are ignored ---

    def test_only_title_block_words_used_when_available(self):
        """Sheet ID in title block takes priority over a different ID elsewhere."""
        # Title block has G0.1; body text has A101 — G0.1 should win
        doc = _make_doc(
            title_block_words=["GENERAL", "NOTES", "G0.1"],
            full_text="Refer to sheet A101 for details. G0.1 general notes.",
        )
        assert _sheet_name_from_doc(doc, 0) == "G0.1"

    # --- Full-page fallback skips noise ---

    def test_full_page_fallback_skips_astm_finds_valid_id(self):
        """Full-page fallback skips ASTM token; returns first valid sheet ID."""
        # No title-block words; full text has ASTM E283 then A-101
        doc = _make_doc(
            title_block_words=[],
            full_text="Spec ref ASTM E283. See architectural plan A-101.",
        )
        assert _sheet_name_from_doc(doc, 0) == "A-101"


# ---------------------------------------------------------------------------
# get_title_block_text
# ---------------------------------------------------------------------------

class TestGetTitleBlockText:
    def test_returns_only_bottom_right_words(self):
        """Words outside the bottom-right region must be excluded."""
        doc = _make_doc(
            title_block_words=["A4.0"],
            full_text="Body text not in title block.",
        )
        tb_text = get_title_block_text(doc, 0)
        assert "A4.0" in tb_text

    def test_empty_title_block_returns_empty_string(self):
        doc = _make_doc(title_block_words=[], full_text="Body text only.")
        tb_text = get_title_block_text(doc, 0)
        assert tb_text.strip() == ""


# ---------------------------------------------------------------------------
# Plan 23-06 Task 1 — the structural window search
#
# get_title_block_text no longer assumes a fixed fraction of the page. It walks
# progressively WIDER bottom-right candidates and keeps the first whose text
# looks like a title block; when none does it returns the widest candidate,
# which is the historical window. That fallback is what makes the change a
# strict refinement, so it is pinned here as behaviour, not as source text.
# ---------------------------------------------------------------------------

from bobbytailor.pipeline.pdf_analyzer import (  # noqa: E402
    _TITLE_BLOCK_WINDOWS,
    _window_text,
)


class TestTitleBlockWindowLadder:
    def test_the_widest_candidate_is_the_historical_window(self):
        """FORBIDDEN by 23-CONTEXT: changing this number as the fix. INV-00 §1d
        measured that sweeping it 0.55 -> 0.88 fixes Moxy and BREAKS Chelsea
        (2 -> 10 skips, floor plans 9 -> 1). Asserted on RESOLVED VALUES so a
        refactor of the search cannot break the pin for the wrong reason."""
        windows = [tuple(map(float, c)) for c in _TITLE_BLOCK_WINDOWS]
        assert windows[-1] == (0.55, 0.80), (
            "the widest candidate must remain the current window, got %r"
            % (windows[-1],)
        )

    def test_the_search_evaluates_at_least_one_tighter_candidate(self):
        windows = [tuple(map(float, c)) for c in _TITLE_BLOCK_WINDOWS]
        assert any(x > 0.55 for x, _y in windows[:-1])

    def test_candidates_run_narrow_to_wide(self):
        widths = [float(x) for x, _y in _TITLE_BLOCK_WINDOWS]
        assert widths == sorted(widths, reverse=True)

    def test_the_height_fraction_is_never_varied(self):
        """Only the width strip is searched; the 0.80 height bound is untouched."""
        assert {float(y) for _x, y in _TITLE_BLOCK_WINDOWS} == {0.80}


class TestTitleBlockFallbackIsUnchangedBehaviour:
    """A page whose bottom-right region is pure keynote prose must extract
    EXACTLY what it extracted before the search existed."""

    KEYNOTE_WORDS = (
        "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING MASTER "
        "SWITCH AND COORDINATE LOCATION OF OUTLET WITH THE RECESS CUTOUT"
    ).split()

    def test_pure_prose_falls_back_to_the_widest_window(self):
        doc = _make_doc(title_block_words=list(self.KEYNOTE_WORDS))
        extracted = get_title_block_text(doc, 0)
        legacy = _window_text(doc[0], *_TITLE_BLOCK_WINDOWS[-1])
        assert extracted == legacy
        assert extracted == " ".join(self.KEYNOTE_WORDS)

    def test_an_empty_bottom_right_region_still_returns_empty(self):
        doc = _make_doc(title_block_words=[], full_text="Body text only.")
        assert get_title_block_text(doc, 0) == _window_text(
            doc[0], *_TITLE_BLOCK_WINDOWS[-1]
        )

    def test_a_structured_title_block_is_still_extracted(self):
        """The stub places every word at x = 0.60 W, i.e. only the widest
        candidate can see it — so a title-block-shaped page also resolves via
        the fallback, and the text is identical either way."""
        doc = _make_doc(
            title_block_words="SHEET NO. A-101 JOB NO. 2601014 DATE".split()
        )
        assert get_title_block_text(doc, 0) == "SHEET NO. A-101 JOB NO. 2601014 DATE"
