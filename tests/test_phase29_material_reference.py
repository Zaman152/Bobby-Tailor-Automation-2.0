"""29-09 — a material word NAMED is not a material wall BUILT.

`wall_material_from_text` matched a material anywhere in a note, so Bob's
page-4 KEYED NOTES entry 07 —

    NEW 4'-0"H x 4"D BLACK SUNBRELLA FABRIC AWNING OVER 1"x1" BLACK POWDER
    COATED ALUM. FRAME. DO NOT INSTALL TO THE STOREFRONT SYSTEM/GLAZING
    MULLIONS.

— an AWNING note, anchored "Storefront". Keynote 07 is placed six times on
FRONT ELEVATION NEW, so with the full note text available the facade tally
became Storefront 13 / CMU Wall 12 and the whole 6,245.2 SF gross renamed
itself from CMU Wall to Storefront.

The defect is dormant today only because the legend reader truncates a wrapped
note to its first line, which never reaches the word STOREFRONT. That makes
this a bug one fix (29-07) away from firing, and it is why 29-07 could not
land: two separate attempts at the wrapped-text reader were blamed for a
regression that was never theirs.

THE RULE IS MEASURED, NOT INVENTED. Over every material mention on all four
plan sets in uploads/, 18 of 68 sit behind NOT / MATCH / MATCHING, and every
one of those 18 is a reference rather than a subject. Cue-to-material token
distances are 1 (x14), 2 (x1) and 4 (x3) with nothing beyond, so the window is
4 — the widest measured case being "DO NOT INSTALL TO THE STOREFRONT".

Free: reads only strings. No API, no fixtures, no paid marker.
"""
from __future__ import annotations

import pytest

from bobbytailor.deterministic.component_library import wall_material_from_text

#: Verbatim from Bob's page 4, the note that renames the facade.
BOBS_NOTE_07 = (
    'NEW 4\'-0"H x 4"D BLACK SUNBRELLA FABRIC AWNING OVER 1"x1" BLACK POWDER '
    'COATED ALUM. FRAME. DO NOT INSTALL TO THE STOREFRONT SYSTEM/GLAZING '
    'MULLIONS.'
)


# ── the defect ───────────────────────────────────────────────────────────────


def test_a_prohibition_does_not_anchor_the_thing_it_prohibits():
    """THE case: an awning note that mentions storefront only to forbid it."""
    assert wall_material_from_text(BOBS_NOTE_07) is None


def test_the_neighbouring_awning_note_is_also_not_a_wall():
    assert wall_material_from_text(
        "NEW METAL BROW AWNING FROM 4 FRONT ENGINEERED SOLUTIONS OVER"
    ) is None


@pytest.mark.parametrize("note", [
    '42" HIGH STEEL GUARDRAIL, FINISH TO MATCH STOREFRONT',
    "DECORATIVE LINEAR WALL LIGHTING LOUVER, MATCH STOREFRONT / WINDOW FRAME",
    "PREFAB ALUMINUM CANOPY, FINISH TO MATCH STOREFRONT",
    "METAL COPING, MATCH STOREFRONT / WINDOW FRAME",
])
def test_a_finish_reference_does_not_anchor_the_material(note):
    """Moxy KEYNOTES 9/10/11/15 — a guardrail finished LIKE storefront is not
    storefront. Four notes, three placements each, on the only Moxy legends
    that feed facade materials."""
    assert wall_material_from_text(note) is None


def test_paint_flashing_matching_a_wall_is_not_that_wall():
    assert wall_material_from_text(
        "PAINT FLASHING TO MATCH EX. SPLIT FACE CMU"
    ) is None


# ── what must NOT move ───────────────────────────────────────────────────────


def test_one_uncued_occurrence_still_anchors_the_material():
    """PER OCCURRENCE, not per note — the distinction this rule turns on.

    Bob's names CMU twice in one note: once as the subject, and once four
    tokens behind a MATCH. It IS a CMU note, and a per-note rule would refuse
    it. This assertion fails against a rule that gives up on the whole string
    as soon as any occurrence is cued.
    """
    assert wall_material_from_text(
        "INFILL WITH CMU TO MATCH EXISTING. TOOTH IN CMU"
    ) == "CMU Wall"


def test_the_demolition_note_still_anchors_cmu():
    """Bob's excluded FRONT ELEVATION DEMOLITION note 02, which gains CMU x6
    once the reader stops truncating. It is genuinely about CMU."""
    assert wall_material_from_text(
        "REPAIR/REPLACE EXISTING CMU AS REQUIRED."
    ) == "CMU Wall"


@pytest.mark.parametrize("note,expected", [
    ("ALUMINUM STOREFRONT/CURTAIN WALL", "Storefront"),
    ("NEW SPLIT FACE CMU AT BASE OF ALL EX. MASONRY", "CMU Wall"),
    ('8" CMU WALL', "CMU Wall"),
    ("EIFS SYSTEM OVER SHEATHING", "EIFS Wall"),
    ("SITE CAST CONCRETE PANEL", "Tilt Up Wall"),
])
def test_an_uncued_mention_is_unaffected(note, expected):
    assert wall_material_from_text(note) == expected


def test_a_note_naming_no_material_still_anchors_nothing():
    assert wall_material_from_text("NEW WALL SCONCE AT 8'-0\" AFF") is None
    assert wall_material_from_text("") is None
    assert wall_material_from_text(None) is None


# ── the window is measured, and stays that way ───────────────────────────────


def test_the_cue_window_reaches_four_tokens_and_not_five():
    """4 is the measured maximum ("NOT INSTALL TO THE STOREFRONT"), so a cue
    five tokens back must NOT govern. Widening the window later would start
    refusing mentions no drawing in the corpus cues, and this pins that."""
    assert wall_material_from_text("MATCH A B C D STOREFRONT") == "Storefront"
    assert wall_material_from_text("MATCH A B C STOREFRONT") is None
