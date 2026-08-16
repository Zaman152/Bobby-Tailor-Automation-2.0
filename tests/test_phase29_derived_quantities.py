"""Phase 29-06 — a quantity the drawing STATES, and the three refusals first.

The motivating case and the refusal case are the same note. Crow general note 13,
read free off the fixture PDF's text layer (page 0, `A-101`), is verbatim:

    ALL BOLLARDS TO BE PAINTED SAFETY YELLOW.  (PROVIDE BOLLARDS AT ALL DRIVE-IN
    OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS, ELECTRICAL TRANSFORMERS AND
    EXPOSED ELECTRICAL PANELS).

It names FOUR referents, and a jamb is not a door. Anything this engine
publishes as a Bollards count from it would be a confidently wrong number
wearing a citation — so the deliverable is the blank, and these tests assert the
blank names all four things an estimator has to go count.

The three refusals are asserted before the happy path here for the same reason
they are implemented first: a second pass that reasons over the assembled ledger
is a machine for producing plausible numbers, and every guard on it is load
bearing.

Free. No API, no paid marker. The four-set sweep reads the plan PDFs' text layer
and skips by name when they are not present.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bobbytailor.pipeline import aggregator
from bobbytailor.pipeline.aggregator import (
    DERIVED_FROM_NOTE_RULE,
    DERIVED_RULE_UNRESOLVED_UNMEASURED,
    _norm_item_key,
    aggregate_takeoff,
)
from bobbytailor.pipeline.derived_quantities import (
    CountedItem,
    REFUSED_COMPOUND,
    REFUSED_REFERENT_AMBIGUOUS,
    REFUSED_REFERENT_NOT_COUNTED,
    read_quantity_rules,
    resolve_quantity_rule,
)

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "uploads"
CROW_FIXTURE = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"

#: Crow general note 13, VERBATIM off the fixture's text layer — including the
#: double space after the first sentence and the line break the extraction puts
#: between "EXPOSED" and "ELECTRICAL PANELS". Pinned as a string rather than read
#: at import so the assertions below name what produced them, exactly as
#: `test_phase29_manifest_binding` pins the strings of the paid run it fixes.
CROW_NOTE_13 = (
    "ALL BOLLARDS TO BE PAINTED SAFETY YELLOW.  (PROVIDE BOLLARDS AT ALL "
    "DRIVE-IN OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS, ELECTRICAL "
    "TRANSFORMERS AND EXPOSED\nELECTRICAL PANELS)."
)

#: The four referents note 13 names. A jamb count is not a door count, and no
#: two of these four are the same thing.
NOTE_13_REFERENTS = (
    "DRIVE-IN OVERHEAD DOOR JAMBS",
    "FIRE PROTECTION RISERS",
    "ELECTRICAL TRANSFORMERS",
    "EXPOSED ELECTRICAL PANELS",
)

#: Real note text off the four plan sets that the WIDER pattern set matched and
#: the shipped one does not — the census that narrowed the reader, kept as
#: strings so a later widening trips over the sentences that caused it.
NOT_QUANTITY_RULES = (
    # `<X> AT (ALL|EACH) <Y>`, dropped: 4 hits across bobs/moxy/chelsea, 0 rules.
    "ALL SEAMS TO BE DUCT TAPED AT ALL EDGES.",
    "TRANSITION STRIPS TO BE PROVIDED AT ALL UNLIKE FLOORING MATERIALS.",
    "VERTICAL FRAMING MEMBERS AT ALL DOOR FRAMES SHALL EXTEND TO STRUCTURE ABOVE.",
    "TO BE PAINTED CORRESPONDING COLOR THEY LAND ON AT ALL EXTERIOR ELEVATION PLANS.",
    # `<N> <X> PER <Y>`, dropped: 2 hits, both UNIT phrases.
    "MECHANICALLY VENTILATED AT 6 AIR CHANGES PER HOUR USING UPBLAST FANS.",
    "AIR INFILTRATION SHALL NOT EXCEED 1.57 POUNDS PER SQUARE FOOT IN "
    "ACCORDANCE WITH ASTM E283.",
)


def _count_row(name, qty=12, unit="ea", sheet="A-601"):
    """One COUNTED row, corroborated by a schedule so it publishes MEASURED."""
    return {
        "description": name,
        "canonical_item": name,
        "item_type": "doors",
        "calculated_quantity": qty,
        "calculated_unit": unit,
        "source_sheet": sheet,
        "qty_source": "plan_schedule_legend",
        "count_corroboration": "schedule",
        "provenance": "schedule_table",
    }


def _note(text, sheet="A-101"):
    return [{"text": text, "sheet": sheet}]


def _row(rows, item):
    hits = [r for r in rows if r["item"] == item]
    assert len(hits) == 1, "expected exactly one %r row: %s" % (
        item, [r["item"] for r in rows]
    )
    return hits[0]


def _reason(row):
    return " ".join(row["review_reasons"])


# ═══ 1 — COMPOUND: refused first and loudest ════════════════════════════════


def test_crow_note_13_reads_as_one_rule_over_four_referents():
    rule, = read_quantity_rules(_note(CROW_NOTE_13))
    assert rule.subject == "BOLLARDS"
    assert rule.compound is True
    assert rule.referents == NOTE_13_REFERENTS


def test_crow_note_13_is_refused_as_compound():
    rule, = read_quantity_rules(_note(CROW_NOTE_13))
    resolution = resolve_quantity_rule(rule, [], _norm_item_key)
    assert resolution.refused == REFUSED_COMPOUND
    assert resolution.quantity is None


def test_a_compound_rule_stays_refused_when_a_referent_IS_counted():
    """The half it could compute is exactly the number it must not publish.

    68 drive-in overhead door jambs counted does not make the note's Bollards
    68: the same sentence also puts them at the risers, the transformers and the
    exposed panels.
    """
    rows = aggregate_takeoff(
        [_count_row("Drive-In Overhead Door Jambs", qty=68)],
        general_notes=_note(CROW_NOTE_13),
    )
    bollards = _row(rows, "Bollards")
    assert bollards["quantity"] is None
    assert bollards["provenance"] == "NOT MEASURED"
    assert bollards["source"] == DERIVED_RULE_UNRESOLVED_UNMEASURED
    assert "68" not in _reason(bollards)


def test_the_compound_blank_quotes_the_note_and_names_every_referent():
    rows = aggregate_takeoff([], general_notes=_note(CROW_NOTE_13))
    reason = _reason(_row(rows, "Bollards"))
    assert " ".join(CROW_NOTE_13.split()) in reason
    for referent in NOTE_13_REFERENTS:
        assert referent in reason, referent
    assert "BLANK, not a zero" in reason


def test_a_two_referent_clause_joined_by_AND_is_compound_too():
    """No comma, still a list — the ` AND ` half of the same test."""
    rule, = read_quantity_rules(["PROVIDE BOLLARDS AT ALL RISERS AND TRANSFORMERS."])
    assert rule.compound is True
    assert rule.referents == ("RISERS", "TRANSFORMERS")


# ═══ 2 — REFERENT NOTHING COUNTED: the blank names what to go count ═════════


def test_a_rule_whose_referent_nothing_counted_blanks_and_names_it():
    rows = aggregate_takeoff(
        [_count_row("Overhead Doors", qty=68)],
        general_notes=_note("PROVIDE ONE BOLLARD AT EACH FIRE PROTECTION RISER."),
    )
    row = _row(rows, "Bollard")
    assert row["quantity"] is None
    assert row["source"] == DERIVED_RULE_UNRESOLVED_UNMEASURED
    assert "FIRE PROTECTION RISER" in _reason(row)
    # ...and it must not have quietly answered with the doors it DID count.
    assert "Overhead Doors" not in _reason(row)


def test_an_area_of_the_referent_is_not_a_count_of_it():
    """A rule needs to know HOW MANY, and 4,000 SF is not an answer to that.

    There is no factor between "how many" and "how much" (C3b), so a referent
    the run measured only as an area is a referent the run did not count.
    """
    rows = aggregate_takeoff(
        [{"description": "TRUCK COURT", "canonical_item": "Truck Court",
          "item_type": "schedule_item", "calculated_quantity": 4000.0,
          "calculated_unit": "SF", "source_sheet": "A-101",
          "qty_source": "plan_schedule_legend"}],
        general_notes=_note("PROVIDE ONE BOLLARD AT EACH TRUCK COURT."),
    )
    assert _row(rows, "Truck Court")["quantity"] == 4000.0
    row = _row(rows, "Bollard")
    assert row["quantity"] is None
    assert "COUNTED no TRUCK COURT" in _reason(row)


def test_a_withheld_count_may_not_be_resurrected_as_a_referent():
    """29-02's lesson, at the seam this pass opens: a guard's refusal is final.

    `Stairs` here is a count read off a DETAILS sheet, which 28-16 withholds. A
    second pass that multiplied it would smuggle the withheld number into the
    take-off under a different name.
    """
    withheld = {
        "description": "stair", "item_type": "component",
        "calculated_quantity": 3, "calculated_unit": "ea",
        "source_sheet": "A-401", "sheet_type": "detail",
        "count_corroboration": "detail_sheet_only",
    }
    rows = aggregate_takeoff(
        [withheld],
        general_notes=_note("PROVIDE ONE HANDRAIL AT EACH STAIR."),
    )
    assert _row(rows, "Stairs")["quantity"] is None
    handrail = _row(rows, "Handrail")
    assert handrail["quantity"] is None
    assert "COUNTED no STAIR" in _reason(handrail)


# ═══ 3 — AMBIGUOUS REFERENT: a tie binds nothing (29-02) ════════════════════


def test_a_referent_matching_two_rows_binds_nothing_and_names_both():
    rows = aggregate_takeoff(
        [_count_row("Drive-In Door", qty=2), _count_row("Drive-In Doors", qty=9)],
        general_notes=_note("PROVIDE BOLLARDS AT ALL DRIVE-IN DOORS."),
    )
    row = _row(rows, "Bollards")
    assert row["quantity"] is None
    reason = _reason(row)
    assert "'Drive-In Door'" in reason and "'Drive-In Doors'" in reason
    assert row["source"] == DERIVED_RULE_UNRESOLVED_UNMEASURED
    # Both candidates keep their own numbers: a refusal is not a deletion.
    assert _row(rows, "Drive-In Door")["quantity"] == 2.0
    assert _row(rows, "Drive-In Doors")["quantity"] == 9.0


def test_the_ambiguity_refusal_is_the_resolver_s_own_verdict():
    counted = [CountedItem("Drive-In Door", 2.0, "EA"),
               CountedItem("Drive-In Doors", 9.0, "EA")]
    rule, = read_quantity_rules(["PROVIDE BOLLARDS AT ALL DRIVE-IN DOORS."])
    resolution = resolve_quantity_rule(rule, counted, _norm_item_key)
    assert resolution.refused == REFUSED_REFERENT_AMBIGUOUS
    assert resolution.matched == ("Drive-In Door", "Drive-In Doors")


def test_a_referent_is_matched_exactly_never_by_containment():
    """The 29-02 defect, refused at this join before it can be repeated.

    "stair" inside "Stair plan truck court clearance from center line of rail to
    wall" published Stairs = 3 EA as a MEASUREMENT. Containment is not evidence
    here either.
    """
    counted = [CountedItem(
        "Stair plan truck court clearance from center line of rail to wall",
        3.0, "EA",
    )]
    rule, = read_quantity_rules(["PROVIDE ONE HANDRAIL AT EACH STAIR."])
    resolution = resolve_quantity_rule(rule, counted, _norm_item_key)
    assert resolution.refused == REFUSED_REFERENT_NOT_COUNTED


# ═══ 4 — the happy path, and what it is allowed to claim ════════════════════


def test_a_single_referent_rule_resolves_against_a_counted_row():
    rows = aggregate_takeoff(
        [_count_row("Drive-In Doors", qty=12)],
        general_notes=_note("PROVIDE TWO BOLLARDS AT EACH DRIVE-IN DOOR."),
    )
    row = _row(rows, "Bollards")
    assert row["quantity"] == 24.0
    assert row["unit"] == "EA"
    assert row["detail"][0]["formula"] == "12 x 2"
    reason = _reason(row)
    assert "PRINTS the multiplier 2" in reason
    assert "'Drive-In Doors'" in reason


def test_a_derived_row_is_flagged_and_is_never_a_measurement():
    rows = aggregate_takeoff(
        [_count_row("Drive-In Doors", qty=12)],
        general_notes=_note("PROVIDE TWO BOLLARDS AT EACH DRIVE-IN DOOR."),
    )
    row = _row(rows, "Bollards")
    assert row["needs_review"] is True
    assert row["auto_verified"] is False
    assert row["provenance"] == "NEEDS REVIEW"
    assert row["measured"] is False
    assert row["source"] == DERIVED_FROM_NOTE_RULE
    # ...while the row it was derived FROM is untouched and still MEASURED.
    assert _row(rows, "Drive-In Doors")["measured"] is True


def test_a_derived_number_is_only_as_reproducible_as_its_referent():
    rows = aggregate_takeoff(
        [_count_row("Drive-In Doors", qty=12)],
        general_notes=_note("PROVIDE TWO BOLLARDS AT EACH DRIVE-IN DOOR."),
    )
    assert _row(rows, "Bollards")["quantity_route"] == (
        _row(rows, "Drive-In Doors")["quantity_route"]
    )


def test_an_unprinted_multiplier_is_1_and_the_row_says_it_was_assumed():
    """A multiplier is never invented, and never presented as the drawing's."""
    rule, = read_quantity_rules(["PROVIDE BOLLARDS AT ALL DRIVE-IN DOORS."])
    assert rule.factor == 1.0 and rule.factor_stated is False
    rows = aggregate_takeoff(
        [_count_row("Drive-In Doors", qty=12)],
        general_notes=_note("PROVIDE BOLLARDS AT ALL DRIVE-IN DOORS."),
    )
    row = _row(rows, "Bollards")
    assert row["quantity"] == 12.0
    assert "NO multiplier, so a factor of 1 was ASSUMED" in _reason(row)


def test_a_subject_stops_where_the_detail_reference_starts():
    """Crow general note 21: the detail number is not part of the object's name."""
    rule, = read_quantity_rules([
        "PERSONNEL DOORS AND MISC. METALS SHALL RECEIVE ONE (1) PRIMER COAT AND "
        "TWO (2) FINISH COATS OF ENAMEL.PROVIDE FIRE DEPARTMENT ACCESS SIGNAGE "
        "PER DETAIL 9/A-002 AT EACH PERSONNEL DOOR."
    ])
    assert rule.subject == "FIRE DEPARTMENT ACCESS SIGNAGE"
    assert rule.referent == "PERSONNEL DOOR"


# ═══ 5 — what the pass may not disturb ══════════════════════════════════════


def test_a_run_whose_notes_state_no_rule_is_byte_identical():
    items = [_count_row("Drive-In Doors", qty=12),
             _count_row("Overhead Doors", qty=68)]
    before = json.dumps(aggregate_takeoff(list(items)), default=str, sort_keys=True)
    after = json.dumps(
        aggregate_takeoff(list(items), general_notes=[
            {"text": t, "sheet": "A-101"} for t in NOT_QUANTITY_RULES
        ]),
        default=str, sort_keys=True,
    )
    assert after == before


def test_the_dropped_patterns_stay_dropped():
    """Each of the six real sentences the wider pattern set matched, by name."""
    for text in NOT_QUANTITY_RULES:
        assert read_quantity_rules([text]) == [], text


def test_a_measured_row_is_never_overwritten_by_a_rule():
    """A measurement outranks a hypothesis assembled from a note."""
    items = [_count_row("Bollards", qty=41, sheet="A-101"),
             _count_row("Drive-In Doors", qty=12)]
    before = aggregate_takeoff(list(items))
    after = aggregate_takeoff(
        list(items),
        general_notes=_note("PROVIDE TWO BOLLARDS AT EACH DRIVE-IN DOOR."),
    )
    assert after == before
    assert _row(after, "Bollards")["quantity"] == 41.0


def test_deriving_one_row_disturbs_no_other_row():
    items = [_count_row("Drive-In Doors", qty=12),
             _count_row("Overhead Doors", qty=68)]
    before = {r["item"]: r for r in aggregate_takeoff(list(items))}
    after = {r["item"]: r for r in aggregate_takeoff(
        list(items),
        general_notes=_note("PROVIDE TWO BOLLARDS AT EACH DRIVE-IN DOOR."),
    )}
    assert set(after) - set(before) == {"Bollards"}
    for name, row in before.items():
        assert after[name] == row, name


def test_a_rule_never_opens_a_second_row_beside_a_measured_singular():
    """`Bollard` measured and `BOLLARDS` stated is ONE object (24-03)."""
    rows = aggregate_takeoff(
        [_count_row("Bollard", qty=41), _count_row("Drive-In Doors", qty=12)],
        general_notes=_note("PROVIDE TWO BOLLARDS AT EACH DRIVE-IN DOOR."),
    )
    assert [r["item"] for r in rows if r["item"].lower().startswith("bollard")] \
        == ["Bollard"]


# ═══ 6 — the marker joins the family, and nothing special-cases it ══════════


def test_the_new_marker_joins_the_existing_unmeasured_markers():
    assert DERIVED_RULE_UNRESOLVED_UNMEASURED in aggregator._UNMEASURED_SOURCES
    # ...and the PUBLISHING marker deliberately does not: that row has a number.
    assert DERIVED_FROM_NOTE_RULE not in aggregator._UNMEASURED_SOURCES


def test_no_consumer_special_cases_the_new_markers():
    src = Path(aggregator.__file__).resolve().parents[1]
    for marker in (DERIVED_RULE_UNRESOLVED_UNMEASURED, DERIVED_FROM_NOTE_RULE):
        named_in = sorted(
            p.relative_to(src).as_posix()
            for p in src.rglob("*.py")
            if marker in p.read_text()
        )
        assert named_in == ["pipeline/aggregator.py"], (marker, named_in)


# ═══ 7 — the four-set sweep, committed as a pin ═════════════════════════════

FOUR_SETS = {
    "crow": UPLOADS / "Crow - Cass White Road-Plans.pdf",
    "bobs": UPLOADS / "Bob's Discount Furniture - Kennesaw, GA-plans.pdf",
    "moxy": UPLOADS / "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
    "chelsea": (
        UPLOADS / "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
    ),
}

#: What the SHIPPED reader matches on each set, measured 2026-08-17. Every hit
#: is a real quantity rule; the noise the wider patterns produced is pinned in
#: `NOT_QUANTITY_RULES` above. Quiet on two sets, and never wrong on the other
#: two — a reader that fires on prose would put "Duct Taped" in a take-off.
SWEEP = {
    "crow": (("BOLLARDS", True), ("FIRE DEPARTMENT ACCESS SIGNAGE", False)),
    "bobs": (),
    "moxy": (("WEATHER STRIPPING", False),),
    "chelsea": (),
}

#: A numbered note starts a line. Test-side scaffolding only: harvesting notes
#: into the pipeline is not this plan's, and the reader is a pure function of
#: whatever text a harvest hands it.
_NOTE_SPLIT = re.compile(r"(?m)^\s*\d{1,2}[\.\)]\s+")


def _notes_of(pdf_path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(str(pdf_path))
    try:
        out = []
        for number in range(doc.page_count):
            for chunk in _NOTE_SPLIT.split(doc[number].get_text()):
                text = " ".join(chunk.split())
                if 20 < len(text) < 800:
                    out.append({"text": text, "sheet": "p%d" % number})
        return out
    finally:
        doc.close()


@pytest.mark.parametrize("plan_set", sorted(FOUR_SETS))
def test_the_reader_matches_only_quantity_rules_on_all_four_plan_sets(plan_set):
    path = FOUR_SETS[plan_set]
    if not path.is_file():
        pytest.skip("plan set not present: %s" % path.name)
    rules = read_quantity_rules(_notes_of(path))
    assert tuple((r.subject, r.compound) for r in rules) == SWEEP[plan_set]


def test_the_crow_fixture_pdf_still_prints_note_13_as_pinned():
    """The pinned string above is the fixture's, not a paraphrase of it."""
    fitz = pytest.importorskip("fitz")
    if not CROW_FIXTURE.is_file():
        pytest.skip("fixture not present: %s" % CROW_FIXTURE.name)
    doc = fitz.open(str(CROW_FIXTURE))
    try:
        text = doc[0].get_text()
    finally:
        doc.close()
    assert CROW_NOTE_13 in text
