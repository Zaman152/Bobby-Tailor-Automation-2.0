"""Contract for the nearest-plan-text anchor primitive (V4-DET-01, plan 24-01).

ZERO API. Every test here runs free: synthetic word lists for the unit
contract, and the real Crow PDF (skipped when absent) for the committed
measurement baseline.

Two disciplines inherited from the phase-23 gates and enforced here:

* **A check either ASSERTS or SKIPS** (``test_phase23_acceptance.py`` rule 3).
  Nothing in this module may pass because its fixture was missing.
* **Assert SHAPES, POSITIONS and SETS — never a scored total**
  (``test_four_set_coverage.py``).  Nothing here moves the 56-mark bollard
  cluster toward the 28 in the human take-off, or the 136-mark cluster toward
  its 132.  Both apparent hits were PROVEN coincidental (collinear dimension
  ticks at ``yspan=0``; ``_dedup_colocated_count(56) -> 56``) in ground truth
  sections 10 and 11.0.  Phase 25 owns whether those counts are right; this
  phase owns only whether they can be NAMED.

The paid-script and credential names this gate greps for are assembled from
fragments below rather than spelled out, because the phase's own acceptance
one-liner greps THIS FILE for those literals and must find none.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.deterministic.text_anchor import (  # noqa: E402
    ANCHOR_RADIUS_PT,
    ANCHOR_RADIUS_TEXT_HEIGHTS,
    anchor_record,
    anchors_for_candidates,
    box_distance_pt,
    nearest_anchor,
    page_radius_pt,
    page_words,
)

MODULE_PATH = ROOT / "src" / "bobbytailor" / "deterministic" / "text_anchor.py"

# Assembled, never spelled — see the module docstring.
FORBIDDEN_CREDENTIAL = "ANTHROPIC" + "_API_KEY"
FORBIDDEN_PAID = (
    FORBIDDEN_CREDENTIAL,
    "accuracy" + "_gate",
    "vision_only" + "_benchmark",
    "gold" + "en_convergence",
    "gold" + "en",
)

ANCHOR_KEYS = {
    "candidate_id",
    "anchor_text",
    "anchor_kind",
    "anchor_dist_pt",
    "anchor_source",
    "ambiguity_reason",
}


# ---------------------------------------------------------------------------
# Synthetic page — the unit contract is provable with no PDF at all.
# ---------------------------------------------------------------------------


class FakePage:
    """The two ``get_text`` shapes this module reads, and nothing else."""

    number = 0

    def __init__(self, words, lines=None):
        # PyMuPDF's own 8-tuple shape, so the harvest is exercised as it ships.
        self._words = [
            (w[0], w[1], w[2], w[3], w[4], 0, 0, i) for i, w in enumerate(words)
        ]
        self._lines = list(lines or [])

    def get_text(self, kind):
        if kind == "words":
            return list(self._words)
        if kind == "dict":
            return {"blocks": [{"lines": list(self._lines)}]}
        raise ValueError("unexpected get_text(%r)" % kind)


def _line(text, bbox, text_dir=(1.0, 0.0)):
    return {"dir": text_dir, "bbox": tuple(bbox), "spans": [{"text": text}]}


def _word(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text)


# ---------------------------------------------------------------------------
# Behaviour 1 — a word inside the bbox is a contained anchor at distance zero.
# ---------------------------------------------------------------------------


def test_a_word_inside_the_bbox_is_a_contained_anchor():
    words = [_word(105.0, 102.0, 125.0, 112.0, "PUMP")]
    rec = nearest_anchor((100.0, 100.0, 140.0, 120.0), words, candidate_id="SYM-1")
    assert rec["anchor_text"] == "PUMP"
    assert rec["anchor_kind"] == "contained"
    assert rec["anchor_dist_pt"] == 0.0
    assert rec["anchor_source"] == "page_words"
    assert rec["candidate_id"] == "SYM-1"


def test_a_contained_word_outranks_a_nearer_looking_outside_word():
    """Precedence is contained-first, not smallest-number-first."""
    words = [
        _word(141.0, 105.0, 150.0, 115.0, "OUTSIDE"),  # 1 pt away, but outside
        _word(105.0, 102.0, 125.0, 112.0, "INSIDE"),
    ]
    rec = nearest_anchor((100.0, 100.0, 140.0, 120.0), words, radius_pt=40.0)
    assert rec["anchor_text"] == "INSIDE"
    assert rec["anchor_kind"] == "contained"


# ---------------------------------------------------------------------------
# Behaviour 2 — a masked word is never the anchor, however near it sits.
# ---------------------------------------------------------------------------


def test_a_masked_word_is_never_the_anchor():
    """A door-schedule tag column must not become a plan-body anchor (T-24-02)."""
    words = [
        _word(142.0, 105.0, 160.0, 115.0, "SCHEDULE-TAG"),  # nearest, but masked
        _word(200.0, 105.0, 240.0, 115.0, "BOLLARD"),
    ]
    mask = [(140.0, 100.0, 180.0, 130.0)]
    rec = nearest_anchor(
        (100.0, 100.0, 140.0, 120.0), words, mask_rects=mask, radius_pt=200.0
    )
    assert rec["anchor_text"] == "BOLLARD"
    assert rec["anchor_kind"] == "nearest_word"


def test_masking_can_leave_a_candidate_with_no_anchor_at_all():
    words = [_word(142.0, 105.0, 160.0, 115.0, "SCHEDULE-TAG")]
    mask = [(140.0, 100.0, 180.0, 130.0)]
    rec = nearest_anchor(
        (100.0, 100.0, 140.0, 120.0), words, mask_rects=mask, radius_pt=200.0
    )
    assert rec["anchor_text"] is None
    assert rec["anchor_kind"] is None


# ---------------------------------------------------------------------------
# Behaviour 3 — no text in range records an ABSENCE, never a substitute.
# ---------------------------------------------------------------------------


def test_no_text_in_range_records_an_absence_not_a_guess():
    words = [_word(1000.0, 1000.0, 1040.0, 1010.0, "FAR AWAY")]
    rec = nearest_anchor((100.0, 100.0, 140.0, 120.0), words, radius_pt=38.0)
    assert rec["anchor_text"] is None
    assert rec["anchor_kind"] is None
    assert rec["anchor_dist_pt"] is None
    assert rec["anchor_source"] is None
    # The absence is not filled from the candidate's own id or shape.
    assert "SYM" not in json.dumps(rec)


def test_an_empty_page_yields_an_absence_for_every_candidate():
    page = FakePage(words=[], lines=[])
    out = anchors_for_candidates(page, {"SYM-1": (10.0, 10.0, 20.0, 20.0)})
    assert set(out) == {"SYM-1"}
    assert out["SYM-1"]["anchor_text"] is None


# ---------------------------------------------------------------------------
# Behaviour 4 — ties resolve identically on every call (document order).
# ---------------------------------------------------------------------------


def test_equal_distance_words_resolve_by_document_order_every_call():
    box = (100.0, 100.0, 140.0, 120.0)
    words = [
        _word(150.0, 100.0, 170.0, 120.0, "RIGHT"),  # 10 pt right
        _word(70.0, 100.0, 90.0, 120.0, "LEFT"),  # 10 pt left — same distance
    ]
    first = nearest_anchor(box, words, radius_pt=38.0)
    assert first["anchor_dist_pt"] == 10.0
    assert first["anchor_text"] == "RIGHT"  # earlier in document order
    for _ in range(5):
        assert nearest_anchor(box, words, radius_pt=38.0) == first
    # Reversing document order reverses the winner — proving the tie really is
    # broken by order and not by geometry luck.
    flipped = nearest_anchor(box, list(reversed(words)), radius_pt=38.0)
    assert flipped["anchor_text"] == "LEFT"


def test_the_nearest_word_wins_when_distances_differ():
    box = (100.0, 100.0, 140.0, 120.0)
    words = [
        _word(160.0, 100.0, 180.0, 120.0, "FURTHER"),
        _word(145.0, 100.0, 165.0, 120.0, "NEARER"),
    ]
    rec = nearest_anchor(box, words, radius_pt=38.0)
    assert rec["anchor_text"] == "NEARER"
    assert rec["anchor_dist_pt"] == 5.0


# ---------------------------------------------------------------------------
# Behaviour 5 — a two-token tag is ONE anchor, not two words.
# ---------------------------------------------------------------------------


def test_a_paired_tag_is_returned_as_one_anchor():
    box = (60.0, 100.0, 95.0, 110.0)
    tag_pairs = [_word(100.0, 100.0, 118.0, 110.0, "B 1")]
    rec = nearest_anchor(box, [], tag_pairs=tag_pairs, radius_pt=38.0)
    assert rec["anchor_text"] == "B 1"
    assert rec["anchor_kind"] == "tag"
    assert rec["anchor_source"] == "tag_pairing"
    assert rec["anchor_dist_pt"] == 5.0


def test_a_page_printed_tag_pairs_through_sp6_and_hides_its_own_tokens():
    """The SP-6 pairer runs on the page, and 'B' alone never becomes an anchor."""
    words = [_word(100.0, 100.0, 108.0, 110.0, "B"), _word(112.0, 100.0, 118.0, 110.0, "1")]
    lines = [
        _line("B", (100.0, 100.0, 108.0, 110.0)),
        _line("1", (112.0, 100.0, 118.0, 110.0)),
    ]
    page = FakePage(words, lines)
    out = anchors_for_candidates(page, {"SYM-1": (60.0, 100.0, 95.0, 110.0)})
    rec = out["SYM-1"]
    assert rec["anchor_text"] == "B 1"
    assert rec["anchor_kind"] == "tag"
    assert rec["anchor_source"] == "tag_pairing"


def test_a_rotated_sheet_pairs_the_same_tag():
    """SP-6's whole point: a y-stacked reader returns nothing on dir=(0,-1)."""
    words = [
        _word(100.0, 100.0, 110.0, 118.0, "B"),
        _word(100.0, 80.0, 110.0, 96.0, "1"),
    ]
    lines = [
        _line("B", (100.0, 100.0, 110.0, 118.0), text_dir=(0.0, -1.0)),
        _line("1", (100.0, 80.0, 110.0, 96.0), text_dir=(0.0, -1.0)),
    ]
    page = FakePage(words, lines)
    out = anchors_for_candidates(page, {"SYM-1": (100.0, 122.0, 110.0, 132.0)})
    assert out["SYM-1"]["anchor_kind"] == "tag"
    assert out["SYM-1"]["anchor_text"] == "B 1"


# ---------------------------------------------------------------------------
# Behaviour 6 — a contested anchor leaves BOTH candidates unanchored.
# ---------------------------------------------------------------------------


def test_a_contested_anchor_leaves_both_candidates_unanchored():
    """SP-7c bind_or_flag: never round-robin a name to whoever was scanned first."""
    words = [_word(100.0, 100.0, 140.0, 110.0, "PUMP")]
    page = FakePage(words, [_line("PUMP", (100.0, 100.0, 140.0, 110.0))])
    out = anchors_for_candidates(
        page,
        {
            "SYM-1": (80.0, 100.0, 90.0, 110.0),  # 10 pt left of PUMP
            "SYM-2": (150.0, 100.0, 160.0, 110.0),  # 10 pt right of PUMP
        },
        radius_pt=38.0,
    )
    for cid in ("SYM-1", "SYM-2"):
        assert out[cid]["anchor_text"] is None, cid
        assert out[cid]["anchor_kind"] is None, cid
        assert "PUMP" in out[cid]["ambiguity_reason"], cid
        assert "SYM-1" in out[cid]["ambiguity_reason"], cid
        assert "SYM-2" in out[cid]["ambiguity_reason"], cid


def test_an_uncontested_anchor_still_binds_when_a_neighbour_has_its_own():
    words = [
        _word(100.0, 100.0, 140.0, 110.0, "PUMP"),
        _word(200.0, 100.0, 240.0, 110.0, "TANK"),
    ]
    page = FakePage(
        words,
        [
            _line("PUMP", (100.0, 100.0, 140.0, 110.0)),
            _line("TANK", (200.0, 100.0, 240.0, 110.0)),
        ],
    )
    out = anchors_for_candidates(
        page,
        {
            "SYM-1": (80.0, 100.0, 90.0, 110.0),
            "SYM-2": (250.0, 100.0, 260.0, 110.0),
        },
        radius_pt=38.0,
    )
    assert out["SYM-1"]["anchor_text"] == "PUMP"
    assert out["SYM-2"]["anchor_text"] == "TANK"


# ---------------------------------------------------------------------------
# Behaviour 7 — records are plain, JSON-serialisable dicts.
# ---------------------------------------------------------------------------


def test_anchor_records_are_plain_json_serialisable_dicts():
    rec = anchor_record("SYM-1", "B 1", "tag", 4.25, "tag_pairing")
    assert isinstance(rec, dict)
    assert set(rec) == ANCHOR_KEYS
    assert json.loads(json.dumps(rec)) == rec
    absent = anchor_record("SYM-2", None, None, None, None, "contested")
    assert json.loads(json.dumps(absent)) == absent
    assert absent["ambiguity_reason"] == "contested"


# ---------------------------------------------------------------------------
# The radius — a POSITIONAL rule, never an accuracy dial.
# ---------------------------------------------------------------------------


def test_the_radius_bounds_the_search_by_position():
    """Hand-provable: 20 pt away is in at r=38, out at r=10."""
    box = (100.0, 100.0, 140.0, 120.0)
    words = [_word(160.0, 100.0, 180.0, 120.0, "LABEL")]
    assert box_distance_pt(box, (160.0, 100.0, 180.0, 120.0)) == 20.0
    assert nearest_anchor(box, words, radius_pt=38.0)["anchor_text"] == "LABEL"
    assert nearest_anchor(box, words, radius_pt=10.0)["anchor_text"] is None


def test_the_radius_is_expressed_in_text_heights_of_the_page_it_reads():
    """The same rule gives a different radius on a differently-drafted sheet.

    Measured free this session over ``page.get_text("words")``: Crow 9.56 pt,
    Moxy 9.64, Chelsea 7.56, Bob's 26.41 — a 3.5x spread on the identical
    3024 x 2160 pt sheet.  A single absolute constant is ~5 text-heights of
    reach on one set and ~1.4 on another, which is the one-plan-set defect
    ``test_four_set_coverage.py`` exists to catch.
    """
    small = [_word(0.0, 0.0, 10.0, 8.0, "A"), _word(0.0, 20.0, 10.0, 28.0, "B")]
    large = [_word(0.0, 0.0, 10.0, 24.0, "A"), _word(0.0, 40.0, 10.0, 64.0, "B")]
    assert page_radius_pt(small) == pytest.approx(8.0 * ANCHOR_RADIUS_TEXT_HEIGHTS)
    assert page_radius_pt(large) == pytest.approx(24.0 * ANCHOR_RADIUS_TEXT_HEIGHTS)
    # A page with no measurable text falls back to the absolute constant.
    assert page_radius_pt([]) == ANCHOR_RADIUS_PT


def test_the_fallback_radius_is_four_nominal_text_heights():
    assert ANCHOR_RADIUS_TEXT_HEIGHTS == 4.0
    assert ANCHOR_RADIUS_PT == pytest.approx(38.0)


# ---------------------------------------------------------------------------
# Determinism and shape of the page-scale entry point.
# ---------------------------------------------------------------------------


def test_anchors_for_candidates_is_byte_identical_on_repeat():
    words = [
        _word(100.0, 100.0, 140.0, 110.0, "PUMP"),
        _word(200.0, 100.0, 240.0, 110.0, "TANK"),
        _word(300.0, 100.0, 340.0, 110.0, "BOLLARD"),
    ]
    lines = [_line(w[4], w[:4]) for w in words]
    page = FakePage(words, lines)
    candidates = {
        "SYM-3": (150.0, 100.0, 160.0, 110.0),
        "SYM-1": (80.0, 100.0, 90.0, 110.0),
        "SYM-2": (345.0, 100.0, 355.0, 110.0),
    }
    first = anchors_for_candidates(page, candidates)
    second = anchors_for_candidates(page, candidates)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert set(first) == set(candidates)


def test_every_candidate_gets_exactly_one_well_formed_record():
    page = FakePage([_word(0.0, 0.0, 10.0, 10.0, "X")], [_line("X", (0, 0, 10, 10))])
    candidates = {"SYM-1": (500.0, 500.0, 510.0, 510.0), "ROOM-1": (0.0, 0.0, 10.0, 10.0)}
    out = anchors_for_candidates(page, candidates)
    assert set(out) == set(candidates)
    for cid, rec in out.items():
        assert set(rec) == ANCHOR_KEYS
        assert rec["candidate_id"] == cid


def test_a_candidate_with_an_unusable_bbox_is_an_absence_not_a_crash():
    page = FakePage([_word(0.0, 0.0, 10.0, 10.0, "X")], [_line("X", (0, 0, 10, 10))])
    out = anchors_for_candidates(page, {"WALL-TC1": ()})
    assert out["WALL-TC1"]["anchor_text"] is None


def test_page_words_survives_an_unreadable_text_layer():
    class Broken:
        number = 0

        def get_text(self, kind):
            raise RuntimeError("corrupt text layer")

    assert page_words(Broken()) == []
    assert anchors_for_candidates(Broken(), {"SYM-1": (0.0, 0.0, 1.0, 1.0)})[
        "SYM-1"
    ]["anchor_text"] is None


# ---------------------------------------------------------------------------
# The module's own boundaries — grep-self, mirroring the phase-23 gate.
# ---------------------------------------------------------------------------


def test_the_module_does_not_reuse_the_drafting_noise_predicate():
    """That predicate returns True for 'B-1' and 'P1' — the tags we need."""
    src = MODULE_PATH.read_text()
    assert "_is_noise_token" not in src
    assert "_is_noise_cluster" not in src
    assert "from bobbytailor.vision" not in src


def test_the_module_runs_free():
    src = MODULE_PATH.read_text()
    for forbidden in (FORBIDDEN_CREDENTIAL, "analyze_drawing", "anthro" + "pic"):
        assert forbidden not in src, forbidden


def test_this_gate_runs_free():
    src = Path(__file__).read_text()
    # Each name appears exactly once — in its own fragment assembly above — so
    # a whole-file grep for the literal returns nothing.
    for forbidden in FORBIDDEN_PAID:
        assert forbidden not in src, forbidden
    # No scored total is asserted against the bollard or column candidates.
    assert re.search(r"==\s*28\b", src) is None
    assert re.search(r"==\s*132\b", src) is None
    assert re.search(r"==\s*136\b", src) is None
    assert re.search(r"==\s*56\b", src) is None
