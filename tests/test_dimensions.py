"""Layer-1 tests for the Recipe A dimension-line association engine."""
from __future__ import annotations

import os
import statistics
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.dimensions import (
    extract_dimension_samples,
    parse_feet_inches,
)

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC_DIR = FIXTURES / "synthetic"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"


# ── parse_feet_inches ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1136' - 0\"", 1136.0),
        ("350'-0", 350.0),
        ("25'-4 1/2\"", 25.375),
        ("60'", 60.0),
        ("12'-6 1/2\"", 12.541666666666666),
        ("3'-0\"", 3.0),
    ],
)
def test_parse_feet_inches_accepts_recipe_formats(text, expected):
    got = parse_feet_inches(text)
    assert got == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "3%",
        "GL 850'",
        "EL 12'-0\"",
        "slope 2/FT",
        "",
    ],
)
def test_parse_feet_inches_rejects_non_dimensions(text):
    assert parse_feet_inches(text) is None


# ── synthetic fixtures ────────────────────────────────────────────────────────


def _ensure_synthetic_fixtures() -> Path:
    pdf_path = SYNTHETIC_DIR / "dimensions_synthetic.pdf"
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


def test_gen_synthetic_cli_writes_pdf_and_truth(tmp_path):
    # The CLI writes into tmp_path, NOT into SYNTHETIC_DIR. This test's job is
    # to prove the generator writes; the checked-in fixtures are not what it
    # needs to write over. PyMuPDF stamps a fresh random /ID into every saved
    # document, so pointing --out at the tracked directory left all three
    # fixture PDFs modified-but-identical in `git status` after any suite run.
    # `_ensure_synthetic_fixtures` above still regenerates in place, but only
    # when the file is genuinely absent.
    subprocess.run(
        [
            sys.executable,
            str(SYNTHETIC_DIR / "gen_synthetic.py"),
            "--out",
            str(tmp_path),
        ],
        check=True,
    )
    assert (tmp_path / "dimensions_synthetic.pdf").exists()
    assert (tmp_path / "truth.json").exists()


def test_synthetic_association_matches_truth():
    import json

    pdf_path = _ensure_synthetic_fixtures()
    truth = json.loads((SYNTHETIC_DIR / "truth.json").read_text())
    expected = truth["pages"][0]["dims"]

    doc = fitz.open(pdf_path)
    samples = extract_dimension_samples(doc[0], page_index=0, doc=doc)
    doc.close()

    for row in expected:
        matches = [s for s in samples if s.feet == pytest.approx(row["feet"])]
        if row["expected_associated"]:
            assert matches, f"Expected associated sample for {row['text']!r}"
            assert matches[0].points > 0
        else:
            assert not matches, f"Decoy {row['text']!r} should not associate"


# ── Crow Cass hard gate ─────────────────────────────────────────────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page0_dimension_samples():
    doc = fitz.open(CROW_PDF)
    samples = extract_dimension_samples(doc[0], page_index=0, doc=doc)
    doc.close()

    assert len(samples) >= 8

    feet_values = {round(s.feet, 3) for s in samples}
    assert 1136.0 in feet_values
    assert 350.0 in feet_values

    ratios = [s.feet / s.points for s in samples if s.points > 0]
    assert ratios
    median = statistics.median(ratios)
    inliers = [r for r in ratios if abs(r - median) / median <= 0.02]
    assert len(inliers) / len(ratios) >= 0.60

    # Record consensus scale for debugging (Crow page 0 prints 40 ft/in).
    consensus_fpi = median * 72
    print(f"consensus_fpi={consensus_fpi:.2f}")


# ── Bob's Discount smoke ────────────────────────────────────────────────────────


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's Discount PDF fixture missing")
def test_bobs_page0_extraction_returns_without_error():
    doc = fitz.open(BOBS_PDF)
    samples = extract_dimension_samples(doc[0], page_index=0, doc=doc)
    doc.close()
    assert isinstance(samples, list)


# ── degenerate guard ───────────────────────────────────────────────────────────


def test_blank_pdf_returns_empty_samples(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    doc = fitz.open(pdf_path)
    samples = extract_dimension_samples(doc[0], page_index=0, doc=doc)
    doc.close()
    assert samples == []
