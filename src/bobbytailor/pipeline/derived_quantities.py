"""Quantities the drawing DEFINES BY RULE rather than by drawing (29-06).

The engine measures what is drawn and reads what is tabulated. It has no route
at all for what is SPECIFIED — and "PROVIDE X AT ALL Y" is how a large part of a
real take-off is communicated. Crow's Bollards is the standing example: general
note 13 states the rule, the door schedule holds a referent, and no stage of the
pipeline ever joins them, so the cell is an opaque blank.

This module is the reader and the resolver for that second pass. Both halves are
PURE functions over evidence some earlier stage already assembled — a note's
text, and the counts a run published. No extraction, no PDF, no API, no I/O.

**It reads a rule; it never infers one.** The pattern set is small, stated, and
was narrowed against the four plan sets rather than guessed:

    reader over notes split out of all four plan PDFs, 2026-08-17
    ────────────────────────────────────────────────────────────
    PROVIDE <X> AT (ALL|EACH) <Y>   crow 2, moxy 1, bobs 0, chelsea 0 — all
                                    three hits are real quantity rules
    <N> <X> AT EACH <Y>             0 on all four sets
    <X> AT (ALL|EACH) <Y>           DROPPED. 4 hits, 0 of them rules:
                                    "DUCT TAPED AT ALL EDGES", "TRANSITION
                                    STRIPS TO BE PROVIDED AT ALL UNLIKE
                                    FLOORING MATERIALS", "VERTICAL FRAMING
                                    MEMBERS AT ALL DOOR FRAMES SHALL EXTEND TO
                                    STRUCTURE ABOVE", "PAINTED CORRESPONDING
                                    COLOR THEY LAND ON AT ALL EXTERIOR
                                    ELEVATION PLANS". Its two real hits were
                                    already found by the PROVIDE form.
    <N> <X> PER <Y>                 DROPPED. 2 hits, both UNIT phrases:
                                    "6 AIR CHANGES PER HOUR" (crow),
                                    "1.57 POUNDS PER SQUARE FOOT IN ACCORDANCE
                                    WITH ASTM E283" (bobs). A unit is not a
                                    quantity rule, and `PER` is how units are
                                    spelled.

Quiet on three sets beats noisy on four: a reader that fires on "DUCT TAPED AT
ALL EDGES" would put a Duct Taped row in a client's take-off.

**A number is the rare outcome, and a blank is the deliverable.** Three refusals
come before the happy path, each of which produces a BLANK that names what it is
waiting for:

* COMPOUND — the referent clause names two or more things. Crow note 13 is the
  motivating case AND this case: "PROVIDE BOLLARDS AT ALL DRIVE-IN OVERHEAD DOOR
  JAMBS, FIRE PROTECTION RISERS, ELECTRICAL TRANSFORMERS AND EXPOSED ELECTRICAL
  PANELS". Computing the half that resolves and publishing it is a confidently
  wrong number wearing a citation.
* REFERENT NOT COUNTED — nothing this run counted answers to the referent. The
  blank names the referent, which is the whole point: it tells the estimator
  what to go count.
* AMBIGUOUS REFERENT — more than one counted row answers to it. 29-02 measured
  what arbitrating that costs: 136 personnel doors published as galvanized
  frames because the tie broke on name length. A text that ties across
  candidates binds NOTHING.
"""
from __future__ import annotations

import re
from typing import Callable, List, NamedTuple, Optional, Sequence, Tuple

#: Refusal verdicts. Each one is a REASON a rule produced no number, and each
#: reads as a sentence to an estimator rather than as a status code.
REFUSED_COMPOUND = "compound_referent"
REFUSED_REFERENT_NOT_COUNTED = "referent_not_counted"
REFUSED_REFERENT_AMBIGUOUS = "referent_ambiguous"

#: Written-out multipliers a note may print. Deliberately short: these are the
#: forms a drawing writes ("TWO BOLLARDS AT EACH ..."), and a lexicon big enough
#: to cover "A DOZEN" would be inventing multipliers rather than reading them.
_WORD_FACTORS = {"ONE": 1.0, "TWO": 2.0, "THREE": 3.0, "FOUR": 4.0}

_FACTOR = r"ONE|TWO|THREE|FOUR|\d{1,3}"

#: The object being specified. Bounded on both ends: it starts alphanumeric and
#: runs at most 60 characters, so a runaway match cannot swallow a paragraph and
#: publish it as an item name.
_SUBJECT = r"[A-Z0-9][A-Z0-9 '\"/&\-\.]{2,60}?"

#: The thing it is specified AT. Stops at the first sentence-ending or bracketing
#: punctuation — which is what closes the clause in note 13, whose whole rule
#: sits inside parentheses.
_REFERENT = r"[^.;:)]{3,120}"

_RULE_PATTERNS = (
    re.compile(
        r"\bPROVIDE\s+(?:(?P<factor>%s)\s+)?(?P<subject>%s)\s+AT\s+(?:ALL|EACH)\s+"
        r"(?P<referent>%s)" % (_FACTOR, _SUBJECT, _REFERENT)
    ),
    re.compile(
        r"\b(?P<factor>%s)\s+(?P<subject>%s)\s+AT\s+EACH\s+(?P<referent>%s)"
        % (_FACTOR, _SUBJECT, _REFERENT)
    ),
)

#: Splits a referent clause into the things it names. The comma and the word AND
#: are the ONLY separators consulted, because they are the only two the compound
#: test itself consults — one expression of "this clause names more than one
#: thing" rather than two that can disagree about note 13.
_REFERENT_SEPARATORS = re.compile(r",|\bAND\b")

#: Where a subject stops being the object and starts being a reference to where
#: it is drawn. Measured on Crow general note 21, whose subject reads "FIRE
#: DEPARTMENT ACCESS SIGNAGE PER DETAIL 9/A-002" — the detail number is not part
#: of the object's name, and a take-off row carrying it is unreadable.
_SUBJECT_TAIL = re.compile(r"\s+(?:PER|SEE|AS)\s+")


class QuantityRule(NamedTuple):
    """One quantity rule a note states, read verbatim and resolved by nobody yet.

    ``factor_stated`` is the honest half of the multiplier: where the note does
    not print one the factor is 1 and this says so, so the published row can
    admit the assumption instead of presenting it as the drawing's word.
    """

    subject: str
    referent: str
    referents: Tuple[str, ...]
    factor: float
    factor_stated: bool
    compound: bool
    note_text: str
    sheet: str


class CountedItem(NamedTuple):
    """One row a run COUNTED, as the resolver is allowed to see it.

    Deliberately three fields, not a bucket: the resolver may join a rule to a
    count and to nothing else. Handing it the bucket would let it read a
    confidence, a review flag or a region and start deciding on them.
    """

    name: str
    quantity: float
    unit: str


class Resolution(NamedTuple):
    """What became of one rule. Exactly one of ``quantity`` / ``refused`` is set."""

    quantity: Optional[float]
    unit: str
    referent_name: Optional[str]
    referent_quantity: Optional[float]
    refused: Optional[str]
    matched: Tuple[str, ...]


def _collapse(text: str) -> str:
    """One line of text out of a PDF's line-broken extraction.

    The breaks are an artifact of where the words sat on the sheet — Crow note
    13 breaks between "EXPOSED" and "ELECTRICAL PANELS" — so collapsing them is
    not editing the note. Nothing else about the string is touched: this is what
    "quoted verbatim" means everywhere below.
    """
    return " ".join(str(text or "").split())


def _note_text_and_sheet(note) -> Tuple[str, str]:
    """Accept a bare string or a ``{"text", "sheet"}`` record. Never raises."""
    if isinstance(note, str):
        return _collapse(note), ""
    try:
        text = note.get("text") or note.get("note") or ""
        sheet = note.get("sheet") or ""
    except AttributeError:
        return "", ""
    return _collapse(text), str(sheet or "").strip()


def _trim_subject(subject: str) -> str:
    parts = _SUBJECT_TAIL.split(_collapse(subject), 1)
    return parts[0].strip(" -,.")


def _referent_phrases(clause: str) -> Tuple[str, ...]:
    out = []
    for part in _REFERENT_SEPARATORS.split(clause):
        part = part.strip(" -,.")
        if part:
            out.append(part)
    return tuple(out)


def _factor_of(raw: Optional[str]) -> Tuple[float, bool]:
    """The multiplier the note PRINTED, or 1 and an admission that it did not."""
    token = (raw or "").strip().upper()
    if not token:
        return 1.0, False
    if token in _WORD_FACTORS:
        return _WORD_FACTORS[token], True
    try:
        return float(int(token)), True
    except ValueError:
        return 1.0, False


def published_name(subject: str) -> str:
    """The take-off row name for a subject the plans printed in all capitals.

    A drawing shouts; a take-off row does not. Case is the only thing changed —
    no word is added, removed or translated, so `_norm_item_key` folds this name
    onto a measured row of the same object exactly as it would have folded the
    shouted one. ``title`` rather than ``capitalize`` because a subject carries
    punctuation the plans mean: "S.C.C.P." survives as itself, and "DRIVE-IN
    OVERHEAD DOOR" reads as "Drive-In Overhead Door".
    """
    return str(subject or "").title()


def read_quantity_rules(notes: Optional[Sequence]) -> List[QuantityRule]:
    """Read every EXPLICIT quantity rule out of already-harvested note text.

    There is no fallback branch and no scoring: a note that does not match one
    of the two stated patterns yields nothing at all. That is the whole design —
    see the census in the module docstring for what the wider patterns matched
    on real plan sets.

    Args:
        notes: note records — bare strings, or mappings with ``text`` and an
            optional ``sheet``. ``None`` and empty yield ``[]``, which is what
            makes this pass invisible to a run that harvested no notes.

    Returns:
        One :class:`QuantityRule` per distinct (subject, referent) a note
        stated, in the order the notes were supplied.
    """
    rules: List[QuantityRule] = []
    seen = set()
    for note in notes or []:
        text, sheet = _note_text_and_sheet(note)
        if not text:
            continue
        haystack = text.upper()
        for pattern in _RULE_PATTERNS:
            for match in pattern.finditer(haystack):
                subject = _trim_subject(match.group("subject"))
                clause = match.group("referent").strip(" -,.")
                referents = _referent_phrases(clause)
                if not subject or not referents:
                    continue
                factor, stated = _factor_of(match.groupdict().get("factor"))
                key = (subject, clause, sheet)
                if key in seen:
                    continue
                seen.add(key)
                rules.append(QuantityRule(
                    subject=subject,
                    referent=referents[0] if len(referents) == 1 else clause,
                    referents=referents,
                    factor=factor,
                    factor_stated=stated,
                    # THE compound test, and the loudest thing this module does.
                    # It reads the CLAUSE rather than the split, so a clause that
                    # separators alone would reduce to one phrase ("DOORS, TYP")
                    # is still refused: the punctuation says the author was
                    # listing, and a list is not a referent.
                    compound=bool(_REFERENT_SEPARATORS.search(clause)),
                    note_text=text,
                    sheet=sheet,
                ))
    return rules


def resolve_quantity_rule(
    rule: QuantityRule,
    counted: Sequence[CountedItem],
    norm_key: Callable[[str], str],
) -> Resolution:
    """Join one rule to the ONE thing this run counted, or refuse to.

    Matching is EXACT on the caller's own canonical key — never containment,
    never similarity. 29-02 measured what containment costs at this exact join:
    the single token "stair" inside "Stair plan truck court clearance from
    center line of rail to wall" published Stairs = 3 EA as a MEASUREMENT.

    Args:
        rule: what the note stated.
        counted: the rows this run COUNTED. A row measured in SF is not a count
            of anything and its absence from this list is what makes "provide one
            at each" refuse rather than multiply an area.
        norm_key: the caller's bucket-identity function, PASSED IN so that the
            app keeps exactly one definition of when two names are one item. A
            second copy here is how a rule starts binding to a row the aggregator
            would have called a different object.
    """
    if rule.compound:
        return Resolution(None, "", None, None, REFUSED_COMPOUND, rule.referents)

    wanted = norm_key(rule.referent)
    matched = [c for c in counted if wanted and norm_key(c.name) == wanted]
    names = tuple(sorted(c.name for c in matched))
    if not matched:
        return Resolution(None, "", None, None, REFUSED_REFERENT_NOT_COUNTED, ())
    if len(matched) > 1:
        return Resolution(None, "", None, None, REFUSED_REFERENT_AMBIGUOUS, names)

    one = matched[0]
    return Resolution(
        quantity=float(one.quantity) * rule.factor,
        unit=one.unit,
        referent_name=one.name,
        referent_quantity=float(one.quantity),
        refused=None,
        matched=names,
    )


def _quote(rule: QuantityRule) -> str:
    where = " (%s)" % rule.sheet if rule.sheet else ""
    return "a general note%s states: %r" % (where, rule.note_text)


def _phrases(items: Sequence[str]) -> str:
    return ", ".join(repr(p) for p in items)


def refusal_reason(rule: QuantityRule, resolution: Resolution) -> str:
    """The review reason for a rule that produced no number.

    This text IS the deliverable for the overwhelming majority of rules. It
    quotes the note and names precisely what blocked it, so the estimator closes
    the row by counting one thing rather than by wondering why a cell is empty.
    """
    quote = _quote(rule)
    if resolution.refused == REFUSED_COMPOUND:
        return (
            "%s — a quantity RULE naming %d referents: %s. The rule is not "
            "resolved and NO number is derived: publishing the part that "
            "resolves would price one referent as if it were all of them. This "
            "is a BLANK, not a zero — count each referent above and the note "
            "gives the total."
            % (quote, len(rule.referents), _phrases(rule.referents))
        )
    if resolution.refused == REFUSED_REFERENT_AMBIGUOUS:
        return (
            "%s — a quantity RULE over %r, and %d rows in this take-off answer "
            "to that name: %s. Nothing here picks between them, because picking "
            "would be arbitration, not evidence. This is a BLANK, not a zero — "
            "say which row the note means."
            % (quote, rule.referent, len(resolution.matched),
               _phrases(resolution.matched))
        )
    return (
        "%s — a quantity RULE over %r, and this run COUNTED no %s. Nothing was "
        "assumed in its place. This is a BLANK, not a zero, and it is the one "
        "thing standing between the note and a number: count the %s and the "
        "rule gives this quantity."
        % (quote, rule.referent, rule.referent, rule.referent)
    )


def derived_reason(rule: QuantityRule, resolution: Resolution) -> str:
    """The review reason for a rule that DID produce a number.

    A quantity assembled from a note and a count is a hypothesis about the
    drawing's intent, not a measurement of it, and this sentence is where that
    is said in words. The factor is reported as printed or as assumed, always:
    a multiplier the drawing never stated is the easiest thing in this pass to
    mistake for the drawing's own.
    """
    factor = (
        "The note PRINTS the multiplier %s" % _plain(rule.factor)
        if rule.factor_stated
        else "The note prints NO multiplier, so a factor of 1 was ASSUMED"
    )
    return (
        "%s — this quantity is DERIVED, not measured: %s x %s from the row %r, "
        "which this run counted. %s. Nothing on the plans was measured as this "
        "object; confirm the rule's referent is the row named here before it is "
        "bid."
        % (_quote(rule), _plain(resolution.referent_quantity),
           _plain(rule.factor), resolution.referent_name, factor)
    )


def _plain(value) -> str:
    """A number as a human writes it — no trailing ``.0`` on a whole one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)
