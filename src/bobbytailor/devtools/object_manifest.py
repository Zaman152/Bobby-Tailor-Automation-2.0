"""
Object Manifest — optional, runtime, data-driven object vocabulary.

In production only PLANS are available (no companion take-off with quantities).
A user can OPTIONALLY upload a manifest: a list of the objects they expect in a
project, with the canonical name + unit they want in the output (and optional
aliases / measurement hints / assumptions). The manifest is NOT a take-off — it
carries no quantities. It is used to:

  1. NAME flexibly at runtime — map any detected item to the user's canonical
     name + unit via alias / token / fuzzy matching (no hardcoded ITEM_NAME_MAP).
  2. GUARANTEE COMPLETENESS — every manifest object must appear in the final
     take-off; anything we could not find is emitted flagged ``needs_review`` so
     nothing is ever silently missed.
  3. DRIVE TARGETED EXTRACTION — tell the vision passes exactly what to look for
     (consumed in later phases) and supply measurement assumptions (wall height,
     slab thickness, ...) for area/length items.

Accepted formats
----------------
JSON: a list of objects, or ``{"objects": [...]}``::

    [
      {"name": "CMU Wall", "unit": "SF", "aliases": ["concrete masonry", "cmu"],
       "measure": "area", "assumptions": {"height_ft": 35}},
      {"name": "Bollards", "unit": "EA", "aliases": ["bollard", "pipe bollard"]},
      {"name": "Columns-H-35'", "unit": "EA", "aliases": ["column"]}
    ]

CSV: header row with at least ``name`` and ``unit``; optional
``aliases`` (``;`` or ``|`` separated), ``measure``, ``height_ft``,
``thickness_in``, ``keywords``::

    name,unit,aliases,measure,height_ft
    CMU Wall,SF,concrete masonry;cmu,area,35
    Bollards,EA,bollard;pipe bollard,count,
"""
from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Tokens that carry no discriminating power when matching item names.
_STOP = {
    "the", "a", "an", "of", "and", "to", "for", "in", "on", "at",
    "alt", "typ", "ea", "total", "system", "assembly",
}

# Unit -> measurement kind (used when a manifest entry omits `measure`).
_UNIT_MEASURE = {
    "EA": "count", "EACH": "count",
    "SF": "area", "SQFT": "area", "SQ_FT": "area",
    "LF": "length", "FT": "length",
    "CY": "volume", "CF": "volume",
    "GAL": "volume", "GALLONS": "volume",
}

# Minimum match confidence for a detected item to bind to a manifest entry.
RESOLVE_CUTOFF = 0.62


def _singular(tok: str) -> str:
    """Light singularization so 'panels'/'panel', 'bollards'/'bollard' align."""
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _tokens(text: str) -> set:
    toks = re.split(r"[-_/\s'\".,()]+", (text or "").lower())
    out = set()
    for t in toks:
        if not t or t in _STOP:
            continue
        # Keep numeric tokens: they are discriminating identifiers (WC-1 vs WC-2,
        # Type 3, etc.). Dropping them merged distinct items and lost components.
        if t.isdigit():
            out.add(t)
            continue
        out.add(_singular(t))
    return out


def _norm(text: str) -> str:
    return " ".join(sorted(_tokens(text)))


def measure_from_unit(unit: str) -> str:
    return _UNIT_MEASURE.get((unit or "").strip().upper(), "count")


@dataclass
class ManifestEntry:
    name: str
    unit: str = ""
    aliases: List[str] = field(default_factory=list)
    measure: str = ""
    assumptions: Dict = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)
    # Populated in __post_init__.
    _phrases: List[str] = field(default_factory=list, repr=False)
    _token_sets: List[set] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self.unit = (self.unit or "").strip().upper()
        if not self.measure:
            self.measure = measure_from_unit(self.unit)
        phrases = [self.name, *self.aliases, *self.keywords]
        self._phrases = [p for p in phrases if p and str(p).strip()]
        self._token_sets = [_tokens(p) for p in self._phrases]

    def score(self, text: str) -> float:
        """Best match score (0..1) of `text` against this entry's name/aliases.

        Matching is TOKEN-based on purpose: a match requires shared significant
        tokens. We deliberately do NOT let raw character similarity cross the
        threshold, which would mis-bind unrelated items (e.g. "Electrical Panels"
        -> "Fiber Cement Panel").
        """
        t_tokens = _tokens(text)
        if not t_tokens:
            return 0.0
        t_norm = " ".join(sorted(t_tokens))
        best = 0.0
        for p_tokens in self._token_sets:
            if not p_tokens:
                continue
            # Exact normalised phrase match.
            if t_norm == " ".join(sorted(p_tokens)):
                return 1.0
            # One side fully contains the other (e.g. "cmu" in {"cmu","wall"}).
            if p_tokens <= t_tokens or t_tokens <= p_tokens:
                best = max(best, 0.9)
                continue
            # Otherwise require shared tokens; score by Jaccard overlap only.
            shared = p_tokens & t_tokens
            if not shared:
                continue
            jaccard = len(shared) / len(p_tokens | t_tokens)
            best = max(best, jaccard)
        return best


class Manifest:
    """A loaded object manifest with name resolution + completeness checking."""

    def __init__(self, entries: List[ManifestEntry], source: str = ""):
        self.entries = entries
        self.source = source

    def __len__(self) -> int:
        return len(self.entries)

    def __bool__(self) -> bool:
        return bool(self.entries)

    # ── Resolution ────────────────────────────────────────────────────────────

    def resolve(self, text: str, unit_hint: str = "") -> Optional[ManifestEntry]:
        """Return the manifest entry that best matches `text`, or None.

        `unit_hint` (the detected unit) is used only as a tie-breaker so that, e.g.,
        an EA detection prefers an EA manifest entry when scores are close.
        """
        if not text:
            return None
        unit_hint = (unit_hint or "").strip().upper()
        scored = []
        for e in self.entries:
            s = e.score(text)
            if s >= RESOLVE_CUTOFF:
                scored.append((s, e))
        if not scored:
            return None
        # Highest score wins; tie-break toward matching unit, then more-specific name.
        scored.sort(
            key=lambda se: (
                round(se[0], 3),
                1 if unit_hint and se[1].unit == unit_hint else 0,
                len(se[1].name),
            ),
            reverse=True,
        )
        return scored[0][1]

    # ── Completeness ────────────────────────────────────────────────────────────

    def missing(self, produced_item_names: Iterable[str]) -> List[ManifestEntry]:
        """Manifest entries with no corresponding produced item (by name match)."""
        produced = [n for n in produced_item_names if n]
        produced_norm = {_norm(n) for n in produced}
        out: List[ManifestEntry] = []
        for e in self.entries:
            e_norm = _norm(e.name)
            if e_norm in produced_norm:
                continue
            # Loose: did any produced item resolve to this entry?
            if any(e.score(n) >= RESOLVE_CUTOFF for n in produced):
                continue
            out.append(e)
        return out


# ── Loading ──────────────────────────────────────────────────────────────────

def _coerce_aliases(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if str(a).strip()]
    # CSV string: split on ; or |
    return [a.strip() for a in re.split(r"[;|]", str(raw)) if a.strip()]


def _entry_from_dict(d: dict) -> Optional[ManifestEntry]:
    name = (d.get("name") or d.get("item") or d.get("item_name") or "").strip()
    if not name:
        return None
    assumptions = dict(d.get("assumptions") or {})
    # Allow flat CSV-style assumption columns. `scale_ft_per_in` lets the user
    # supply a reliable drawing scale (e.g. 20 for 1"=20') that unlocks accurate
    # vector-geometry measurement.
    for k in ("height_ft", "thickness_in", "coats", "coverage",
              "scale_ft_per_in", "scale_feet_per_inch"):
        if d.get(k) not in (None, ""):
            try:
                assumptions[k] = float(d[k])
            except (TypeError, ValueError):
                pass
    return ManifestEntry(
        name=name,
        unit=(d.get("unit") or "").strip(),
        aliases=_coerce_aliases(d.get("aliases")),
        measure=(d.get("measure") or "").strip().lower(),
        assumptions=assumptions,
        keywords=_coerce_aliases(d.get("keywords")),
    )


def load_manifest(path: str) -> Manifest:
    """Load an object manifest from a JSON or CSV file. Tolerant of minor variance.

    Raises FileNotFoundError if the path does not exist; returns an empty Manifest
    (falsy) if the file has no usable rows.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)

    raw_entries: List[dict] = []
    suffix = p.suffix.lower()
    text = p.read_text(encoding="utf-8", errors="ignore").strip()

    if suffix == ".json" or text.startswith("[") or text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("objects") or data.get("items") or data.get("manifest") or []
        if isinstance(data, list):
            raw_entries = [d for d in data if isinstance(d, dict)]
    else:
        reader = csv.DictReader(text.splitlines())
        raw_entries = [dict(r) for r in reader]

    entries: List[ManifestEntry] = []
    seen = set()
    for d in raw_entries:
        e = _entry_from_dict({k.strip().lower(): v for k, v in d.items()})
        if not e:
            continue
        key = _norm(e.name)
        if key in seen:
            continue
        seen.add(key)
        entries.append(e)

    logger.info("Loaded object manifest %s with %d entries", p.name, len(entries))
    return Manifest(entries, source=str(p))


def load_manifest_safe(path: Optional[str]) -> Optional[Manifest]:
    """Like load_manifest but returns None on any error / empty / missing path."""
    if not path:
        return None
    try:
        m = load_manifest(path)
        return m if m else None
    except Exception as exc:  # noqa: BLE001 - manifest is optional, never fatal
        logger.warning("Could not load object manifest %r: %s", path, exc)
        return None


# ── Auto-discovery ────────────────────────────────────────────────────────────
# StackCT runs are launched from the plan picker, which has no manifest upload
# control. To let those runs still benefit from manifest naming + completeness,
# we look for a project-associated manifest file dropped in a `manifests/` dir.
# Name the file after the project (e.g. ``manifests/crow_cass.json``) — matching
# is slug-based and fuzzy, so "Crow - Cass White Road" finds "crow_cass.json".
# ``manifests/default.json`` (if present) is used as a last-resort fallback.

DEFAULT_MANIFEST_DIRS = ("manifests",)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def discover_manifest_path(
    project_name: str,
    search_dirs: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Find a manifest file matching ``project_name`` in the manifests dir(s).

    Returns the best-matching file path, or None. Matching is slug-based:
      - exact slug match (score 3),
      - one slug contained in the other, min 3 chars (score 2),
      - a file literally named ``default`` (score 0, fallback only).
    The most specific (longest stem) highest-scoring file wins.
    """
    slug = _slug(project_name)
    dirs = [Path(d) for d in (search_dirs or DEFAULT_MANIFEST_DIRS)]
    candidates: List[tuple] = []  # (score, stem_len, path)
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.suffix.lower() not in (".json", ".csv"):
                continue
            fslug = _slug(f.stem)
            if fslug == "default":
                candidates.append((0, len(fslug), str(f)))
                continue
            if not fslug or not slug:
                continue
            if fslug == slug:
                candidates.append((3, len(fslug), str(f)))
            elif len(fslug) >= 3 and (fslug in slug or slug in fslug):
                candidates.append((2, len(fslug), str(f)))
    if not candidates:
        return None
    candidates.sort(reverse=True)  # highest score, then longest stem
    return candidates[0][2]


def resolve_project_manifest(
    project_name: str,
    explicit_path: Optional[str] = None,
    search_dirs: Optional[Iterable[str]] = None,
) -> Optional[Manifest]:
    """Load the manifest for a run: explicit path first, else auto-discovery.

    Never raises — returns None when nothing usable is found.
    """
    if explicit_path:
        m = load_manifest_safe(explicit_path)
        if m:
            return m
    found = discover_manifest_path(project_name, search_dirs=search_dirs)
    if found:
        logger.info("Auto-discovered object manifest %s for project %r", found, project_name)
        return load_manifest_safe(found)
    return None


# ── Template (for the upload UI / users to fill in) ──────────────────────────

TEMPLATE_COLUMNS = ["name", "unit", "aliases", "measure", "height_ft", "thickness_in"]

TEMPLATE_EXAMPLE_ROWS = [
    {"name": "CMU Wall", "unit": "SF", "aliases": "concrete masonry;cmu",
     "measure": "area", "height_ft": "", "thickness_in": ""},
    {"name": "Bollards", "unit": "EA", "aliases": "bollard;pipe bollard",
     "measure": "count", "height_ft": "", "thickness_in": ""},
    {"name": "Columns-H-35'", "unit": "EA", "aliases": "column;structural column",
     "measure": "count", "height_ft": "35", "thickness_in": ""},
    {"name": "Gas Piping", "unit": "LF", "aliases": "gas pipe;gas line",
     "measure": "length", "height_ft": "", "thickness_in": ""},
]


def template_csv() -> str:
    """Return a CSV template string users can download, fill in, and upload."""
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TEMPLATE_COLUMNS)
    w.writeheader()
    for row in TEMPLATE_EXAMPLE_ROWS:
        w.writerow(row)
    return buf.getvalue()
