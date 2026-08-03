"""Layer-1 tests for the room-tag reader and the fail-closed unit-mix census.

The census exists to remove the single largest human input from the Moxy path,
so its failure mode is the thing worth testing hardest: a duplicated room number
must produce a REFUSAL, never a partial count.  A wrong unit multiplier is not a
wrong line item — it multiplies every per-unit quantity in the take-off at once
(threat T-23-18).

The four asserted unit counts were derived from the drawing before any
comparison was made, and they match ``docs/PIPELINE-GROUND-TRUTH.md``'s golden
multipliers 4 of 4.  Nothing here was tuned toward them: the pairing rule is the
set's own printed ``ROOM TAG / ROOM NAME / ROOM NUMBER`` legend.
"""
from __future__ import annotations

import os

import fitz
import pytest

from bobbytailor.deterministic.room_tags import (
    MAX_ROOM_NAME_CHARS,
    ROOM_TAG_MAX_GAP_PT,
    RoomMix,
    RoomTag,
    census_room_tags,
    derive_room_mix,
    extract_room_tags,
    is_room_name,
    is_room_number,
    normalise_room_name,
)

UPLOADS = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
MOXY = os.path.join(UPLOADS, "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf")

#: Moxy's stacked unit key plans, ID-001 and ID-002 (INV-05 §2 Key B).
MOXY_KEY_PLAN_PAGES = [7, 8]

#: The golden unit multipliers from ``docs/PIPELINE-GROUND-TRUTH.md``, keyed the
#: way the census keys them.  ID-413 QQ A 90, ID-407 KING A 26,
#: ID-411 KING SUITE B 2, ID-417 BUNK B 1.
MOXY_GOLDEN_MULTIPLIERS = {"qq a": 90, "king a": 26, "k suite b": 2, "bunk b": 1}

#: The door schedule's own bbox on Moxy page index 6, as
#: ``tables.extract_schedules`` reports it.  Transcribed rather than recomputed
#: because detecting it is ``test_schedule_extraction``'s job, not this file's,
#: and the whole-document ``find_tables`` scan costs minutes.
MOXY_DOOR_SCHEDULE_BBOX = (776.78, 185.70, 1882.99, 1288.20)

_needs_moxy = pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")


# ── Stubs: a page and a document exposing only what the reader touches ───────


class _StubPage:
    def __init__(self, records, number=0):
        self.number = number
        self._records = list(records)

    def get_text(self, kind):
        assert kind == "dict"
        return {
            "blocks": [
                {
                    "lines": [
                        {"bbox": bbox, "dir": text_dir, "spans": [{"text": text}]}
                        for text, bbox, text_dir in self._records
                    ]
                }
            ]
        }


class _StubDoc:
    def __init__(self, pages):
        self._pages = list(pages)
        self.page_count = len(self._pages)

    def __getitem__(self, index):
        return self._pages[index]


def _room_tag_records(name, number, dx=0.0, dy=0.0):
    """The MEASURED Moxy page-7 room-tag geometry, translated by (dx, dy)."""
    return [
        (name, (625.0 + dx, 1336.0 + dy, 636.7 + dx, 1369.4 + dy), (0.0, -1.0)),
        (number, (637.9 + dx, 1346.7 + dy, 649.6 + dx, 1358.5 + dy), (0.0, -1.0)),
    ]


# ── Vocabulary ───────────────────────────────────────────────────────────────


def test_room_number_shapes_are_the_ones_the_symbol_legend_prints():
    for good in ("204", "715", "T21", "L1", "G1"):
        assert is_room_number(good), good
    for bad in ("12", "1204", "204A", "", "QQ A", "T210"):
        assert not is_room_number(bad), bad


def test_a_room_name_is_alphabetic_and_is_not_itself_a_number():
    for good in ("KING A", "QQ A", "K SUITE B", "BUNK B", "STAIR 1", "MECH.", "ADA (RIS)"):
        assert is_room_name(good), good
    for bad in ("204", "T21", "", "07", "  "):
        assert not is_room_name(bad), bad


def test_prose_is_kept_out_by_length_not_by_a_word_list():
    """Room names are the drawing's vocabulary; a deny-list would be ours."""
    sentence = "ALL DIMENSIONS ARE TO FACE OF STUD UNLESS NOTED"
    assert len(sentence) > MAX_ROOM_NAME_CHARS
    assert not is_room_name(sentence)
    assert is_room_name("A" * MAX_ROOM_NAME_CHARS)
    assert not is_room_name("A" * (MAX_ROOM_NAME_CHARS + 1))


def test_the_census_key_collapses_whitespace_and_case():
    assert normalise_room_name("  K   SUITE  B ") == "k suite b"
    assert normalise_room_name("King A") == "king a"


# ── Reading a tag ────────────────────────────────────────────────────────────


def test_a_room_tag_is_read_from_a_name_over_a_number():
    page = _StubPage(_room_tag_records("KING A", "204"))
    tags = extract_room_tags(page, (), 7)
    assert [(t.name, t.number) for t in tags] == [("KING A", "204")]
    assert tags[0].page_index == 7
    assert tags[0].text_dir == (0, -1)
    assert tags[0].bbox_pt == pytest.approx((625.0, 1336.0, 649.6, 1369.4))


def test_a_number_too_far_from_its_name_is_not_that_room_s_number():
    records = _room_tag_records("KING A", "204")
    text, (x0, y0, x1, y1), d = records[1]
    records[1] = (text, (x0 + ROOM_TAG_MAX_GAP_PT + 2.0, y0,
                         x1 + ROOM_TAG_MAX_GAP_PT + 2.0, y1), d)
    assert extract_room_tags(_StubPage(records), (), 7) == []


def test_a_name_and_number_pair_inside_a_mask_yields_no_tag():
    page = _StubPage(_room_tag_records("KING A", "204"))
    assert len(extract_room_tags(page, (), 7)) == 1
    mask = (600.0, 1300.0, 700.0, 1400.0)
    assert extract_room_tags(page, [mask], 7) == []
    assert len(extract_room_tags(page, [(0.0, 0.0, 10.0, 10.0)], 7)) == 1


def test_extraction_survives_a_page_whose_text_layer_raises():
    class _Hostile:
        number = 0

        def get_text(self, _kind):
            raise RuntimeError("corrupt content stream")

    assert extract_room_tags(_Hostile(), (), 0) == []


# ── The census: uniqueness, and the refusal ─────────────────────────────────


def test_a_duplicated_room_number_refuses_rather_than_counting_partially():
    """The synthetic two-page overlap INV-05 risk 4 describes."""
    page = _StubPage(_room_tag_records("KING A", "204"))
    doc = _StubDoc([page, _StubPage(_room_tag_records("KING A", "204"), number=1)])
    mix = derive_room_mix(doc)
    assert mix.refused is True
    assert mix.counts == {}, "a partial census is not an acceptable fallback"
    assert mix.duplicate_numbers == ("204",)
    assert "204" in mix.reason
    assert mix.total_tags == 2 and mix.distinct_numbers == 1


def test_a_refusal_is_distinguishable_from_a_set_with_no_room_tags():
    """Threat T-23-20: silence and refusal must not look the same."""
    empty = derive_room_mix(_StubDoc([_StubPage([])]))
    assert empty.counts == {} and empty.refused is False
    assert empty.duplicate_numbers == () and empty.reason == ""

    refused = census_room_tags(
        [
            RoomTag(name="KING A", number="204", bbox_pt=(0, 0, 1, 1)),
            RoomTag(name="QQ A", number="204", bbox_pt=(0, 0, 1, 1)),
        ]
    )
    assert refused.counts == {} and refused.refused is True
    assert refused.duplicate_numbers == ("204",)


def test_a_clean_census_counts_by_normalised_name():
    mix = census_room_tags(
        [
            RoomTag(name="KING A", number="204", bbox_pt=(0, 0, 1, 1)),
            RoomTag(name="king  a", number="304", bbox_pt=(0, 0, 1, 1)),
            RoomTag(name="QQ A", number="206", bbox_pt=(0, 0, 1, 1)),
        ]
    )
    assert mix.refused is False
    assert mix.counts == {"king a": 2, "qq a": 1}
    assert mix.total_tags == 3 and mix.distinct_numbers == 3


def test_the_refusal_reason_names_at_most_ten_numbers_but_reports_the_count():
    tags = []
    for i in range(12):
        number = "%03d" % (200 + i)
        tags.append(RoomTag(name="QQ A", number=number, bbox_pt=(0, 0, 1, 1)))
        tags.append(RoomTag(name="QQ A", number=number, bbox_pt=(0, 0, 1, 1)))
    mix = census_room_tags(tags)
    assert len(mix.duplicate_numbers) == 12
    assert "12 number(s)" in mix.reason
    assert "2 more" in mix.reason


def test_room_mix_is_serialisable():
    mix = RoomMix(counts={"qq a": 90}, total_tags=1)
    assert mix.to_dict()["counts"] == {"qq a": 90}


# ── The real key plans ───────────────────────────────────────────────────────


@_needs_moxy
def test_moxy_key_plan_census_has_no_duplicate_room_numbers():
    doc = fitz.open(MOXY)
    try:
        mix = derive_room_mix(doc, pages=MOXY_KEY_PLAN_PAGES)
    finally:
        doc.close()
    assert mix.refused is False
    assert mix.duplicate_numbers == ()
    assert mix.total_tags == 214
    assert mix.distinct_numbers == 214


@_needs_moxy
def test_moxy_unit_multipliers_are_recovered_from_the_drawings():
    """The claim that this number needs a human is false, and here is why.

    Four unit types, four exact matches, read from the plan's own room tags with
    no manifest, no human input and no API call.
    """
    doc = fitz.open(MOXY)
    try:
        mix = derive_room_mix(doc, pages=MOXY_KEY_PLAN_PAGES)
    finally:
        doc.close()
    for name, expected in MOXY_GOLDEN_MULTIPLIERS.items():
        assert mix.counts.get(name) == expected, name


@_needs_moxy
def test_the_key_plan_tags_are_rotated_which_is_why_the_axis_must_be_generic():
    doc = fitz.open(MOXY)
    try:
        tags = extract_room_tags(doc[7], (), 7)
    finally:
        doc.close()
    assert tags
    assert {t.text_dir for t in tags} == {(0, -1)}


@_needs_moxy
def test_the_whole_document_refuses_because_sheets_genuinely_repeat_rooms():
    """The fail-closed path, on real data rather than a synthetic.

    Moxy draws the same rooms on its key plans and again on its floor plans, so
    a whole-document census would count them twice.  ``derive_room_mix`` cannot
    tell a repeat from a re-use, so it refuses — and the caller scopes the
    census to the key plans instead.
    """
    doc = fitz.open(MOXY)
    try:
        mix = derive_room_mix(doc)
    finally:
        doc.close()
    assert mix.refused is True
    assert mix.counts == {}
    # Rooms that appear on both a key plan and a floor plan — genuine repeats,
    # not artefacts of an unmasked schedule sheet.
    assert {"101", "103", "113", "118"}.issubset(set(mix.duplicate_numbers))


@_needs_moxy
def test_the_door_schedule_sheet_holds_no_rooms_once_its_table_is_masked():
    """Without the mask the door-schedule sheet invents two rooms."""
    doc = fitz.open(MOXY)
    try:
        unmasked = extract_room_tags(doc[6], (), 6)
        masked = extract_room_tags(doc[6], [MOXY_DOOR_SCHEDULE_BBOX], 6)
    finally:
        doc.close()
    invented = {("LEVEL 01 LOWER", "003"), ("LEVEL 07", "715")}
    assert invented.issubset({(t.name, t.number) for t in unmasked})
    assert invented.isdisjoint({(t.name, t.number) for t in masked})
    assert len(masked) < len(unmasked)


# ── One projection helper, not two ──────────────────────────────────────────


def test_no_consumer_grows_its_own_copy_of_the_projection():
    """The must-have SP-6 exists to satisfy: ONE helper, three consumers.

    Two copies would satisfy today's assertions and diverge the first time a
    fifth text orientation or a tighter gap is needed — which is exactly how
    the rotated-only reader that lost pages 18-20 came to exist.
    """
    import inspect

    from bobbytailor.deterministic import finish_tags, room_tags, tag_pairing

    for module in (finish_tags, room_tags):
        source = inspect.getsource(module)
        assert "def project_bbox" not in source, module.__name__
        assert "def pair_two_token_tags" not in source, module.__name__
        assert "from bobbytailor.deterministic.tag_pairing import" in source
        # And the objects they use are literally the shared ones.
        assert module.pair_two_token_tags is tag_pairing.pair_two_token_tags
