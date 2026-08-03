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


def _require_pdf(key):
    """Skip unless the fixture PDF exists — for tests that read one page and so
    must not pay for the module-wide audit."""
    if not _pdf_path(key).exists():
        pytest.skip("fixture PDF for %r is not present in uploads/" % key)
    return _pdf_path(key)


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


# Moxy pages 23-38 inclusive are the 16 guestroom prototypes. Every guestroom
# quantity in the building (Gyp Ceiling, Gyp Wall) lives on these sheets, and
# all 16 were discarded before geometry ran. Read off the drawings, not fitted.
MOXY_GUESTROOM_PROTOTYPES = tuple(range(23, 39))


def test_moxy_guestroom_prototypes_reach_the_engine(audits):
    """The 16 sheets holding every guestroom quantity reach the engine.

    Asserted as an OUTCOME, deliberately not as a mechanism. Plan 23-01
    delivered the skip veto and this test originally required >= 16 pages to be
    *recovered by the veto*. Plan 23-06 then repaired the classifier itself, so
    the pages are never misclassified in the first place and the veto correctly
    recovers nothing — which failed a test asserting the backstop had fired.
    A test that only passes while the bug is still present is measuring the
    wrong thing. What matters is that the sheet is measured, by whichever route.

    Validated by POSITION/SHAPE — each page must carry at least one plan title
    with a printed scale beneath it, or a scaled viewport — never by a quantity.
    """
    result = _require(audits, "moxy")
    by_index = {row["page_index"]: row for row in result["pages"]}

    not_reaching = [i for i in MOXY_GUESTROOM_PROTOTYPES if by_index[i]["skipped"]]
    assert not not_reaching, (
        "guestroom prototype pages %s are still discarded before geometry"
        % not_reaching
    )

    unmeasurable = [
        i for i in MOXY_GUESTROOM_PROTOTYPES
        if not (by_index[i]["measurable_signal"]["plan_titles"] > 0
                or by_index[i]["measurable_signal"]["viewports"] > 0)
    ]
    assert not unmeasurable, (
        "guestroom prototype pages %s reach the engine with no scaled plan "
        "geometry — they would be measured at a borrowed scale" % unmeasurable
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


# ---------------------------------------------------------------------------
# Plan 23-06 Task 1 — real-PDF assertions on the structural window search
#
# Pre-change values below were MEASURED on the four real PDFs immediately
# before the change landed, by re-running the probe's own computation. They are
# page counts read off the drawings, never fitted to a quantity, a golden
# take-off or an accuracy score.
# ---------------------------------------------------------------------------

# Sheet identifiers per page, BEFORE the window search existed — the exact
# sequence _sheet_name_from_doc returned on today's HEAD, dumped page by page.
# get_title_block_text feeds sheet NAMING as well as classification (gitnexus
# impact: _sheet_name_from_doc is a direct caller, blast radius HIGH), so a
# narrower window that renamed sheets would silently corrupt every report.
#
# These are RECORDED OUTPUTS, not desired ones. Several are plainly poor —
# Moxy's title blocks yield "Page_3"… and its page 0 yields the accessibility
# standard "A117.1" — but repairing sheet NAMING is not this plan's job, and
# pinning the honest current output is what makes the invariance claim mean
# something. Any improvement to naming must update this list deliberately.
PRE_CHANGE_SHEET_IDS = {
    "moxy": [
        'A117.1', 'S001', 'Page_3', 'Page_4', 'Page_5', 'Page_6',
        'Page_7', 'Page_8', 'Page_9', 'Page_10', 'Page_11', 'Page_12',
        'Page_13', 'Page_14', 'Page_15', 'Page_16', 'Page_17', 'Page_18',
        'Page_19', 'Page_20', 'Page_21', 'Page_22', 'Page_23', 'Page_24',
        'Page_25', 'Page_26', 'Page_27', 'Page_28', 'Page_29', 'Page_30',
        'Page_31', 'Page_32', 'Page_33', 'Page_34', 'Page_35', 'Page_36',
        'Page_37', 'Page_38', 'Page_39', 'Page_40',
    ],
    "crow": ['A-101', 'A-201', 'A-401', 'A-601'],
    "bobs": ['A2.0', 'A8.0', 'A2.0', 'D1.0', 'C402.4', 'A156.10', 'A8.3'],
    "chelsea": [
        'A061', 'A311', 'A112', 'A311', 'A122', 'A311', 'A132', 'A311',
        'A142', 'A211', 'A221', 'A231', 'A232', 'A251', 'A253', 'A255',
        'A902', 'A903', 'A904', 'G000', 'G001', 'A200', 'F108', 'F108',
        'L112', 'L112', 'C103', 'C104', 'Page_29', 'Page_30', 'Page_31',
        'Page_32',
    ],
}


def test_moxy_page_27_extracts_its_title_block_not_the_keynote_column():
    """THE root cause, asserted on the real PDF (INV-00 §1c).

    Page 27 (ID-411, KING SUITE B) is one of the 16 guestroom prototypes that
    carried every guestroom quantity in the building and were discarded before
    geometry ever ran. Both the correct and the incorrect window contain the
    sheet ID and the unit name — the classifier was outvoted by 84 words of
    electrical keynote prose, not blind. So this asserts BOTH: that the field
    labels are present, and that the verdict is a plan type.
    """
    import fitz

    from bobbytailor.pipeline.pdf_analyzer import get_title_block_text
    from bobbytailor.pipeline.sheet_pass_matrix import (
        classify_sheet_type_from_text,
        plan_passes,
    )

    _require_pdf("moxy")
    doc = fitz.open(str(_pdf_path("moxy")))
    try:
        text = get_title_block_text(doc, 27)
    finally:
        doc.close()

    upper = text.upper()
    assert "SHEET TITLE" in upper, text
    assert "SHEET NO" in upper, text
    assert "KING SUITE" in upper, text     # the unit name
    assert "ID-411" in upper, text         # the sheet identifier

    sheet_type = classify_sheet_type_from_text(text)
    assert sheet_type != "title_sheet", (
        "page 27 classified %r — the guestroom prototype is being discarded "
        "again" % sheet_type
    )
    assert plan_passes(sheet_type, title_block_text=text), (
        "page 27 has an empty pass list, i.e. it is skipped entirely"
    )


def test_sheet_identifiers_are_unchanged_on_every_page_of_every_set():
    """The second consumer of the title-block window must not move.

    _sheet_name_from_doc reads the same region, so a narrower window could
    silently rename sheets across every report. Measured: 83 pages, 0 changes.
    """
    import fitz

    from bobbytailor.pipeline.pdf_analyzer import _sheet_name_from_doc

    checked = 0
    for key, expected in PRE_CHANGE_SHEET_IDS.items():
        if not _pdf_path(key).exists():
            continue
        checked += 1
        doc = fitz.open(str(_pdf_path(key)))
        try:
            actual = [_sheet_name_from_doc(doc, i) for i in range(doc.page_count)]
        finally:
            doc.close()
        assert actual == expected, (
            "%s sheet identifiers changed: %s"
            % (key, [(i, a, b) for i, (a, b) in enumerate(zip(expected, actual))
                     if a != b])
        )
    if not checked:
        pytest.skip("no plan-set fixtures in uploads/")


def test_no_page_fraction_was_changed_to_achieve_any_of_this():
    """23-CONTEXT's hard prohibition, pinned on resolved values.

    Sweeping the width fraction is the documented fixture-blindness trap: it
    fixes Moxy and destroys Chelsea (INV-00 §1d). The ladder may use fractions
    as CANDIDATES, but the widest one must still be today's window so a sheet
    whose title block cannot be identified behaves exactly as it did.
    """
    from bobbytailor.pipeline.pdf_analyzer import _TITLE_BLOCK_WINDOWS

    windows = [tuple(map(float, c)) for c in _TITLE_BLOCK_WINDOWS]
    assert windows[-1] == (0.55, 0.80), (
        "the widest candidate must remain the current window, got %r"
        % (windows[-1],)
    )
    assert any(x > 0.55 for x, _y in windows[:-1]), (
        "the search must evaluate at least one strictly tighter candidate"
    )
