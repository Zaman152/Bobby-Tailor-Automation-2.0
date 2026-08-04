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
)
from bobbytailor.pipeline.provenance import provenance_of_row

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

_UNMEASURED_SOURCES = frozenset({
    "manifest_missing", "expected_not_measured", LIBRARY_FALLBACK_UNMEASURED,
})

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


def _norm_item_key(name: str) -> str:
    """Loose canonical key for 'have we already got a row for this?'."""
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()

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
    """
    hay = (name or "").lower()
    squashed = re.sub(r"[^a-z0-9]+", "", hay)
    if not squashed:
        return name, unit
    for pattern, canon, default_unit in ITEM_NAME_MAP:
        if re.search(pattern, hay, re.IGNORECASE):
            if re.sub(r"[^a-z0-9]+", "", canon.lower()) == squashed:
                return canon, (unit or default_unit)
    return name, unit


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
        if not name or _norm_item_key(name) in {_norm_item_key(k) for k in out}:
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


def _row_status(bucket: Dict, is_unknown: bool) -> str:
    """The four-value client status, COMPUTED FROM THE RECORD.

    The old exporter inferred it from the value (``float(qty or 0) <= 0 -> NOT
    MEASURED``), which made a building with genuinely no CMU indistinguishable
    from one whose CMU was never measured. Nothing here looks at the number.
    """
    if is_unknown:
        return ITEM_NOT_MEASURED
    if bucket.get("item_type") == "standard_line_item" and not bucket.get("has_rows"):
        # A convention (1 EA Mobilization), not something taken off a drawing.
        return ITEM_HUMAN_INPUT
    if not bucket.get("has_rows"):
        return ITEM_NOT_MEASURED
    if bucket.get("needs_review"):
        return ITEM_NEEDS_REVIEW
    if bucket.get("source") == "plan_schedule_legend":
        # The authoritative companion take-off: a human's own quantity, kept
        # verbatim. The app did not earn this number off the drawing.
        return ITEM_HUMAN_INPUT
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
    buckets: Dict[str, Dict] = defaultdict(lambda: {
        "quantity": 0.0,
        "unit": "",
        "source_sheets": set(),
        "source_rows": [],
        "item_type": "",
        "needs_review": False,
        "confidence": None,
        "review_reasons": set(),
        "source": "",
        "auto_verified": True,   # AND of contributing rows; only meaningful with rows
        "has_rows": False,
    })

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
        if is_legend:
            # Trust the plan's own printed schedule: keep its label and unit
            # exactly as printed.
            canonical_name = _clean_legend_label(desc)
            canonical_unit = (unit or "").strip().upper()
            bucket_source = "plan_schedule_legend"
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
            if entry is not None:
                canonical_name = entry.name
                canonical_unit = (entry.unit or unit or "").strip().upper()
                bucket_source = "manifest"
            else:
                # Learned corrections take precedence over the library; both
                # precede the static map. normalize_item_name already checks
                # learned first, so consult learned explicitly to know whether
                # the name came from a human correction.
                learned_hit = None
                if learned is not None:
                    try:
                        learned_hit = learned.lookup_name(desc)
                    except Exception:  # noqa: BLE001
                        learned_hit = None
                if learned_hit is not None:
                    canonical_name, canonical_unit = normalize_item_name(
                        desc, itype, unit, learned=learned,
                    )
                    bucket_source = "learned"
                else:
                    if lib_hit is not None:
                        # SP-7a: the library name goes through the SAME
                        # canonicalisation as every other naming path.
                        canonical_name, _ = canonical_library_name(
                            lib_hit[0], lib_hit[1])
                        canonical_unit = (lib_hit[1] or unit or "").strip().upper()
                        bucket_source = "library"
                    else:
                        canonical_name, canonical_unit = normalize_item_name(
                            desc, itype, unit, learned=learned,
                        )
                        bucket_source = "vision"
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

        bucket = buckets[canonical_name]
        bucket["quantity"] += qty
        bucket["unit"] = canonical_unit or unit
        bucket["source_sheets"].add(item.get("source_sheet", ""))
        bucket["item_type"] = itype
        if bucket_source and not bucket["source"]:
            bucket["source"] = bucket_source
        # Roll up uncertainty signals so the summary can highlight shaky rows.
        if item.get("needs_review"):
            bucket["needs_review"] = True
        reason = item.get("review_reason")
        if reason:
            bucket["review_reasons"].add(reason)
        bucket["confidence"] = _worse_conf(bucket["confidence"], item.get("confidence"))
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
        present = {_norm_item_key(k) for k in buckets}
        present |= {_norm_item_key(n) for n in legend_names}
        present |= {_norm_item_key(n) for n in library_bound}
        for name, info in expected.items():
            if _norm_item_key(name) in present:
                continue
            present.add(_norm_item_key(name))
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
