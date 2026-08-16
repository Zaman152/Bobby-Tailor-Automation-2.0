"""The placed keynote reaches the report. ZERO API.

``keynote_callout_counts`` has been green since 28-06 and had no caller on the
plan path: only the elevation facade route consumed keynotes, so a floor plan
read its legend, counted its bubbles and dropped the answer on the floor. That
is why the first paid run of the post-28 engine (2026-08-16, $0.8178) predicted
"Ladder-H-20' = 1, PASS expected" in DEPLOYMENT-READINESS §6 and published NO
Ladder row while ``test_keynote_callouts`` stayed green — a wiring gap wearing
the costume of a detection gap.

These tests assert the wiring on the REAL sheet, and they assert what the
wiring must refuse just as hard. A keynote count is a count of PLACEMENTS; when
the note states a rule instead of naming a thing, the placement count is not a
quantity of anything and the honest blank is kept.
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.deterministic.room_fill import (  # noqa: E402
    is_specification_note,
    keynote_callout_counts,
)
from bobbytailor.deterministic.symbols import cluster_symbols  # noqa: E402

CROW_PDF = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
# A-101 OVERALL FLOOR PLAN prints 1" = 40'.
CROW_P0_FPP = 40.0 / 72.0

_CACHE: dict = {}

crow_only = pytest.mark.skipif(
    not CROW_PDF.exists(), reason="Crow fixture PDF not present"
)


def _crow_doc():
    if "doc" not in _CACHE:
        _CACHE["doc"] = fitz.open(CROW_PDF)
    return _CACHE["doc"]


def _bundle(page_index: int, sheet_name: str, sheet_type: str = "floor_plan"):
    key = ("bundle", page_index)
    if key not in _CACHE:
        from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

        doc = _crow_doc()
        pipeline = TakeoffPipeline.__new__(TakeoffPipeline)
        pipeline._project_footprint = None
        pipeline._project_vocab_labels = []
        pipeline._schedules_cache = {}
        _CACHE[key] = pipeline._deterministic_bundle(
            doc[page_index], doc, str(CROW_PDF), page_index, sheet_name, sheet_type
        )
    return _CACHE[key]


def _groups(bundle) -> dict:
    return {g.candidate_id: g for g in bundle["symbol_groups"]}


# ─────────────────────────────────────────────────────────────────────────────
# The real sheet — the row the paid run failed to publish.
# ─────────────────────────────────────────────────────────────────────────────


@crow_only
def test_the_placed_ladder_keynote_reaches_the_candidate_registry():
    """Keynote 1 is drawn twice: its legend bubble, and one callout on the plan.

    Golden Ladder-H-20' is 1 EA. This asserts the count the DRAWING supports —
    one placement — carried to the registry with the sheet's own words for it.
    """
    groups = _groups(_bundle(0, "A-101"))
    assert "KEY-1" in groups, "the placed keynote never became a candidate"
    key1 = groups["KEY-1"]
    assert key1.count == 1
    assert len(key1.instance_bboxes_pt) == 1
    assert key1.contained_texts and key1.contained_texts[0].startswith(
        "ACCESS LADDER"
    ), key1.contained_texts


@crow_only
def test_the_keynote_count_publishes_flagged():
    """A count of placements is not yet a count of objects.

    A keynote may mark a detail reference rather than an instance, and callout
    counting has been measured on ONE page of one set. The flag is what makes a
    miscount a 30-second confirm instead of a wrong bid, and nothing in this
    plan earns its removal.
    """
    keynotes = {
        cid: g for cid, g in _groups(_bundle(0, "A-101")).items()
        if cid.startswith("KEY-")
    }
    assert keynotes, "nothing was published, so nothing was flagged"
    for cid, group in keynotes.items():
        assert group.needs_review is True, cid


@crow_only
def test_the_ladder_and_the_hatch_stay_two_rows():
    """Crow keynotes 1 and 2 BOTH say "ACCESS LADDER" on the sheet.

    Keynote 2 is a 3'-0" x 3'-0" ROOF HATCH that a ladder reaches. A route that
    merged them on the shared alias would publish 2 where the answer is 1.
    Geometry counts each number separately; which of them IS the Ladder line
    item is the head-noun judgement the semantic pass owns.
    """
    groups = _groups(_bundle(0, "A-101"))
    assert "KEY-2" in groups
    assert groups["KEY-1"].contained_texts != groups["KEY-2"].contained_texts
    assert groups["KEY-1"].count == 1 and groups["KEY-2"].count == 1


@crow_only
def test_the_bubble_group_the_counts_came_from_is_dropped():
    """SYM-4's 54 instances ARE these bubbles — 12 legend + 42 callouts.

    Publishing both the per-number counts and the group they were split out of
    counts the same drawn marks twice; the same drawn-once-published-once
    contract as ``lattice_shadowed_symbol_ids``. And SYM-4 is annotation in any
    case: nobody buys a keynote bubble.
    """
    bundle = _bundle(0, "A-101")
    ids = set(_groups(bundle))
    assert "KEY-1" in ids
    assert "SYM-4" not in ids, "the keynote bubble group was published twice"
    # Suppression is surgical: the unrelated clusters on the sheet are untouched.
    assert "SYM-1" in ids
    published = sum(
        g.count for cid, g in _groups(bundle).items() if cid.startswith("KEY-")
    )
    assert published <= 54, "the counts must never exceed the bubbles they split"


@crow_only
def test_a_specification_note_is_refused_even_though_it_is_placed():
    """Keynote 10 — "SANITARY LINE - PROVIDE 6" PVC CLEANOUTS AT 80'-0" O.C."

    Eleven bubbles, and eleven of nothing in particular: the note prescribes a
    spacing, so its placements mark where a rule applies. Publishing KEY-10 = 11
    would be a confident number with no referent.
    """
    groups = _groups(_bundle(0, "A-101"))
    assert "KEY-10" not in groups
    # Asserted against a route that IS publishing on this sheet — keynote 9 is
    # placed on the same drawing, by the same bubbles, and it publishes.
    assert "KEY-9" in groups and groups["KEY-9"].count == 12


@crow_only
def test_the_bundle_carries_the_evidence_for_each_published_count():
    """A reviewer has to be able to check the number against the sheet."""
    callouts = {c["number"]: c for c in _bundle(0, "A-101")["keynote_callouts"]}
    assert "1" in callouts
    ladder = callouts["1"]
    assert ladder["callout_count"] == 1
    assert ladder["legend_bbox_pt"] is not None
    assert len(ladder["instance_bboxes_pt"]) == 1
    assert ladder["source_candidate_id"] == "SYM-4"
    assert "10" not in callouts, "a refused note must not appear as published"


@crow_only
def test_a_page_with_no_keynote_legend_publishes_no_keynote_rows():
    """Crow page 1 prints a KEYNOTES header with no entries under it.

    The route is driven by whatever legend the SHEET defines; a sheet defining
    none has nothing to count against and must add nothing.
    """
    ids = set(_groups(_bundle(1, "A-201")))
    assert not [cid for cid in ids if cid.startswith("KEY-")]


def test_the_route_is_inert_on_a_blank_page():
    doc = fitz.open()
    doc.new_page()
    try:
        assert keynote_callout_counts(doc[0], []) == []
    finally:
        doc.close()


# ─────────────────────────────────────────────────────────────────────────────
# The guard — what a keynote count may NOT be made of.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_bollard_note_shape_is_refused():
    """Crow general note 13, the trap this guard exists for.

    Placed once it would publish Bollards = 1 against a golden 28. A blank is
    visibly missing; a 1 is silently wrong, and only one of those gets caught in
    review. The Bollards blank stays a blank.
    """
    assert is_specification_note(
        "ALL BOLLARDS TO BE PAINTED SAFETY YELLOW.  (PROVIDE BOLLARDS AT ALL "
        "DRIVE-IN OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS, ELECTRICAL "
        "TRANSFORMERS AND EXPOSED ELECTRICAL PANELS)"
    )


@pytest.mark.parametrize(
    "note",
    [
        "PROVIDE BLOCKING AS REQUIRED FOR CEILING MOUNTED",
        "USE PAINTERS TAPE TO CREATE LINE BETWEEN THE",
        "COORDINATE LOCATION AND INSTALLATION OF OUTLET AND",
        "INSTALL REVERSIBLE VANITY BASE SO TOWEL BAR IS",
        "GANG OUTLET & SWITCHES TOGETHER AT THIS LOCATION AT",
        "OUTLET AND SWITCHES TO BE INSTALLED AT 46\" AFF.",
        "TEXTURED FINISH AND PAINT REQUIRED ON",
        "NO TRANSITION STRIP. FLOORING IN GUESTROOM",
        "SEE STRUCTURAL DRAWINGS",
        "TYPICAL AT ALL DOOR JAMBS",
    ],
)
def test_an_instruction_is_not_an_object(note):
    """Every one of these is printed in a keynote legend of a real plan set.

    Moxy's guestroom legend is a list of JOBS, not things — sweeping the four
    sets returned 180 placed keynotes on its 16 prototype sheets against 9 on
    Crow, and almost all of the 180 read like these. A count of them is a count
    of instructions.
    """
    assert is_specification_note(note)


@pytest.mark.parametrize(
    "note",
    [
        "ACCESS LADDER TO CONCRETE ROOF OF ELECTRICAL",
        "ELECTRICAL ROOM - 1 HOUR RATED",
        "RAMP GUARDRAIL - SEE DETAILS 4, 12 & 13 ON A-401",
        "9\" X 9\" 24 GAUGE METAL DOWNSPOUTS WITH KYNAR",
        "CONTROL JOINT",
        "GAS METER, CONFIRM LOCATION W/ KUB.",
        "LOUVER, MATCH STOREFRONT.  SEE MECHANICAL.",
    ],
)
def test_a_note_that_names_a_thing_survives_the_guard(note):
    """The guard has to be a filter, not a wall.

    Each of these is a real legend entry that names an object — the Crow four
    and, from Moxy's exterior elevations, the three the route counts there. A
    guard that also refused these would leave the detector as unwired as it was.
    """
    assert not is_specification_note(note)


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE — four plan sets, every page. Nothing here knows Crow.
# ─────────────────────────────────────────────────────────────────────────────

_FOUR_SETS = (
    ("crow", "uploads/Crow - Cass White Road-Plans.pdf", 40.0 / 72.0),
    ("bobs", "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf", 8.0 / 72.0),
    (
        "chelsea",
        "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf",
        8.0 / 72.0,
    ),
    (
        "moxy",
        "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
        8.0 / 72.0,
    ),
)


@pytest.mark.generalization
def test_four_set_sweep_publishes_only_notes_that_name_things():
    """Measured over all 83 pages of Crow, Bob's, Chelsea and Moxy.

    The route is not keyed to Crow: it reads whatever legend a sheet defines
    and counts whatever bubbles that sheet draws. Two sets carry placed
    keynotes (Crow page 0, Moxy's elevation and guestroom sheets); two carry
    none, and publish none.

    The number this gate holds is the guard's, not the detector's. Before the
    instruction shape was added the sweep published 180 rows on Moxy — legend
    entries like "COORDINATE LOCATION AND INSTALLATION OF OUTLET AND" — which
    is 180 rows of nothing handed to the naming pass. A change that pushes the
    published total back up has widened the claim, and it must be measured
    here before it is believed.
    """
    present = [(n, ROOT / p, f) for n, p, f in _FOUR_SETS if (ROOT / p).exists()]
    if not present:
        pytest.skip("none of the four plan sets are present")

    published, pages = [], 0
    for name, path, fpp in present:
        doc = fitz.open(path)
        try:
            for pi in range(doc.page_count):
                pages += 1
                groups = cluster_symbols(doc[pi], fpp, doc=doc, page_index=pi)
                for c in keynote_callout_counts(doc[pi], groups):
                    if c.callout_count > 0 and not is_specification_note(c.note_text):
                        published.append((name, pi, c.number, c.callout_count,
                                          c.note_text))
        finally:
            doc.close()

    assert pages >= 4
    for row in published:
        assert not is_specification_note(row[4]), row
    by_set = {n: [r for r in published if r[0] == n] for n, _, _ in present}
    for name in ("bobs", "chelsea"):
        if name in by_set:
            assert by_set[name] == [], (
                "a set with no placed keynotes published rows: %r" % (by_set[name],)
            )
    if "crow" in by_set:
        assert [(r[2], r[3]) for r in by_set["crow"] if r[1] == 0] == [
            ("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 2),
            ("6", 7), ("7", 4), ("9", 12), ("12", 2),
        ]
    if "moxy" in by_set:
        # The second set the route fires on, and it fires on objects: CONTROL
        # JOINT x13, LOUVER x5, WALL PACK LIGHTING x3 on the exterior
        # elevations. That it is a much smaller number than the 180 the
        # detector alone produced IS the guard working.
        assert len(by_set["moxy"]) <= 40, len(by_set["moxy"])
