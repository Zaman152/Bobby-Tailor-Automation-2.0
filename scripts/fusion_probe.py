#!/usr/bin/env python3
"""Offline fusion-binding probe (ZERO API). Feeds the REAL Crow page-1 geometry
into the deterministic binding predicates so we can see exactly what
_is_regular_grid / deterministic_symbol_name / _library_symbol_bindings /
perimeter-ring produce — the free iteration loop for making bindings
deterministic (memory crow-manifest-free-baseline)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import fitz  # noqa: E402
from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline  # noqa: E402
from bobbytailor.vision import fusion as F  # noqa: E402

PDF = "uploads/Crow - Cass White Road-Plans.pdf"
PAGE = 1

pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
doc = fitz.open(PDF)
page = doc[PAGE]
bundle = pipe._deterministic_bundle(page, doc, PDF, PAGE, "page1", "floor_plan")
groups = bundle.get("symbol_groups") or []
print(f"n groups={len(groups)}  fpp={bundle.get('fpp')}")
print("\n=== per-group deterministic predicates ===")
print(f"{'id':8}{'count':>6}{'size_ft':>16}  grid? marker? uniform? perim? det_name")
for g in sorted(groups, key=lambda g: -g.count)[:20]:
    cents = F._instance_centroids(g)
    grid = F._is_regular_grid(cents, g)
    marker = F._is_small_marker(g)
    uni = F._size_uniform(g)
    perim = F._is_perimeter_ring(g)
    det = F.deterministic_symbol_name(g)
    sz = tuple(round(x, 2) for x in (g.bbox_size_ft or (0, 0)))
    print(f"{g.candidate_id:8}{g.count:>6}{str(sz):>16}  {str(grid):5} {str(marker):6} {str(uni):7} {str(perim):5} {det}")

print("\n=== wall classes: LF + thickness(in) ===")
lf = bundle.get("wall_lf_by_class") or {}
walls = bundle.get("walls") or []
fpp = bundle.get("fpp") or 0.0
thk, n = {}, {}
for w in walls:
    c = w.thickness_class or ""
    if not c: continue
    thk[c] = thk.get(c, 0.0) + w.thickness_pt * fpp
    n[c] = n.get(c, 0) + 1
for c in sorted(lf, key=lambda c: -lf[c]):
    ti = round((thk[c]/n[c])*12, 2) if n.get(c) else 0
    print(f"  {c:6} LF={lf[c]:>8.1f}  thick={ti:>5}in  nseg={n.get(c)}")
fp = bundle.get("footprint")
if fp is not None:
    print(f"\nfootprint area_sf={getattr(fp,'area_sf',None)} perimeter_lf={getattr(fp,'perimeter_lf',None)}")
doc.close()
