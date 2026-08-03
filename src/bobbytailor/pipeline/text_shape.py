"""text_shape.py — structural shape tests for text lifted off a drawing sheet.

Two consumers, one tokenizer:

  * ``pdf_analyzer.get_title_block_text`` asks "does this window LOOK like a
    title block?" while searching bottom-right candidate windows;
  * ``sheet_pass_matrix`` asks "does this keyword match sit in a title POSITION,
    or inside a sentence?" before letting a bare "COVER"/"INDEX" discard a sheet.

Both questions are the same question at different scales — *is this a grid of
short labelled fields, or is it running prose?* — so the tokenizer, the
function-word set and the run definition live here once rather than being
copied into two modules that must then be kept in step. `sheet_pass_matrix`
cannot import `pdf_analyzer` (that is a cycle), which is the other reason this
is its own module.

**Why this module exists at all.** INV-00 §1c: on Moxy page 27 the sheet
identifier ``ID-411`` and the unit name ``KING SUITE`` are present in BOTH the
correct and the incorrect title-block window. The classifier was never failing
to SEE the title — it was being outvoted by 84 words of adjacent electrical
keynote prose. That makes the defect signal-to-noise, and the repair is to
recognise prose as prose rather than to retune a page fraction (INV-00 §1d
proves a fraction sweep fixes Moxy and destroys Chelsea).

Pure text in, booleans out. No I/O, no ``fitz``, no page geometry.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# A "plain word": letters only, optionally with an apostrophe or ampersand
# joiner. Anything carrying a digit, a period, a colon, a quote or a hyphen is
# NOT a plain word — on a drawing those characters are precisely what separates
# one title-block field from the next ("SHEET NO." / "ID-411" / "25-13.01"),
# and what terminates a keynote sentence.
_PLAIN_WORD_RE = re.compile(r"^[A-Z][A-Z'&]*$")

# English function words. This is a GRAMMAR list, deliberately NOT a list of
# drawing phrases: a deny list of "COVER PLATE", "WALL COVERING" and friends
# would fix the two collisions we happen to have seen and miss the next one.
#
# Single-letter tokens are excluded on purpose. A lone "A" in a title block is
# a designator — "PHASE A", "KING TYPE A", "REV A" — not the English article,
# and counting it as one made the genuine Moxy title-block window read as prose
# (measured: Moxy pages 23/26/29/32 fell through to the fallback window until
# single letters were excluded).
FUNCTION_WORDS = frozenset(
    """
    AND AS AT BE BY FOR FROM IF IN INTO IS IT OF ON OR THE TO WITH
    WHERE WHEN THIS THAT THESE THOSE SHALL WILL NOT PER ARE WAS WERE
    """.split()
)


def _tokens_with_spans(text: str) -> List[Tuple[str, int, int]]:
    """(token, start, end) for every whitespace-delimited token, upper-cased."""
    return [
        (m.group(0).upper(), m.start(), m.end())
        for m in re.finditer(r"\S+", text)
    ]


def word_runs(text: str) -> List[List[Tuple[str, int, int]]]:
    """Maximal runs of consecutive PLAIN words, each as (token, start, end).

    A run is broken by any token that is not a plain word — a number, a sheet
    ID, an abbreviation ending in a period, a quoted string. On a title block
    the fields are short and constantly interrupted by exactly those tokens; a
    keynote is a long uninterrupted run of words.
    """
    runs: List[List[Tuple[str, int, int]]] = []
    current: List[Tuple[str, int, int]] = []
    for token, start, end in _tokens_with_spans(text):
        if _PLAIN_WORD_RE.match(token):
            current.append((token, start, end))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def function_word_count(run: Sequence[Tuple[str, int, int]]) -> int:
    """How many tokens of *run* are English function words."""
    return sum(1 for token, _s, _e in run if token in FUNCTION_WORDS)


# ---------------------------------------------------------------------------
# Prose thresholds
#
# Observed values, read off the four real plan sets — never fitted to a skip
# count or to a golden quantity:
#
#   Genuine title-block field values run 2 tokens between separators:
#     Moxy p0 tight window  "CS-00 COVER SHEET 25-13.01"   -> run ["COVER","SHEET"]
#     Moxy p1 tight window  "CS-01 SHEET INDEX 25-13.01"   -> run ["SHEET","INDEX"]
#     Bob's p0              "CS-1 COVER SHEET GN-1"        -> run ["COVER","SHEET"]
#   The longest run inside a CORRECT title-block window is 9 tokens
#     ("DATE SHEET TITLE PHASE A KING TYPE A GUESTROOM", Moxy p23 @ the tight
#     window) but it carries ZERO function words.
#   The keynote prose that caused the defect runs 9-10 tokens WITH function words:
#     "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING"  -> 9 tokens, ON+THE
#     "SWITCHES TOGETHER AT THIS LOCATION AT IF REQUIRED"         -> 8 tokens, 4 fn
#
# So neither signal alone separates the two populations — length alone would
# reject the correct Moxy window, function words alone would accept a short
# instruction. Requiring BOTH is what makes the test discriminate, and it is
# why the plan specifies two independent signals.
#
# MIN margins: 6 sits 3x above the observed 2-token genuine field value and 2-3
# tokens below the observed prose runs; 2 function words is one more than the
# single "AND" a compound title ("COVER SHEET AND DRAWING INDEX") can carry.
# ---------------------------------------------------------------------------
PROSE_MIN_RUN_TOKENS = 6
PROSE_MIN_FUNCTION_WORDS = 2


def prose_runs(text: str) -> List[List[Tuple[str, int, int]]]:
    """The runs in *text* that are sentence-shaped: long AND function-word-heavy."""
    return [
        run for run in word_runs(text)
        if len(run) >= PROSE_MIN_RUN_TOKENS
        and function_word_count(run) >= PROSE_MIN_FUNCTION_WORDS
    ]


def is_prose_shaped(text: str) -> bool:
    """True when *text* contains at least one sentence-shaped word run."""
    return bool(prose_runs(text))


def run_containing(
    text: str, start: int, end: int,
) -> Optional[List[Tuple[str, int, int]]]:
    """The plain-word run spanning the character range [start, end), or None.

    None means the match is not inside a plain-word run at all — it abuts
    punctuation or numerals on both sides, which is the shape of a title-block
    field value, not of a word inside a sentence.
    """
    for run in word_runs(text):
        if run[0][1] <= start and end <= run[-1][2]:
            return run
    return None


# ---------------------------------------------------------------------------
# Title-block field-label registry
#
# The labels a title block prints beside its values. Sourced from what the four
# real sets actually print (INV-00 §1c lists SHEET NO., JOB NO., DATE, SHEET
# TITLE and PHASE on Moxy; Crow prints "Sheet No. Sheet Title Issue Date Job
# No."; Moxy's cover prints "PROJECT NUMBER: SHEET TITLE: SHEET NUMBER:") plus
# the remaining ANSI/ASME Y14.1 fields, so a fifth drafting office is covered
# without touching this file.
# ---------------------------------------------------------------------------
_FIELD_LABEL_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("sheet_number", r"SHEET\s+(?:NO|NUM|NUMBER)\b\.?"),
    ("sheet_title", r"SHEET\s+TITLE"),
    ("drawing_number", r"(?:DWG|DRAWING)\s+(?:NO|NUM|NUMBER)\b\.?"),
    ("drawing_title", r"DRAWING\s+TITLE"),
    ("job_number", r"JOB\s+(?:NO|NUM|NUMBER)\b\.?"),
    ("project_number", r"PROJECT\s+(?:NO|NUM|NUMBER)\b\.?"),
    ("project_name", r"PROJECT\s+NAME"),
    ("drawn_by", r"DRAWN\s+BY"),
    ("checked_by", r"CHECKED\s+BY"),
    ("issue_date", r"ISSUE\s+DATE"),
    ("date", r"\bDATE\b"),
    ("scale", r"\bSCALE\b"),
    ("phase", r"\bPHASE\b"),
    ("revision", r"\bREVISIONS?\b"),
)
_FIELD_LABEL_RES: Tuple[Tuple[str, "re.Pattern"], ...] = tuple(
    (name, re.compile(pattern)) for name, pattern in _FIELD_LABEL_PATTERNS
)

# A sheet identifier as this codebase already defines one for the HYPHENATED
# convention: letters, a hyphen, digits — "ID-411", "A-101", "CS-00", "GN-1".
# The bare three-digit form ("A111") is deliberately NOT accepted here: without
# a hyphen it is indistinguishable from a wall type, a keynote number or a
# product code, so it is not evidence that a window is a title block.
_SHEET_ID_TOKEN_RE = re.compile(r"\b[A-Z]{1,3}-\d{1,4}\b")


def title_block_field_labels(text: str) -> Set[str]:
    """The names of the distinct title-block field labels present in *text*."""
    upper = text.upper()
    return {name for name, rx in _FIELD_LABEL_RES if rx.search(upper)}


def has_sheet_identifier(text: str) -> bool:
    """True when *text* carries a hyphenated sheet-ID token."""
    return bool(_SHEET_ID_TOKEN_RE.search(text.upper()))


# Two independent pieces of evidence are required, so neither a lone "DATE" in
# a revision note nor a lone sheet-ID cross-reference ("SEE A-101") can pass a
# window off as a title block.
MIN_TITLE_BLOCK_EVIDENCE = 2


def looks_like_title_block(text: str) -> bool:
    """True when *text* has the STRUCTURE of a title block.

    Two independent signals, per INV-00 §1d's "identify the title block by its
    own structure, not by a fixed fraction of the page":

      1. LABEL DENSITY — at least two pieces of field evidence, counting each
         distinct field label once and a hyphenated sheet-ID token once.
      2. LOW PROSE DENSITY — no sentence-shaped word run anywhere in the window.
         A title block is a grid of short labelled fields; a keynote is
         sentences, and it was 84 words of keynote that outvoted the title.
    """
    if not text or not text.strip():
        return False
    evidence = len(title_block_field_labels(text)) + (
        1 if has_sheet_identifier(text) else 0
    )
    if evidence < MIN_TITLE_BLOCK_EVIDENCE:
        return False
    return not is_prose_shaped(text)


# ---------------------------------------------------------------------------
# Match-position test (sheet_pass_matrix's keyword-context guard)
#
# Observed: the two live collisions are "…LIGHT SWITCH COVER PLATE INDICATING…"
# (9-token run, function words ON + THE) and a wall-covering finish note. Both
# are compounds inside sentences. Every genuine hit measured across the four
# sets sits in a 2-token run with zero function words.
# ---------------------------------------------------------------------------
MAX_TITLE_RUN_TOKENS = PROSE_MIN_RUN_TOKENS  # 6 — same boundary, one number


def is_title_shaped_match(text: str, start: int, end: int) -> bool:
    """True when the match at [start, end) sits in a TITLE position in *text*.

    A title-block field value is a short token run bounded by sheet IDs,
    numbers and colons. A keynote is a long run of words with function words in
    it. Both conditions must hold, which is what keeps this a structural test
    rather than a deny list of unlucky phrases.
    """
    run = run_containing(text, start, end)
    if run is None:
        # Not inside a plain-word run: the match abuts numerals or punctuation,
        # i.e. it is a field value ("SHEET TITLE: COVER").
        return True
    if len(run) > MAX_TITLE_RUN_TOKENS:
        return False
    return function_word_count(run) < PROSE_MIN_FUNCTION_WORDS
