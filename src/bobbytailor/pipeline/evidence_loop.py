"""The reasoning pass that spans SHEETS and repeats until it stops learning (29-10).

Everything upstream is extract -> fuse -> aggregate -> report: one direction, one
sheet at a time. A general note on A-101 and a door schedule on A-601 never meet,
so a quantity the drawing states plainly across two sheets is unreachable — and a
sheet the set CITES but does not CONTAIN is reported as a bare absent file name
rather than as the questions it would have answered.

This module is that missing pass, and it produces TWO outputs. The second matters
as much as the first:

1. answers assembled from evidence on ANOTHER sheet, each citing BOTH the sheet
   that asked and the sheet that answered, always DERIVED and never measured;
2. the INPUT GAPS report — every need the loop could not close, and every
   cited-but-absent sheet with the questions grouped UNDER it. "A-111 is missing"
   is a fact; "A-111 is missing and A-101 defers to it at 'SEE 1/A-111'" is an
   instruction the client can act on.

**Everything here is ADDITIVE.** The loop never writes into the take-off. It reads
assembled evidence and publishes its own artifact beside ``coverage.json``, which
is not a stylistic choice: a pass that could edit a measured quantity, rename a
row an authority already named, or raise a confidence would be able to undo any
guard upstream of it. 29-02 measured what one bypass costs — 136 personnel doors
published as galvanized frames because a naming tie broke on name length.

**Ambiguity refuses, always.** A need matching two candidate answers closes
UNRESOLVED naming both. There is no tie-break on score, length or order anywhere
in this file, because a tie-break is arbitration wearing the clothes of evidence.

**Matching is EXACT on the caller's own canonical key.** Never containment, never
similarity, never "the counts happen to be equal". A loop that guesses is worse
than no loop: it manufactures citations, and a wrong number wearing evidence is
harder to catch than a blank.

**Where the loop must refuse, it may still ASK** (29-11). Measured marks nothing
named stay unresolvable here forever — but the same record can be OFFERED to the
human against their own manifest. Publishing a name is a claim and only a claim
can be wrong; an offer is a question, and it is safe precisely because it changes
nothing. See :func:`offers_for`.

No extraction, no PDF re-read, no API, no I/O — except :func:`publish_input_gaps`,
which is the one impure function here and does nothing but write what the pure
ones computed.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

# The client status vocabulary is IMPORTED, never restated. A second flag shape
# for the same fact is how a report ends up with two disagreeing accounts of one
# gap — the exact defect INV-08 exists to prevent.
from bobbytailor.pipeline.coverage import (
    ITEM_HUMAN_INPUT,
    ITEM_NEEDS_REVIEW,
    ITEM_NOT_MEASURED,
)
from bobbytailor.pipeline.cross_references import sheet_ids_in_text
from bobbytailor.pipeline.derived_quantities import published_name, read_quantity_rules
# The manifest's OWN unit->measure map, imported rather than restated: an offer
# that disagreed with the manifest loader about what EA means would be eligible
# on a basis the entry itself does not have.
from bobbytailor.devtools.object_manifest import measure_from_unit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Need kinds — each one already produced somewhere in the run today. Nothing
# here invents a need; every one is collected from assembled evidence.
# ---------------------------------------------------------------------------
NEED_REFERENT_COUNT = "referent_count"      # a 29-06 rule whose referent nothing counted
NEED_ABSENT_SHEET = "absent_sheet"          # a sheet the set cites and does not contain
NEED_UNNAMED_GEOMETRY = "unnamed_geometry"  # measured marks with no name (24-04)
NEED_HYPOTHESIS_NAME = "hypothesis_name"    # a row whose NAME is an inference

NEED_KINDS = (
    NEED_REFERENT_COUNT,
    NEED_ABSENT_SHEET,
    NEED_UNNAMED_GEOMETRY,
    NEED_HYPOTHESIS_NAME,
)

# -- resolution outcomes ----------------------------------------------------
RESOLVED = "resolved"
#: Two or more candidate answers. The need is CLOSED and no number is published;
#: every candidate is named so a human picks in seconds. Never arbitrated.
UNRESOLVED_AMBIGUOUS = "unresolved_ambiguous"
OPEN = "open"

# -- where a piece of evidence came from ------------------------------------
SOURCE_SCHEDULE = "schedule"          # a row of a tabulated schedule/legend
SOURCE_COUNTED_ROW = "counted_row"    # a row this run published with a count
SOURCE_KEYNOTE = "keynote"            # keynote legend text
SOURCE_DERIVED = "derived_by_loop"    # an answer THIS loop assembled (round N)

#: Sources that count as the drawing having PRINTED a name. A derived answer is
#: deliberately absent: a name this loop assembled cannot then confirm someone
#: else's hypothesis, or the loop would be citing itself.
_PRINTED_SOURCES = frozenset({SOURCE_SCHEDULE, SOURCE_KEYNOTE})

#: Termination bound, stated rather than assumed. The open set shrinks strictly
#: every round (a need is closed or the round is the last), so the loop already
#: terminates in at most len(needs) rounds; this constant bounds a pathological
#: set as well and is LOGGED when hit, so "the loop stopped early" can never be
#: a silent fact. Measured over the four plan sets the deepest real chain is one
#: round — 4 is headroom, not a guess about the data.
MAX_ROUNDS = 4

#: How many consecutive text lines may be joined when looking for a quantity
#: rule. Crow general note 21 breaks mid-rule ("...PER DETAIL 9/A-002" /
#: "AT EACH PERSONNEL DOOR."), so a one-line window would miss it entirely; the
#: windows are tried SHORTEST FIRST so the note quoted back to the client is the
#: tightest one that still contains the whole rule.
_NOTE_WINDOW_LINES = 3


class Need(NamedTuple):
    """One question the assembled run raised and could not answer by itself.

    ``factor`` / ``factor_stated`` carry the multiplier a note PRINTED, and they
    exist for one reason: a derived number that silently drops "TWO BOLLARDS AT
    EACH ..." is off by 2x while looking exactly as confident. Where the note
    printed no multiplier the factor is 1 and ``factor_stated`` is False, so the
    published answer admits the assumption instead of presenting it as the
    drawing's word.
    """

    kind: str
    subject: str
    wanted: str
    asked_by_sheet: str
    evidence_text: str
    blocking_item: str
    factor: float = 1.0
    factor_stated: bool = False


class EvidenceItem(NamedTuple):
    """One fact some sheet of this run states, as the resolver may see it.

    Deliberately narrow. The resolver may read a name, a number, a unit and where
    it was printed — and nothing else. Handing it the whole bucket would let it
    start deciding on confidences and review flags, which is how a reasoning pass
    quietly becomes a second aggregator.
    """

    name: str
    quantity: Optional[float]
    unit: str
    sheet: str
    source: str
    text: str


class Resolution(NamedTuple):
    """What became of one need in the round that closed it."""

    need: Need
    status: str
    candidates: Tuple[EvidenceItem, ...]
    answered_by_sheet: str
    quantity: Optional[float]
    unit: str
    round_index: int
    reason: str


class LoopRun(NamedTuple):
    """The whole pass: what closed, what did not, and how it terminated.

    ``open_reasons`` is positional with ``open_needs``: the sentence the resolver
    gave the LAST time it looked at that need. An unmet need whose report cannot
    say why it is unmet is a status code, and the client cannot act on it.
    """

    resolutions: Tuple[Resolution, ...]
    open_needs: Tuple[Need, ...]
    rounds: int
    hit_max_rounds: bool
    evidence: Tuple[EvidenceItem, ...]
    open_reasons: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Collecting evidence
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _number(value: Any) -> Optional[float]:
    """A quantity, or None. A cell that is not a number is not a count of one."""
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _sheet_of(extracted: Dict[str, Any]) -> str:
    return _text(
        extracted.get("_sheet_name")
        or extracted.get("_source_sheet")
        or extracted.get("sheet_title")
    )


#: Schedule columns that hold the name of the thing, and the ones that hold how
#: many. Read in order, first hit wins — the same shape the door-schedule legend
#: emits (ITEM / DESCRIPTION / QTY / QUANTITY / UNIT).
_NAME_COLUMNS = ("ITEM", "NAME", "TYPE", "MARK", "DESCRIPTION")
_QTY_COLUMNS = ("QTY", "QUANTITY", "COUNT", "TOTAL")
_UNIT_COLUMNS = ("UNIT", "UOM", "UNITS")


def _column(row: Dict[str, Any], names: Sequence[str]) -> Any:
    upper = {str(k).strip().upper(): v for k, v in row.items()}
    for key in names:
        if upper.get(key) not in (None, ""):
            return upper[key]
    return None


def collect_evidence(
    all_extracted: Optional[Sequence[Dict[str, Any]]],
    takeoff_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Tuple[EvidenceItem, ...]:
    """Every named fact this run assembled, flattened and stamped with its sheet.

    This is the "across sheets" half of the pass: a schedule row on A-601 and a
    counted row from A-101 land in ONE list, which is the first time in the
    pipeline they are ever in the same place.
    """
    out: List[EvidenceItem] = []
    for extracted in all_extracted or []:
        if not isinstance(extracted, dict):
            continue
        sheet = _sheet_of(extracted)
        for sched in extracted.get("schedules") or []:
            if not isinstance(sched, dict):
                continue
            purpose = _text(sched.get("table_purpose")).lower()
            source = SOURCE_KEYNOTE if "keynote" in purpose else SOURCE_SCHEDULE
            for row in sched.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                name = _text(_column(row, _NAME_COLUMNS))
                if not name:
                    continue
                out.append(EvidenceItem(
                    name=name,
                    quantity=_number(_column(row, _QTY_COLUMNS)),
                    unit=_text(_column(row, _UNIT_COLUMNS)).upper(),
                    sheet=_text(sched.get("_source_sheet")) or sheet,
                    source=source,
                    text=_text(sched.get("name")) or name,
                ))
    for row in takeoff_rows or []:
        if not isinstance(row, dict):
            continue
        name = _text(row.get("item") or row.get("name"))
        quantity = _number(row.get("quantity"))
        if not name or quantity is None:
            continue
        sheets = [s for s in (row.get("source_sheets") or []) if _text(s)]
        out.append(EvidenceItem(
            name=name,
            quantity=quantity,
            unit=_text(row.get("unit")).upper(),
            sheet=_text(sheets[0]) if sheets else "",
            source=SOURCE_COUNTED_ROW,
            text=_text(row.get("item_type")),
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Collecting needs
# ---------------------------------------------------------------------------


def _note_windows(text: str) -> List[str]:
    """Bounded line windows of a sheet's text, WIDEST FIRST.

    A quantity rule is quoted back to the client verbatim, so the window has to
    be small enough to still read as a note — but it must be WIDE enough to hold
    the whole rule, and widest-first is not a stylistic preference. A rule split
    across a line break is read from the narrow window as a TRUNCATED clause:
    "...AT ALL EXTERIOR" / "DOORS" yields the referent "EXTERIOR", which is a
    referent the note never stated and which can then match a row. The widest
    window that contains the sentence stops at the sentence's own punctuation,
    so it reads what the note says.
    """
    lines = [ln.strip() for ln in str(text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    windows: List[str] = []
    for size in range(_NOTE_WINDOW_LINES, 0, -1):
        for start in range(0, max(len(lines) - size + 1, 0)):
            windows.append(" ".join(lines[start:start + size]))
    return windows


#: A numbered general note's own marker ("13. ", "21. ").
_NOTE_NUMBER = re.compile(r"\b\d{1,2}\.\s")


def _trim_quote(note_text: str, subject: str) -> str:
    """Drop the text BEFORE the note that stated the rule. Never edits it.

    The window that reads a rule reliably is wider than the rule (see
    ``_note_windows``), so the raw window can open in the middle of the previous
    note — Crow's note 21 arrives preceded by the tail of note 20, "...PPG1001-1
    DELICATE WHITE". Quoting that back makes the client read noise before the
    sentence that matters. Only leading text is removed, at a note number or a
    sentence end, so what remains is still verbatim.
    """
    text = _text(note_text)
    head = _text(subject).upper().split()
    if not head:
        return text
    cut = text.upper().find(head[0])
    if cut <= 0:
        return text
    starts = [m.start() for m in _NOTE_NUMBER.finditer(text[:cut])]
    if not starts:
        starts = [m.start() + 2 for m in re.finditer(r"\.\s", text[:cut])]
    return text[starts[-1]:].strip() if starts else text


def _citing_lines(text: str, sheet_id: str) -> List[str]:
    """Lines of *text* that cite *sheet_id* AND say something besides its name.

    A bare "A-111" is a drawing-reference bubble: it proves the citation but asks
    no question. "SEE 1/A-111" is the deferral — it is the thing that becomes a
    client instruction, so only lines carrying that surplus text are published as
    questions. The bare bubbles are still counted as citations by
    ``missing_referenced_sheets``; nothing is lost, only the noise is.
    """
    wanted = sheet_id.upper()
    out: List[str] = []
    for raw in str(text or "").splitlines():
        line = _text(raw)
        if not line or wanted not in line.upper():
            continue
        remainder = line.upper().replace(wanted, " ")
        if len([c for c in remainder if c.isalnum()]) < 2:
            continue
        if line not in out:
            out.append(line)
    return out


def collect_needs(
    sheets: Optional[Sequence[Dict[str, Any]]] = None,
    takeoff_rows: Optional[Sequence[Dict[str, Any]]] = None,
    unnamed_geometry: Optional[Sequence[Dict[str, Any]]] = None,
    missing_sheets: Optional[Sequence[Dict[str, Any]]] = None,
    hypothesis_sources: Optional[frozenset] = None,
) -> Tuple[Need, ...]:
    """Every open question the assembled run raised, collected — never invented.

    Args:
        sheets: one record per analysed page — ``{"sheet", "page_index",
            "text"}``. The text is the page's own text layer, already harvested.
        takeoff_rows: ``report["takeoff_summary"]``. Read only for rows whose
            NAME is a hypothesis; quantities here are evidence, not needs.
        unnamed_geometry: ``report["unnamed_geometry"]`` (24-06) — measured marks
            nothing named.
        missing_sheets: ``missing_referenced_sheets`` output — sheets cited and
            not contained.
        hypothesis_sources: the aggregator's own answer to "is this row's name a
            hypothesis?", passed in for the same reason ``resolve_quantity_rule``
            takes ``norm_key``: the app keeps ONE definition of it.
    """
    needs: List[Need] = []
    seen: Dict[tuple, int] = {}

    def _add(need: Need) -> None:
        # ONE NEED PER SUBJECT PER SHEET for a quantity rule — the aggregator's
        # own house rule ("one name is one row"), applied here for the same
        # reason: overlapping note windows read ONE note several times, and two
        # needs for one subject would put the same question in the client's
        # report twice with two differently-truncated quotes.
        #
        # Where the same note is read twice, the reading with the LONGEST
        # referent clause wins. That is not a tie-break between candidate
        # answers — the shorter clause is a prefix of the longer one, both come
        # from the same note, and the longer is simply the reading that saw the
        # whole sentence. Crow note 13 is the case: a window that ends mid-clause
        # reads "...ELECTRICAL TRANSFORMERS AND EXPOSED", which is not what the
        # note says.
        key = (need.kind, need.subject, need.asked_by_sheet)
        if need.kind != NEED_REFERENT_COUNT:
            key = key + (need.wanted, need.evidence_text)
        index = seen.get(key)
        if index is None:
            seen[key] = len(needs)
            needs.append(need)
        elif len(need.wanted) > len(needs[index].wanted):
            needs[index] = need

    # -- a rule whose referent nothing counted (29-06 is the producer) --------
    for record in sheets or []:
        if not isinstance(record, dict):
            continue
        sheet = _text(record.get("sheet"))
        windows = _note_windows(record.get("text"))
        for rule in read_quantity_rules(
            [{"text": w, "sheet": sheet} for w in windows]
        ):
            # A COMPOUND rule keeps 29-06's refusal. Its `wanted` is the whole
            # clause, which no row name can ever equal, so it can only ever be
            # REPORTED — this loop supplies the reason reaching the client, it
            # does not overrule the refusal. Crow's Bollards stays a blank.
            _add(Need(
                kind=NEED_REFERENT_COUNT,
                subject=published_name(rule.subject),
                wanted=rule.referent,
                asked_by_sheet=sheet,
                evidence_text=_trim_quote(rule.note_text, rule.subject),
                blocking_item=published_name(rule.subject),
                factor=rule.factor,
                factor_stated=rule.factor_stated,
            ))

    # -- a sheet the set cites and does not contain --------------------------
    for missing in missing_sheets or []:
        if not isinstance(missing, dict):
            continue
        sheet_id = _text(missing.get("sheet_id")).upper()
        if not sheet_id:
            continue
        for record in sheets or []:
            if not isinstance(record, dict):
                continue
            for line in _citing_lines(record.get("text"), sheet_id):
                _add(Need(
                    kind=NEED_ABSENT_SHEET,
                    subject=sheet_id,
                    wanted="the sheet %s itself" % sheet_id,
                    asked_by_sheet=_text(record.get("sheet")),
                    evidence_text=line,
                    blocking_item=sheet_id,
                ))

    # -- measured marks nothing named ----------------------------------------
    for record in unnamed_geometry or []:
        if not isinstance(record, dict):
            continue
        candidate = _text(record.get("candidate_id")) or "unnamed candidate"
        quantity = _number(record.get("quantity"))
        _add(Need(
            kind=NEED_UNNAMED_GEOMETRY,
            subject=candidate,
            wanted="a name for %s measured mark(s)"
                   % (_plain(quantity) if quantity is not None else "the"),
            asked_by_sheet=_text(record.get("sheet")),
            evidence_text=_text(record.get("detail")) or _text(record.get("reason")),
            blocking_item=candidate,
        ))

    # -- a row whose NAME is an inference ------------------------------------
    sources = hypothesis_sources or frozenset()
    for row in takeoff_rows or []:
        if not isinstance(row, dict) or _text(row.get("source")) not in sources:
            continue
        name = _text(row.get("item") or row.get("name"))
        if not name:
            continue
        sheets_named = [s for s in (row.get("source_sheets") or []) if _text(s)]
        _add(Need(
            kind=NEED_HYPOTHESIS_NAME,
            subject=name,
            wanted=name,
            asked_by_sheet=_text(sheets_named[0]) if sheets_named else "",
            evidence_text="this row's NAME is a hypothesis (%s), not a name the "
                          "drawing printed" % _text(row.get("source")),
            blocking_item=name,
        ))

    return tuple(needs)


# ---------------------------------------------------------------------------
# The resolver — across every sheet, and refusing rather than arbitrating
# ---------------------------------------------------------------------------


def _distinct(candidates: Sequence[EvidenceItem], norm_key: Callable[[str], str]):
    """One ANSWER per (name, quantity, unit), not one per place it is printed.

    A door count printed on A-601 and carried into a published row is one fact
    seen twice; two sheets stating DIFFERENT counts for one name is a genuine
    disagreement. Collapsing the first and keeping the second is the whole
    difference between citing two sheets and arbitrating between them.
    """
    grouped: Dict[Tuple[str, Optional[float], str], List[EvidenceItem]] = {}
    for cand in candidates:
        grouped.setdefault(
            (norm_key(cand.name), cand.quantity, cand.unit.upper()), []
        ).append(cand)
    return [tuple(group) for group in grouped.values()]


def resolve_need(
    need: Need,
    evidence: Sequence[EvidenceItem],
    norm_key: Callable[[str], str],
    round_index: int = 1,
) -> Resolution:
    """Search EVERY sheet's evidence for the one thing that answers *need*.

    Zero candidates leaves it open, one resolves it, and two or more CLOSE it as
    unresolved naming every candidate. There is no fourth branch, and in
    particular there is no branch that picks.
    """
    if need.kind == NEED_ABSENT_SHEET:
        # There is no route and there never will be: the answer is not in the
        # file. No detector — deterministic, ML or vision — can read a sheet
        # nobody uploaded, and anything published here would be a fabrication.
        return _open(need, round_index,
                     "the sheet is not in the upload; nothing in this set can "
                     "answer for it")
    if need.kind == NEED_UNNAMED_GEOMETRY:
        # Deliberately unresolvable. The record exists precisely BECAUSE no
        # legend, no library bind and no text anchor identified the marks, so
        # every remaining "match" would be a coincidence — an equal count, a
        # similar-looking label. That coincidence is the defect this branch is
        # named for; a name invented here would enter a client's take-off.
        return _open(need, round_index,
                     "nothing in this set keys these marks to a printed name, "
                     "and a match on count alone would be a coincidence")

    wanted = norm_key(need.wanted)
    if not wanted:
        return _open(need, round_index, "nothing to match on")

    if need.kind == NEED_HYPOTHESIS_NAME:
        pool = [
            e for e in evidence
            if e.source in _PRINTED_SOURCES and norm_key(e.name) == wanted
        ]
        if not pool:
            return _open(need, round_index,
                         "no schedule, legend or keynote in this set prints "
                         "this name")
        sheets = _sheets_of(pool)
        return Resolution(
            need=need, status=RESOLVED, candidates=tuple(pool),
            answered_by_sheet=", ".join(sheets), quantity=None, unit="",
            round_index=round_index,
            reason="the name %r is PRINTED on %s (%s) — the row's name is "
                   "confirmed by the drawing, not by us. Nothing else about "
                   "the row is changed."
                   % (need.subject, ", ".join(sheets) or "another sheet",
                      ", ".join(sorted({e.source for e in pool}))),
        )

    # NEED_REFERENT_COUNT — the join 29-06 could not make, because it only ever
    # saw the buckets the aggregator had already built.
    pool = [
        e for e in evidence
        if e.quantity is not None and norm_key(e.name) == wanted
    ]
    groups = _distinct(pool, norm_key)
    if not groups:
        return _open(need, round_index,
                     "no schedule, legend, keynote or counted row in this set "
                     "answers to %r" % need.wanted)
    if len(groups) > 1:
        named = "; ".join(
            "%s = %s %s (%s)" % (g[0].name, _plain(g[0].quantity), g[0].unit,
                                 ", ".join(_sheets_of(g)) or "sheet unknown")
            for g in groups
        )
        return Resolution(
            need=need, status=UNRESOLVED_AMBIGUOUS,
            candidates=tuple(c for g in groups for c in g),
            answered_by_sheet="", quantity=None, unit="",
            round_index=round_index,
            reason="%d different answers to %r in this set: %s. Nothing here "
                   "picks between them, because picking would be arbitration, "
                   "not evidence. This is a BLANK, not a zero — say which one "
                   "the note means." % (len(groups), need.wanted, named),
        )

    group = groups[0]
    one = group[0]
    sheets = _sheets_of(group)
    quantity = float(one.quantity) * float(need.factor)
    factor_note = (
        "the note PRINTS the multiplier %s" % _plain(need.factor)
        if need.factor_stated
        else "the note prints NO multiplier, so a factor of 1 was ASSUMED"
    )
    return Resolution(
        need=need, status=RESOLVED, candidates=tuple(group),
        answered_by_sheet=", ".join(sheets), quantity=quantity, unit=one.unit,
        round_index=round_index,
        reason="%r asked on %s for a count of %r; %s answers it with %s = %s "
               "%s. %s x %s is DERIVED, not measured — nothing on the plans was "
               "measured as this object, and %s. Confirm the referent before it "
               "is bid."
               % (need.subject, need.asked_by_sheet or "an unnamed sheet",
                  need.wanted, ", ".join(sheets) or "another sheet", one.name,
                  _plain(one.quantity), one.unit or "EA",
                  _plain(one.quantity), _plain(need.factor), factor_note),
    )


def _open(need: Need, round_index: int, reason: str) -> Resolution:
    return Resolution(
        need=need, status=OPEN, candidates=(), answered_by_sheet="",
        quantity=None, unit="", round_index=round_index, reason=reason,
    )


def _sheets_of(items: Sequence[EvidenceItem]) -> List[str]:
    return sorted({e.sheet for e in items if e.sheet})


# ---------------------------------------------------------------------------
# Naming OFFERS — the question that sits BESIDE the refusal above (29-11)
#
# `resolve_need` refuses `unnamed_geometry` outright, and that refusal is not
# weakened by anything below: a name published from an equal count is a
# coincidence wearing evidence. What follows never publishes. It builds a
# QUESTION — "your manifest lists Columns as EA/count; are these 36 marks
# Columns?" — and hands it to the human with the crop data the record already
# carries. Publishing a name is a claim and only a claim can be wrong; asking
# is safe precisely because the take-off is identical either way.
#
# Measured on the paid Crow run of 2026-08-17: 39 of 46 open needs are
# `unnamed_geometry` carrying 209 EA of counted marks, 16 of them with NO text
# at all and 12 with only drafting noise ('A-101', 'DWG', '1/A-112'). Manifest
# resolution matches TEXT, so no alias table can ever bind those rows — the
# only route left is to ask.
# ---------------------------------------------------------------------------

#: The most eligible entries one cluster may be asked about. Over it the
#: candidate is SUPPRESSED whole, never truncated: truncating would be a
#: ranking, and this file has no ranking anywhere. Sized against the real
#: project manifests in this repo — Crow's has 6 EA/count entries, Bob's has 7,
#: so a genuine project manifest fits under the bound; the 91-entry generic
#: catalogue carries 50 EA/count entries and would put 50 equally-grounded
#: options on every one of 27 clusters (1,350 questions), which is not a
#: question a human answers but a wall they close.
MAX_OFFERS_PER_CANDIDATE = 8

#: How the `why` names the measurement, per measure basis. A count of marks and
#: an area of floor are not the same sentence, and a client reads the sentence.
_MEASURE_PHRASE = {
    "count": "%s counted marks",
    "area": "%s %s of measured area",
    "length": "%s %s of measured line work",
    "volume": "%s %s of measured volume",
}


class NamingOffer(NamedTuple):
    """A QUESTION about one unnamed cluster. Never an answer.

    Deliberately carries no score, no rank and no default flag: every field
    here is either something the run already measured or the manifest name
    being asked about. There is nothing in this tuple a UI could sort by
    "confidence", because no confidence was computed — the grounds are unit and
    measure basis, which every offer on a cluster shares equally.
    """

    candidate_id: str
    sheet: str
    quantity: Optional[float]
    unit: str
    position_pt: Tuple[float, ...]
    manifest_name: str
    why: str


def _entry_fields(entry: Any) -> Tuple[str, str, str]:
    """``(name, unit, measure)`` of one manifest entry — dataclass or dict.

    Both shapes are accepted because both exist already: ``load_manifest``
    returns ``ManifestEntry`` objects and every fixture on disk is a list of
    plain dicts. Requiring one of them here would only add a conversion step
    for a caller to get wrong.
    """
    if isinstance(entry, dict):
        name = _text(entry.get("name") or entry.get("item"))
        unit = _text(entry.get("unit")).upper()
        measure = _text(entry.get("measure") or entry.get("measure_basis")).lower()
    else:
        name = _text(getattr(entry, "name", ""))
        unit = _text(getattr(entry, "unit", "")).upper()
        measure = _text(getattr(entry, "measure", "")).lower()
    if not measure and unit:
        measure = measure_from_unit(unit)
    return name, unit, measure


def _candidate_fields(record: Dict[str, Any]) -> Tuple[str, str]:
    """``(unit, measure)`` of one unnamed-geometry record.

    A record with NO unit yields ``("", "")`` and is offered nothing.
    ``measure_from_unit`` defaults to ``count`` for an unknown unit, so reading
    a blank unit through it would silently make every unitless cluster eligible
    for every EA entry in the manifest — the coincidence this whole path exists
    to avoid.
    """
    unit = _text(record.get("unit")).upper()
    if not unit:
        return "", ""
    measure = _text(record.get("measure") or record.get("measure_basis")).lower()
    return unit, measure or measure_from_unit(unit)


def candidate_signature(record: Dict[str, Any]) -> str:
    """A stable identity for one cluster, for remembering a DECLINE across runs.

    Deliberately NOT ``candidate_id``: ``SYM-6`` is minted by position in this
    run's detection order, so one extra cluster upstream renumbers everything
    after it and yesterday's decline would silently attach to a different pile
    of marks. Sheet + unit + count + where it sits identifies the same marks
    again; the position is rounded to whole points because a re-run of the same
    PDF may differ in the third decimal.
    """
    unit, _ = _candidate_fields(record)
    quantity = _number(record.get("quantity"))
    place: List[str] = []
    for value in list(record.get("position_pt") or [])[:2]:
        try:
            place.append(str(int(round(float(value)))))
        except (TypeError, ValueError):
            place.append("?")
    return "|".join([
        _text(record.get("sheet")),
        unit,
        _plain(quantity) if quantity is not None else "",
        ",".join(place),
    ])


def decline_key(
    project_key: str, record: Dict[str, Any], manifest_name: str
) -> str:
    """The ``(project, candidate signature, manifest name)`` triple, as one key.

    Scoped to the project on purpose: "these marks are not Bollards" is a fact
    about ONE drawing set. Letting it travel would be the cross-project naming
    leak the exact-scope rule already forbids for vocabulary.
    """
    return "|".join([_text(project_key), candidate_signature(record),
                     _text(manifest_name)])


def record_decline(
    declined: Optional[Sequence[str]],
    project_key: str,
    record: Dict[str, Any],
    manifest_name: str,
) -> Tuple[str, ...]:
    """The declined set with this answer added — a NEW tuple, nothing mutated.

    Returned to the caller to persist rather than written from here: the
    learning store is a naming-suggestion store with its own schema, and
    widening it is not this change's to make. A caller that persists nothing
    simply re-asks, which is the behaviour before this existed.
    """
    key = decline_key(project_key, record, manifest_name)
    existing = tuple(_text(d) for d in (declined or []) if _text(d))
    return existing if key in existing else existing + (key,)


def _offer_why(
    record: Dict[str, Any],
    quantity: Optional[float],
    unit: str,
    measure: str,
    entry_name: str,
    entry_unit: str,
    entry_measure: str,
) -> str:
    template = _MEASURE_PHRASE.get(measure, "%s %s measured")
    amount = _plain(quantity) if quantity is not None else "the"
    measured = (
        template % amount if template.count("%s") == 1
        else template % (amount, unit)
    )
    return (
        "%s on %s; your manifest lists %s as %s/%s. Matching unit and measure "
        "basis is the ONLY thing that produced this question — nothing on the "
        "sheet names these marks. Confirm only if that is what these are."
        % (measured, _text(record.get("sheet")) or "an unnamed sheet",
           entry_name, entry_unit, entry_measure)
    )


def _eligible_entries(
    record: Dict[str, Any], manifest: Any
) -> List[Tuple[str, str, str]]:
    """Manifest entries whose unit AND measure basis match this cluster's.

    That is the WHOLE test, and the omissions are the point. No token overlap
    (there is no token — 16 of the 39 real records carry no text at all), no
    fuzzy score, no "marks on a grid are columns". Each of those is a shape
    guess, and a shape guess behind a surface the human trusts is worse than
    silence: it converts a machine's hunch into a human's confirmation.
    """
    unit, measure = _candidate_fields(record)
    if not unit or not measure:
        return []
    entries = getattr(manifest, "entries", None)
    if entries is None:
        entries = manifest
    out: List[Tuple[str, str, str]] = []
    for entry in entries or []:
        name, entry_unit, entry_measure = _entry_fields(entry)
        if not name or not entry_unit:
            continue
        if entry_unit == unit and entry_measure == measure:
            out.append((name, entry_unit, entry_measure))
    return out


def offers_for(
    record: Dict[str, Any],
    manifest: Any,
    project_key: str = "",
    declined: Optional[Sequence[str]] = None,
    max_per_candidate: int = MAX_OFFERS_PER_CANDIDATE,
) -> Tuple[NamingOffer, ...]:
    """Every question worth asking about ONE unnamed cluster.

    Three eligible entries produce THREE offers, in the order the human wrote
    their manifest, with no default and nothing marked best — manifest order
    implies nothing about fit, which is exactly why it is used. Zero eligible
    entries produce nothing, and so does an absent manifest: with no manifest
    there is no vocabulary to ask in, and inventing one would be the app naming
    geometry again by another route.
    """
    if not manifest:
        return ()
    eligible = _eligible_entries(record, manifest)
    if not eligible:
        return ()
    blocked = {_text(d) for d in (declined or [])}
    eligible = [
        e for e in eligible
        if decline_key(project_key, record, e[0]) not in blocked
    ]
    # The cap is applied AFTER declines, because a decline can only ever shrink
    # the question — an answer the human already rejected should not keep a
    # cluster suppressed.
    if not eligible or len(eligible) > max_per_candidate:
        return ()
    unit, measure = _candidate_fields(record)
    quantity = _number(record.get("quantity"))
    position = tuple(
        float(v) for v in (record.get("position_pt") or [])
        if isinstance(v, (int, float))
    )
    return tuple(
        NamingOffer(
            candidate_id=_text(record.get("candidate_id")),
            sheet=_text(record.get("sheet")),
            quantity=quantity,
            unit=unit,
            position_pt=position,
            manifest_name=name,
            why=_offer_why(record, quantity, unit, measure,
                           name, entry_unit, entry_measure),
        )
        for name, entry_unit, entry_measure in eligible
    )


def naming_offers(
    unnamed_geometry: Optional[Sequence[Dict[str, Any]]],
    manifest: Any,
    project_key: str = "",
    declined: Optional[Sequence[str]] = None,
    max_per_candidate: int = MAX_OFFERS_PER_CANDIDATE,
) -> Tuple[NamingOffer, ...]:
    """Every offer across every unnamed cluster of one run."""
    out: List[NamingOffer] = []
    for record in unnamed_geometry or []:
        if not isinstance(record, dict):
            continue
        out.extend(offers_for(record, manifest, project_key, declined,
                              max_per_candidate))
    return tuple(out)


def offers_report(
    unnamed_geometry: Optional[Sequence[Dict[str, Any]]],
    manifest: Any,
    project_key: str = "",
    declined: Optional[Sequence[str]] = None,
    max_per_candidate: int = MAX_OFFERS_PER_CANDIDATE,
) -> Dict[str, Any]:
    """The offers plus what was NOT asked, and why.

    A suppressed cluster is reported by name and count. A cap that hides its
    own effect would let a manifest quietly stop producing questions while the
    report still read as though every cluster had been considered.
    """
    records = [r for r in (unnamed_geometry or []) if isinstance(r, dict)]
    offers: List[NamingOffer] = []
    suppressed: List[Dict[str, Any]] = []
    no_entry = 0
    for record in records:
        raised = offers_for(record, manifest, project_key, declined,
                            max_per_candidate)
        eligible = _eligible_entries(record, manifest) if manifest else []
        if raised:
            offers.extend(raised)
        elif len(eligible) > max_per_candidate:
            suppressed.append({
                "candidate_id": _text(record.get("candidate_id")),
                "sheet": _text(record.get("sheet")),
                "unit": _candidate_fields(record)[0],
                "eligible_entries": len(eligible),
                "reason": "%d manifest entries share this cluster's unit and "
                          "measure basis, which is more than the %d a human "
                          "can be asked at once. Nothing is ranked or dropped "
                          "— the whole question is withheld; narrow the "
                          "manifest to ask it."
                          % (len(eligible), max_per_candidate),
            })
        else:
            no_entry += 1
    return {
        "max_offers_per_candidate": max_per_candidate,
        "candidates_seen": len(records),
        "candidates_offered": len({o.candidate_id for o in offers}),
        "candidates_with_no_eligible_entry": no_entry,
        "candidates_suppressed": suppressed,
        "offers": [
            {
                "candidate_id": o.candidate_id,
                "sheet": o.sheet,
                "quantity": o.quantity,
                "unit": o.unit,
                "position_pt": list(o.position_pt),
                "manifest_name": o.manifest_name,
                "why": o.why,
            }
            for o in offers
        ],
    }


def accept_offer(offer: NamingOffer) -> Dict[str, Any]:
    """What a row looks like once a HUMAN has answered one offer. Pure.

    Returns the row a caller would write; nothing here writes it. The status is
    HUMAN INPUT and never MEASURED even though the count was measured, because
    the row's IDENTITY came from the estimator rather than the drawing — and
    29-02 measured what a manifest-sourced identity published as MEASURED costs
    (Stairs = 3 EA manufactured from a clearance note, unflagged). The quantity
    is carried through untouched: accepting a name never restates a count.
    """
    return {
        "item": offer.manifest_name,
        "quantity": offer.quantity,
        "unit": offer.unit,
        "source": "human",
        "status": ITEM_HUMAN_INPUT,
        "candidate_id": offer.candidate_id,
        "source_sheets": [offer.sheet] if offer.sheet else [],
        "naming_provenance": "named by the estimator from a naming offer; the "
                             "drawing prints no name for these marks",
    }


def decline_offer(
    offer: NamingOffer,
    record: Dict[str, Any],
    project_key: str = "",
    declined: Optional[Sequence[str]] = None,
) -> Tuple[str, ...]:
    """The declined set with this offer's answer recorded. Nothing mutated."""
    return record_decline(declined, project_key, record, offer.manifest_name)


# ---------------------------------------------------------------------------
# The fixed-point loop
# ---------------------------------------------------------------------------


def extend_evidence(
    evidence: Sequence[EvidenceItem],
    resolutions: Sequence[Resolution],
    norm_key: Callable[[str], str],
) -> Tuple[EvidenceItem, ...]:
    """ADD what the round learned. It may only ever add.

    Nothing existing is replaced, re-ordered or re-priced, and a name evidence
    already carries is never shadowed: an answer whose subject is already spoken
    for is dropped rather than allowed to compete with it. A loop able to shadow
    its own inputs would make the fixed point depend on round order.
    """
    known = {norm_key(e.name) for e in evidence if e.quantity is not None}
    out = list(evidence)
    for res in resolutions:
        if res.status != RESOLVED or res.quantity is None:
            continue
        key = norm_key(res.need.subject)
        if not key or key in known:
            continue
        known.add(key)
        out.append(EvidenceItem(
            name=res.need.subject,
            quantity=res.quantity,
            unit=res.unit,
            sheet=res.answered_by_sheet,
            source=SOURCE_DERIVED,
            text=res.need.evidence_text,
        ))
    return tuple(out)


def run_evidence_loop(
    needs: Sequence[Need],
    evidence: Sequence[EvidenceItem],
    norm_key: Callable[[str], str],
    max_rounds: int = MAX_ROUNDS,
) -> LoopRun:
    """Resolve to a FIXED POINT: repeat until a round learns nothing.

    One pass is provably not enough. Answering a need can supply the evidence
    another was waiting for — a subject counted in round 1 is a referent another
    rule can be resolved against in round 2 — and a single pass cannot see that
    by construction.

    Termination is proved, not assumed, in two independent ways: the open set
    shrinks strictly on every round that does not break, and ``max_rounds``
    bounds the whole thing regardless. Hitting the bound is LOGGED and reported,
    never swallowed.
    """
    open_needs: List[Need] = list(needs)
    current: Tuple[EvidenceItem, ...] = tuple(evidence)
    resolutions: List[Resolution] = []
    reasons: Dict[Need, str] = {}
    rounds = 0
    hit_max = False

    while open_needs:
        if rounds >= max_rounds:
            hit_max = True
            logger.warning(
                "evidence loop stopped at MAX_ROUNDS=%d with %d need(s) still "
                "open — they are reported as INPUT GAPS, not dropped",
                max_rounds, len(open_needs),
            )
            break
        rounds += 1
        closed: List[Resolution] = []
        still_open: List[Need] = []
        for need in open_needs:
            res = resolve_need(need, current, norm_key, round_index=rounds)
            if res.status == OPEN:
                still_open.append(need)
                reasons[need] = res.reason
            else:
                closed.append(res)
        if not closed:
            # The fixed point: this round learned nothing, so no later round can
            # learn anything either — the evidence it would read is unchanged.
            break
        resolutions.extend(closed)
        open_needs = still_open
        current = extend_evidence(current, closed, norm_key)

    return LoopRun(
        resolutions=tuple(resolutions),
        open_needs=tuple(open_needs),
        rounds=rounds,
        hit_max_rounds=hit_max,
        evidence=current,
        open_reasons=tuple(reasons.get(n, "") for n in open_needs),
    )


# ---------------------------------------------------------------------------
# The INPUT GAPS report — a first-class deliverable, not a log line
# ---------------------------------------------------------------------------

#: What would close each kind of need, in the client's own terms. This is the
#: half of the report that turns "we failed" into "send A-111 and the count
#: becomes available".
_WHAT_WOULD_ANSWER = {
    NEED_REFERENT_COUNT: "a count of %(wanted)s — a schedule, legend or "
                         "keynote in the set that tabulates them, or the sheet "
                         "they are drawn on",
    NEED_ABSENT_SHEET: "%(wanted)s, added to the upload",
    NEED_UNNAMED_GEOMETRY: "%(wanted)s — a legend, schedule or note in the set "
                           "that names the symbol these marks use",
    NEED_HYPOTHESIS_NAME: "the name %(wanted)s printed somewhere in the set — a "
                          "schedule, a legend or a keynote — confirming the row "
                          "is what we called it",
}


def _plain(value: Any) -> str:
    """A number as a human writes it — no trailing ``.0`` on a whole one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def _need_dict(need: Need, reason: str = "") -> Dict[str, Any]:
    return {
        "kind": need.kind,
        "item": need.subject,
        "wanted": need.wanted,
        "asked_by_sheet": need.asked_by_sheet,
        "evidence_text": need.evidence_text,
        "blocking_item": need.blocking_item,
        # The take-off consequence, in the SHARED vocabulary. An unmet need is
        # an item with no measurement path — the same fact the ledger publishes,
        # said in the same words.
        "status": ITEM_NOT_MEASURED,
        "what_would_answer": _WHAT_WOULD_ANSWER.get(need.kind, "") % {
            "wanted": need.wanted,
        },
        "why_open": reason,
    }


def input_gaps_report(
    loop: LoopRun,
    missing_sheets: Optional[Sequence[Dict[str, Any]]] = None,
    needs: Optional[Sequence[Need]] = None,
) -> Dict[str, Any]:
    """Group every unmet need under the thing that would answer it.

    An absent sheet gets the QUESTIONS it would have answered attached to it,
    which is what makes the list actionable. A need is filed under a sheet when
    it IS that sheet's absence, or when the evidence that raised it cites that
    sheet — Crow's note 21 defers to detail 9/A-002 for the fire-department
    signage, so the signage question belongs under A-002 rather than in a
    separate list a reader has to cross-reference by hand.
    """
    raised = list(needs) if needs is not None else (
        list(loop.open_needs) + [r.need for r in loop.resolutions]
    )
    by_kind: Dict[str, int] = {}
    for need in raised:
        by_kind[need.kind] = by_kind.get(need.kind, 0) + 1

    reasons = list(loop.open_reasons) + [""] * len(loop.open_needs)
    unmet: List[Tuple[Need, str]] = list(zip(loop.open_needs, reasons))

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    filed = set()
    sheet_ids = [
        _text(m.get("sheet_id")).upper()
        for m in (missing_sheets or [])
        if isinstance(m, dict) and _text(m.get("sheet_id"))
    ]
    for index, (need, reason) in enumerate(unmet):
        cited = set(sheet_ids_in_text(need.evidence_text)) & set(sheet_ids)
        if need.kind == NEED_ABSENT_SHEET:
            cited.add(need.subject.upper())
        for sheet_id in sorted(cited):
            grouped.setdefault(sheet_id, []).append(_need_dict(need, reason))
            filed.add(index)

    missing_block: List[Dict[str, Any]] = []
    for record in missing_sheets or []:
        if not isinstance(record, dict):
            continue
        sheet_id = _text(record.get("sheet_id")).upper()
        if not sheet_id:
            continue
        questions = grouped.get(sheet_id, [])
        missing_block.append({
            "sheet_id": sheet_id,
            "cited_on_pages": list(record.get("cited_on_pages") or []),
            "citations": record.get("citations", 0),
            "asked_by_sheets": sorted({
                q["asked_by_sheet"] for q in questions if q["asked_by_sheet"]
            }),
            "status": ITEM_NOT_MEASURED,
            "questions": questions,
        })

    answers = [
        {
            "item": r.need.subject,
            "kind": r.need.kind,
            "wanted": r.need.wanted,
            "asked_by_sheet": r.need.asked_by_sheet,
            "answered_by_sheet": r.answered_by_sheet,
            "quantity": r.quantity,
            "unit": r.unit,
            "factor": r.need.factor,
            "factor_stated": r.need.factor_stated,
            # A derived quantity is NEVER a measurement and never counts as
            # coverage — it is a hypothesis about the drawing's intent that a
            # human confirms.
            "status": ITEM_NEEDS_REVIEW,
            "measured": False,
            "round": r.round_index,
            "evidence": [
                {"sheet": c.sheet, "name": c.name, "quantity": c.quantity,
                 "unit": c.unit, "source": c.source, "text": c.text}
                for c in r.candidates
            ],
            "reason": r.reason,
        }
        for r in loop.resolutions if r.status == RESOLVED
    ]
    ambiguous = [
        {
            "item": r.need.subject,
            "kind": r.need.kind,
            "wanted": r.need.wanted,
            "asked_by_sheet": r.need.asked_by_sheet,
            "status": ITEM_NOT_MEASURED,
            "candidates": [
                {"sheet": c.sheet, "name": c.name, "quantity": c.quantity,
                 "unit": c.unit, "source": c.source}
                for c in r.candidates
            ],
            "reason": r.reason,
        }
        for r in loop.resolutions if r.status == UNRESOLVED_AMBIGUOUS
    ]

    return {
        "rounds": loop.rounds,
        "max_rounds": MAX_ROUNDS,
        "hit_max_rounds": loop.hit_max_rounds,
        "needs_raised": len(raised),
        "needs_by_kind": by_kind,
        "needs_resolved": len(answers),
        "needs_unresolved": len(ambiguous) + len(loop.open_needs),
        "answers": answers,
        "unresolved_ambiguous": ambiguous,
        "missing_sheets": missing_block,
        "open_needs": [
            _need_dict(need, reason)
            for index, (need, reason) in enumerate(unmet)
            if index not in filed
        ],
    }


def input_gaps_text(gaps: Dict[str, Any]) -> str:
    """The INPUT GAPS section, as a client reads it in ``summary.txt``.

    Empty string when there is nothing to say, which is what keeps a run with no
    open needs byte-identical to one from before this pass existed.
    """
    if not gaps:
        return ""
    missing = gaps.get("missing_sheets") or []
    answers = gaps.get("answers") or []
    ambiguous = gaps.get("unresolved_ambiguous") or []
    open_needs = gaps.get("open_needs") or []
    if not (missing or answers or ambiguous or open_needs):
        return ""

    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("INPUT GAPS — what this drawing set does not answer")
    lines.append("=" * 70)
    lines.append(
        "Nothing below is a zero. Each line names a question the set raised, "
        "which sheet asked it, and what would close it."
    )
    lines.append("")

    if missing:
        lines.append("SHEETS CITED BUT NOT IN THE UPLOAD")
        for record in missing:
            lines.append(
                "  %s — cited %s time(s) on page(s) %s"
                % (record["sheet_id"], record.get("citations", 0),
                   ", ".join(str(p) for p in record.get("cited_on_pages") or []))
            )
            if not record.get("questions"):
                lines.append(
                    "      no question in the text layer names it; it is cited "
                    "as a drawing reference only"
                )
            for question in record["questions"]:
                lines.append(
                    "      asked by %s: %s"
                    % (question["asked_by_sheet"] or "an unnamed sheet",
                       question["evidence_text"] or question["wanted"])
                )
                lines.append("          would answer: %s"
                             % question["what_would_answer"])
        lines.append("")

    if answers:
        lines.append("ANSWERED ACROSS SHEETS (DERIVED — confirm before bidding)")
        for answer in answers:
            lines.append(
                "  %s = %s %s [%s] — asked on %s, answered by %s (round %d)"
                % (answer["item"],
                   _plain(answer["quantity"]) if answer["quantity"] is not None
                   else "(name confirmed)",
                   answer["unit"], answer["status"],
                   answer["asked_by_sheet"] or "an unnamed sheet",
                   answer["answered_by_sheet"] or "another sheet",
                   answer["round"])
            )
            lines.append("      %s" % answer["reason"])
        lines.append("")

    if ambiguous:
        lines.append("CLOSED UNRESOLVED — two or more answers, nothing picked")
        for record in ambiguous:
            lines.append("  %s: %s" % (record["item"], record["reason"]))
        lines.append("")

    if open_needs:
        lines.append("STILL OPEN")
        for need in open_needs:
            lines.append(
                "  %s (%s) — asked by %s" % (need["item"], need["kind"],
                                             need["asked_by_sheet"] or "an "
                                             "unnamed sheet")
            )
            if need["evidence_text"]:
                lines.append("      raised by: %s" % need["evidence_text"])
            lines.append("      would answer: %s" % need["what_would_answer"])
        lines.append("")

    lines.append(
        "Resolution ran %d round(s)%s."
        % (gaps.get("rounds", 0),
           " and STOPPED AT THE %d-ROUND LIMIT with needs still open"
           % gaps.get("max_rounds", MAX_ROUNDS)
           if gaps.get("hit_max_rounds") else " and reached a fixed point")
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Wiring — the ONE impure function here
# ---------------------------------------------------------------------------


def run_evidence_pass(
    report: Dict[str, Any],
    pages: Optional[Sequence[Dict[str, Any]]],
    all_extracted: Optional[Sequence[Dict[str, Any]]],
    missing_sheets: Optional[Sequence[Dict[str, Any]]] = None,
    manifest: Any = None,
    project_key: str = "",
    declined_offers: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Run the loop over one finished run and publish what it found.

    Deliberately runs AFTER the report is written and never touches it. The
    take-off, its CSVs and ``coverage.json`` are already on disk and stay
    byte-identical; this adds ``input_gaps.json`` beside them and — only when
    there is something to say — an INPUT GAPS section at the end of
    ``summary.txt``. A run with no open needs writes nothing at all.

    ``manifest`` turns on NAMING OFFERS (29-11) and is the only thing that
    does: with none supplied the run raises no question, which is why every
    existing caller behaves exactly as it did. The offers land in the gaps
    artifact and nowhere else — no quantity, no coverage number and no
    ``takeoff_summary`` row differs between a run with offers and the same run
    without.
    """
    from bobbytailor.pipeline.aggregator import (  # local: avoids an import cycle
        _HYPOTHESIS_NAME_SOURCES, _norm_item_key,
    )

    sheets = [
        {
            "sheet": _text(page.get("sheet_name")),
            "page_index": page.get("page_index"),
            "text": page.get("full_page_text") or "",
        }
        for page in (pages or []) if isinstance(page, dict)
    ]
    takeoff_rows = report.get("takeoff_summary") or []
    needs = collect_needs(
        sheets=sheets,
        takeoff_rows=takeoff_rows,
        unnamed_geometry=report.get("unnamed_geometry") or [],
        missing_sheets=missing_sheets,
        hypothesis_sources=_HYPOTHESIS_NAME_SOURCES,
    )
    evidence = collect_evidence(all_extracted, takeoff_rows)
    loop = run_evidence_loop(needs, evidence, _norm_item_key)
    gaps = input_gaps_report(loop, missing_sheets, needs=needs)
    if manifest:
        # Beside the open needs, never instead of them: every cluster offered
        # here is STILL an open `unnamed_geometry` need in the same report,
        # still NOT MEASURED, still unnamed. The offer adds a question.
        gaps["naming_offers"] = offers_report(
            report.get("unnamed_geometry") or [], manifest,
            project_key=project_key, declined=declined_offers,
        )

    text = input_gaps_text(gaps)
    if not text:
        # THE inert path, and the common one. Nothing is written and nothing is
        # added to the report, so this run's artifacts are identical to the ones
        # it would have produced before this pass existed.
        return gaps

    report["input_gaps"] = gaps
    files = report.get("_files") or {}
    run_folder = files.get("run_folder")
    if not run_folder:
        return gaps
    try:
        path = os.path.join(run_folder, "input_gaps.json")
        with open(path, "w") as handle:
            json.dump(gaps, handle, indent=2)
        files["input_gaps_json"] = path
    except Exception as exc:  # noqa: BLE001 — additive; never break a finished run
        logger.error("failed to write input_gaps.json: %s", exc)
    try:
        summary_txt = files.get("summary_txt")
        if summary_txt:
            with open(summary_txt, "a") as handle:
                handle.write("\n" + text)
    except Exception as exc:  # noqa: BLE001 — additive; never break a finished run
        logger.error("failed to append INPUT GAPS to summary.txt: %s", exc)

    logger.info(
        "evidence loop: %d need(s) raised, %d answered across sheets, %d left "
        "open, %d round(s)%s",
        gaps["needs_raised"], gaps["needs_resolved"], gaps["needs_unresolved"],
        gaps["rounds"], " (MAX_ROUNDS)" if gaps["hit_max_rounds"] else "",
    )
    return gaps
