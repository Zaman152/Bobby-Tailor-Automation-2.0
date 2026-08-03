"""Deterministic room-tag reader and the fail-closed unit-mix census.

**The long-standing claim that the unit multiplier is unrecoverable from the
drawings is FALSE.**  ``pipeline/takeoff_pipeline.py::_manifest_room_mix``
states in its docstring that a repeat count is "routinely not in the drawing set
at all … so no reading of the plan can recover it", and
``docs/PIPELINE-GROUND-TRUTH.md`` records the same claim as "BLOCKER A".

Moxy's pages 7 and 8 (ID-001 / ID-002) are stacked unit key plans carrying 214
room tags with 214 distinct room numbers and no duplicates.  Counting them blind
— before any comparison was made — yields ``QQ A 90``, ``KING A 26``,
``K SUITE B 2``, ``BUNK B 1``, a 4/4 exact match against the golden multipliers
(INV-05 §2 Key B).  The multiplier is in the input.  The pipeline docstring was
corrected in plan 23-08, which also wired :func:`resolve_room_mix` into the
pipeline; correcting the ground-truth document is plan 23-16 (decision D-01).

The convention is the drawing's, not ours
-----------------------------------------
Take-off page 2 (CS-02) prints this set's own symbol legend verbatim:
``ROOM TAG / ROOM NAME / ROOM NUMBER``.  A room tag is therefore a name line
with a number line beneath it — beneath in the text's own advance direction,
which on these rotated sheets is +x on the page.  That is why the pairing goes
through ``tag_pairing.pair_two_token_tags(..., axis=ACROSS)`` and not through a
second copy of the geometry.

Why the census must fail closed
-------------------------------
Every guestroom quantity in the take-off is a per-prototype area multiplied by a
unit count, so a census that double-counts multiplies the error into Gyp
Ceiling, Gyp Wall, Guestroom-Wall Covering and Doors at once (threat T-23-18).
Moxy's key plans happen to number levels 2-7 uniquely.  A set drawn with
per-floor key plans would repeat ``101`` on every floor, and a census that
quietly counted it once — or twice — would be a guess.  :func:`derive_room_mix`
therefore REFUSES on any duplicated number: it returns an empty mapping plus a
flag naming the duplicates, never a partial count (INV-05 risk 4).

Precedence, and why the manifest is kept (D-10)
-----------------------------------------------
:func:`resolve_room_mix` merges the census with the estimator's manifest under
the precedence 23-CONTEXT resolution 3 locks: **the in-plan census WINS wherever
it has a count for a name**, the manifest fills only the names the census does
not cover, and where both carry a count and they DISAGREE the census value is
used *and the disagreement is flagged naming both numbers and both sources*.
Nothing is silently overwritten in either direction, and
``human_inputs/*.json`` is never edited — a wrong human number is surfaced, not
corrected behind the estimator's back.

Every published count therefore carries a SOURCE
(:data:`UNIT_COUNT_SOURCE_CENSUS` / :data:`UNIT_COUNT_SOURCE_MANIFEST` /
:data:`UNIT_COUNT_SOURCE_ASSUMED`), which is threat T-23-32: a count that
silently switches provenance between runs is unauditable.

This module stays a PURE EXTRACTOR: no pipeline import, no fusion import, no
bundle key.  Choosing WHICH sheets are unit key plans, and calling the resolver,
is the pipeline's job (plan 23-08).
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.tag_pairing import (
    ACROSS,
    TagLine,
    bbox_inside_any,
    normalise_text,
    page_tag_lines,
    pair_two_token_tags,
    union_bbox,
)

logger = logging.getLogger(__name__)

#: A room number: three digits (``204``), or a discipline letter with one or two
#: digits (``T21`` for a stair, ``L1`` for a lobby core).  This is the shape the
#: set's own ROOM TAG legend prints.
ROOM_NUMBER_RE = re.compile(r"^(?:\d{3}|[A-Z]\d{1,2})$")

#: A room name: begins with a letter and holds only the characters a drawn room
#: label uses.  Prose is excluded by :data:`MAX_ROOM_NAME_CHARS` rather than by a
#: word list, because room names are the drawing's vocabulary, not ours.
ROOM_NAME_RE = re.compile(r"^[A-Z][A-Z0-9 .&()'/-]*$")

#: Longest accepted room name.  The longest observed on Moxy's key plans is
#: ``VALET HANGER`` at 12 characters; 24 leaves generous room for a compound
#: name while keeping a sentence of general notes out of the census.
MAX_ROOM_NAME_CHARS = 24

#: Largest advance-axis gap between a room tag's two lines, in points.  Pinned
#: from measurement: across every Moxy sheet the observed gap between the name
#: line and the number line runs 1.12 pt to 3.57 pt, because the two lines are
#: drawn as one symbol and set solid.  6.0 pt is under half the observed line
#: extent (11.7 pt), which is the geometric reason it is safe — a line belonging
#: to the text block below cannot reach into the window without first colliding
#: with its own block.  It is a different constant from the material tag's
#: 16.0 pt because it measures a different axis, not because it was relaxed.
ROOM_TAG_MAX_GAP_PT = 6.0

#: Overlap tolerance on the reading axis.  A room number is drawn centred under
#: its name, so the two lines overlap substantially; 3.0 pt only absorbs the
#: case where a long name is set slightly off-centre.
ROOM_TAG_PERP_TOL_PT = 3.0


@dataclass(frozen=True)
class RoomTag:
    """One ``ROOM NAME`` / ``ROOM NUMBER`` tag read from a plan."""

    name: str                                    # "KING A" — normalised
    number: str                                  # "204" — exactly as printed
    bbox_pt: Tuple[float, float, float, float]   # union of the two line boxes
    page_index: int = 0
    text_dir: Tuple[int, int] = (1, 0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RoomMix:
    """The result of a room-tag census, including its refusal.

    ``refused`` is the whole point: an empty ``counts`` with ``refused=True`` and
    a populated ``duplicate_numbers`` is a REFUSAL, and an empty ``counts`` with
    ``refused=False`` means the drawing set carries no room tags at all.  Threat
    T-23-20 is exactly that those two states must be distinguishable.
    """

    counts: Dict[str, int] = field(default_factory=dict)
    total_tags: int = 0
    distinct_numbers: int = 0
    duplicate_numbers: Tuple[str, ...] = ()
    pages_censused: Tuple[int, ...] = ()
    refused: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def is_room_name(text: str) -> bool:
    """True for an alphabetic room label that is not itself a number."""
    t = normalise_text(text)
    if not t or len(t) > MAX_ROOM_NAME_CHARS:
        return False
    if ROOM_NUMBER_RE.match(t):
        return False
    if not ROOM_NAME_RE.match(t):
        return False
    return any(c.isalpha() for c in t)


def is_room_number(text: str) -> bool:
    """True for the room-number shape the set's own symbol legend prints."""
    return bool(ROOM_NUMBER_RE.match(normalise_text(text)))


def normalise_room_name(name: str) -> str:
    """The census key: whitespace-collapsed, lower case."""
    return " ".join(str(name or "").split()).strip().lower()


def extract_room_tags(
    page,
    mask_rects: Sequence = (),
    page_index: Optional[int] = None,
    max_gap_pt: float = ROOM_TAG_MAX_GAP_PT,
    perp_tol_pt: float = ROOM_TAG_PERP_TOL_PT,
) -> List[RoomTag]:
    """Every ``ROOM NAME`` / ``ROOM NUMBER`` tag on *page*, in document order.

    ``mask_rects`` carry the same obligation they carry for material tags: a
    door-schedule tag column reads exactly like a plan-body room tag.  On Moxy
    page index 6 — the door-schedule sheet, which holds no rooms at all — the
    unmasked reader pairs ``LEVEL 01 LOWER`` with ``003`` and ``LEVEL 07`` with
    ``715``, two rooms that do not exist.  Supplying the door schedule's own
    bbox from ``tables.extract_schedules`` removes them along with every other
    tag drawn inside the table (measured: 5 tags on that sheet become 1).
    """
    lines: List[TagLine] = page_tag_lines(page, page_index)
    pairs = pair_two_token_tags(
        lines,
        is_room_name,
        is_room_number,
        max_gap_pt=max_gap_pt,
        perp_tol_pt=perp_tol_pt,
        axis=ACROSS,
    )
    out: List[RoomTag] = []
    for name_line, number_line in pairs:
        bbox = union_bbox(name_line.bbox_pt, number_line.bbox_pt)
        if bbox_inside_any(bbox, mask_rects):
            continue
        out.append(
            RoomTag(
                name=normalise_text(name_line.text),
                number=normalise_text(number_line.text),
                bbox_pt=bbox,
                page_index=name_line.page_index,
                text_dir=name_line.text_dir,
            )
        )
    return out


def census_room_tags(tags: Sequence[RoomTag], pages: Sequence[int] = ()) -> RoomMix:
    """Turn a bag of room tags into a unit mix, or into a refusal.

    The uniqueness gate is the contract: a room number identifies a room, so a
    number appearing twice means the censused sheets overlap and the count would
    be inflated.  There is no partial answer for that case — the mapping comes
    back empty with the offending numbers named.
    """
    seen: Dict[str, List[str]] = {}
    counts: Dict[str, int] = {}
    for tag in tags:
        seen.setdefault(tag.number, []).append(tag.name)
        key = normalise_room_name(tag.name)
        counts[key] = counts.get(key, 0) + 1
    duplicates = tuple(sorted(n for n, names in seen.items() if len(names) > 1))
    if duplicates:
        shown = ", ".join(duplicates[:10])
        if len(duplicates) > 10:
            shown += ", … (%d more)" % (len(duplicates) - 10)
        return RoomMix(
            counts={},
            total_tags=len(tags),
            distinct_numbers=len(seen),
            duplicate_numbers=duplicates,
            pages_censused=tuple(pages),
            refused=True,
            reason=(
                "room numbers are not unique across the censused sheets, so the "
                "census would double-count: %d number(s) appear more than once "
                "(%s). No unit mix is published." % (len(duplicates), shown)
            ),
        )
    return RoomMix(
        counts=counts,
        total_tags=len(tags),
        distinct_numbers=len(seen),
        duplicate_numbers=(),
        pages_censused=tuple(pages),
        refused=False,
        reason="",
    )


def derive_room_mix(
    doc,
    pages: Optional[Sequence[int]] = None,
    mask_rects_by_page: Optional[Dict[int, Sequence]] = None,
) -> RoomMix:
    """Census the room tags of an open ``fitz.Document`` into a unit mix.

    ``pages`` restricts the census to the sheets that actually key the units.
    That restriction belongs to the CALLER, because deciding which sheet is a
    unit key plan is sheet classification, not tag reading — and because the
    whole-document default is the honest one: a set that draws the same room on
    a key plan and again on a floor plan does repeat its numbers, this function
    cannot tell a repeat from a re-use, and so it refuses.  On Moxy the whole
    document refuses and pages ``[7, 8]`` alone reproduce 4 of 4 golden unit
    multipliers.

    Never falls back to a partial census (threat T-23-18).
    """
    page_indices = (
        list(range(int(getattr(doc, "page_count", 0))))
        if pages is None
        else [int(p) for p in pages]
    )
    tags: List[RoomTag] = []
    for page_index in page_indices:
        try:
            page = doc[page_index]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Page %s unreadable: %s", page_index, exc)
            continue
        rects: Sequence = ()
        if mask_rects_by_page:
            rects = mask_rects_by_page.get(page_index, ())
        tags.extend(extract_room_tags(page, rects, page_index))
    return census_room_tags(tags, page_indices)


# ── Provenance of a published unit count (threat T-23-32) ────────────────────
#
# A count that cannot say where it came from is unauditable, and the whole point
# of the census is that a number the drawing contains must never require a
# human.  Exactly three answers are possible, and every published count carries
# one of them.

#: Counted from the room tags the drawing itself prints on its unit key plans.
UNIT_COUNT_SOURCE_CENSUS = "unit_tag_census"

#: Supplied by the estimator's manifest — a human input the drawings did not
#: confirm.  Retained as a cross-check, never as an override (D-10).
UNIT_COUNT_SOURCE_MANIFEST = "manifest"

#: No count exists at all, so the measured prototype stands for one unit.  This
#: is the value a CONSUMER reports when it finds no entry in the resolved mix;
#: :func:`resolve_room_mix` never publishes it, because publishing an assumed
#: count would be inventing a multiplier.
UNIT_COUNT_SOURCE_ASSUMED = "assumed"


@dataclass(frozen=True)
class RoomMixResolution:
    """The unit mix actually published, with the source of every count.

    ``counts`` is a LOOKUP TABLE, not a list of units: one count may appear
    under more than one key when the drawing abbreviates a name on its key plan
    (``K SUITE B``) and spells it out on the prototype sheet
    (``KING SUITE B``).  Consumers look a count up by whichever name their sheet
    prints, so both keys must resolve; summing ``counts.values()`` is therefore
    meaningless and no consumer does it.

    ``sources`` is keyed identically to ``counts`` and is never partial —
    a count with no source would defeat T-23-32.

    ``flags`` are the run-level disagreements (a refusal, a manifest that
    disagrees with the drawings); ``name_flags`` are the same statements keyed
    by the name they concern, so the row that USES a number can carry the
    reason it is doubted.
    """

    counts: Dict[str, int] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)
    name_flags: Dict[str, str] = field(default_factory=dict)
    flags: Tuple[str, ...] = ()
    census_refused: bool = False
    census_total_tags: int = 0
    pages_censused: Tuple[int, ...] = ()

    def source_of(self, name: str) -> str:
        """Provenance of *name*'s count — ``assumed`` when there is none."""
        return self.sources.get(normalise_room_name(name), UNIT_COUNT_SOURCE_ASSUMED)

    def to_dict(self) -> dict:
        return asdict(self)


def abbreviation_target(name: str, targets: Sequence[str]) -> Tuple[Optional[str], bool]:
    """The one full name *name* is a printed abbreviation of, and ambiguity.

    A drawing set abbreviates by TRUNCATION: Moxy's key plans tag a suite
    ``K SUITE B`` and its prototype sheet titles the same unit ``KING SUITE B``.
    The rule is therefore purely structural — same number of words, and every
    word of the short name is a prefix of the corresponding word of the long
    one.  It is not an expansion dictionary: nothing here knows that ``K``
    stands for ``KING``, and nothing may be added that does, because a
    substitution table is our vocabulary rather than the drawing's.

    It FAILS CLOSED.  ``('king a', 'king b')`` cannot merge (``b`` is not a
    prefix of ``a``), ``ada (ris)`` cannot reach ``ada king ris`` (two words
    against three), and when two full names both admit the abbreviation nothing
    is matched at all — the second element of the return is that ambiguity, so
    the caller can flag it rather than pick one.

    Returns ``(target, ambiguous)``; ``target`` is None when there is no unique
    match.  An exact match is not an abbreviation and returns None.
    """
    short = normalise_room_name(name).split()
    if not short:
        return None, False
    hits = set()
    for candidate in targets or ():
        full = normalise_room_name(candidate).split()
        if len(full) != len(short) or full == short:
            continue
        if all(a and b.startswith(a) for a, b in zip(short, full)):
            hits.add(" ".join(full))
    if len(hits) == 1:
        return hits.pop(), False
    return None, len(hits) > 1


def resolve_room_mix(
    manifest_counts: Optional[Dict[str, int]],
    census: Optional[RoomMix],
    alias_targets: Sequence[str] = (),
) -> RoomMixResolution:
    """Merge the in-plan census with the manifest under the D-10 precedence.

    The drawings outrank the manifest.  Where the census has a count for a name
    that count is published with :data:`UNIT_COUNT_SOURCE_CENSUS`; where the
    manifest disagrees, the census value still wins and a flag names BOTH
    numbers and BOTH sources.  Names the census does not cover fall back to the
    manifest, flagged as not derived from the drawings.  Where the census
    REFUSED — duplicate room numbers, so the sheets overlap — the manifest is
    used wholesale with the refusal named: a partial census is never published
    (threat T-23-18).

    ``alias_targets`` are the full names the drawing spells out elsewhere (its
    prototype plan titles, plus the manifest's own names).  A census key that is
    a printed abbreviation of exactly one of them publishes its count under that
    name too, flagged, so the prototype sheet can find it — see
    :func:`abbreviation_target`.

    Pure: it reads no PDF, edits no human input, and invents no count.
    """
    manifest_mix: Dict[str, int] = {}
    for raw_name, raw_count in (manifest_counts or {}).items():
        key = normalise_room_name(raw_name)
        try:
            value = int(raw_count)
        except (TypeError, ValueError):
            continue
        if key and value > 0:
            manifest_mix[key] = value

    counts: Dict[str, int] = {}
    sources: Dict[str, str] = {}
    name_flags: Dict[str, str] = {}
    flags: List[str] = []

    def _from_manifest(key: str, note: str) -> None:
        counts[key] = manifest_mix[key]
        sources[key] = UNIT_COUNT_SOURCE_MANIFEST
        name_flags[key] = note
        flags.append(note)

    # ── The census could not be taken, or refused ────────────────────────────
    if census is None or census.refused:
        if manifest_mix:
            if census is not None and census.refused:
                reason = (
                    "the in-plan unit-tag census REFUSED and no partial count was "
                    "used: %s Every unit count below therefore comes from the "
                    "human manifest (source %s) and none was derived from the "
                    "drawings." % (census.reason, UNIT_COUNT_SOURCE_MANIFEST)
                )
            else:
                reason = (
                    "no unit key plan was identified in this drawing set, so no "
                    "in-plan unit-tag census was taken. Every unit count below "
                    "comes from the human manifest (source %s) and none was "
                    "derived from the drawings." % UNIT_COUNT_SOURCE_MANIFEST
                )
            flags.append(reason)
            for key in sorted(manifest_mix):
                counts[key] = manifest_mix[key]
                sources[key] = UNIT_COUNT_SOURCE_MANIFEST
                name_flags[key] = reason
        return RoomMixResolution(
            counts=counts,
            sources=sources,
            name_flags=name_flags,
            flags=tuple(flags),
            census_refused=bool(census is not None and census.refused),
            census_total_tags=int(getattr(census, "total_tags", 0) or 0),
            pages_censused=tuple(getattr(census, "pages_censused", ()) or ()),
        )

    # ── The census has counts: it wins, and disagreement is flagged ──────────
    for key in sorted(census.counts):
        value = int(census.counts[key])
        counts[key] = value
        sources[key] = UNIT_COUNT_SOURCE_CENSUS
        declared = manifest_mix.get(key)
        if declared is not None and declared != value:
            note = (
                "unit count for %r DISAGREES between the drawings and the human "
                "input: the in-plan unit-tag census reads %d (source %s) and the "
                "manifest declares %d (source %s). The census value %d is "
                "published because a number the drawings contain outranks a "
                "human input; the manifest entry is retained as a cross-check "
                "and was NOT edited."
                % (key, value, UNIT_COUNT_SOURCE_CENSUS, declared,
                   UNIT_COUNT_SOURCE_MANIFEST, value)
            )
            name_flags[key] = note
            flags.append(note)

    # ── The same count under the name the prototype sheet spells out ─────────
    for key in sorted(census.counts):
        target, ambiguous = abbreviation_target(key, alias_targets)
        if ambiguous:
            note = (
                "the census name %r is a printed abbreviation of more than one "
                "full name in this set, so it was NOT matched to any of them and "
                "its count was published under %r alone." % (key, key)
            )
            flags.append(note)
            continue
        if not target or target in counts:
            continue
        value = int(census.counts[key])
        counts[target] = value
        sources[target] = UNIT_COUNT_SOURCE_CENSUS
        note = (
            "unit count %d for %r was read from the key plan's abbreviated tag "
            "%r (source %s); the two names were matched because every word of "
            "%r is a prefix of the corresponding word of %r, uniquely in this "
            "set." % (value, target, key, UNIT_COUNT_SOURCE_CENSUS, key, target)
        )
        declared = manifest_mix.get(target)
        if declared is not None and declared != value:
            note += (
                " It DISAGREES with the manifest, which declares %d (source %s); "
                "the census value is published and the manifest was NOT edited."
                % (declared, UNIT_COUNT_SOURCE_MANIFEST)
            )
        name_flags[target] = note
        flags.append(note)

    # ── The manifest fills only what the drawings never stated ───────────────
    for key in sorted(manifest_mix):
        if key in counts:
            continue
        _from_manifest(
            key,
            "unit count %d for %r is NOT derived from the drawings: the in-plan "
            "census carries no tag for that name, so the human manifest supplies "
            "it (source %s) and nothing in the drawing set confirms it."
            % (manifest_mix[key], key, UNIT_COUNT_SOURCE_MANIFEST),
        )

    return RoomMixResolution(
        counts=counts,
        sources=sources,
        name_flags=name_flags,
        flags=tuple(flags),
        census_refused=False,
        census_total_tags=int(census.total_tags),
        pages_censused=tuple(census.pages_censused or ()),
    )


if __name__ == "__main__":  # quick measurement harness (free, no API)
    import sys

    import fitz

    from bobbytailor.deterministic.tag_pairing import sheet_mask_rects

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    page_args = [a for a in sys.argv[1:] if a.startswith("--pages=")]
    only = None
    if page_args:
        only = [int(v) for v in page_args[-1].split("=", 1)[1].split(",") if v.strip()]
    paths = args or ["uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"]
    for path in paths:
        doc = fitz.open(path)
        masks = {
            i: sheet_mask_rects(doc[i])
            for i in (only if only is not None else range(doc.page_count))
        }
        mix = derive_room_mix(doc, pages=only, mask_rects_by_page=masks)
        per_page = {}
        for i in sorted(masks):
            n = len(extract_room_tags(doc[i], masks[i], i))
            if n:
                per_page[i] = n
        doc.close()
        print("\n=== %s pages=%s ===" % (path.split("/")[-1], only or "all"))
        print("  tags=%d distinct numbers=%d duplicates=%d"
              % (mix.total_tags, mix.distinct_numbers, len(mix.duplicate_numbers)))
        print("  per-page tag counts: %s" % per_page)
        if mix.refused:
            print("  REFUSED: %s" % mix.reason)
        else:
            for key in sorted(mix.counts, key=lambda k: (-mix.counts[k], k)):
                print("    %-20s %d" % (key, mix.counts[key]))
