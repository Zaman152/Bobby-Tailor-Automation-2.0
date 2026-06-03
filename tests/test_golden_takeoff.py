"""
Golden regression tests: Crow Cass + Bob's Discount PDF pipelines.

Two test layers:
  1. test_golden_validator_logic — always runs (no PDF, no API); validates
     GoldenValidator math, fuzzy matching, and tolerance modes.
  2. test_crow_cass_golden / test_bobs_discount_golden — integration tests
     that call run_pdf_analysis; skipped when PDF fixtures are absent.

Run all: pytest tests/test_golden_takeoff.py -v
Skip PDF tests: pytest tests/test_golden_takeoff.py -v -k "validator_logic"
Run only golden marks: pytest tests/test_golden_takeoff.py -v -m golden
"""
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
CROW_GOLDEN = FIXTURES / "crow_cass" / "crow_cass_golden.csv"
BOBS_GOLDEN = FIXTURES / "bobs_discount" / "bobs_discount_golden.csv"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"

# Import here so tests fail loudly (not skip) if the module is broken
from tests.golden_validator import GoldenValidator


# ─── Unit test: validator logic (always runs) ─────────────────────────────────

def test_golden_validator_logic():
    """Validate GoldenValidator math, fuzzy matching, and tolerance modes.

    Uses a 3-item synthetic CSV to avoid coupling to the full golden files.
    """
    import csv, tempfile, os

    # ── Build a tiny synthetic golden CSV ──
    rows = [
        {"item_name": "Bollards", "quantity": "28", "unit": "EA",
         "tolerance_pct": "0", "match_mode": "exact_or_within_1"},
        {"item_name": "Sealed Concrete", "quantity": "395673.42", "unit": "SF",
         "tolerance_pct": "3", "match_mode": "pct"},
        {"item_name": "Mobilization", "quantity": "1", "unit": "EA",
         "tolerance_pct": "0", "match_mode": "exact_or_within_1"},
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        csv_path = f.name

    try:
        validator = GoldenValidator(csv_path)

        # ── 1. Perfect match → pass=True, score=1.0 ──────────────────────────
        perfect = [
            {"item": "Bollards", "quantity": 28, "unit": "EA"},
            {"item": "Sealed Concrete", "quantity": 395673.42, "unit": "SF"},
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        report = validator.validate(perfect, fixture_name="synthetic-perfect")
        assert report["pass"] is True, report
        assert report["score"] == 1.0, report
        assert report["missing"] == [], report

        # ── 2. EA exact match: bollard count off by 1 → passes ────────────────
        off_by_one = [
            {"item": "Bollards", "quantity": 27, "unit": "EA"},      # 28-1 = ok
            {"item": "Sealed Concrete", "quantity": 395673.42, "unit": "SF"},
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        r2 = validator.validate(off_by_one)
        bollard_result = next(x for x in r2["items"] if x["item"] == "Bollards")
        assert bollard_result["status"] == "PASS", bollard_result

        # ── 3. EA count off by 5 → fails ─────────────────────────────────────
        bad_count = [
            {"item": "Bollards", "quantity": 10, "unit": "EA"},      # -18 — fail
            {"item": "Sealed Concrete", "quantity": 395673.42, "unit": "SF"},
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        r3 = validator.validate(bad_count)
        assert r3["pass"] is False
        assert next(x for x in r3["items"] if x["item"] == "Bollards")["status"] == "FAIL"

        # ── 4. PCT tolerance: 2% error on SF → passes (within 3%) ────────────
        within_tol = [
            {"item": "Bollards", "quantity": 28, "unit": "EA"},
            {"item": "Sealed Concrete", "quantity": 395673.42 * 1.02, "unit": "SF"},
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        r4 = validator.validate(within_tol)
        sf_result = next(x for x in r4["items"] if x["item"] == "Sealed Concrete")
        assert sf_result["status"] == "PASS", sf_result

        # ── 5. PCT tolerance: 5% error on SF → fails (exceeds 3%) ───────────
        outside_tol = [
            {"item": "Bollards", "quantity": 28, "unit": "EA"},
            {"item": "Sealed Concrete", "quantity": 395673.42 * 1.05, "unit": "SF"},
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        r5 = validator.validate(outside_tol)
        sf_fail = next(x for x in r5["items"] if x["item"] == "Sealed Concrete")
        assert sf_fail["status"] == "FAIL", sf_fail

        # ── 6. Fuzzy name match: "bollard" → "Bollards" ──────────────────────
        fuzzy = [
            {"item": "bollard", "quantity": 28, "unit": "EA"},       # lowercase
            {"item": "Sealed Concrete", "quantity": 395673.42, "unit": "SF"},
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        r6 = validator.validate(fuzzy)
        assert r6["score"] == 1.0, f"Fuzzy match failed: {r6['items']}"

        # ── 7. Missing item → score < 1.0 ────────────────────────────────────
        missing_one = [
            {"item": "Bollards", "quantity": 28, "unit": "EA"},
            # Sealed Concrete absent
            {"item": "Mobilization", "quantity": 1, "unit": "EA"},
        ]
        r7 = validator.validate(missing_one)
        assert r7["score"] < 1.0
        assert len(r7["missing"]) == 1
        assert r7["missing"][0]["item"] == "Sealed Concrete"

        # ── 8. Empty AI summary → score=0.0, all items missing ───────────────
        r8 = validator.validate([])
        assert r8["pass"] is False
        assert r8["score"] == 0.0
        assert len(r8["missing"]) == 3

        # ── 9. Extra items don't count against score ──────────────────────────
        with_extra = perfect + [
            {"item": "Unknown Widget", "quantity": 42, "unit": "EA"},
        ]
        r9 = validator.validate(with_extra)
        assert r9["score"] == 1.0, "Extra AI items should not reduce score"

    finally:
        os.unlink(csv_path)


# ─── Integration tests (skipped when PDFs absent) ─────────────────────────────

@pytest.mark.golden
@pytest.mark.skipif(
    not CROW_PDF.exists(),
    reason="Crow Cass PDF fixture not present (tests/fixtures/crow_cass/crow_cass_plans.pdf)"
)
def test_crow_cass_golden():
    """End-to-end regression: Crow Cass PDF → GoldenValidator ≥97% accuracy."""
    from pdf_analyzer import run_pdf_analysis

    result = run_pdf_analysis(
        str(CROW_PDF),
        project_name="Crow Cass Test",
    )
    summary = result["takeoff_summary"]

    validator = GoldenValidator(str(CROW_GOLDEN))
    report = validator.validate(summary, fixture_name="Crow Cass")

    if not report["pass"]:
        print("\n" + validator.format_report(report))

    assert report["score"] >= 0.97, (
        f"Crow Cass accuracy {report['score']:.1%} < 97%.\n"
        f"{validator.format_report(report)}"
    )


@pytest.mark.golden
@pytest.mark.skipif(
    not BOBS_PDF.exists(),
    reason="Bob's Discount PDF fixture not present (tests/fixtures/bobs_discount/bobs_discount_plans.pdf)"
)
def test_bobs_discount_golden():
    """End-to-end regression: Bob's Discount PDF → GoldenValidator ≥97% accuracy."""
    from pdf_analyzer import run_pdf_analysis

    result = run_pdf_analysis(
        str(BOBS_PDF),
        project_name="Bobs Discount Test",
    )
    summary = result["takeoff_summary"]

    validator = GoldenValidator(str(BOBS_GOLDEN))
    report = validator.validate(summary, fixture_name="Bob's Discount")

    if not report["pass"]:
        print("\n" + validator.format_report(report))

    assert report["score"] >= 0.97, (
        f"Bob's Discount accuracy {report['score']:.1%} < 97%.\n"
        f"{validator.format_report(report)}"
    )
