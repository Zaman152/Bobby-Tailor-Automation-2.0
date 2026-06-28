"""
Drawing scale extraction — turn a printed scale notation into a usable ratio.

Construction drawings state a scale in the title block or near each detail, e.g.:

  Architectural : 1/4" = 1'-0",  3/16" = 1'-0",  1 1/2" = 1'-0"
  Engineering   : 1" = 20',  1" = 50'
  Metric / ratio: 1:100,  1:50,  SCALE 1:200

This module parses those notations into:
  - ``feet_per_inch``: real-world feet represented by one inch of drawing paper
  - ``ratio``: real-world units per one drawing unit (dimensionless)
  - ``system``: "architectural" | "engineering" | "ratio"

Combined with the render DPI (pixels per drawing inch) this yields feet-per-pixel,
which a future pixel-measurement (CV) step can use to convert traced geometry into
real quantities. On its own it lets the app surface the scale it detected and gives
the measurement pass an explicit, trustworthy conversion factor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ScaleInfo:
    raw: str
    feet_per_inch: Optional[float]   # real feet per 1 paper inch
    ratio: Optional[float]           # real units per 1 drawing unit
    system: str                      # architectural | engineering | ratio | unknown

    def to_dict(self) -> dict:
        return asdict(self)

    def feet_per_pixel(self, render_dpi: float) -> Optional[float]:
        """Feet represented by one rendered pixel at *render_dpi* pixels/inch."""
        if not self.feet_per_inch or not render_dpi:
            return None
        return self.feet_per_inch / render_dpi


def _to_inches(token: str) -> Optional[float]:
    """Parse an inch token like '1/4', '3/16', '1 1/2', '1' into inches."""
    token = token.strip().strip('"').strip()
    if not token:
        return None
    m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", token)  # mixed: 1 1/2
    if m:
        whole, num, den = map(int, m.groups())
        return whole + num / den
    m = re.match(r"^(\d+)/(\d+)$", token)          # fraction: 1/4
    if m:
        return int(m.group(1)) / int(m.group(2))
    try:
        return float(token)
    except ValueError:
        return None


def _to_feet(token: str) -> Optional[float]:
    """Parse a feet/inch token like "1'-0\"", "20'", "1'-6\"" into feet."""
    token = token.strip()
    m = re.match(r"^(\d+)\s*'\s*-?\s*(\d+)?\s*\"?$", token)
    if m:
        feet = int(m.group(1))
        inches = int(m.group(2)) if m.group(2) else 0
        return feet + inches / 12.0
    try:
        return float(token)
    except ValueError:
        return None


# "1/4\" = 1'-0\"" / "3/16in = 1'-0"  (architectural)
_ARCH = re.compile(
    r"""(?P<paper>\d+(?:\s+\d+/\d+|/\d+)?)\s*(?:"|in|inch|inches)?\s*=\s*
        (?P<real>\d+\s*'\s*-?\s*\d*\s*"?|\d+(?:\.\d+)?\s*(?:'|ft|feet))""",
    re.IGNORECASE | re.VERBOSE,
)
# "1:100" / "SCALE 1:50" (ratio / metric)
_RATIO = re.compile(r"\b(\d+)\s*:\s*(\d+)\b")


def parse_scale(text: Optional[str]) -> Optional[ScaleInfo]:
    """Parse the first recognizable scale notation in *text*. None if absent.

    "NTS"/"NOT TO SCALE" returns a ScaleInfo with system="unknown" and no ratio so
    callers can explicitly know the sheet is unscaled.
    """
    if not text:
        return None
    raw = " ".join(str(text).split())

    if re.search(r"\bN\.?T\.?S\.?\b|not\s+to\s+scale", raw, re.IGNORECASE):
        return ScaleInfo(raw="NTS", feet_per_inch=None, ratio=None, system="unknown")

    m = _ARCH.search(raw)
    if m:
        paper_in = _to_inches(m.group("paper"))
        real_ft = _to_feet(m.group("real"))
        if paper_in and real_ft:
            fpi = real_ft / paper_in
            # Engineering scales (1" = 20') vs architectural (fractional inch = 1').
            system = "engineering" if paper_in >= 1 and real_ft >= 10 else "architectural"
            return ScaleInfo(
                raw=raw[:80], feet_per_inch=round(fpi, 6),
                ratio=round(fpi * 12.0, 6), system=system,
            )

    m = _RATIO.search(raw)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a == 1 and b > 1:
            # 1:b ratio — 1 drawing unit = b real units. Assume inch paper unit.
            fpi = b / 12.0
            return ScaleInfo(
                raw=raw[:80], feet_per_inch=round(fpi, 6),
                ratio=float(b), system="ratio",
            )

    return None
