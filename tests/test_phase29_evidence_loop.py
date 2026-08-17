"""The cross-sheet reasoning pass, and the INPUT GAPS report (29-10). ZERO API.

Every assertion here is about one of five properties, and each one is a defect
this repository has already paid for:

* ADDITIVE ONLY — the loop may not overwrite a measured quantity, rename a row
  an authority named, or raise a confidence. A pass that could would be able to
  undo every guard upstream of it (29-02: 136 personnel doors published as
  galvanized frames when one naming route bypassed one guard).
* AMBIGUITY REFUSES — two candidates close a need UNRESOLVED naming both. There
  is no tie-break on length, score or order anywhere.
* TERMINATION IS PROVED — a fixed point, or the stated ``MAX_ROUNDS``, logged.
* INERTNESS IS PROVED — a run with no open needs leaves the take-off
  byte-identical. This is the test that protects every existing report.
* THE INPUT GAPS REPORT IS A DELIVERABLE — an absent sheet carries the QUESTIONS
  it would have answered, asserted on Crow's real A-111/112/113 case.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.pipeline.aggregator import _norm_item_key  # noqa: E402
from bobbytailor.pipeline.coverage import (  # noqa: E402
    ITEM_NEEDS_REVIEW,
    ITEM_NOT_MEASURED,
)
from bobbytailor.pipeline.cross_references import (  # noqa: E402
    missing_referenced_sheets,
    sheet_ids_in_text,
)
from bobbytailor.pipeline.evidence_loop import (  # noqa: E402
    MAX_ROUNDS,
    NEED_ABSENT_SHEET,
    NEED_HYPOTHESIS_NAME,
    NEED_REFERENT_COUNT,
    NEED_UNNAMED_GEOMETRY,
    OPEN,
    RESOLVED,
    SOURCE_COUNTED_ROW,
    SOURCE_DERIVED,
    SOURCE_SCHEDULE,
    UNRESOLVED_AMBIGUOUS,
    EvidenceItem,
    Need,
    collect_evidence,
    collect_needs,
    extend_evidence,
    input_gaps_report,
    input_gaps_text,
    resolve_need,
    run_evidence_loop,
    run_evidence_pass,
)

CROW_PDF = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"


def _need(subject, wanted, sheet="A-101", text="", factor=1.0, stated=False):
    return Need(
        kind=NEED_REFERENT_COUNT,
        subject=subject,
        wanted=wanted,
        asked_by_sheet=sheet,
        evidence_text=text or "PROVIDE %s AT EACH %s" % (subject.upper(), wanted),
        blocking_item=subject,
        factor=factor,
        factor_stated=stated,
    )


def _item(name, quantity, sheet, source=SOURCE_SCHEDULE, unit="EA"):
    return EvidenceItem(
        name=name, quantity=quantity, unit=unit, sheet=sheet, source=source,
        text=name,
    )


# ---------------------------------------------------------------------------
# 1. A need on one sheet, answered by evidence on another, citing both
# ---------------------------------------------------------------------------


def test_a_need_raised_on_one_sheet_is_answered_by_another_and_cites_both():
    need = _need("Fire Department Access Signage", "PERSONNEL DOOR", sheet="A-101")
    evidence = [_item("Personnel Doors", 136.0, "A-601")]

    res = resolve_need(need, evidence, _norm_item_key)

    assert res.status == RESOLVED
    assert res.answered_by_sheet == "A-601"
    assert res.quantity == 136.0
    # BOTH sheets, in the sentence a human reads. A derived number that cannot
    # say who asked and who answered is a number with a citation-shaped hole.
    assert "A-101" in res.reason and "A-601" in res.reason
    assert "DERIVED, not measured" in res.reason


def test_a_printed_multiplier_is_applied_and_an_assumed_one_is_admitted():
    stated = _need("Bollards", "OVERHEAD DOOR", factor=2.0, stated=True)
    evidence = [_item("Overhead Doors", 12.0, "A-601")]
    res = resolve_need(stated, evidence, _norm_item_key)
    assert res.quantity == 24.0
    assert "PRINTS the multiplier 2" in res.reason

    assumed = _need("Bollards", "OVERHEAD DOOR")
    res = resolve_need(assumed, evidence, _norm_item_key)
    assert res.quantity == 12.0
    assert "ASSUMED" in res.reason


def test_matching_is_exact_on_the_canonical_key_never_containment():
    """29-02 measured containment at this exact join: the token "stair" inside a
    clearance dimension published Stairs = 3 EA as a MEASUREMENT."""
    need = _need("Handrail", "STAIR")
    evidence = [_item(
        "Stair plan truck court clearance from center line of rail to wall",
        3.0, "A-401",
    )]
    assert resolve_need(need, evidence, _norm_item_key).status == OPEN


# ---------------------------------------------------------------------------
# 2. The fixed point — a single pass is provably insufficient
# ---------------------------------------------------------------------------


def test_a_single_pass_cannot_see_what_the_second_round_sees():
    first = _need("Bollards", "PERSONNEL DOOR")
    second = _need("Bollard Sleeves", "BOLLARDS")
    evidence = [_item("Personnel Doors", 10.0, "A-601")]

    # The proof that one pass is not enough: round 1's evidence cannot answer it.
    assert resolve_need(second, evidence, _norm_item_key).status == OPEN

    loop = run_evidence_loop([first, second], evidence, _norm_item_key)

    assert loop.rounds == 2
    assert [r.round_index for r in loop.resolutions] == [1, 2]
    assert loop.open_needs == ()
    sleeves = [r for r in loop.resolutions if r.need.subject == "Bollard Sleeves"][0]
    assert sleeves.quantity == 10.0
    # Round 2's answer is cited to the sheet that supplied round 1's count, not
    # to the loop itself.
    assert sleeves.answered_by_sheet == "A-601"


def test_the_loop_stops_the_moment_a_round_learns_nothing():
    needs = [_need("A", "NOTHING COUNTED"), _need("B", "ALSO NOTHING")]
    loop = run_evidence_loop(needs, [], _norm_item_key)
    assert loop.rounds == 1
    assert loop.resolutions == ()
    assert len(loop.open_needs) == 2
    assert loop.hit_max_rounds is False
    # Every open need carries the sentence saying WHY, not a status code.
    assert all("answers to" in r for r in loop.open_reasons)


def test_a_cyclic_need_set_reaches_a_fixed_point_and_resolves_nothing():
    """Each need waits for the other's subject. Neither can ever start."""
    loop = run_evidence_loop(
        [_need("Chicken", "EGGS"), _need("Eggs", "CHICKENS")], [], _norm_item_key,
    )
    assert loop.rounds == 1
    assert loop.hit_max_rounds is False
    assert len(loop.open_needs) == 2


def test_an_unbounded_chain_stops_at_max_rounds_and_says_so(caplog):
    """A chain longer than MAX_ROUNDS resolves one link per round forever."""
    links = MAX_ROUNDS + 3
    needs = [_need("Link %d" % i, "LINK %d" % (i - 1)) for i in range(1, links + 1)]
    evidence = [_item("Link 0", 1.0, "A-601")]

    with caplog.at_level(logging.WARNING, logger="bobbytailor.pipeline.evidence_loop"):
        loop = run_evidence_loop(needs, evidence, _norm_item_key)

    assert loop.rounds == MAX_ROUNDS
    assert loop.hit_max_rounds is True
    assert len(loop.resolutions) == MAX_ROUNDS
    assert len(loop.open_needs) == links - MAX_ROUNDS
    assert "MAX_ROUNDS" in caplog.text
    # Stopping early never drops a need: what did not close is REPORTED.
    gaps = input_gaps_report(loop, [], needs=needs)
    assert gaps["hit_max_rounds"] is True
    assert len(gaps["open_needs"]) == links - MAX_ROUNDS
    assert "STOPPED AT THE" in input_gaps_text(gaps)


# ---------------------------------------------------------------------------
# 3. Ambiguity refuses — never arbitrated
# ---------------------------------------------------------------------------


def test_two_candidate_answers_close_the_need_unresolved_naming_both():
    need = _need("Bollards", "DOOR")
    evidence = [_item("Doors", 70.0, "A-601"), _item("Door", 29.0, "A-602")]

    res = resolve_need(need, evidence, _norm_item_key)

    assert res.status == UNRESOLVED_AMBIGUOUS
    assert res.quantity is None
    assert len(res.candidates) == 2
    for token in ("Doors", "Door", "70", "29", "A-601", "A-602"):
        assert token in res.reason
    assert "arbitration, not evidence" in res.reason


def test_ambiguity_does_not_break_on_order_length_or_score():
    # Same object under two spellings and two counts: the shorter name, the
    # bigger number and the first-seen row are all available to break the tie.
    evidence = [_item("Door", 70.0, "A-601"), _item("Doors", 29.0, "A-602")]
    forward = resolve_need(_need("X", "DOORS"), evidence, _norm_item_key)
    backward = resolve_need(_need("X", "DOORS"), list(reversed(evidence)),
                            _norm_item_key)
    # The shorter name does not win, the first-seen does not win, nothing wins.
    assert forward.status == backward.status == UNRESOLVED_AMBIGUOUS
    assert forward.quantity is backward.quantity is None


def test_an_unresolved_need_adds_no_evidence_and_no_number():
    need = _need("Bollards", "DOOR")
    evidence = [_item("Doors", 70.0, "A-601"), _item("Doors", 29.0, "A-602")]
    res = resolve_need(need, evidence, _norm_item_key)
    assert extend_evidence(evidence, [res], _norm_item_key) == tuple(evidence)


def test_one_fact_printed_on_two_sheets_is_one_answer_not_an_ambiguity():
    """A schedule row and the published row it produced are one fact seen twice."""
    need = _need("Bollards", "OVERHEAD DOOR")
    evidence = [
        _item("Overhead Doors", 12.0, "A-601"),
        _item("Overhead Doors", 12.0, "A-101", source=SOURCE_COUNTED_ROW),
    ]
    res = resolve_need(need, evidence, _norm_item_key)
    assert res.status == RESOLVED
    assert res.answered_by_sheet == "A-101, A-601"


# ---------------------------------------------------------------------------
# 4. Additive only
# ---------------------------------------------------------------------------


def _authored_rows():
    return [
        {"item": "Doors - Hollow Metal", "quantity": 29.0, "unit": "EA",
         "source_sheets": ["A-601"], "source": "schedule", "confidence": "high",
         "needs_review": False, "measured": True, "item_type": "component"},
        {"item": "Bollards", "quantity": 12.0, "unit": "EA",
         "source_sheets": ["A-101"], "source": "manifest", "confidence": "medium",
         "needs_review": False, "measured": True, "item_type": "component"},
    ]


def test_the_loop_never_overwrites_a_quantity_a_name_or_a_confidence():
    rows = _authored_rows()
    before = json.dumps(rows, sort_keys=True)
    # Needs whose subjects are EXACTLY the two authored rows: if the pass could
    # write anywhere, this is the input that would make it.
    needs = [
        _need("Bollards", "DOORS - HOLLOW METAL"),
        Need(NEED_HYPOTHESIS_NAME, "Bollards", "Bollards", "A-101",
             "this row's NAME is a hypothesis", "Bollards"),
    ]
    evidence = collect_evidence([], rows)
    loop = run_evidence_loop(needs, evidence, _norm_item_key)

    assert json.dumps(rows, sort_keys=True) == before
    gaps = input_gaps_report(loop, [], needs=needs)
    for answer in gaps["answers"]:
        # A derived quantity is NEVER a measurement and never counts as coverage.
        assert answer["measured"] is False
        assert answer["status"] == ITEM_NEEDS_REVIEW
    for record in gaps["open_needs"]:
        assert record["status"] == ITEM_NOT_MEASURED


def test_extend_never_shadows_a_name_the_evidence_already_carries():
    evidence = [_item("Bollards", 12.0, "A-101"), _item("Doors", 70.0, "A-601")]
    res = resolve_need(_need("Bollards", "DOORS"), evidence, _norm_item_key)
    assert res.status == RESOLVED and res.quantity == 70.0
    extended = extend_evidence(evidence, [res], _norm_item_key)
    # The measured Bollards = 12 stands; the loop's 70 does not shadow it.
    assert extended == tuple(evidence)
    assert not [e for e in extended if e.source == SOURCE_DERIVED]


def test_a_resolved_need_adds_exactly_one_evidence_item_and_removes_none():
    evidence = [_item("Doors", 70.0, "A-601")]
    res = resolve_need(_need("Bollards", "DOORS"), evidence, _norm_item_key)
    extended = extend_evidence(evidence, [res], _norm_item_key)
    assert len(extended) == len(evidence) + 1
    assert extended[:1] == tuple(evidence)
    assert extended[-1].source == SOURCE_DERIVED
    assert extended[-1].name == "Bollards"


# ---------------------------------------------------------------------------
# 5. The kinds that must never resolve
# ---------------------------------------------------------------------------


def test_an_absent_sheet_is_never_answered_by_anything_in_the_set():
    need = Need(NEED_ABSENT_SHEET, "A-111", "the sheet A-111 itself", "A-101",
                "SEE 1/A-111", "A-111")
    evidence = [_item("A-111", 1.0, "A-101"), _item("the sheet A-111 itself", 1.0,
                                                    "A-401")]
    res = resolve_need(need, evidence, _norm_item_key)
    assert res.status == OPEN
    assert "not in the upload" in res.reason


def test_unnamed_geometry_is_never_named_by_a_coincidence_of_counts():
    """The record exists BECAUSE nothing named it. An equal count is not a name."""
    need = Need(NEED_UNNAMED_GEOMETRY, "SYM-7", "a name for 12 measured mark(s)",
                "A-101", "12 repeated marks were measured", "SYM-7")
    evidence = [_item("Bollards", 12.0, "A-601")]
    res = resolve_need(need, evidence, _norm_item_key)
    assert res.status == OPEN
    assert "coincidence" in res.reason


def test_a_hypothesis_name_is_confirmed_only_by_a_name_the_drawing_printed():
    need = Need(NEED_HYPOTHESIS_NAME, "Bollards", "Bollards", "A-101",
                "this row's NAME is a hypothesis", "Bollards")
    # A counted row is not printed evidence — it may itself be the hypothesis.
    assert resolve_need(
        need, [_item("Bollards", 12.0, "A-101", source=SOURCE_COUNTED_ROW)],
        _norm_item_key,
    ).status == OPEN

    res = resolve_need(need, [_item("Bollards", None, "A-601")], _norm_item_key)
    assert res.status == RESOLVED
    assert res.quantity is None                      # a name is not a number
    assert "PRINTED on A-601" in res.reason


# ---------------------------------------------------------------------------
# 6. Collection — from the run, never invented
# ---------------------------------------------------------------------------


def test_a_run_with_nothing_open_raises_no_needs_at_all():
    assert collect_needs() == ()
    assert collect_needs(
        sheets=[{"sheet": "A-101", "text": "1. ALL WORK SHALL COMPLY."}],
        takeoff_rows=[{"item": "Doors", "quantity": 4, "source": "schedule"}],
    ) == ()


def test_a_quantity_rule_split_across_a_line_break_is_read_whole():
    """Crow note 21 breaks mid-rule; a one-line reader misses it entirely."""
    needs = collect_needs(sheets=[{
        "sheet": "A-101",
        "text": "20. PANELS SHALL RECEIVE ONE COAT\n"
                "21. PROVIDE FIRE DEPARTMENT ACCESS SIGNAGE PER DETAIL 9/A-002\n"
                "AT EACH PERSONNEL DOOR.\n",
    }])
    assert len(needs) == 1
    assert needs[0].subject == "Fire Department Access Signage"
    assert needs[0].wanted == "PERSONNEL DOOR"
    # The quote starts at the note that stated the rule, not mid-note-20.
    assert needs[0].evidence_text.startswith("21. PROVIDE FIRE DEPARTMENT")


def test_overlapping_note_windows_raise_one_need_per_subject_not_three():
    needs = collect_needs(sheets=[{
        "sheet": "A-101",
        "text": "1. FILLER\n2. PROVIDE BOLLARDS AT EACH OVERHEAD DOOR\n3. FILLER\n",
    }])
    assert [n.subject for n in needs] == ["Bollards"]


def test_the_reading_that_saw_the_whole_sentence_is_the_one_published():
    """A window that ends mid-clause reads a referent the note never stated."""
    needs = collect_needs(sheets=[{
        "sheet": "A-101",
        "text": "11. FILLER\n12. FILLER\n"
                "13. ALL BOLLARDS TO BE PAINTED YELLOW. (PROVIDE BOLLARDS AT "
                "ALL DOOR JAMBS, FIRE PROTECTION RISERS AND EXPOSED\n"
                "ELECTRICAL PANELS).\n",
    }])
    assert len(needs) == 1
    assert needs[0].wanted.endswith("EXPOSED ELECTRICAL PANELS")
    assert needs[0].evidence_text.startswith("13. ALL BOLLARDS")


def test_a_compound_rule_keeps_29_06_s_refusal_and_is_reported_not_resolved():
    """Crow note 13 names four referents. Half a rule is a wrong number."""
    needs = collect_needs(sheets=[{
        "sheet": "A-101",
        "text": "13. PROVIDE BOLLARDS AT ALL DRIVE-IN OVERHEAD DOOR JAMBS, FIRE "
                "PROTECTION RISERS, ELECTRICAL TRANSFORMERS AND EXPOSED "
                "ELECTRICAL PANELS.\n",
    }])
    assert len(needs) == 1
    assert needs[0].subject == "Bollards"
    assert "," in needs[0].wanted
    # Every referent counted, and the rule still yields no number.
    evidence = [
        _item("Drive-In Overhead Door Jambs", 12.0, "A-601"),
        _item("Fire Protection Risers", 2.0, "A-601"),
        _item("Electrical Transformers", 1.0, "A-601"),
        _item("Exposed Electrical Panels", 3.0, "A-601"),
    ]
    loop = run_evidence_loop(needs, evidence, _norm_item_key)
    assert loop.resolutions == ()
    assert len(loop.open_needs) == 1


def test_needs_are_collected_from_every_producer_the_run_already_has():
    needs = collect_needs(
        sheets=[{"sheet": "A-101",
                 "text": "13. PROVIDE BOLLARDS AT EACH RISER\nSEE 1/A-111\n"}],
        takeoff_rows=[{"item": "Slab On Grade", "quantity": 100.0,
                       "source": "library", "source_sheets": ["A-101"]}],
        unnamed_geometry=[{"candidate_id": "SYM-7", "quantity": 12, "sheet": "A-201",
                           "detail": "12 repeated marks were measured"}],
        missing_sheets=[{"sheet_id": "A-111", "cited_on_pages": [0], "citations": 1}],
        hypothesis_sources=frozenset({"library", "learned"}),
    )
    assert sorted({n.kind for n in needs}) == sorted([
        NEED_ABSENT_SHEET, NEED_HYPOTHESIS_NAME, NEED_REFERENT_COUNT,
        NEED_UNNAMED_GEOMETRY,
    ])


def test_a_bare_drawing_bubble_is_a_citation_but_not_a_question():
    """"A-111" alone proves the reference; "SEE 1/A-111" is the deferral."""
    needs = collect_needs(
        sheets=[{"sheet": "A-101", "text": "A-111\nSEE 1/A-111\n"}],
        missing_sheets=[{"sheet_id": "A-111", "cited_on_pages": [0], "citations": 2}],
    )
    assert [n.evidence_text for n in needs] == ["SEE 1/A-111"]


def test_evidence_is_collected_across_sheets_with_the_sheet_that_printed_it():
    evidence = collect_evidence(
        [{"_source_sheet": "A-601", "schedules": [{
            "name": "Door Schedule", "table_purpose": "takeoff_legend",
            "rows": [{"ITEM": "Doors-HM", "QTY": "29", "UNIT": "EA"},
                     {"ITEM": "", "QTY": "3"}],
        }]}],
        [{"item": "Bollards", "quantity": 12.0, "unit": "EA",
          "source_sheets": ["A-101"]}],
    )
    assert [(e.name, e.quantity, e.sheet, e.source) for e in evidence] == [
        ("Doors-HM", 29.0, "A-601", SOURCE_SCHEDULE),
        ("Bollards", 12.0, "A-101", SOURCE_COUNTED_ROW),
    ]


# ---------------------------------------------------------------------------
# 7. The INPUT GAPS report, and Crow's real absent sheets
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not CROW_PDF.exists(), reason="Crow fixture PDF not present")
def test_crow_absent_sheets_carry_the_questions_they_would_have_answered():
    """"A-111 is missing" is a fact; "A-101 defers to it here" is an instruction."""
    import fitz

    from scripts.coverage_probe import get_title_block_text

    doc = fitz.open(CROW_PDF)
    try:
        sheets, present, texts = [], [], []
        for i in range(doc.page_count):
            title = get_title_block_text(doc, i)
            ids = sheet_ids_in_text(title)
            text = doc[i].get_text()
            sheets.append({"sheet": ids[0] if ids else "", "page_index": i,
                           "text": text})
            present.extend(ids)
            texts.append(text)
        missing = missing_referenced_sheets(present, texts)
    finally:
        doc.close()

    needs = collect_needs(sheets=sheets, missing_sheets=missing)
    loop = run_evidence_loop(needs, (), _norm_item_key)
    gaps = input_gaps_report(loop, missing, needs=needs)
    grouped = {m["sheet_id"]: m for m in gaps["missing_sheets"]}

    for enlarged in ("A-111", "A-112", "A-113"):
        record = grouped[enlarged]
        assert record["cited_on_pages"] == [0]
        assert record["asked_by_sheets"] == ["A-101"]
        # The QUESTION, verbatim from the drawing.
        assert [q["evidence_text"] for q in record["questions"]] == [
            "SEE 1/%s" % enlarged
        ]
        assert record["questions"][0]["kind"] == NEED_ABSENT_SHEET
        assert record["questions"][0]["status"] == ITEM_NOT_MEASURED
        assert "added to the upload" in record["questions"][0]["what_would_answer"]

    # A-002 is cited by note 21, which is also the note that raises a count
    # question — so the missing sheet carries the take-off consequence too.
    kinds = {q["kind"] for q in grouped["A-002"]["questions"]}
    assert NEED_REFERENT_COUNT in kinds
    signage = [q for q in grouped["A-002"]["questions"]
               if q["kind"] == NEED_REFERENT_COUNT][0]
    assert signage["item"] == "Fire Department Access Signage"
    assert signage["wanted"] == "PERSONNEL DOOR"
    assert signage["evidence_text"].startswith("21. PERSONNEL DOORS")

    # Crow's Bollards stays a blank: 29-06 refuses note 13 as compound and this
    # loop does not overrule it. What it adds is the reason reaching the client.
    bollards = [n for n in gaps["open_needs"] if n["item"] == "Bollards"]
    assert len(bollards) == 1
    # The whole clause, exactly as 29-06 reads it: four referents, not the
    # truncation a narrower window would have published.
    assert bollards[0]["wanted"] == (
        "DRIVE-IN OVERHEAD DOOR JAMBS, FIRE PROTECTION RISERS, ELECTRICAL "
        "TRANSFORMERS AND EXPOSED ELECTRICAL PANELS"
    )
    assert bollards[0]["evidence_text"].startswith("13. ALL BOLLARDS")
    assert gaps["needs_resolved"] == 0

    text = input_gaps_text(gaps)
    for enlarged in ("A-111", "A-112", "A-113", "A-002", "A-501"):
        assert enlarged in text
    assert "SHEETS CITED BUT NOT IN THE UPLOAD" in text
    assert "Nothing below is a zero." in text


def test_the_report_says_nothing_when_there_is_nothing_to_say():
    loop = run_evidence_loop([], [], _norm_item_key)
    gaps = input_gaps_report(loop, [])
    assert gaps["needs_raised"] == 0
    assert gaps["rounds"] == 0
    assert input_gaps_text(gaps) == ""


def test_an_answer_reports_both_sheets_the_factor_and_that_it_is_not_measured():
    need = _need("Bollards", "OVERHEAD DOOR", factor=2.0, stated=True)
    loop = run_evidence_loop([need], [_item("Overhead Doors", 12.0, "A-601")],
                             _norm_item_key)
    gaps = input_gaps_report(loop, [])
    answer = gaps["answers"][0]
    assert answer["asked_by_sheet"] == "A-101"
    assert answer["answered_by_sheet"] == "A-601"
    assert answer["quantity"] == 24.0
    assert answer["factor"] == 2.0 and answer["factor_stated"] is True
    assert answer["measured"] is False
    assert answer["evidence"][0]["sheet"] == "A-601"
    assert "DERIVED" in input_gaps_text(gaps)


# ---------------------------------------------------------------------------
# 8. Inertness — the test that protects every existing customer report
# ---------------------------------------------------------------------------


def _finished_run(tmp_path, rows=None):
    run = tmp_path / "run"
    run.mkdir()
    takeoff = run / "takeoff.json"
    takeoff.write_text(json.dumps({"takeoff_summary": rows or []}, indent=2))
    summary = run / "summary.txt"
    summary.write_text("TAKEOFF SUMMARY\nDoors - Hollow Metal   29 EA\n")
    report = {
        "takeoff_summary": rows or [],
        "_files": {"run_folder": str(run), "json": str(takeoff),
                   "summary_txt": str(summary)},
    }
    return report, run, takeoff, summary


def test_a_run_with_no_open_needs_leaves_the_takeoff_byte_identical(tmp_path):
    report, run, takeoff, summary = _finished_run(tmp_path, _authored_rows())
    before = (takeoff.read_bytes(), summary.read_bytes(),
              sorted(p.name for p in run.iterdir()))

    run_evidence_pass(report, pages=[{"sheet_name": "A-101", "page_index": 0,
                                      "full_page_text": "1. ALL WORK SHALL "
                                                        "COMPLY WITH CODE."}],
                      all_extracted=[], missing_sheets=[])

    assert (takeoff.read_bytes(), summary.read_bytes(),
            sorted(p.name for p in run.iterdir())) == before
    assert "input_gaps" not in report
    assert "input_gaps_json" not in report["_files"]


def test_a_run_with_gaps_publishes_beside_coverage_and_still_never_edits_it(tmp_path):
    report, run, takeoff, summary = _finished_run(tmp_path, _authored_rows())
    takeoff_before = takeoff.read_bytes()
    summary_before = summary.read_text()

    gaps = run_evidence_pass(
        report,
        pages=[{"sheet_name": "A-101", "page_index": 0,
                "full_page_text": "SEE 1/A-111\n"}],
        all_extracted=[],
        missing_sheets=[{"sheet_id": "A-111", "cited_on_pages": [0],
                         "citations": 1}],
    )

    # The take-off is not the loop's to edit — not one byte of it.
    assert takeoff.read_bytes() == takeoff_before
    assert report["takeoff_summary"] == _authored_rows()
    # The gaps report is its own artifact, beside coverage.json.
    published = json.loads((run / "input_gaps.json").read_text())
    assert published["missing_sheets"][0]["sheet_id"] == "A-111"
    assert report["_files"]["input_gaps_json"] == str(run / "input_gaps.json")
    assert report["input_gaps"] == gaps
    # summary.txt is APPENDED to; nothing it already said is changed.
    grown = summary.read_text()
    assert grown.startswith(summary_before)
    assert "INPUT GAPS" in grown
    assert "SEE 1/A-111" in grown


def test_a_finished_run_with_no_folder_still_never_raises(tmp_path):
    report = {"takeoff_summary": [], "_files": {}}
    gaps = run_evidence_pass(
        report,
        pages=[{"sheet_name": "A-101", "page_index": 0,
                "full_page_text": "SEE 1/A-111\n"}],
        all_extracted=[],
        missing_sheets=[{"sheet_id": "A-111", "cited_on_pages": [0],
                         "citations": 1}],
    )
    assert gaps["missing_sheets"][0]["sheet_id"] == "A-111"
