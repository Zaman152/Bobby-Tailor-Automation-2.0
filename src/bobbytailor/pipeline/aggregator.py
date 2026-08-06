"""
Consolidate per-sheet takeoff items into project-level totals (StackCT summary format).
"""
import logging
import re
from collections import OrderedDict, defaultdict
from typing import Dict, List, Optional

from bobbytailor.pipeline.coverage import (
    ITEM_HUMAN_INPUT,
    ITEM_MEASURED,
    ITEM_NEEDS_REVIEW,
    ITEM_NOT_MEASURED,
    ITEM_STANDARD,
)
from bobbytailor.pipeline.provenance import provenance_of_row
# ONE definition of what a unit measures, shared with vision.fusion (C3b).
from bobbytailor.pipeline.units import (
    classes_conflict as _classes_conflict,
    unit_class as _unit_class,
)


def _unit_classes_conflict(original_unit, canonical_unit) -> bool:
    """True when canonicalisation would move a number across measure classes."""
    return _classes_conflict(_unit_class(original_unit), _unit_class(canonical_unit))

logger = logging.getLogger(__name__)

# Bucket ``source`` values that mean "this item was EXPECTED and never
# measured". Their quantity is ``None``, never the defaultdict's 0.0:
# ``manifest_missing`` shipped a numeric zero for a blank (INV-08 §2 row S12),
# which every consumer — takeoff.json, the exporter, scoring — read as "the
# building has none of this".
#: A name whose ONLY evidence was a library-named fallback reading too small to
#: be a real building quantity. The object was NOT measured, and saying so is
#: the whole point — see :func:`_degenerate_measure`.
LIBRARY_FALLBACK_UNMEASURED = "library_fallback_unmeasured"

#: A name whose ONLY evidence was a reading in a DIFFERENT measurement class
#: from the unit the row would publish in — a count named into an area object,
#: or the reverse. There is no conversion between them, so the object was not
#: measured in this unit and the row says so (C3b).
UNIT_CLASS_CONFLICT_UNMEASURED = "unit_class_conflict_unmeasured"

#: A name whose ONLY evidence was a count taken off a sheet this run classified
#: as DETAILS. A details sheet draws how a thing is built, not how many are
#: installed, so the reading counts detail drawings rather than objects: a count
#: of stair details is not a count of stairs. The number is withheld and the row
#: says so — see the withheld-detail-count block in :func:`aggregate_takeoff`.
DETAIL_SHEET_COUNT_UNMEASURED = "detail_sheet_count_unmeasured"

_UNMEASURED_SOURCES = frozenset({
    "manifest_missing", "expected_not_measured", LIBRARY_FALLBACK_UNMEASURED,
    UNIT_CLASS_CONFLICT_UNMEASURED, DETAIL_SHEET_COUNT_UNMEASURED,
})

# ─── What corroborated a count (28-01 records it, this layer acts on it) ─────
#
#: The verdicts :func:`calculator._count_corroboration` records on a count row,
#: ranked. A HIGHER rank wins a combination, which gives the roll-up two
#: properties at once: one corroborated contributing row vouches for the whole
#: bucket, and among uncorroborated rows the more specific verdict survives to
#: be reported (`detail_sheet_only` says which sheet kind; `none` only shrugs).
#: This table is the ONLY expression of the precedence — see
#: :func:`_stronger_corroboration`, its only reader.
_CORROBORATION_RANK = {
    "none": 0,
    "detail_sheet_only": 1,
    "schedule": 2,
    "geometry": 3,
}

#: The verdicts that mean something outside the reading itself backs the count:
#: a table PRINTED on the plans, or geometry that recorded where the instances
#: are. A description read off a drawing is neither.
_CORROBORATED = frozenset({"schedule", "geometry"})


def _stronger_corroboration(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    """Combine two corroboration verdicts. THE one place the precedence lives.

    Modelled on :func:`_worse_conf`, and deliberately the mirror of it: the
    worst confidence wins there because confidence is a claim about certainty,
    while the BEST corroboration wins here because corroboration is evidence —
    one row that was backed by a printed schedule vouches for the object even
    if a weaker reading of the same object also landed in the bucket.

    ``None`` means "no count row has contributed yet" and is never the answer
    when a real verdict is available, in either argument order. An empty string
    is treated the same way. An unrecognised verdict ranks with ``none``, so a
    string this function has never seen can never be mistaken for corroboration.
    """
    a = (current or "").strip() or None
    b = (incoming or "").strip() or None
    if a is None:
        return b
    if b is None:
        return a
    return b if _CORROBORATION_RANK.get(b, 0) > _CORROBORATION_RANK.get(a, 0) else a


def _count_is_uncorroborated(bucket: Dict) -> bool:
    """True when a count contributed to this bucket and nothing backed it.

    The two-state test the whole rule turns on. An UNSET verdict is not an
    uncorroborated one: an area, a length, a blank and the injected Mobilization
    convention all carry no verdict at all, and reading their silence as "no
    evidence" would flag the entire take-off instead of the count rows this
    exists for.
    """
    verdict = (bucket.get("count_corroboration") or "").strip()
    return bool(verdict) and verdict not in _CORROBORATED


def _new_bucket() -> Dict:
    """One project-level bucket, before any row has contributed to it."""
    return {
        "quantity": 0.0,
        "unit": "",
        "source_sheets": set(),
        "source_rows": [],
        "item_type": "",
        "needs_review": False,
        "confidence": None,
        "review_reasons": set(),
        "source": "",
        # Where a legend-backed quantity actually came from (C4). Only
        # "human_input" — an estimator's own take-off, ingested from a human
        # input file — may publish as HUMAN INPUT; a schedule the app read off
        # the plans is a machine measurement.
        "legend_origin": "",
        "auto_verified": True,   # AND of contributing rows; only meaningful with rows
        "has_rows": False,
        # What backed the COUNT rows that built this bucket, rolled up from
        # their recorded verdicts (28-01). ``None`` means no count row has
        # contributed — distinguishable from ``"none"``, which means one did
        # and nothing corroborated it.
        "count_corroboration": None,
    }

#: Units in which a building quantity is counted, not dimensioned. A value in
#: these units below one whole unit is not a small measurement — it is a
#: mis-scaled or mis-typed one.
_MEASURE_UNITS = frozenset({"SF", "LF", "SY", "CY", "SQ", "FT", "CF"})


def _degenerate_measure(qty, unit) -> bool:
    """True when a quantity is too small to be a real measured building figure.

    No drawing carries 0.15 square feet of floor finish or 0.02 linear feet of
    handrail. On Crow all three such rows came from the same place: a printed
    DETAIL dimension ("TAPERED CONCRETE SLAB", 12 in; "4\\"-0\\"" curb width;
    "1 1/2\\" O.D. HANDRAIL") was pushed through the slab-volume calculator as
    though the dimension were an area, and the resulting cubic yards were
    published under an SF/LF unit.
    """
    if (unit or "").strip().upper() not in _MEASURE_UNITS:
        return False
    try:
        return abs(float(qty)) < 1.0
    except (TypeError, ValueError):
        return False

# A learned expectation weaker than this is a one-off, not a pattern. Same
# threshold the learned-context prompt renderer applies, so an item cannot be
# "expected enough to enumerate" and "too weak to mention" at once.
_MIN_LEARNED_EXPECTATION = 0.5


#: Endings that make a trailing ``s`` part of the SINGULAR word rather than a
#: plural marker. Stripping them would fold `Glass`->`Glas`, `Radius`->`Radiu`,
#: `Axis`->`Axi` — a rename, not a form fold.
_NOT_A_PLURAL_ENDINGS = ("ss", "us", "is")

#: Stems that take ``-es`` rather than ``-s`` in the plural (`Box`/`Boxes`,
#: `Arch`/`Arches`). Deliberately EXCLUDES a stem ending in ``s``: `Base`/`Bases`
#: and `Bus`/`Buses` are indistinguishable without a lexicon, and this function
#: has none — so `-ses` falls through to the plain ``s`` rule, which folds
#: `Bases`->`Base` correctly and merely fails to fold `Buses`->`Bus`. Failing to
#: fold is the status quo and is safe; folding two different words together is
#: the defect this whole boundary exists to prevent.
_ES_PLURAL_STEM_ENDINGS = ("x", "z", "ch", "sh")

#: A stem shorter than this is not a word this function is willing to invent.
#: `Gas` must not become `Ga`, `Bus` must not become `Bu`.
_MIN_PLURAL_STEM_LEN = 3


def _plural_stem(token: str) -> str:
    """Reduce ONE squashed alphanumeric token to a plural-insensitive stem.

    A PURE string function: no lexicon, no external data, no similarity
    measure. The only transformation it can perform is removing a trailing
    plural suffix from an otherwise character-identical stem, which is a
    transformation of the same class as the spacing/case folding
    :func:`canonical_library_name` already performs and is in-boundary under
    that function's stated contract (24-RESEARCH §4.3, pitfall 5).

    What it deliberately CANNOT do is map one word to a different word. There
    is no alias table, no edit distance and no stemming lexicon here, because
    any of those would turn `Dock Bumper` into `Bollards` — a strictly worse
    defect than the singular/plural split it would appear to fix.

    Degenerate inputs (empty, single character, a stem that would vanish) are
    returned unchanged rather than collapsed to nothing.
    """
    word = token or ""
    if len(word) <= _MIN_PLURAL_STEM_LEN or not word.endswith("s"):
        return word
    if word.endswith("es"):
        stem = word[:-2]
        if (len(stem) >= _MIN_PLURAL_STEM_LEN
                and stem.endswith(_ES_PLURAL_STEM_ENDINGS)):
            return stem
    if word.endswith(_NOT_A_PLURAL_ENDINGS):
        return word
    stem = word[:-1]
    return stem if len(stem) >= _MIN_PLURAL_STEM_LEN else word


def _norm_item_key(name: str) -> str:
    """Loose canonical key for 'have we already got a row for this?'.

    Plural-aware since 24-03. This key IS the bucket identity that decides
    whether two rows are one item, and collapsing separators and case but not
    plurals is exactly why a measured `Bollard` row and a blank `Bollards` row
    stood side by side, unreconciled, in BOTH saved paid runs. Two genuinely
    different objects still key apart — the fold is per-token and suffix-only.
    """
    squashed = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()
    if not squashed:
        return squashed
    return " ".join(_plural_stem(tok) for tok in squashed.split())

# Confidence ordering, worst -> best. Used to roll a bucket's confidence up to
# the lowest (most cautious) confidence among the rows that built it.
_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}


def _worse_conf(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the lower-confidence of two values (None means 'unknown/ignore')."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _CONF_ORDER.get(a, 1) <= _CONF_ORDER.get(b, 1) else b


def _clean_legend_label(label: str) -> str:
    """Normalise whitespace in a companion take-off legend label, preserving it
    otherwise verbatim so the app reports the estimator's own item names."""
    return re.sub(r"\s+", " ", (label or "").strip())


ITEM_NAME_MAP = [
    # ── Civil / Site ──────────────────────────────────────────────────────────
    (r"bollard", "Bollards", "EA"),
    (r"catch basin|bb ci|drop inlet|curb inlet|storm inlet", "Catch Basins", "EA"),
    (r"manhole|\bmh\b|access structure", "Manholes", "EA"),
    (r"headwall|flared end|end section|\bfes\b|wingwall", "Headwall", "EA"),
    (r"trench drain|channel drain|slot drain|linear drain", "Trench Drain", "LF"),
    (r"gas.*pip|gas\s*pipe|black\s*steel.*pip|csst.*pip|gas\s*line", "Gas Piping", "LF"),
    # Fire hydrant before conduit/storm to avoid \bfh\b ambiguity
    (r"fire.*hydrant|\bfh\b", "Fire Hydrants", "EA"),
    (r"area.*drain|floor.*drain|cleanout", "Area Drain / Cleanout", "EA"),
    # Conduit/duct before storm pipe to prevent PVC conduit matching \bpvc\b
    (r"\bconduit\b|\bemt\b|wireway|cable.*tray|raceway\b", "Conduit LF", "LF"),
    (r"duct.*lf|ductwork|\bduct\b(?!.*liner)", "Duct LF", "LF"),
    # Sanitary pipe BEFORE storm pipe so sanitary descriptions don't collapse to Storm Pipe
    (r"sanitary.*pipe|sanitary.*sewer|\bss\s*pipe\b", "Sanitary Pipe", "LF"),
    # Storm pipe — match PVC/HDPE/RCP only in piping context; conduit must be excluded above
    (r"pvc.*pipe|pvc.*sch|pvc.*sewer|\bhdpe\b|\brcp\b|\bdip\b|storm pipe|storm sewer|culvert|sanitary sewer", "Storm Pipe", "LF"),
    (r"water.*main|water.*line|domestic.*water", "Water Main", "LF"),
    (r"guard.*rail|guardrail|barrier.*rail|w.?beam", "Guard Rail", "LF"),
    (r"hand.*rail|handrail|stair.*rail|pipe.*rail", "Hand Rail", "LF"),
    (r"strip|pavement.*mark|lane.*mark", "Striping", "LF"),
    (r"curb.*gutter|curb.*and.*gutter|\bcurb\b", "Curb & Gutter", "LF"),
    (r"\basphalt\b|\bhma\b|blacktop", "Asphalt", "SF"),
    # Concrete pavement — match common abbreviations and context phrases
    (r"concrete.*pavement|\bpcc\b|\bflatwork\b|concrete.*drive|concrete.*walk|concrete.*sidewalk", "Concrete Pavement", "SF"),
    (r"detention|retention.*pond|bioswale", "Stormwater Basin", "EA"),
    (r"\bfence\b|chain.*link|ornamental.*fence", "Fence", "LF"),
    (r"grading|cut.*fill|mass.*grade", "Grading", "CY"),
    (r"dumpster.*enclos", "Dumpster Enclosure", "EA"),

    # ── Structure ─────────────────────────────────────────────────────────────
    (r"column.*h.*\d+", "Columns", "EA"),
    (r"\bcolumn\b(?!.*h.*\d)", "Columns", "EA"),
    (r"sealed.*concrete|polished.*concrete|slab.on.grade|\bsog\b|concrete.*floor", "Sealed Concrete", "SF"),
    (r"exposed.*struct|exposed.*deck|open.*web.*joist|bar.*joist", "Exposed Structure", "SF"),
    (r"exterior.*soffit|canopy.*soffit", "Exterior Soffit", "SF"),
    # Tilt-up: interior variants before exterior catch-all
    (r"internal.*tilt|interior.*tilt|int.*tilt.*up", "Interior Tilt Up Walls", "SF"),
    (r"tilt.*up.*wall|tiltup.*wall|precast.*panel|ext.*tilt", "Exterior Tilt Up Wall", "SF"),
    # CMU paint BEFORE CMU Wall (both match \bcmu\b; paint is more specific)
    (r"cmu.*paint|paint.*cmu|block.*paint|paint.*block|masonry.*paint|paint.*masonry|epoxy.*block", "CMU Paint", "SF"),
    (r"\bcmu\b|masonry.*wall|block.*wall|concrete.*masonry", "CMU Wall", "SF"),
    (r"\blintels?\b|steel.*lintel|angle.*lintel", "Lintels", "LF"),
    (r"stair", "Stairs", "EA"),
    (r"\bladder\b", "Ladder", "EA"),
    (r"\blift\b|elevator", "Lift", "EA"),
    (r"mobiliz", "Mobilization", "EA"),

    # ── Architectural ─────────────────────────────────────────────────────────
    (r"flooring|floor tile|\blvt\b|\bvct\b|\bcarpet\b|luxury.*vinyl|ceramic.*tile|porcelain.*tile", "Flooring", "SF"),
    # Drywall Ceiling BEFORE Ceiling Grid — suspended/gyp ceiling is distinct from ACT tile grid
    (r"suspended.*ceil|gyp.*ceil|acoustical.*ceil.*grid", "Drywall Ceiling", "SF"),
    (r"ceiling.*tile|\bact\b|t.bar.*ceil|acoustic.*ceil|lay.in.*ceil", "Ceiling Grid", "SF"),
    (r"drywall|\bgwb\b|gypsum.*board|sheetrock|wallboard", "Drywall", "sheets"),
    (r"\bpaint\b|primer|finish.*coat|epoxy.*floor", "Paint", "gallons"),
    (r"\beifs\b|exterior.*insulation|dryvit|synthetic.*stucco", "EIFS", "SF"),
    (r"\bcanopy\b|metal.*canopy|entrance.*canopy|shade.*canopy", "Canopy", "SF"),
    (r"insulation|\bbatt\b|rigid.*insul|spray.*foam|r-\d+", "Insulation", "SF"),
    # Dock doors/levelers BEFORE generic door catch-all
    (r"dock.*door|overhead.*door|coiling.*door", "Dock Doors", "EA"),
    (r"dock.*leveler|dock.*seal|dock.*bumper", "Dock Leveler", "EA"),
    # Door type separation — Frame-HM and specific types BEFORE generic door catch-all
    (r"hollow.?metal.*frame|frame.*hollow.?metal|frame.*\bhm\b|\bhm\b.*frame", "Frame-HM", "EA"),
    (r"door.*hollow.?metal|hollow.?metal.*door|hm.*door(?!.*frame)|door.*\bhm\b(?!.*frame)", "Doors-HM", "EA"),
    (r"door.*\bwood\b|\bwood\b.*door|\bwd\b.*door|door.*\bwd\b", "Doors-WD", "EA"),
    (r"door.*alum|alum.*door|\bal\b.*door|door.*\bal\b", "Doors-AL", "EA"),
    # Glass door BEFORE generic catch-all
    (r"glass.*door|aluminum.*storefront.*door", "Doors-GL", "EA"),
    # Generic door catch-all — must follow specific types above
    (r"door(?!.*frame)", "Doors", "EA"),
    # Storefront/Curtain Wall AFTER all door patterns so door-bearing descriptions resolve to door types
    (r"storefront|curtain.*wall|window.*wall", "Storefront/Curtain Wall", "SF"),
    (r"window|glazing|storefront.*glass", "Windows", "EA"),
    (r"gauge.*metal|metal.*gauge", "Gauge Metal", "EA"),
    (r"interior.*concrete.*wall", "Interior Concrete Walls", "SF"),

    # ── MEP / Fire Protection ─────────────────────────────────────────────────
    # Fire suppression before generic MEP entries
    (r"sprinkler.*head|fire.*sprinkler|pendent", "Sprinkler Heads", "EA"),
    (r"smoke.*detector|fire.*alarm|horn.*strobe", "Fire Alarm", "EA"),
    # HVAC subtypes — VAV/RTU/unit heater more specific than generic AHU
    (r"\bvav\b|variable.*air.*volume", "VAV Boxes", "EA"),
    (r"unit.*heater|cabinet.*heater", "Unit Heater", "EA"),
    (r"refrigerant.*line|ref.*line|line.*set", "Refrigerant Piping", "LF"),
    (r"thermostat|t-stat", "Thermostat", "EA"),
    (r"panel|mcc\b|switchboard|distribution.*board", "Electrical Panels", "EA"),
    (r"light.*fix|fixture.*light|\bled\b|luminaire", "Lighting Fixtures", "EA"),
    (r"receptacle|outlet\b", "Receptacles", "EA"),
    (r"exit sign", "Exit Signs", "EA"),
    (r"fan coil|\bfcu\b", "Fan Coil Units", "EA"),
    (r"air handler|\bahu\b", "Air Handling Units", "EA"),
    # RTU AFTER Air Handling Units so "air handling unit" descriptions don't collapse to RTU
    (r"\brtu\b|rooftop.*unit|packaged.*unit", "RTU", "EA"),
    (r"exhaust fan", "Exhaust Fans", "EA"),
]


def _extract_spec_for_name(canonical: str, description: str) -> str:
    if "Column" in canonical or "Ladder" in canonical:
        m = re.search(r"h[-\s]*(\d+\'?\s*\d*\"?)", description, re.IGNORECASE)
        if m:
            return f"H-{m.group(1)}"
    if "Pipe" in canonical:
        m = re.search(r'(\d+)\s*(?:in|")', description, re.IGNORECASE)
        if m:
            return f'{m.group(1)}"'
    return ""


def normalize_item_name(description: str, item_type: str, unit: str, learned=None) -> tuple:
    d = (description or "").lower()
    # Learned vocabulary FIRST (V3-LEARN-02): the learned_vocabulary rows
    # (learning_vocabulary table, distilled from prior human corrections)
    # are consulted via an exact/normalized match BEFORE the static regex
    # list, so a correction made once never recurs. On a miss the static
    # ITEM_NAME_MAP below runs
    # unchanged: it is the cold-start floor and is never deleted, and its
    # carefully sequenced first-match-wins ordering (20-05/20-09 decisions)
    # is never disturbed by the learned lookup.
    if learned is not None:
        try:
            hit = learned.lookup_name(description)
        except Exception:  # noqa: BLE001 — learning must never break naming
            hit = None
        if hit is not None:
            learned_name, learned_unit = hit
            return learned_name, (learned_unit or unit or "EA")
    for pattern, name, default_unit in ITEM_NAME_MAP:
        if re.search(pattern, d, re.IGNORECASE):
            spec_match = _extract_spec_for_name(name, d)
            if spec_match:
                name = f"{name}-{spec_match}"
            return name, default_unit
    # Unnamed clusters must stay DISTINCT. A generic item_type ("component" /
    # "general") is NOT a name — collapsing every unnamed SYM-* cluster to a
    # single "Component" bucket silently merges physically distinct clusters and
    # buries their individual counts. Prefer the row's own description (the
    # candidate_id or its contained text) so two unnamed clusters surface as two
    # flagged rows carrying their own counts, never one "Component" blob.
    it = (item_type or "").strip().lower()
    if it and it not in ("component", "general"):
        canonical = item_type.replace("_", " ").title()
    else:
        desc_name = (description or "").strip()
        if desc_name:
            canonical = desc_name[:40]
        elif item_type:
            canonical = item_type.replace("_", " ").title()
        else:
            canonical = "Component"
    return canonical, unit or "EA"


# Standard estimating line items that appear on virtually every commercial
# construction take-off but are never *drawn* on the plans (they are scope/
# logistics conventions). They are injected once per project at quantity 1 so
# the take-off reflects how an estimator actually bids work. Only added when a
# real take-off was produced (calculated_items non-empty) and not already
# present from the drawings/notes. Kept deliberately small and generic.
STANDARD_LINE_ITEMS: List[Dict] = [
    {"name": "Mobilization", "unit": "EA", "quantity": 1},
]


def _inject_standard_line_items(buckets: Dict[str, Dict]) -> None:
    """Add universal estimating line items (e.g. Mobilization) if absent.

    Matching is by canonical name so an item already extracted from the
    drawings/notes (e.g. a "MOBILIZATION" note) is never double-counted.
    """
    existing_norm = {re.sub(r"[-_/]+", " ", k.lower()).strip() for k in buckets}
    for std in STANDARD_LINE_ITEMS:
        norm = re.sub(r"[-_/]+", " ", std["name"].lower()).strip()
        if norm in existing_norm:
            continue
        bucket = buckets[std["name"]]
        bucket["quantity"] = float(std["quantity"])
        bucket["unit"] = std["unit"]
        bucket["item_type"] = "standard_line_item"
        bucket["source_rows"].append({
            "sheet": None,
            "qty": float(std["quantity"]),
            "description": f"{std['name']} (standard estimating line item)",
            "formula": "standard_line_item",
        })


def canonical_library_name(name: str, unit: str = "") -> tuple:
    """Route a library-verbatim name through THE one canonicalisation (SP-7a).

    The saved Crow run emitted ``Guardrail`` / ``Handrail`` while ITEM_NAME_MAP
    canonicalises both to their spaced forms — because the library-verbatim
    naming path bypassed the map entirely. One canonical name FORM, one place
    that decides it: when a map rule matches AND its canonical name is the
    same words as the library name (differing only in spacing / separators /
    case), the map's form wins. A genuinely different name — novel plan
    vocabulary like "Fiber Cement Panel", or the library's own more-specific
    "Tilt Up Wall" — is kept verbatim: this normalises the FORM of one item's
    name, it never renames one item to another (the mangling the
    legend-verbatim comment below warns about). The library's own unit always
    wins when present.

    24-03 widens "the same words" by EXACTLY one form: a trailing plural. The
    agreement test compares the plural-insensitive STEMS of both sides, so
    `Bollard` binds ITEM_NAME_MAP's `Bollards` the same way `Guardrail` already
    bound `Guard Rail`. Nothing else about the contract moves: the function
    still accepts a map rule only when its canonical name is the same words as
    the input, now also modulo a trailing plural. A synonym is NOT a plural —
    `Dock Bumper` still resolves to itself and never to `Dock Leveler` or
    `Bollards`, and :func:`_plural_stem` is deliberately incapable of mapping
    one word to a different word (24-RESEARCH pitfall 5).
    """
    hay = (name or "").lower()
    squashed = re.sub(r"[^a-z0-9]+", "", hay)
    if not squashed:
        return name, unit
    squashed_stem = _plural_stem(squashed)
    for pattern, canon, default_unit in ITEM_NAME_MAP:
        if re.search(pattern, hay, re.IGNORECASE):
            canon_stem = _plural_stem(re.sub(r"[^a-z0-9]+", "", canon.lower()))
            if canon_stem == squashed_stem:
                return canon, (unit or default_unit)
    return name, unit


# ── THE naming-authority precedence (24-03) ──────────────────────────────────
#
# Three authorities used to reach publication independently, with no arbiter,
# and the two saved paid runs show the cost: the SAME 56-EA candidate published
# as `Bollard` (source: learned) in one run and `Dock Bumper` (source: library)
# in the other. Nothing decided between them; whichever branch happened to fire
# first named the row. There is now exactly ONE function that decides which
# authority names a row, and one declared order it obeys.

#: The drawing's own printed schedule/legend. Published VERBATIM.
NAME_AUTHORITY_LEGEND = "plan_schedule_legend"
#: The user's own object manifest. Published VERBATIM.
NAME_AUTHORITY_MANIFEST = "manifest"
#: A correction a real estimator made on this project, distilled into
#: ``learning_vocabulary`` with ``source='human'``.
NAME_AUTHORITY_LEARNED_HUMAN = "learned_human"
#: The component library harvested off the plans, merged with the project
#: vocabulary.
NAME_AUTHORITY_LIBRARY = "library"
#: A name ``record_ai_manifest`` wrote into ``learning_vocabulary`` with
#: ``source='ai'`` — a model's own answer, persisted. This is the tier the F1
#: evidence indicts.
NAME_AUTHORITY_LEARNED_AI = "learned_ai"
#: The vision label / static-map reading, kept verbatim.
NAME_AUTHORITY_VISION = "vision"

#: THE precedence, most authoritative FIRST. Declared once; every publication
#: path routes through :func:`resolve_published_name`.
#:
#: 24-RESEARCH §4.3.2 states the order as ``library > learned > vision``. That
#: is the order this tuple encodes for the learned store's **AI** tier, which
#: is the tier the evidence indicts (`record_ai_manifest` writes a model's own
#: manifest name into the store, and a persisted model answer is still a model
#: answer). It is NOT applied to the store's **human** tier: `learning_vocabulary`
#: carries two provenances (`store.py:142`) and the store's own retrieval already
#: ranks ``source='human'`` above ``source='ai'`` — its documented "human-wins
#: invariant". Demoting a human correction below a machine-harvested library
#: would break V3-LEARN-02 ("a correction made once never recurs") and would put
#: the LLM-derived half of the project vocabulary — the very list defect F3 shows
#: is re-derived differently every run — above a human's explicit rename.
NAME_AUTHORITY_PRECEDENCE = (
    NAME_AUTHORITY_LEGEND,
    NAME_AUTHORITY_MANIFEST,
    NAME_AUTHORITY_LEARNED_HUMAN,
    NAME_AUTHORITY_LIBRARY,
    NAME_AUTHORITY_LEARNED_AI,
    NAME_AUTHORITY_VISION,
)

_NAME_AUTHORITY_RANK = {a: i for i, a in enumerate(NAME_AUTHORITY_PRECEDENCE)}

#: Authorities whose name is published exactly as supplied. A legend label and
#: a manifest entry are a human's or the drawing's OWN words, and rewriting them
#: is the mangling the legend-verbatim comment in :func:`aggregate_takeoff`
#: warns about ("Fiber Cement Panel" SF -> "Electrical Panels" EA).
_VERBATIM_NAME_AUTHORITIES = frozenset({
    NAME_AUTHORITY_LEGEND, NAME_AUTHORITY_MANIFEST,
})

#: The published ``source`` marker per authority. Deliberately the EXISTING
#: field and the EXISTING strings (T-24-11): a reader can already tell a library
#: bind from a learned recall from a vision label, and inventing a parallel
#: provenance channel would leave two that could disagree. Both learned tiers
#: publish as ``learned`` — the tier is an arbitration input, not a new client
#: -visible vocabulary.
_PUBLISHED_SOURCE_BY_AUTHORITY = {
    NAME_AUTHORITY_LEGEND: "plan_schedule_legend",
    NAME_AUTHORITY_MANIFEST: "manifest",
    NAME_AUTHORITY_LEARNED_HUMAN: "learned",
    NAME_AUTHORITY_LIBRARY: "library",
    NAME_AUTHORITY_LEARNED_AI: "learned",
    NAME_AUTHORITY_VISION: "vision",
}


def resolve_published_name(candidates) -> Optional[tuple]:
    """THE arbiter. Return ``(name, unit, authority)`` for the winning authority.

    *candidates* is an iterable of ``(authority, name, unit)`` triples — every
    name the row could carry, tagged with where it came from. The highest-ranked
    authority in :data:`NAME_AUTHORITY_PRECEDENCE` that offered a non-blank name
    wins; unknown authorities and blank names are ignored. Returns ``None`` when
    nothing offered a name.

    The winner is routed through :func:`canonical_library_name` exactly once, so
    the plural fold happens in ONE place — except for the verbatim authorities,
    whose whole contract is that their words are reproduced untouched.

    The winner's own unit is returned unchanged. This function arbitrates NAMES;
    a unit that travels with a name is C3b's problem and is checked separately
    by the caller, which is why the unit :func:`canonical_library_name` would
    have supplied is deliberately discarded here.
    """
    best = None
    for authority, name, unit in candidates or ():
        rank = _NAME_AUTHORITY_RANK.get(authority)
        if rank is None or not str(name or "").strip():
            continue
        if best is None or rank < best[0]:
            best = (rank, authority, name, unit)
    if best is None:
        return None
    _, authority, name, unit = best
    if authority not in _VERBATIM_NAME_AUTHORITIES:
        name, _ = canonical_library_name(name, unit)
    return name, unit, authority


def _learned_name_authority(learned, description) -> str:
    """Which TIER of the learned store produced the name for *description*.

    ``learning_vocabulary`` holds two provenances (``store.py:142``):
    ``'human'``, a correction distilled from a real estimator's edit, and
    ``'ai'``, a name :func:`record_ai_manifest` persisted from a model's own
    manifest. :meth:`LearnedContext.lookup_name` returns only ``(name, unit)``,
    so the winning row is re-found here the same way ``_vocab_index`` finds it:
    rows arrive human-first / weight-DESC, so the FIRST row whose normalised
    ``raw_pattern`` matches is the one that answered.

    Unknown provenance resolves to the HUMAN tier. That is the store's own
    schema default (``source TEXT NOT NULL DEFAULT 'human'``) and the
    conservative reading: an authority is demoted on evidence, never on
    assumption. A caller that supplies no ``vocabulary`` at all (every test
    double, and any future context object) therefore keeps exactly the
    precedence it had before this change.
    """
    try:
        key = re.sub(r"\s+", " ", str(description or "").strip()).lower()
        if not key:
            return NAME_AUTHORITY_LEARNED_HUMAN
        for row in getattr(learned, "vocabulary", None) or []:
            if not isinstance(row, dict):
                continue
            if not str(row.get("canonical_name") or "").strip():
                continue
            raw = re.sub(r"\s+", " ", str(row.get("raw_pattern") or "").strip()).lower()
            if raw != key:
                continue
            if str(row.get("source") or "").strip().lower() == "ai":
                return NAME_AUTHORITY_LEARNED_AI
            return NAME_AUTHORITY_LEARNED_HUMAN
    except Exception:  # noqa: BLE001 — provenance must never break naming
        return NAME_AUTHORITY_LEARNED_HUMAN
    return NAME_AUTHORITY_LEARNED_HUMAN


def _resolve_library_name(description: str, library) -> Optional[tuple]:
    """Resolve a raw description to a component-library ``(name, unit)`` via aliases.

    Thin wrapper over :func:`component_library.resolve_library_name` — imported
    lazily and fully guarded so a missing/empty library (or any error) falls
    through to the existing naming path unchanged (additive-only).
    """
    if not library:
        return None
    try:
        from bobbytailor.deterministic.component_library import resolve_library_name
        return resolve_library_name(description, library)
    except Exception:  # noqa: BLE001 — library resolution must never break naming
        return None


def _expected_items_without_a_manifest(learned, library) -> "OrderedDict":
    """Line items this run had reason to expect, from evidence other than a manifest.

    The completeness guarantee used to be gated on ``if manifest:``, so in
    **plans-only mode — the mission mode — nothing enumerated what was expected**
    and an unmeasured item had no row of any kind (INV-08 §2 row S13). That is
    why Bob's civil, elevation and lintel items are absent rather than blank:
    ``Lintels`` is right there in the harvested component library with basis
    ``linear``, and the take-off never mentions it.

    Two sources, both already available at this call site:

    * ``learned.expected_items`` — items seen in prior VERIFIED runs of this
      project type. Filtered at the same expectation threshold the prompt
      renderer uses, so an item cannot be strong enough to enumerate here and
      too weak to mention there.
    * ``library`` — the deterministic component library merged with the LLM
      project vocabulary (``pipeline._project_vocabulary``; the same object
      ``pdf_analyzer`` and ``scraper`` already pass in). Only entries carrying a
      measure ``basis`` count: a basis is the app's own statement that it knows
      what measuring this item would MEAN, which is precisely what makes its
      absence a gap rather than noise. Measured on the real sets this is 10
      entries for Bob's and 25 for Crow — bounded, not a flood.

    Returns:
        ``OrderedDict`` of canonical name -> ``{unit, measure, expected_from}``,
        in a deterministic order (learned first, then library) so two runs over
        the same inputs produce the same take-off.
    """
    out: "OrderedDict" = OrderedDict()

    for row in getattr(learned, "expected_items", None) or []:
        if not isinstance(row, dict):
            continue
        try:
            if float(row.get("expectation") or 0.0) < _MIN_LEARNED_EXPECTATION:
                continue
        except (TypeError, ValueError):
            continue
        name = str(row.get("item_name") or "").strip()
        if not name:
            continue
        # Canonicalised on READ (24-03, T-24-10). An expected-item placeholder
        # must carry the SAME canonical form a measured row of the object
        # would, or a learned `Metal Downspout` spawns a phantom NOT-MEASURED
        # row beside a measured `Metal Downspouts`. Same rule the library
        # branch below has applied since SP-7a; the learned branch was simply
        # never routed through it.
        name, _ = canonical_library_name(name, str(row.get("unit") or ""))
        if _norm_item_key(name) in {_norm_item_key(k) for k in out}:
            continue
        out[name] = {
            "unit": str(row.get("unit") or "").strip(),
            "measure": str(row.get("basis") or row.get("measure") or "").strip(),
            "expected_from": "learned",
        }

    for entry in library or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        basis = str(entry.get("basis") or "").strip()
        if not name or not basis:
            continue
        # SP-7a: an expected-item placeholder must carry the SAME canonical
        # form a measured row of the object would — otherwise an unspaced
        # library "Guardrail" spawns a phantom NOT-MEASURED row beside the
        # measured "Guard Rail" one.
        name, _ = canonical_library_name(name, str(entry.get("unit") or ""))
        if _norm_item_key(name) in {_norm_item_key(k) for k in out}:
            continue
        out[name] = {
            "unit": str(entry.get("unit") or "").strip(),
            "measure": basis,
            "expected_from": "library",
        }

    return out


# ── A blank expected row never stands unexplained beside a measured one ──────
#
# 24-03 Task 3. With the plural-aware `_norm_item_key`, a measured `Bollard` and
# an expected `Bollards` are ONE bucket and the blank is correctly suppressed.
# What folding cannot fix is the case the evidence also shows: a measured
# `Dock Bumper 56 EA` beside a blank `Bollards`. Those are two different names
# and merging them is exactly the rename this phase forbids — it is how a
# genuinely distinct object disappears. But leaving them unmarked is the defect
# 24-RESEARCH §4.3.4 names: the client reads "bollards were not found".
#
# So neither row is merged and neither is deleted. BOTH are annotated, and a
# human closes the loop. Same shape as Phase 23's "a blank is never a zero":
# move the information to where it reads correctly rather than removing it.

#: How many partner names a cross-reference spells out before falling back to a
#: count. The count is ALWAYS exact — the cap trims the list, never the truth.
_CROSS_REFERENCE_NAMES_SHOWN = 3

#: Naming authorities whose answer is a HYPOTHESIS about identity rather than
#: evidence of it. A legend label and a manifest entry are the drawing's or the
#: user's own printed words — if one of those had been the bollards, the name
#: itself would say so and `_norm_item_key` would already have reconciled it. A
#: `vision` row named from a bare candidate id is unnamed geometry, which is
#: 24-04's ledger and not a naming question. What remains — a library alias
#: resolution and a learned-store recall — is precisely the class of answer that
#: can be confidently wrong about WHICH object was measured.
_HYPOTHESIS_NAME_SOURCES = frozenset({"library", "learned"})


def _library_basis_by_key(library) -> Dict[str, str]:
    """Measure basis per canonical name key, from the same list expected rows use.

    A measured bucket's ``item_type`` comes from the reading (``component``,
    ``concrete_slab``) while an expected row's comes from the library's
    ``basis`` (``count``, ``wall_area``). Comparing those two directly would be
    comparing two different vocabularies, so the measured row's basis is looked
    up in the SAME library that produced the expected row — basis against basis.
    """
    out: Dict[str, str] = {}
    for entry in library or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        basis = str(entry.get("basis") or "").strip()
        if not name or not basis:
            continue
        out.setdefault(_norm_item_key(canonical_library_name(name, "")[0]), basis)
    return out


def _name_list(names: List[str]) -> str:
    shown = names[:_CROSS_REFERENCE_NAMES_SHOWN]
    text = ", ".join(repr(n) for n in shown)
    extra = len(names) - len(shown)
    return "%s and %d more" % (text, extra) if extra > 0 else text


def _cross_reference_unreconciled(
    buckets: Dict[str, Dict], blanks: List[tuple], measured: List[tuple],
    library,
) -> None:
    """Flag BOTH halves of a pair that could not be reconciled by name.

    Pairing is conservative and STRUCTURAL: same unit, same measure basis, and
    the measured row's name must be a hypothesis rather than printed evidence.
    Name similarity is deliberately not consulted — that is the approximate
    name matcher arriving by another route, and it renames one object into
    another (24-RESEARCH pitfall 5). The word this sentence avoids spelling is
    the one the module's own guard grep searches for; a guard that its own
    prose can trip is a guard nobody trusts.

    Nothing here changes a name, a quantity or a unit. The only effect is a
    review reason on each side.
    """
    if not blanks or not measured:
        return
    basis_by_key = _library_basis_by_key(library)
    candidates = []
    for name, bucket in measured:
        if bucket.get("source") not in _HYPOTHESIS_NAME_SOURCES:
            continue
        basis = basis_by_key.get(_norm_item_key(name))
        unit = (bucket.get("unit") or "").strip().upper()
        if not basis or not unit:
            continue
        candidates.append((name, unit, basis))
    if not candidates:
        return

    annotated: List[tuple] = []
    blanks_for_measured: Dict[str, List[str]] = defaultdict(list)
    for name, info in blanks:
        unit = (info.get("unit") or "").strip().upper()
        basis = (info.get("measure") or "").strip()
        if not unit or not basis:
            continue
        answers = sorted(
            c[0] for c in candidates if c[1] == unit and c[2] == basis
        )
        if not answers:
            continue
        annotated.append((name, unit, basis, answers))
        for answer in answers:
            blanks_for_measured[answer].append(name)

    for name, unit, basis, answers in annotated:
        buckets[name]["review_reasons"].add(
            "NOT reconciled by name: %d measured row(s) share this unit (%s) "
            "and measure basis (%s) and were named by a hypothesis rather than "
            "by printed evidence — %s. This row is still a BLANK, not a zero, "
            "and nothing was renamed or merged; a human must decide whether "
            "any of them is this object"
            % (len(answers), unit, basis, _name_list(answers))
        )
    for name, blank_names in blanks_for_measured.items():
        buckets[name]["needs_review"] = True
        buckets[name]["review_reasons"].add(
            "this row's NAME is a hypothesis, and %d expected item(s) sharing "
            "its unit and measure basis were never measured — %s. It may be "
            "answering one of them under a different name; the quantity and "
            "unit are unchanged and nothing was merged"
            % (len(blank_names), _name_list(sorted(blank_names)))
        )


def _row_status(bucket: Dict, is_unknown: bool) -> str:
    """The client status, COMPUTED FROM THE RECORD.

    The old exporter inferred it from the value (``float(qty or 0) <= 0 -> NOT
    MEASURED``), which made a building with genuinely no CMU indistinguishable
    from one whose CMU was never measured. Nothing here looks at the number.

    **HUMAN INPUT is EARNED, never defaulted into (C4).** It means one thing: a
    human handed us this number in a human input file. Crow's plans-only run —
    no manifest, no companion take-off, no human input of any kind — published
    five rows as HUMAN INPUT: four door counts the app itself parsed off the
    plan's printed door schedule, and its own injected Mobilization convention.
    Presenting machine-read data as human-vouched inverts the one distinction
    this vocabulary exists to draw, and it inflates apparent trust in exactly
    the rows a reviewer would otherwise check.
    """
    if is_unknown:
        return ITEM_NOT_MEASURED
    if bucket.get("item_type") == "standard_line_item" and not bucket.get("has_rows"):
        # A convention the APP injects (1 EA Mobilization). Nobody measured it
        # and nobody supplied it, so it is neither MEASURED nor HUMAN INPUT —
        # it gets the status that says exactly what it is.
        return ITEM_STANDARD
    if not bucket.get("has_rows"):
        return ITEM_NOT_MEASURED
    if bucket.get("needs_review"):
        return ITEM_NEEDS_REVIEW
    if bucket.get("source") == "plan_schedule_legend":
        # An authoritative legend — but authoritative is not the same question
        # as human-vouched. Only an estimator's own take-off, ingested from a
        # human input file, is HUMAN INPUT; a schedule the app read off the
        # plans is a machine measurement like any other.
        if bucket.get("legend_origin") == "human_input":
            return ITEM_HUMAN_INPUT
        return ITEM_MEASURED
    return ITEM_MEASURED


def aggregate_takeoff(
    calculated_items: List[Dict], manifest=None, learned=None, library=None,
) -> List[Dict]:
    """Consolidate per-sheet items into project-level totals.

    When ``manifest`` (an :class:`object_manifest.Manifest`) is supplied, detected
    items are resolved to the user's canonical name + unit VERBATIM (data-driven,
    no hardcoded map), and every manifest object is guaranteed to appear in the
    output — anything not found in the plans is emitted flagged ``needs_review``
    so nothing is ever silently missed.

    When ``learned`` (a :class:`bobbytailor.learning.retrieval.LearnedContext`)
    is supplied, learning_vocabulary mappings distilled from prior human
    corrections are consulted before the static ITEM_NAME_MAP (V3-LEARN-02).

    When ``library`` (the deterministic component library from
    :func:`component_library.harvest_component_library`, merged with the LLM
    vocabulary) is supplied, a detected item's raw text is resolved to the
    plan's own printed name via the library's aliases — the manifest-resolve
    replacement under plans-only. Additive: an empty library leaves naming
    unchanged.

    Naming precedence: companion legend > manifest > learned > library > static.
    Rows whose NAME came from learned vocabulary carry ``source: "learned"``
    — the naming provenance marker only; quantities are summed from the
    underlying items untouched (quantity provenance is never altered here).
    """
    buckets: Dict[str, Dict] = defaultdict(_new_bucket)

    # Items whose quantity comes from an authoritative companion take-off legend
    # are the single source of truth for that item. The legend's printed label and
    # unit are preserved VERBATIM — we deliberately do NOT route them through the
    # rule-based name map, which is built for messy vision text and can mangle
    # unseen object types (e.g. "Fiber Cement Panel" SF -> "Electrical Panels" EA).
    # This lets the app reproduce any estimator's take-off faithfully and handle
    # brand-new object types at runtime with zero hardcoding.
    #
    # `legend_names` holds the NORMALISED legend labels; it is used only to suppress
    # vision/room-derived duplicates of items the legend already covers.
    legend_names: set = set()
    # Which legend BUCKET each alias belongs to, so a suppressed duplicate can
    # be recorded on the row that survived it (INV-08 §2 row S14). Without this
    # the suppression is correct and completely silent: a measured row is
    # deleted and the report shows no sign it ever existed.
    legend_bucket_by_name: Dict[str, str] = {}
    # Library objects some contributing description resolved to, regardless of
    # which naming path finally won. Guards the plans-only completeness
    # guarantee against telling a client "your tilt-up walls were not measured"
    # when they WERE, under the name a human previously corrected them to.
    library_bound: set = set()
    # Library-named readings dropped for being degenerate, keyed by the name
    # they would have published under. Materialised after the row loop so the
    # object still gets a ROW — an explicit blank, never a silent deletion.
    suppressed_library: Dict[str, List[Dict]] = defaultdict(list)
    # Readings whose unit CLASS changed under canonicalisation (a count named
    # into an area object, or the reverse). Materialised after the row loop for
    # the same reason as above: withholding the number must leave a ROW.
    unit_class_conflicts: Dict[str, List[Dict]] = defaultdict(list)
    # Counts whose ONLY corroboration was the drawing they were read off, on a
    # sheet this run typed `detail`. Materialised after the row loop for the
    # same reason as the two collectors above: withholding the number must
    # leave a ROW, and the row must quote what it withheld.
    withheld_detail_counts: Dict[str, List[Dict]] = defaultdict(list)
    for item in calculated_items:
        if item.get("qty_source") == "plan_schedule_legend":
            desc = item.get("description", "")
            bucket_key = _clean_legend_label(desc)
            name, _ = normalize_item_name(
                desc, item.get("item_type", ""), item.get("unit", ""), learned=learned,
            )
            legend_names.add(name)
            legend_bucket_by_name.setdefault(name, bucket_key)
            legend_bucket_by_name.setdefault(bucket_key, bucket_key)
            # A legend bucket is keyed by its cleaned label, and a vision row binds
            # to its manifest name. Add BOTH so a vision/measured duplicate of a
            # legend item is suppressed regardless of which naming path it took
            # (otherwise the two same-named buckets silently SUM — e.g. a measured
            # footprint area doubling on top of a vision-read area).
            legend_names.add(bucket_key)
            if manifest:
                entry = manifest.resolve(desc, item.get("unit", ""))
                if entry:
                    legend_names.add(entry.name)
                    legend_bucket_by_name.setdefault(entry.name, bucket_key)

    for item in calculated_items:
        desc = item.get("description", "")
        itype = item.get("item_type", "")
        unit = item.get("calculated_unit") or item.get("unit", "")
        qty_raw = item.get("calculated_quantity") or item.get("quantity", 0)
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            continue

        is_legend = item.get("qty_source") == "plan_schedule_legend"
        bucket_source = ""
        bucket_legend_origin = ""
        if is_legend:
            # Trust the plan's own printed schedule: keep its label and unit
            # exactly as printed. Routed through the arbiter like every other
            # path — as a VERBATIM authority, so this is behaviourally the same
            # assignment it always was, and "exactly one function decides which
            # authority names a row" stays literally true.
            canonical_name, canonical_unit, authority = resolve_published_name([
                (NAME_AUTHORITY_LEGEND, _clean_legend_label(desc),
                 (unit or "").strip().upper()),
            ]) or (_clean_legend_label(desc), (unit or "").strip().upper(),
                   NAME_AUTHORITY_LEGEND)
            bucket_source = _PUBLISHED_SOURCE_BY_AUTHORITY[authority]
            # Absent marker => plan_parsed. HUMAN INPUT is earned, not defaulted.
            bucket_legend_origin = str(item.get("legend_origin") or "plan_parsed")
        else:
            # Manifest takes priority over the hardcoded map: when the user told us
            # what objects exist and what to call them, use that name + unit VERBATIM.
            entry = manifest.resolve(desc, unit) if manifest else None
            # Resolve the library ONCE, before naming precedence is applied.
            # This raw text IS that library object whatever name the run ends up
            # publishing it under, and the completeness guarantee below must not
            # claim the object was never measured merely because a human's
            # rename outranked the library's term for it.
            lib_hit = _resolve_library_name(desc, library)
            if lib_hit is not None:
                library_bound.add(lib_hit[0])
                # Track the canonical form too — the expected-item guard below
                # compares against canonicalised names (SP-7a).
                library_bound.add(canonical_library_name(lib_hit[0], "")[0])
            # ── ONE arbiter, not three racing branches (24-03) ────────────
            #
            # Every name this row could carry is offered to the arbiter with
            # the authority it came from, and NAME_AUTHORITY_PRECEDENCE decides.
            # Before this, the learned branch and the library branch each
            # reached publication on their own and the vision label was a third
            # — which is how one 56-EA candidate published under two different
            # names across two runs of the same drawing.
            name_candidates = []
            if entry is not None:
                name_candidates.append((
                    NAME_AUTHORITY_MANIFEST, entry.name,
                    (entry.unit or unit or "").strip().upper(),
                ))
            learned_hit = None
            if learned is not None:
                try:
                    learned_hit = learned.lookup_name(desc)
                except Exception:  # noqa: BLE001
                    learned_hit = None
            if learned_hit is not None:
                # Canonicalised on READ, never migrated (T-24-10). Rows already
                # in `learning_vocabulary` were written by the un-canonicalised
                # path and may hold either spelling of one name; folding them
                # here is idempotent and needs no destructive SQL. 24-05 owns
                # the store and will not write one either.
                learned_name, learned_unit = normalize_item_name(
                    desc, itype, unit, learned=learned,
                )
                name_candidates.append((
                    _learned_name_authority(learned, desc),
                    learned_name, learned_unit,
                ))
            if lib_hit is not None:
                name_candidates.append((
                    NAME_AUTHORITY_LIBRARY, lib_hit[0],
                    (lib_hit[1] or unit or "").strip().upper(),
                ))
            # The static-map reading is always available and always last.
            vision_name, vision_unit = normalize_item_name(desc, itype, unit)
            name_candidates.append((
                NAME_AUTHORITY_VISION, vision_name, vision_unit,
            ))

            canonical_name, canonical_unit, authority = resolve_published_name(
                name_candidates
            ) or (vision_name, vision_unit, NAME_AUTHORITY_VISION)
            bucket_source = _PUBLISHED_SOURCE_BY_AUTHORITY[authority]
            # Suppress non-legend duplicates of any legend-backed item. Matches exact
            # canonical names and base-vs-spec variants (e.g. vision "Columns" when
            # the legend reports "Columns-H-35'") so the authoritative legend isn't
            # shadowed by a coarser vision count of the same physical item.
            shadowed_by = next(
                (
                    ln for ln in sorted(legend_names)
                    if ln == canonical_name
                    or ln.startswith(canonical_name + "-")
                    or canonical_name.startswith(ln + "-")
                ),
                None,
            )
            if shadowed_by is not None:
                # Suppressing the duplicate is CORRECT — the legend is the
                # authoritative source and letting both through would silently
                # SUM them. But the deletion must leave a trace on the row that
                # survived, or a client cannot tell a suppressed duplicate from
                # a reading the app never made.
                target = legend_bucket_by_name.get(shadowed_by)
                if target:
                    buckets[target]["review_reasons"].add(
                        "a separate %r reading of this item (%s) was suppressed "
                        "as a duplicate of the authoritative legend row %r — it "
                        "was NOT added to this quantity"
                        % (canonical_name, bucket_source or "detected", shadowed_by)
                    )
                continue
        # ── Canonicalising a NAME may not silently reclassify its UNIT ───────
        #
        # C3b, in the direction the aggregator owns. Naming precedence lets a
        # library/manifest/learned entry overwrite the row's unit — and Crow
        # shows why that is not free: a symbol group of FIVE tilt-up panels
        # (5 EA, a count) resolved to the library object "Tilt Up Wall", whose
        # unit is SF, and shipped as `Tilt Up Wall 5.0 SF`, item_type
        # concrete_slab, formula "count", confidence high, needs_review false.
        # The right answer — 106,992 SF — was in the audit trail.
        #
        # There is no conversion between "how many" and "how much", so a
        # canonicalisation that crosses measurement classes cannot carry the
        # number with it. The reading is withheld and materialised below as an
        # explicit BLANK with its reason — never a number in a unit it does
        # not mean, and never a silent deletion. Only fires when BOTH classes
        # are known and differ, so a blank or novel unit changes nothing.
        if _unit_classes_conflict(unit, canonical_unit):
            unit_class_conflicts[canonical_name].append({
                "sheet": item.get("source_sheet"),
                "qty": qty,
                "unit": (unit or "").upper(),
                "canonical_unit": (canonical_unit or "").upper(),
                "description": desc,
                "formula": item.get("formula_applied") or item.get("formula", ""),
            })
            continue

        if (canonical_unit or unit or "").lower() in ("ea", "each"):
            qty = float(round(qty))

        # ── A library-named fallback never publishes an unflagged quantity ───
        #
        # source "library" means the object's IDENTITY was inferred from an
        # alias table rather than read off the drawing, so the row is a naming
        # HYPOTHESIS and has to say so. On Crow three printed detail DIMENSIONS
        # were library-named into estimator-standard objects and published as
        # "Sealed Concrete 0.15 SF", "Concrete Curb 0.05 LF" and "Pipe Handrail
        # 0.02 LF", all at needs_review=False. That is strictly worse than a
        # blank: unflagged, AND occupying the row a real measurement of the
        # same object would have filled.
        if bucket_source == "library" and _degenerate_measure(
            qty, canonical_unit or unit
        ):
            suppressed_library[canonical_name].append({
                "sheet": item.get("source_sheet"),
                "qty": qty,
                "unit": (canonical_unit or unit or "").upper(),
                "description": desc,
            })
            continue

        # ── A count of detail DRAWINGS never becomes a count of objects ──────
        #
        # 28-01 recorded the verdict on the row; this is where it is acted on.
        # On Crow, `Stairs` published 1 EA in one run and 2 EA in an identical
        # re-run, both times MEASURED at needs_review=False — a count of the
        # stair details drawn on A-401, presented as a count of installed
        # stairs. Flagging it would not be enough: the reading does not measure
        # the object the row names, so the number is WITHHELD and materialised
        # below as a blank that quotes it. Diverted here, exactly like a
        # unit-class conflict, so it can never reach `bucket["quantity"]`.
        if str(item.get("count_corroboration") or "").strip() == "detail_sheet_only":
            withheld_detail_counts[canonical_name].append({
                "sheet": item.get("source_sheet"),
                "qty": qty,
                "unit": (canonical_unit or unit or "").upper(),
                "description": desc,
                "sheet_kind": item.get("count_evidence_sheet_kind"),
            })
            continue

        bucket = buckets[canonical_name]
        bucket["quantity"] += qty
        bucket["unit"] = canonical_unit or unit
        bucket["source_sheets"].add(item.get("source_sheet", ""))
        bucket["item_type"] = itype
        if bucket_source and not bucket["source"]:
            bucket["source"] = bucket_source
        # A bucket is human-vouched only if a HUMAN-SOURCED legend row built it.
        # First-seen wins, exactly like `source`.
        if bucket_legend_origin and not bucket["legend_origin"]:
            bucket["legend_origin"] = bucket_legend_origin
        # Roll up uncertainty signals so the summary can highlight shaky rows.
        if item.get("needs_review"):
            bucket["needs_review"] = True
        reason = item.get("review_reason")
        if reason:
            bucket["review_reasons"].add(reason)
        bucket["confidence"] = _worse_conf(bucket["confidence"], item.get("confidence"))
        # ...and roll up what BACKED the count, beside the flag it rolls up.
        # A row that is not a count carries no verdict and leaves this unset.
        bucket["count_corroboration"] = _stronger_corroboration(
            bucket["count_corroboration"], item.get("count_corroboration"),
        )
        # A bucket is auto-verified only if EVERY contributing row was auto-accepted.
        bucket["has_rows"] = True
        if not item.get("auto_verified"):
            bucket["auto_verified"] = False
        bucket["source_rows"].append({
            "sheet": item.get("source_sheet"),
            "qty": qty,
            "description": desc,
            "formula": item.get("formula_applied") or item.get("formula", ""),
        })

    # ── Suppressed library readings become BLANKS, never silence ─────────────
    #
    # Dropping the number is only half the contract. An object whose sole
    # evidence was a degenerate reading must still appear, saying "not
    # measured" — otherwise the fix trades a fabricated 0.15 SF for a deletion,
    # and INV-08's whole point is that a deletion and a zero read the same to a
    # client. Where a real measurement of the same object DID land, the bucket
    # keeps its quantity and carries a note that the degenerate reading was
    # dropped rather than summed into it.
    for name, dropped in suppressed_library.items():
        detail = "; ".join(
            "%r read %s %s on %s"
            % (d["description"], d["qty"], d["unit"], d["sheet"] or "?")
            for d in dropped
        )
        if buckets.get(name, {}).get("has_rows"):
            buckets[name]["needs_review"] = True
            buckets[name]["review_reasons"].add(
                "a library-named reading too small to be a real measurement "
                "was NOT summed into this quantity (%s)" % detail
            )
            continue
        bucket = buckets[name]
        bucket["unit"] = dropped[0]["unit"]
        bucket["item_type"] = bucket["item_type"] or "library_object"
        bucket["needs_review"] = True
        bucket["confidence"] = "low"
        bucket["source"] = LIBRARY_FALLBACK_UNMEASURED
        bucket["review_reasons"].add(
            "the only reading that resolved to this library object was too "
            "small to be a real measurement and was NOT published — this is a "
            "BLANK, not a zero (%s)" % detail
        )
        bucket["source_rows"].append({
            "sheet": None,
            "qty": None,
            "description": "%s (library-named reading suppressed as degenerate,"
                           " not measured on the plans)" % name,
            "formula": "library_fallback_not_measured",
        })

    # ── Unit-class conflicts become BLANKS, never silence (C3b) ──────────────
    #
    # Same contract as the degenerate-reading block above, for the same
    # reason: dropping the number is only half of it. An object whose only
    # evidence was a reading in the wrong measurement class must still appear
    # saying "not measured", or the fix trades a false `5.0 SF` for a deletion
    # — and a deletion and a zero read the same to a client.
    for name, conflicts in unit_class_conflicts.items():
        detail = "; ".join(
            "%r read %s %s%s and this row publishes in %s — %s vs %s"
            % (
                c["description"], c["qty"], c["unit"],
                (" via formula %r" % c["formula"]) if c["formula"] else "",
                c["canonical_unit"],
                _unit_class(c["unit"]) or "unknown",
                _unit_class(c["canonical_unit"]) or "unknown",
            )
            for c in conflicts
        )
        if buckets.get(name, {}).get("has_rows"):
            buckets[name]["needs_review"] = True
            buckets[name]["review_reasons"].add(
                "a reading in a DIFFERENT measurement class was NOT summed "
                "into this quantity (%s)" % detail
            )
            continue
        bucket = buckets[name]
        bucket["unit"] = conflicts[0]["canonical_unit"]
        bucket["item_type"] = bucket["item_type"] or "unit_class_conflict"
        bucket["needs_review"] = True
        bucket["confidence"] = "low"
        bucket["source"] = UNIT_CLASS_CONFLICT_UNMEASURED
        bucket["review_reasons"].add(
            "the only reading that resolved to this object was measured in a "
            "DIFFERENT measurement class from the unit it would publish in, "
            "and there is no conversion between them, so the number is "
            "WITHHELD — this is a BLANK, not a zero (%s)" % detail
        )
        bucket["source_rows"].append({
            "sheet": None,
            "qty": None,
            "description": "%s (reading withheld — measured in a different "
                           "unit class from this row's unit)" % name,
            "formula": "unit_class_conflict_not_measured",
        })

    # ── Withheld detail-sheet counts become BLANKS, never silence ────────────
    #
    # The third instance of the same contract, and for the same reason as the
    # two above: dropping the number is only half of it. An object whose only
    # evidence was a count of its own detail drawings must still appear saying
    # "not measured", with the withheld reading quoted — otherwise the fix
    # trades a confidently wrong `1 EA` for a deletion, and a deletion and a
    # zero read the same to a client.
    for name, withheld in withheld_detail_counts.items():
        detail = "; ".join(
            "%r read %s %s on %s" % (
                w["description"],
                int(w["qty"]) if float(w["qty"]) == int(w["qty"]) else w["qty"],
                w["unit"], w["sheet"] or "?",
            )
            for w in withheld
        )
        if buckets.get(name, {}).get("has_rows"):
            buckets[name]["needs_review"] = True
            buckets[name]["review_reasons"].add(
                "a count read off a details sheet was NOT summed into this "
                "quantity (%s) — a details sheet shows how a thing is built "
                "rather than how many are installed" % detail
            )
            continue
        bucket = buckets[name]
        bucket["unit"] = withheld[0]["unit"]
        bucket["item_type"] = bucket["item_type"] or "detail_sheet_count"
        bucket["needs_review"] = True
        bucket["confidence"] = "low"
        bucket["source"] = DETAIL_SHEET_COUNT_UNMEASURED
        bucket["review_reasons"].add(
            "the only reading that resolved to this object was a count taken "
            "from a sheet this run classified as details (%s); a details sheet "
            "shows how a thing is built rather than how many are installed, so "
            "the reading counts detail drawings and is WITHHELD — this is a "
            "BLANK, not a zero, and it needs a plan-sheet or schedule "
            "confirmation" % detail
        )
        bucket["source_rows"].append({
            "sheet": None,
            "qty": None,
            "description": "%s (count withheld — read off a details sheet, "
                           "which shows how a thing is built rather than how "
                           "many are installed)" % name,
            "formula": "detail_sheet_count_not_measured",
        })

    # Only enrich with standard line items when a genuine take-off was produced.
    if buckets:
        _inject_standard_line_items(buckets)

    # Completeness guarantee: every manifest object must appear in the take-off.
    # Anything we never found in the plans is emitted with qty unknown and flagged
    # needs_review so it is reviewed by a human rather than silently dropped.
    if manifest:
        for entry in manifest.missing(list(buckets.keys())):
            bucket = buckets[entry.name]
            bucket["unit"] = entry.unit
            bucket["item_type"] = entry.measure or "manifest_object"
            bucket["needs_review"] = True
            bucket["confidence"] = "low"
            bucket["source"] = "manifest_missing"
            bucket["review_reasons"].add("manifest object not found in plans")
            bucket["source_rows"].append({
                "sheet": None,
                "qty": None,
                "description": f"{entry.name} (expected from manifest, not located on plans)",
                "formula": "manifest_object_not_found",
            })

    # ...and the SAME guarantee with no manifest at all. A plans-only run is
    # the mission mode, and until now it enumerated nothing: an expected item
    # that never appeared had no row, so "we did not measure your lintels" and
    # "your building has no lintels" were the same artifact (INV-08 S13).
    expected = _expected_items_without_a_manifest(learned, library)
    if expected:
        # `_norm_item_key` is plural-aware since 24-03, so a measured `Bollard`
        # row and an expected `Bollards` item are ONE key here and the blank is
        # suppressed. That reconciliation is the cheap half; the half folding
        # cannot do is handled after this loop.
        present = {_norm_item_key(k) for k in buckets}
        present |= {_norm_item_key(n) for n in legend_names}
        present |= {_norm_item_key(n) for n in library_bound}
        # Snapshot the MEASURED rows before a single blank row is created, so a
        # blank can never be offered as the answer to another blank.
        measured_before_blanks = [
            (n, b) for n, b in buckets.items() if b.get("has_rows")
        ]
        unreconciled_blanks: List[tuple] = []
        for name, info in expected.items():
            if _norm_item_key(name) in present:
                continue
            present.add(_norm_item_key(name))
            unreconciled_blanks.append((name, info))
            bucket = buckets[name]
            bucket["unit"] = info["unit"]
            bucket["item_type"] = info["measure"] or "expected_object"
            bucket["needs_review"] = True
            bucket["confidence"] = "low"
            bucket["source"] = "expected_not_measured"
            bucket["review_reasons"].add(
                "expected from the %s but never measured on the plans — this is "
                "a BLANK, not a zero" % info["expected_from"]
            )
            bucket["source_rows"].append({
                "sheet": None,
                "qty": None,
                "description": "%s (expected from the %s, not measured on the plans)"
                               % (name, info["expected_from"]),
                "formula": "expected_object_not_measured",
            })

        _cross_reference_unreconciled(
            buckets, unreconciled_blanks, measured_before_blanks, library,
        )

    result = []
    for name in sorted(buckets.keys()):
        b = buckets[name]
        is_unknown = b.get("source") in _UNMEASURED_SOURCES
        # THE one-line change INV-08 calls the highest-value in its map: a
        # never-measured item ships None, not the defaultdict's 0.0. `is None`
        # is the only test any consumer should apply — a measured 0.0 is a real,
        # publishable finding (a building with genuinely no CMU) and must stay
        # distinguishable from an absence.
        qty = None if is_unknown else b["quantity"]
        if qty is None:
            qty_fmt = "—"
        elif qty == int(qty):
            qty_fmt = f"{qty:,.0f}"
        else:
            qty_fmt = f"{qty:,.1f}"
        status = _row_status(b, is_unknown)
        row = {
            "item": name,
            "quantity": qty,
            "quantity_fmt": qty_fmt,
            "unit": (b["unit"] or "").upper(),
            "source_sheets": sorted(b["source_sheets"] - {""}),
            "item_type": b["item_type"],
            "line_count": len([r for r in b["source_rows"] if r.get("qty") is not None]),
            "needs_review": bool(b.get("needs_review")),
            "confidence": b.get("confidence"),
            "auto_verified": bool(b.get("has_rows") and b.get("auto_verified")
                                  and not b.get("needs_review") and not is_unknown),
            "review_reasons": sorted(b.get("review_reasons") or []),
            "source": b.get("source", ""),
            "detail": b["source_rows"],
        }
        # Provenance is READ FROM THE RECORD, never sniffed from the value:
        # provenance_of_row's first branch returns the status this run computed
        # from what it actually did. Passing the status is what keeps a measured
        # zero MEASURED and a manifest-NAMED measurement from being relabelled
        # as a human input (the aggregator's `source` is a NAMING marker — its
        # own docstring says quantity provenance is never altered here).
        row["provenance"] = provenance_of_row(dict(row, status=status))
        row["measured"] = bool(qty is not None and b.get("has_rows"))
        result.append(row)
    return result
