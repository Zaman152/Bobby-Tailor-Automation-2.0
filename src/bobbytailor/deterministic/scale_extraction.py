"""
Robust printed-scale extraction from CAD-exported PDFs.

Why this exists
---------------
Architectural scales are drawn as STACKED fractions (numerator above denominator,
no slash glyph). PyMuPDF's linear text extraction reads them left-to-right and
collapses the stack, so the printed scale is silently mangled:

    1/8" = 1'-0"   ->  "18" = 1'-0"   (parsed as 1/18  -> wrong by ~140x)
    3/32" = 1'-0"  ->  "32" = 1'-0"   (parsed as 1/32  -> wrong by ~340x)

This module reconstructs the real scale by reading char-level geometry
(`page.get_text("rawdict")`): digits sitting higher on the line are the numerator,
digits lower are the denominator. Every recovered value is then SNAPPED to the
standard architectural / engineering scale ladder and anything that does not map
to a real scale is rejected — so a garbled reading can never become a quantity.

Public API
----------
- ``feet_per_inch_ladder()``          -> the set of valid scale fpi values
- ``snap_fpi(fpi)``                   -> nearest valid scale fpi, or None
- ``extract_scales_from_page(page)``  -> [(fpi, count)] most-common first
- ``extract_scales_from_text(text)``  -> text-only fallback, [(fpi, count)]
- ``dominant_scale(page, scale_text)``-> (fpi|None, confidence, detail)
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Tuple

# ── Standard scale ladder (feet represented by one paper inch) ────────────────
# Architectural "<paper inch> = 1'-0"": fpi = 1 ft / paper_in.
_ARCH_PAPER_IN = [1/32, 1/16, 3/32, 1/8, 3/16, 1/4, 3/8, 1/2, 3/4, 1.0, 1.5, 3.0]
ARCH_FPI = sorted({round(1.0 / p, 6) for p in _ARCH_PAPER_IN})
# Engineering "1" = N'": fpi = N.
ENG_FPI = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 200.0]
_ALL_FPI = sorted(set(ARCH_FPI) | set(ENG_FPI))

# Relative tolerance for snapping a recovered value to a ladder entry.
_SNAP_TOL = 0.04


def feet_per_inch_ladder() -> List[float]:
    return list(_ALL_FPI)


def snap_fpi(fpi: Optional[float]) -> Optional[float]:
    """Snap *fpi* to the nearest standard scale within tolerance, else None."""
    if not fpi or fpi <= 0:
        return None
    best, best_err = None, 1e9
    for cand in _ALL_FPI:
        err = abs(fpi - cand) / cand
        if err < best_err:
            best, best_err = cand, err
    return best if best_err <= _SNAP_TOL else None


_FEET_RE = re.compile(r"(\d+)\s*'\s*-?\s*(\d+)?\s*\"?")


def _real_feet(text_after_eq: str) -> Optional[float]:
    """Parse the real-world side, e.g. "1'-0"" -> 1.0, "20'" -> 20.0."""
    m = _FEET_RE.search(text_after_eq)
    if not m:
        return None
    return int(m.group(1)) + (int(m.group(2)) / 12.0 if m.group(2) else 0)


def _paper_inches_from_chars(chars: List[Tuple[float, float, str]]) -> Optional[float]:
    """Reconstruct the paper-inch value from char-level (x, y, c) before '='.

    Handles stacked fractions (numerator higher on the line than denominator),
    explicit slash fractions, mixed numbers, and plain whole inches.
    """
    # Keep only the trailing run of digits / slash (stop at a letter like SCALE).
    kept: List[Tuple[float, float, str]] = []
    for x, y, c in reversed(chars):
        if c.isdigit() or c == "/":
            kept.append((x, y, c))
        elif c in (" ", '"', "'", "-", ".", ":"):
            if kept:
                # allow a single space gap, but stop once we hit the label area
                continue
        else:
            break
    if not kept:
        return None
    kept.reverse()  # back to reading order

    # Explicit slash fraction (some PDFs keep the glyph).
    if any(c == "/" for _, _, c in kept):
        s = "".join(c for _, _, c in kept)
        m = re.match(r"^(?:(\d+)\s+)?(\d+)/(\d+)$", s)
        if m:
            whole = int(m.group(1)) if m.group(1) else 0
            return whole + int(m.group(2)) / int(m.group(3))
        return None

    digits = [(x, y, c) for x, y, c in kept if c.isdigit()]
    if not digits:
        return None
    if len(digits) == 1:
        return float(digits[0][2])

    ys = [y for _, y, _ in digits]
    y_min, y_max = min(ys), max(ys)
    # Stacked fraction: a meaningful vertical split between numerator/denominator.
    if (y_max - y_min) >= 1.5:
        mid = (y_min + y_max) / 2.0
        top = [(x, c) for x, y, c in digits if y < mid]      # numerator (higher)
        bot = [(x, c) for x, y, c in digits if y >= mid]     # denominator (lower)
        if top and bot:
            num = int("".join(c for _, c in sorted(top)))
            den = int("".join(c for _, c in sorted(bot)))
            if den:
                return num / den
    # No vertical split -> a plain whole number (e.g. 1" = 20').
    s = "".join(c for _, _, c in digits)
    try:
        return float(s)
    except ValueError:
        return None


def _line_chars(line) -> List[Tuple[float, float, str]]:
    out = []
    for span in line.get("spans", []):
        for ch in span.get("chars", []):
            b = ch["bbox"]
            out.append((b[0], b[1], ch.get("c", "")))
    return out


def _scale_from_line(chars: List[Tuple[float, float, str]]) -> Optional[float]:
    """Recover a single feet-per-inch value from one line's chars, snapped."""
    text = "".join(c for _, _, c in chars)
    if "=" not in text:
        return None
    eq_idx = next((i for i, (_, _, c) in enumerate(chars) if c == "="), -1)
    if eq_idx < 0:
        return None
    real_ft = _real_feet("".join(c for _, _, c in chars[eq_idx + 1:]))
    if not real_ft:
        return None
    paper_in = _paper_inches_from_chars(chars[:eq_idx])
    if not paper_in or paper_in <= 0:
        return None
    return snap_fpi(real_ft / paper_in)


def extract_scales_from_page(page) -> List[Tuple[float, int]]:
    """Char-geometry scale extraction. Returns [(fpi, count)] most-common first."""
    fpis: Counter = Counter()
    for c in extract_scale_callouts(page):
        fpis[c["feet_per_inch"]] += 1
    return fpis.most_common()


def extract_scale_callouts(page) -> List[dict]:
    """Positioned scale callouts: [{feet_per_inch, x, y}] for per-viewport binding.

    The anchor (x, y) is the location of the callout text — used to associate each
    drawing viewport on a multi-scale sheet with its own scale.
    """
    out: List[dict] = []
    try:
        rd = page.get_text("rawdict")
    except Exception:
        return out
    if not isinstance(rd, dict):  # e.g. a stub page that returns plain text
        return out
    for block in rd.get("blocks", []):
        for line in block.get("lines", []):
            chars = _line_chars(line)
            fpi = _scale_from_line(chars)
            if not fpi:
                continue
            xs = [x for x, _, _ in chars]
            ys = [y for _, y, _ in chars]
            out.append({
                "feet_per_inch": fpi,
                "x": sum(xs) / len(xs) if xs else 0.0,
                "y": sum(ys) / len(ys) if ys else 0.0,
            })
    return out


# ── Text-only fallback (when rawdict is unavailable, e.g. supplied scale_text) ──

_COLLAPSED = {  # slash-stripped fraction -> paper inches
    "132": 1/32, "116": 1/16, "332": 3/32, "18": 1/8, "316": 3/16,
    "14": 1/4, "38": 3/8, "12": 1/2, "34": 3/4,
    # leading-numerator-dropped variants seen in the wild (e.g. 3/32 -> "32")
    "32": 3/32, "16": 3/16,
}
_CALLOUT_RE = re.compile(
    r"(?P<paper>\d+(?:\s+\d+/\d+|/\d+)?)\s*(?:\"|in|inch|inches)?\s*=\s*"
    r"(?P<real>\d+\s*'\s*-?\s*\d*\s*\"?|\d+(?:\.\d+)?\s*(?:'|ft|feet))",
    re.IGNORECASE,
)


def extract_scales_from_text(text: str) -> List[Tuple[float, int]]:
    """Best-effort scale extraction from already-linearized text."""
    if not text:
        return []
    fpis: Counter = Counter()
    for m in _CALLOUT_RE.finditer(text):
        real_ft = _real_feet(m.group("real"))
        if not real_ft:
            continue
        paper_raw = m.group("paper").strip()
        candidates: List[float] = []
        if "/" in paper_raw:
            pm = re.match(r"^(?:(\d+)\s+)?(\d+)/(\d+)$", paper_raw)
            if pm:
                whole = int(pm.group(1)) if pm.group(1) else 0
                candidates.append(whole + int(pm.group(2)) / int(pm.group(3)))
        else:
            digits = re.sub(r"\D", "", paper_raw)
            if digits in _COLLAPSED:                 # mangled stacked fraction
                candidates.append(_COLLAPSED[digits])
            if digits:                                # also try as a whole number
                candidates.append(float(digits))
        for paper_in in candidates:
            if paper_in and paper_in > 0:
                snapped = snap_fpi(real_ft / paper_in)
                if snapped:
                    fpis[snapped] += 1
                    break
    return fpis.most_common()


def dominant_scale(page=None, scale_text: Optional[str] = None) -> Tuple[Optional[float], str, str]:
    """Return (feet_per_inch, confidence, detail) for the page's dominant scale.

    Confidence is "high" when a single scale dominates (>=66% share or sole
    scale), else "medium". Returns (None, "none", "") when nothing valid is found.
    """
    scales: List[Tuple[float, int]] = []
    if page is not None:
        scales = extract_scales_from_page(page)
    if not scales and scale_text:
        scales = extract_scales_from_text(scale_text)
    if not scales and page is not None:
        # last resort: linear text of the page
        try:
            scales = extract_scales_from_text(page.get_text("text"))
        except Exception:
            scales = []
    if not scales:
        return None, "none", ""
    (fpi, count), *_ = scales
    total = sum(c for _, c in scales)
    share = count / total if total else 0
    conf = "high" if (len(scales) == 1 or share >= 0.66) else "medium"
    detail = f"{fpi:g} ft/in (share {share:.0%} of {len(scales)} scales)"
    return fpi, conf, detail
