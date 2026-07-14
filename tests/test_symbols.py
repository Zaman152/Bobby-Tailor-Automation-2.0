"""Layer-1 tests for the Recipe D symbol instance clustering engine."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.symbols import (
    _collapse_hatch_fields,
    cluster_symbols,
)

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC_DIR = FIXTURES / "synthetic"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"

# Crow page 0 (A-101 OVERALL FLOOR PLAN) printed scale is 1"=40'
# (STATE 21-03 decision: page-0 consensus fpi ~= 40 matches dominant_scale).
CROW_P0_FPP = 40.0 / 72.0


def _ensure_synthetic_fixtures() -> Path:
    pdf_path = SYNTHETIC_DIR / "symbols_synthetic.pdf"
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


# ── synthetic fixtures ────────────────────────────────────────────────────────


def test_gen_synthetic_cli_writes_symbols_pdf_and_truth():
    out = SYNTHETIC_DIR
    subprocess.run(
        [sys.executable, str(out / "gen_synthetic.py"), "--out", str(out)],
        check=True,
    )
    assert (out / "symbols_synthetic.pdf").exists()
    truth = json.loads((out / "truth.json").read_text())
    assert "symbols" in truth
    assert sorted(g["count"] for g in truth["symbols"]["expected_groups"]) == [5, 12]


def test_synthetic_exactly_two_groups_rotation_mirror_invariant():
    """12 flags (7 plain + 3 rotated + 2 mirrored) and 5 circles → exactly
    two groups with counts 12 and 5 — the dihedral min-hash makes rotated and
    mirrored instances land in the SAME group; the unique triangle is
    excluded by the count >= 3 filter; the hatch field creates no group."""
    pdf_path = _ensure_synthetic_fixtures()
    truth = json.loads((SYNTHETIC_DIR / "truth.json").read_text())["symbols"]

    doc = fitz.open(pdf_path)
    groups = cluster_symbols(doc[0], truth["fpp"], page_index=0, doc=doc)
    doc.close()

    assert sorted(g.count for g in groups) == sorted(
        g["count"] for g in truth["expected_groups"]
    )
    for g in groups:
        assert len(g.instance_bboxes_pt) == g.count
        assert g.candidate_id.startswith("SYM-")
        assert not g.needs_review


def test_synthetic_hatch_field_is_collapsed():
    """The 20-stroke 45-degree hatch field (Pitfall 2) is detected as a dense
    same-angle same-spacing run: its members are dropped before clustering
    and one hatch-region record is emitted."""
    pdf_path = _ensure_synthetic_fixtures()
    truth = json.loads((SYNTHETIC_DIR / "truth.json").read_text())["symbols"]

    doc = fitz.open(pdf_path)
    segments = []
    for path in doc[0].get_drawings():
        for it in path["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                segments.append((a.x, a.y, b.x, b.y))
    doc.close()

    kept, regions = _collapse_hatch_fields(segments)
    assert len(regions) == 1
    assert regions[0]["count"] == truth["hatch_strokes"]
    assert len(kept) == len(segments) - truth["hatch_strokes"]
    # Region metadata is the hatch-class signal for vision labeling.
    assert regions[0]["angle_deg"] == pytest.approx(45.0, abs=1.0)
    assert regions[0]["spacing_pt"] == pytest.approx(4.0 / 2 ** 0.5, abs=0.1)


def test_blank_page_returns_empty():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    assert cluster_symbols(page, 0.1, doc=doc) == []
    doc.close()


# ── Crow Cass hard gate (pinned truths) ───────────────────────────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page0_column_grid_group():
    """PINNED TRUTH (21-CONTEXT known failures): the Crow golden take-off has
    132 columns; vision counted 90. Clustering on page 0 (A-101 overall floor
    plan) must enumerate the column-grid block: a group of >= 132 identical
    column-scale instances (discovery probe: 136 light-gray filled rects,
    ~1.0 x 0.4 ft at 1"=40')."""
    doc = fitz.open(CROW_PDF)
    groups = cluster_symbols(doc[0], CROW_P0_FPP, page_index=0, doc=doc)
    doc.close()

    column_groups = [
        g for g in groups if g.count >= 132 and max(g.bbox_size_ft) <= 2.0
    ]
    assert column_groups, (
        "Expected a column-grid group with >= 132 instances on Crow page 0; "
        f"got counts {sorted((g.count, g.bbox_size_ft) for g in groups if g.count >= 25)}"
    )
    g = column_groups[0]
    assert len(g.instance_bboxes_pt) == g.count


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page0_bollard_scale_group():
    """PINNED TRUTH (21-CONTEXT known failures): the Crow golden take-off has
    28 bollards; vision counted 0-17. Clustering on page 0 must find a group
    of >= 28 bollard-scale (sub-1.5 ft) identical instances (discovery probe:
    56 instances at ~0.8 x 0.87 ft at 1"=40')."""
    doc = fitz.open(CROW_PDF)
    groups = cluster_symbols(doc[0], CROW_P0_FPP, page_index=0, doc=doc)
    doc.close()

    bollard_scale = [
        g for g in groups if g.count >= 28 and max(g.bbox_size_ft) <= 1.5
    ]
    assert bollard_scale, (
        "Expected a bollard-scale group with >= 28 instances on Crow page 0; "
        f"got counts {sorted((g.count, g.bbox_size_ft) for g in groups if g.count >= 10)}"
    )
    g = bollard_scale[0]
    assert len(g.instance_bboxes_pt) == g.count


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page0_candidate_registry_shape():
    """Every group is a vision-ready candidate: stable SYM-{n} id ordered by
    count desc, instance bbox list matching count, and a dict form carrying
    the registry fields the fusion layer consumes."""
    doc = fitz.open(CROW_PDF)
    groups = cluster_symbols(doc[0], CROW_P0_FPP, page_index=0, doc=doc)
    doc.close()

    assert len(groups) >= 2
    counts = [g.count for g in groups]
    assert counts == sorted(counts, reverse=True)
    for n, g in enumerate(groups, start=1):
        assert g.candidate_id == f"SYM-{n}"
        assert g.count >= 3
        assert len(g.instance_bboxes_pt) == g.count
        d = g.to_dict()
        assert d["candidate_id"] == g.candidate_id
        assert d["instance_bboxes_pt"] == list(g.instance_bboxes_pt)
        assert d["confidence"] in ("high", "medium")
