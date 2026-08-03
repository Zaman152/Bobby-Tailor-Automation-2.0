"""The mandatory four-plan-set no-regression gate (D-05). ZERO API.

**This is the phase's central safety net.** The documented failure mode of this
codebase is a change validated on ONE plan set: sweeping the title-block width
fraction 0.55 -> 0.88 fixes Moxy (18 -> 2 skips) and BREAKS Chelsea (2 -> 10),
and nothing caught it because nothing looked at Chelsea.

So the gate is a SINGLE assertion over Moxy, Crow, Bob's and Chelsea
simultaneously — four drafting offices, four title-block conventions, 83 pages.
Improving one fixture while regressing another is a failure, not a trade.

The numbers below are counts of PAGES CARRYING SCALED PLAN GEOMETRY, read off
the drawings by ``scripts/coverage_probe.py``. They are not fitted to any
quantity, any golden take-off or any accuracy score. Nothing in this file may
ever be adjusted to make a total match — that is the documented coincidence
trap, and it has already cost this project days.

Runs the probe's computation over the real PDFs in ``uploads/``; skips cleanly
when a fixture is absent. ~1.5 s/page, no API key, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from scripts.coverage_probe import FOUR_SETS, audit_pdf  # noqa: E402

pytestmark = pytest.mark.generalization


# ---------------------------------------------------------------------------
# Baseline, BEFORE the skip veto — the recorded starting point.
# Source: INV-08 §1.1, whose per-page audit was re-run on today's HEAD.
# Chelsea is not tabulated in §1.1; its 0 was measured by the same probe.
# ---------------------------------------------------------------------------
PRE_VETO_SKIPS = {
    "moxy": 18,     # 2 real cover/index sheets + 16 guestroom prototypes
    "crow": 0,
    "bobs": 1,      # page 0, a genuine cover sheet
    "chelsea": 0,
}

# ---------------------------------------------------------------------------
# Post-veto expectations. Rationale for each literal — all four are read from
# the drawings, never fitted to a quantity:
#
#   moxy    <= 2  Only pages 0 and 1 hold no measurable geometry: page 0 is the
#                 cover, page 1 the LIGHTING COVER SHEET whose index lists 11
#                 drawing names and carries ZERO printed scales. The other 16
#                 title_sheet pages each carry 5-6 scaled "<NAME> - <KIND> PLAN"
#                 drawings, so a keyword must not be able to discard them.
#   crow    == 0  Nothing to recover; page 0 already classifies floor_plan. This
#                 pins that the veto is NOT a blanket "measure everything".
#   bobs    == 1  Page 0 is a REAL cover sheet (titles=0, scales=0). A correct
#                 skip must survive the veto, or the veto is just noise.
#   chelsea <= 2  The documented Chelsea baseline is 2 (INV-00 §1d). Today's
#                 title-block routing measures 0. Either passes; an increase
#                 beyond 2 is the 0.88 regression returning.
# ---------------------------------------------------------------------------
MAX_SKIPS = {"moxy": 2, "crow": 0, "bobs": 1, "chelsea": 2}
EXACT_SKIPS = {"crow": 0, "bobs": 1}

# Moxy is the fixture the veto exists for: no page may be discarded while it
# carries measurable geometry.
NO_SILENT_LOSS = ("moxy", "crow", "bobs", "chelsea")


def _pdf_path(key: str) -> Path:
    return ROOT / FOUR_SETS[key]


@pytest.fixture(scope="module")
def audits():
    """Audit every available plan set once. Skips if none are present."""
    available = {k: _pdf_path(k) for k in FOUR_SETS if _pdf_path(k).exists()}
    if not available:
        pytest.skip("no plan-set fixtures in uploads/")
    return {k: audit_pdf(str(v)) for k, v in available.items()}


def _require(audits, key):
    if key not in audits:
        pytest.skip("fixture PDF for %r is not present in uploads/" % key)
    return audits[key]


# ---------------------------------------------------------------------------
# THE GATE — one assertion, all four sets at once
# ---------------------------------------------------------------------------


def test_four_plan_set_skip_counts_do_not_regress(audits):
    """One assertion across all four sets. Improving one by regressing another
    fails here, deliberately."""
    report = {}
    failures = []

    for key in ("moxy", "crow", "bobs", "chelsea"):
        if key not in audits:
            continue
        result = audits[key]
        skipped = len(result["pages_skipped"])
        silent = result["silent_loss_pages"]
        report[key] = {
            "pages": result["page_count"],
            "skipped": skipped,
            "skipped_pages": result["pages_skipped"],
            "recovered": len(result["pages_overruled"]),
            "silent_loss": silent,
        }

        if skipped > MAX_SKIPS[key]:
            failures.append(
                "%s: %d pages skipped, limit %d (was %d before the veto)"
                % (key, skipped, MAX_SKIPS[key], PRE_VETO_SKIPS[key])
            )
        if key in EXACT_SKIPS and skipped != EXACT_SKIPS[key]:
            failures.append(
                "%s: %d pages skipped, must be exactly %d"
                % (key, skipped, EXACT_SKIPS[key])
            )
        if key in NO_SILENT_LOSS and silent:
            failures.append(
                "%s: pages %s were discarded while carrying measurable "
                "geometry — a blank is not a zero" % (key, silent)
            )

    assert not failures, (
        "four-plan-set no-regression gate FAILED:\n  "
        + "\n  ".join(failures)
        + "\n\nfull four-set report: %r" % report
    )


# ---------------------------------------------------------------------------
# Per-fixture detail — so a failure above names its cause immediately
# ---------------------------------------------------------------------------


def test_moxy_guestroom_prototypes_are_recovered(audits):
    """The 16 sheets holding every guestroom quantity reach the engine.

    Validated by POSITION/SHAPE — each recovered page must carry at least one
    plan title with a printed scale beneath it — never by a quantity.
    """
    result = _require(audits, "moxy")
    recovered = result["pages_overruled"]
    assert len(recovered) >= 16, (
        "expected >= 16 recovered guestroom prototype pages, got %s" % recovered
    )
    for row in result["pages"]:
        if row["classifier_overruled"]:
            assert row["measurable_signal"]["plan_titles"] > 0 or \
                row["measurable_signal"]["viewports"] > 0, (
                    "page %d was overruled without measurable geometry"
                    % row["page_index"]
                )


def test_moxy_keeps_its_real_cover_and_index_skipped(audits):
    """18 -> 2: pages 0 and 1 stay skipped. The veto is evidence, not a blanket."""
    result = _require(audits, "moxy")
    assert result["pages_skipped"] == [0, 1]
    for row in result["pages"]:
        if row["page_index"] in (0, 1):
            assert sum(row["measurable_signal"].values()) == 0, (
                "page %d has no printed scale, so nothing on it is measurable"
                % row["page_index"]
            )


def test_crow_is_completely_unchanged(audits):
    """Proves the veto is not a blanket 'measure everything'."""
    result = _require(audits, "crow")
    assert result["pages_skipped"] == []
    assert result["pages_overruled"] == []
    assert result["pages_reaching_report"] == result["page_count"]


def test_bobs_real_cover_sheet_stays_skipped(audits):
    """A correct skip must survive the veto, and be labelled not_applicable."""
    result = _require(audits, "bobs")
    assert result["pages_skipped"] == [0]
    page0 = result["pages"][0]
    assert page0["titles"] == 0
    assert page0["scales"] == 0
    assert page0["disposition"] == "not_applicable"
    assert page0["classifier_overruled"] is False


def test_chelsea_does_not_regress(audits):
    """The fixture the 0.55 -> 0.88 sweep destroyed. It must stay intact."""
    result = _require(audits, "chelsea")
    assert len(result["pages_skipped"]) <= MAX_SKIPS["chelsea"]
    assert result["silent_loss_pages"] == []


# ---------------------------------------------------------------------------
# The ledger invariant, on real PDFs
# ---------------------------------------------------------------------------


def test_every_source_page_has_exactly_one_ledger_row(audits):
    """len(ledger) == pages_in_source == fitz page_count, for every PDF."""
    import fitz

    for key, result in audits.items():
        page_count = fitz.open(str(_pdf_path(key))).page_count
        assert result["page_count"] == page_count, key
        assert len(result["pages"]) == page_count, key
        assert result["summary"]["pages_in_source"] == page_count, key
        assert result["unaccounted_pages"] == [], key
        assert {r["page_index"] for r in result["pages"]} == set(range(page_count))
        assert all(r["disposition"] for r in result["pages"]), key


def test_every_page_is_accounted_for_in_exactly_one_disposition(audits):
    """measured / vision-only / skipped / not-applicable / errored sum to the
    page count — no page falls between two categories."""
    for key, result in audits.items():
        s = result["summary"]
        total = (
            s["sheets_measured"] + s["sheets_vision_only"] + s["sheets_skipped"]
            + s["sheets_not_applicable"] + s["sheets_errored"]
        )
        assert total == result["page_count"], (key, s)


def test_the_probe_spends_nothing(audits):
    """No paid entry point may appear in the probe or in this gate."""
    forbidden = (
        "ANTHROPIC_API_KEY", "pytest -m golden", "accuracy_gate.sh",
        "vision_only_benchmark", "golden_convergence",
    )
    for path in (ROOT / "scripts" / "coverage_probe.py", Path(__file__)):
        source = path.read_text()
        for token in forbidden:
            if path == Path(__file__) and token in ("ANTHROPIC_API_KEY",):
                continue  # named in this very list
            assert token not in source.replace(
                '"%s"' % token, ""
            ).replace("'%s'" % token, ""), "%s references %r" % (path.name, token)
