"""Naming OFFERS — asking about unnamed geometry without claiming it (29-11). ZERO API.

The whole change turns on one distinction, and every test here is about it:
**publishing a name is a CLAIM, offering one is a QUESTION, and only the first
can be wrong.** So the properties asserted are:

* AN OFFER PUBLISHES NOTHING — the take-off, its quantities, its review flags
  and its coverage are byte-identical whether offers were raised or not.
* ELIGIBILITY IS UNIT AND MEASURE BASIS, AND NOTHING ELSE — no token overlap
  (16 of the 39 real records carry NO text), no fuzzy score, no position
  heuristic. Each of those is a shape guess, and one hidden behind a surface a
  human trusts is worse than no offer at all.
* AMBIGUITY SHOWS — three eligible entries produce three offers, no default.
* THE CAP SUPPRESSES WHOLE, NEVER TRUNCATES — truncating a list of equally
  grounded options is a ranking, and there is no ranking anywhere in this file.
* 29-10'S REFUSAL IS UNTOUCHED — `unnamed_geometry` still never RESOLVES.
* A DECLINE STICKS — the same question is not re-asked on the next run.

The measured problem this is sized against is the paid Crow run of 2026-08-17:
39 of 46 open needs are `unnamed_geometry` carrying 209 EA of counted marks,
16 with `evidence_texts: []` and 12 with only drafting noise ('A-101', 'DWG',
'1/A-112'). Manifest resolution matches TEXT, so no alias table can ever bind
them.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.devtools.object_manifest import load_manifest  # noqa: E402
from bobbytailor.pipeline.coverage import (  # noqa: E402
    ITEM_HUMAN_INPUT,
    ITEM_MEASURED,
)
from bobbytailor.pipeline.evidence_loop import (  # noqa: E402
    MAX_OFFERS_PER_CANDIDATE,
    NEED_UNNAMED_GEOMETRY,
    OPEN,
    Need,
    NamingOffer,
    accept_offer,
    candidate_signature,
    decline_key,
    decline_offer,
    naming_offers,
    offers_for,
    offers_report,
    record_decline,
    resolve_need,
    run_evidence_pass,
)
from bobbytailor.pipeline.provenance import provenance_of_row  # noqa: E402

GENERIC_MANIFEST = ROOT / "tests" / "fixtures" / "generic_catalog_manifest.json"
CROW_MANIFEST = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_manifest.json"
#: The paid run this plan is sized against. Under `output/`, which is
#: gitignored, so the tests reading it SKIP rather than fail on a fresh clone.
PAID_RUN = (ROOT / "output" / "VisionOnly_Crow_Small_Repro_20260817_065118"
            / "takeoff.json")


def _marks(candidate_id="SYM-6", quantity=36, unit="EA", sheet="A-101",
           position=(433.2, 1030.68, 442.2, 1039.68), texts=None):
    """One unnamed-geometry record, in the exact shape the real run emits."""
    return {
        "candidate_id": candidate_id,
        "kind": "symbol_group",
        "quantity": quantity,
        "unit": unit,
        "position_pt": list(position),
        "evidence_texts": list(texts or []),
        "reason": "no_name_source",
        "detail": "%s repeated marks were measured, but no vision label, no "
                  "naming-library bind, no deterministic geometry name and no "
                  "text anchor identifies them" % quantity,
        "sheet": sheet,
    }


def _manifest(*entries):
    return [dict(e) for e in entries]


COLUMNS = {"name": "Columns", "unit": "EA", "measure": "count"}
BOLLARDS = {"name": "Bollards", "unit": "EA", "measure": "count"}
LADDER = {"name": "Ladder-H-20'", "unit": "EA", "measure": "count"}
SEALED_CONCRETE = {"name": "Sealed Concrete", "unit": "SF", "measure": "area"}
BLOCKING = {"name": "Blocking", "unit": "LF", "measure": "length"}


# ---------------------------------------------------------------------------
# 1. The offer, and the words it uses
# ---------------------------------------------------------------------------


def test_an_unnamed_count_cluster_is_offered_a_count_entry_with_its_why():
    offers = offers_for(_marks(), _manifest(COLUMNS))

    assert len(offers) == 1
    offer = offers[0]
    assert offer.manifest_name == "Columns"
    # Everything a UI needs to show the crop and ask, carried through unchanged.
    assert (offer.candidate_id, offer.sheet, offer.quantity, offer.unit) == (
        "SYM-6", "A-101", 36.0, "EA")
    assert offer.position_pt == (433.2, 1030.68, 442.2, 1039.68)
    # The `why` states the ONLY grounds, and states them as grounds for a
    # QUESTION — the count, where it was measured, the entry's unit/basis, and
    # an explicit "nothing on the sheet names these".
    assert offer.why == (
        "36 counted marks on A-101; your manifest lists Columns as EA/count. "
        "Matching unit and measure basis is the ONLY thing that produced this "
        "question — nothing on the sheet names these marks. Confirm only if "
        "that is what these are."
    )


def test_an_offer_carries_no_score_rank_or_default_field():
    """There is nothing to sort by, because nothing was scored.

    A `confidence`, a `rank` or a `recommended` field would be read as the app
    having an opinion about which name is right. It has none: every offer on a
    cluster rests on the identical grounds.
    """
    assert NamingOffer._fields == (
        "candidate_id", "sheet", "quantity", "unit", "position_pt",
        "manifest_name", "why",
    )


# ---------------------------------------------------------------------------
# 2. Eligibility: unit AND measure basis, and nothing else
# ---------------------------------------------------------------------------


def test_an_area_entry_is_never_offered_against_a_count_cluster():
    offers = offers_for(_marks(), _manifest(SEALED_CONCRETE, BLOCKING, COLUMNS))

    assert [o.manifest_name for o in offers] == ["Columns"]


def test_a_matching_unit_with_a_different_basis_is_not_eligible():
    """Unit alone is not the test. Both must match.

    A manifest may state a basis its unit does not imply; when it does, the
    entry's own word wins and an EA/area entry is not a home for EA/count marks.
    """
    ea_but_area = {"name": "Storefront", "unit": "EA", "measure": "area"}

    assert offers_for(_marks(), _manifest(ea_but_area)) == ()


def test_a_cluster_with_no_unit_is_offered_nothing():
    """A blank unit must not fall through to the `count` default.

    `measure_from_unit("")` answers "count", so reading a unitless record
    through it would make every unitless cluster eligible for every EA entry in
    the manifest — a coincidence, which is the thing this path exists to avoid.
    """
    record = _marks()
    record["unit"] = ""

    assert offers_for(record, _manifest(COLUMNS, BOLLARDS)) == ()


def test_text_on_the_record_changes_nothing_about_eligibility():
    """No token overlap, in either direction.

    The 12 real records whose only text is drafting noise must be treated
    exactly like the 16 with no text at all — and a record that happens to say
    'BOLLARD' still earns no preference, because a preference is a ranking.
    """
    silent = offers_for(_marks(texts=[]), _manifest(BOLLARDS, COLUMNS))
    noisy = offers_for(_marks(texts=["A-101", "DWG"]), _manifest(BOLLARDS, COLUMNS))
    talkative = offers_for(_marks(texts=["BOLLARD"]), _manifest(BOLLARDS, COLUMNS))

    names = [o.manifest_name for o in silent]
    assert names == ["Bollards", "Columns"]
    assert [o.manifest_name for o in noisy] == names
    assert [o.manifest_name for o in talkative] == names


# ---------------------------------------------------------------------------
# 3. Ambiguity SHOWS
# ---------------------------------------------------------------------------


def test_three_eligible_entries_produce_three_offers_and_no_default():
    offers = offers_for(_marks(), _manifest(COLUMNS, BOLLARDS, LADDER))

    assert len(offers) == 3
    # All three, in the order the human wrote the manifest — an order that
    # implies nothing about fit, which is why it is the one used.
    assert [o.manifest_name for o in offers] == [
        "Columns", "Bollards", "Ladder-H-20'"]
    # Nothing distinguishes them but the name: identical grounds, identical
    # sentence structure, identical measured facts.
    assert len({o.why.replace(o.manifest_name, "") for o in offers}) == 1
    assert len({(o.candidate_id, o.quantity, o.unit) for o in offers}) == 1


# ---------------------------------------------------------------------------
# 4. The cap: suppress whole, never truncate
# ---------------------------------------------------------------------------


def test_more_eligible_entries_than_the_cap_suppresses_the_whole_question():
    many = _manifest(*[
        {"name": "Count Item %d" % i, "unit": "EA", "measure": "count"}
        for i in range(MAX_OFFERS_PER_CANDIDATE + 1)
    ])

    assert offers_for(_marks(), many) == ()

    report = offers_report([_marks()], many)
    assert report["offers"] == []
    assert report["candidates_offered"] == 0
    suppressed = report["candidates_suppressed"]
    # The cap REPORTS itself. A cap that hid its own effect would let a
    # manifest quietly stop producing questions while the report still read as
    # though every cluster had been considered.
    assert len(suppressed) == 1
    assert suppressed[0]["candidate_id"] == "SYM-6"
    assert suppressed[0]["eligible_entries"] == MAX_OFFERS_PER_CANDIDATE + 1
    assert str(MAX_OFFERS_PER_CANDIDATE) in suppressed[0]["reason"]


def test_exactly_the_cap_is_still_asked():
    at_cap = _manifest(*[
        {"name": "Count Item %d" % i, "unit": "EA", "measure": "count"}
        for i in range(MAX_OFFERS_PER_CANDIDATE)
    ])

    assert len(offers_for(_marks(), at_cap)) == MAX_OFFERS_PER_CANDIDATE


def test_a_decline_can_bring_a_suppressed_cluster_back_under_the_cap():
    """Declines shrink the question, so the cap is applied after them."""
    record = _marks()
    over = _manifest(*[
        {"name": "Count Item %d" % i, "unit": "EA", "measure": "count"}
        for i in range(MAX_OFFERS_PER_CANDIDATE + 1)
    ])
    assert offers_for(record, over) == ()

    declined = record_decline((), "Crow", record, "Count Item 0")

    assert len(offers_for(record, over, "Crow", declined)) == \
        MAX_OFFERS_PER_CANDIDATE


# ---------------------------------------------------------------------------
# 5. Declines persist per (project, candidate signature, manifest name)
# ---------------------------------------------------------------------------


def test_a_declined_offer_is_not_re_raised_and_the_others_still_are():
    record = _marks()
    offers = offers_for(record, _manifest(COLUMNS, BOLLARDS, LADDER))
    declined = decline_offer(offers[0], record, "Crow")

    again = offers_for(record, _manifest(COLUMNS, BOLLARDS, LADDER),
                       "Crow", declined)

    assert [o.manifest_name for o in again] == ["Bollards", "Ladder-H-20'"]


def test_a_decline_is_scoped_to_its_project():
    record = _marks()
    declined = record_decline((), "Crow", record, "Columns")

    # "These marks are not Columns" is a fact about ONE drawing set.
    assert offers_for(record, _manifest(COLUMNS), "Crow", declined) == ()
    assert len(offers_for(record, _manifest(COLUMNS), "Bobs", declined)) == 1


def test_a_decline_survives_a_candidate_id_renumbering():
    """`SYM-6` is minted by detection order; the marks are not.

    One extra cluster upstream renumbers everything after it, so keying a
    decline on `candidate_id` would silently attach yesterday's answer to a
    different pile of marks. The signature keys on sheet, unit, count and
    position instead.
    """
    first_run = _marks(candidate_id="SYM-6")
    declined = record_decline((), "Crow", first_run, "Columns")
    renumbered = _marks(candidate_id="SYM-9")

    assert candidate_signature(renumbered) == candidate_signature(first_run)
    assert offers_for(renumbered, _manifest(COLUMNS), "Crow", declined) == ()


def test_a_different_cluster_is_still_asked_after_a_decline():
    declined = record_decline((), "Crow", _marks(), "Columns")
    elsewhere = _marks(candidate_id="SYM-7", quantity=32,
                       position=(374.28, 1195.56, 383.28, 1204.56))

    assert len(offers_for(elsewhere, _manifest(COLUMNS), "Crow", declined)) == 1


def test_recording_the_same_decline_twice_adds_nothing():
    record = _marks()
    once = record_decline((), "Crow", record, "Columns")

    assert record_decline(once, "Crow", record, "Columns") == once
    assert once == (decline_key("Crow", record, "Columns"),)


# ---------------------------------------------------------------------------
# 6. No manifest, no offers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("manifest", [None, [], {}])
def test_a_run_with_no_manifest_raises_no_offers_at_all(manifest):
    assert naming_offers([_marks(), _marks(candidate_id="SYM-7")], manifest) == ()


def test_an_empty_loaded_manifest_raises_no_offers(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]")

    assert naming_offers([_marks()], load_manifest(str(empty))) == ()


def test_a_loaded_manifest_object_is_accepted_as_it_comes_off_disk():
    """`load_manifest` returns ManifestEntry objects; fixtures are dicts."""
    loaded = load_manifest(str(CROW_MANIFEST))

    offers = offers_for(_marks(), loaded)

    assert [o.manifest_name for o in offers] == [
        "Bollards", "Columns-H-35'", "Ladder-H-20'", "Lift", "Mobilization",
        "Stairs",
    ]


# ---------------------------------------------------------------------------
# 7. 29-10's refusal is untouched — the bar moved, it did not come down
# ---------------------------------------------------------------------------


def test_unnamed_geometry_still_never_resolves_however_many_offers_exist():
    need = Need(
        kind=NEED_UNNAMED_GEOMETRY,
        subject="SYM-6",
        wanted="a name for 36 measured mark(s)",
        asked_by_sheet="A-101",
        evidence_text="36 repeated marks were measured",
        blocking_item="SYM-6",
    )

    resolution = resolve_need(need, [], lambda s: s.strip().lower())

    assert resolution.status == OPEN
    assert "coincidence" in resolution.reason
    # And the offers for the same cluster exist alongside it.
    assert len(offers_for(_marks(), _manifest(COLUMNS, BOLLARDS))) == 2


# ---------------------------------------------------------------------------
# 8. An offer publishes NOTHING — the test that protects every existing report
# ---------------------------------------------------------------------------


def _authored_rows():
    return [
        {"item": "Doors - Hollow Metal", "quantity": 29.0, "unit": "EA",
         "source": "plan_schedule_legend", "status": ITEM_MEASURED,
         "needs_review": False, "source_sheets": ["A-601"]},
        {"item": "CMU Wall", "quantity": 1240.0, "unit": "SF",
         "source": "geometry", "status": ITEM_MEASURED,
         "needs_review": False, "source_sheets": ["A-101"]},
    ]


def _finished_run(tmp_path, name):
    run = tmp_path / name
    run.mkdir()
    summary = run / "summary.txt"
    summary.write_text("TAKEOFF SUMMARY\nDoors - Hollow Metal   29 EA\n")
    report = {
        "takeoff_summary": _authored_rows(),
        "coverage": {"items_measured": 2, "items_not_measured": 1,
                     "coverage_pct": 66.7},
        "unnamed_geometry": [_marks(), _marks(candidate_id="SYM-7", quantity=32,
                                              position=(374.28, 1195.56,
                                                        383.28, 1204.56))],
        "_files": {"run_folder": str(run), "summary_txt": str(summary)},
    }
    return report, run, summary


#: The keys an offer may never touch. Everything a client bids from.
_TAKEOFF_KEYS = ("takeoff_summary", "coverage", "unnamed_geometry")


def test_the_takeoff_is_byte_identical_with_offers_present_and_absent(tmp_path):
    pages = [{"sheet_name": "A-101", "page_index": 0,
              "full_page_text": "1. ALL WORK SHALL COMPLY WITH CODE.\n"}]

    without_report, without_run, without_summary = _finished_run(tmp_path, "a")
    without = run_evidence_pass(without_report, pages, all_extracted=[],
                                missing_sheets=[])

    with_report, with_run, with_summary = _finished_run(tmp_path, "b")
    with_offers = run_evidence_pass(
        with_report, pages, all_extracted=[], missing_sheets=[],
        manifest=_manifest(COLUMNS, BOLLARDS), project_key="Crow",
    )

    # The offers were really raised — without this the equality below is vacuous.
    assert len(with_offers["naming_offers"]["offers"]) == 4
    assert "naming_offers" not in without

    for key in _TAKEOFF_KEYS:
        assert json.dumps(with_report[key], sort_keys=True) == \
            json.dumps(without_report[key], sort_keys=True)
    # No quantity, no review flag, no name anywhere in the published rows moved.
    assert with_report["takeoff_summary"] == _authored_rows()
    assert all(not row.get("needs_review")
               for row in with_report["takeoff_summary"])
    assert "Columns" not in json.dumps(with_report["takeoff_summary"])
    # The gaps report itself is identical too, apart from the added question.
    stripped = {k: v for k, v in with_report["input_gaps"].items()
                if k != "naming_offers"}
    assert json.dumps(stripped, sort_keys=True) == \
        json.dumps(without_report["input_gaps"], sort_keys=True)
    # summary.txt says the same thing in both runs: an offer is not a finding.
    assert with_summary.read_text() == without_summary.read_text()


def test_an_offered_cluster_is_still_an_open_unmet_need(tmp_path):
    """The offer is BESIDE the refusal, not instead of it."""
    report, _run, _summary = _finished_run(tmp_path, "c")

    gaps = run_evidence_pass(
        report, pages=[], all_extracted=[], missing_sheets=[],
        manifest=_manifest(COLUMNS), project_key="Crow",
    )

    assert gaps["naming_offers"]["candidates_offered"] == 2
    open_kinds = [n["kind"] for n in gaps["open_needs"]]
    assert open_kinds == [NEED_UNNAMED_GEOMETRY, NEED_UNNAMED_GEOMETRY]
    assert all(n["status"] == "NOT MEASURED" for n in gaps["open_needs"])


def test_the_offers_reach_the_published_gaps_artifact(tmp_path):
    report, run, _summary = _finished_run(tmp_path, "d")

    run_evidence_pass(
        report, pages=[], all_extracted=[], missing_sheets=[],
        manifest=_manifest(COLUMNS), project_key="Crow",
    )

    published = json.loads((run / "input_gaps.json").read_text())
    assert [o["manifest_name"] for o in published["naming_offers"]["offers"]] \
        == ["Columns", "Columns"]
    assert published["naming_offers"]["candidates_seen"] == 2


def test_existing_callers_that_pass_no_manifest_are_unchanged(tmp_path):
    """The production call site passes four positional arguments and no more."""
    report, _run, _summary = _finished_run(tmp_path, "e")
    before = copy.deepcopy(report)

    gaps = run_evidence_pass(report, [], [], [])

    assert "naming_offers" not in gaps
    for key in _TAKEOFF_KEYS:
        assert report[key] == before[key]


# ---------------------------------------------------------------------------
# 9. Accepting: a name from the human, never a measurement from the app
# ---------------------------------------------------------------------------


def test_accepting_an_offer_names_the_row_as_human_input_never_measured():
    offer = offers_for(_marks(), _manifest(COLUMNS))[0]

    row = accept_offer(offer)

    assert row["item"] == "Columns"
    assert provenance_of_row(row) == ITEM_HUMAN_INPUT
    assert provenance_of_row(row) != ITEM_MEASURED
    # The count is carried through untouched: accepting a NAME never restates a
    # number, and nothing about the number was ever in question.
    assert (row["quantity"], row["unit"]) == (36.0, "EA")
    assert row["candidate_id"] == "SYM-6"
    assert "estimator" in row["naming_provenance"]


def test_accepting_is_pure_and_leaves_the_record_alone():
    record = _marks()
    before = copy.deepcopy(record)

    accept_offer(offers_for(record, _manifest(COLUMNS))[0])

    assert record == before


# ---------------------------------------------------------------------------
# 10. The measured run this plan is sized against
# ---------------------------------------------------------------------------


def _paid_unnamed_geometry():
    if not PAID_RUN.is_file():
        pytest.skip("paid run artifact not present (output/ is gitignored)")
    return json.loads(PAID_RUN.read_text())["unnamed_geometry"]


def test_the_real_run_with_its_own_project_manifest_asks_a_readable_question():
    """Crow's own 10-entry manifest: 33 of 39 clusters get a short list."""
    records = _paid_unnamed_geometry()
    assert len(records) == 39

    report = offers_report(records, load_manifest(str(CROW_MANIFEST)),
                           project_key="Crow")

    assert report["candidates_offered"] == 33
    assert report["candidates_with_no_eligible_entry"] == 6  # LF walls
    assert report["candidates_suppressed"] == []
    per_cluster = {}
    for offer in report["offers"]:
        per_cluster[offer["candidate_id"]] = \
            per_cluster.get(offer["candidate_id"], 0) + 1
    assert max(per_cluster.values()) <= MAX_OFFERS_PER_CANDIDATE
    assert len(report["offers"]) == 186


def test_the_real_run_with_a_generic_catalogue_asks_nothing_at_all():
    """91 generic entries — 50 of them EA/count — discriminate nothing.

    Uncapped this is 1,584 equally-grounded questions over 39 clusters. The cap
    withholds every one of them and says so, which is the honest answer: a
    catalogue that lists 50 possible count items is not a project vocabulary,
    and no question posed from it is answerable.
    """
    records = _paid_unnamed_geometry()

    report = offers_report(records, load_manifest(str(GENERIC_MANIFEST)),
                           project_key="Crow")

    assert report["offers"] == []
    assert len(report["candidates_suppressed"]) == 39
    assert sum(c["eligible_entries"] for c in report["candidates_suppressed"]) \
        == 1584


def test_the_real_sym_6_and_sym_7_offers_read_as_questions():
    records = _paid_unnamed_geometry()
    manifest = load_manifest(str(CROW_MANIFEST))
    by_id = {r["candidate_id"]: r for r in records}

    six = offers_for(by_id["SYM-6"], manifest, "Crow")
    seven = offers_for(by_id["SYM-7"], manifest, "Crow")

    assert six[1].why == (
        "36 counted marks on A-101; your manifest lists Columns-H-35' as "
        "EA/count. Matching unit and measure basis is the ONLY thing that "
        "produced this question — nothing on the sheet names these marks. "
        "Confirm only if that is what these are."
    )
    assert seven[0].why == (
        "32 counted marks on A-101; your manifest lists Bollards as EA/count. "
        "Matching unit and measure basis is the ONLY thing that produced this "
        "question — nothing on the sheet names these marks. Confirm only if "
        "that is what these are."
    )
    # SYM-7's only text is the drafting noise 'A-101'; it changes nothing.
    assert by_id["SYM-7"]["evidence_texts"] == ["A-101"]
    assert len(seven) == 6
