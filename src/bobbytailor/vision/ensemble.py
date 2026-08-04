"""Ensemble / self-consistency voting for residual vision numbers (21-11).

Implements V3-ACC-03 (N-run voting) and the guard half of V3-PROD-02 (hard
per-run API budget). Scope is strictly the RESIDUAL vision path — raster-only
PDFs, symbols the clusterer cannot isolate, semantic disagreements. Anything
geometry or the text layer can answer never reaches this module
(21-RESEARCH.md §4, normative).

Voting rules (RESEARCH §4, exact):

- EA counts → median; accept when ``max − min ≤ max(1, 10% of median)``.
- SF/LF (raster path only) → median; accept only when relative spread
  ``(max − min) / |median| ≤ 10%``; else ``needs_review``.
- Agreement → confidence mapping: unanimous → ``high``; majority within
  tolerance → ``medium``; no majority → ``low`` + ``needs_review``.
- The full per-item vote vector is persisted on every result for
  auditability — disagreement can never silently pass through. This is the
  structural fix for the historical 397,500-vs-1,131,112 SF run-to-run
  variance failure.

Budget rules (V3-PROD-02 / Pitfall 7, verbatim policy):

- Every API call on an ensemble path must pass through
  :meth:`BudgetGuard.charge` using the ``_cost_usd`` result-metadata stamp
  (claude_analyzer convention).
- The cap is HARD: a charge that would exceed it raises
  :class:`BudgetExceeded` and is NOT accumulated; remaining items become
  ``needs_review`` with reason ``"budget_exhausted"`` — never a silent
  partial result.

All API access goes through an injectable ``analyze_call`` callable
(TakeoffPipeline analyzer-injection pattern, 20-00 decision) — this module
never touches the Anthropic client directly, so tests stub it with zero API
spend.
"""

from __future__ import annotations

import inspect
import json
import logging
import math
import threading
from dataclasses import asdict, dataclass, field
from statistics import median as _median
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Unit kinds measured as areas/lengths on the raster fallback path. Anything
# else (EA counts and unknown kinds) uses the discrete-count tolerance.
_SPREAD_UNIT_KINDS = frozenset({"SF", "LF"})

# Relative spread acceptance threshold for SF/LF raster votes (RESEARCH §4).
SPREAD_TOLERANCE = 0.10

# EA tolerance floor: max(1, 10% of median) — a ±1 disagreement on small
# counts is normal sampling noise, never a review trigger by itself.
EA_TOLERANCE_FLOOR = 1.0


class BudgetExceeded(RuntimeError):
    """Raised when a charge would push spend past the per-run budget cap.

    Carries the accounting state so callers can report exactly how much was
    spent against the cap (Pitfall 7: the flag must say WHY items were left
    unresolved, never silently truncate).
    """

    def __init__(self, spent_usd: float, cap_usd: float, attempted_usd: Optional[float] = None):
        self.spent_usd = float(spent_usd)
        self.cap_usd = float(cap_usd)
        self.attempted_usd = None if attempted_usd is None else float(attempted_usd)
        msg = "API budget exhausted: spent ${:.4f} of ${:.4f} cap".format(
            self.spent_usd, self.cap_usd
        )
        if self.attempted_usd is not None:
            msg += " (refused charge of ${:.4f})".format(self.attempted_usd)
        super().__init__(msg)


class BudgetGuard:
    """Thread-safe hard cap on per-run API spend (V3-PROD-02 guard half).

    Consumed by the ensemble fan-out here, verify-retry (21-14) and the
    pipeline (21-13). ``charge()`` accumulates the actual ``_cost_usd`` of a
    completed call; a charge that would exceed the cap raises
    :class:`BudgetExceeded` WITHOUT accumulating, so ``spent_usd`` only ever
    reflects paid-and-accepted work. An optional before-call reservation is
    available via :meth:`would_exceed` for callers that can estimate cost
    up front.
    """

    def __init__(self, max_usd: float):
        max_usd = float(max_usd)
        if max_usd < 0:
            raise ValueError("BudgetGuard: max_usd must be >= 0, got {}".format(max_usd))
        self.max_usd = max_usd
        self._spent = 0.0
        self._refused = 0
        self._lock = threading.Lock()

    @property
    def spent_usd(self) -> float:
        """Total accepted charges so far, in USD."""
        with self._lock:
            return self._spent

    @property
    def remaining(self) -> float:
        """Budget still available, in USD (never negative)."""
        with self._lock:
            return max(0.0, self.max_usd - self._spent)

    @property
    def exhausted(self) -> bool:
        """True when no budget remains."""
        return self.remaining <= 0.0

    @property
    def refused_charges(self) -> int:
        """How many completed calls this guard REFUSED to accept.

        A refusal is the moment the cap stopped the run doing work. Counting
        them is what makes truncation provable after the fact.
        """
        with self._lock:
            return self._refused

    @property
    def truncated(self) -> bool:
        """True once the cap has actually STOPPED work — not merely run low.

        ``exhausted`` answers a different question: does budget REMAIN? Crow's
        paid run finished with $0.0012 of its $0.60 cap unspent, so
        ``exhausted`` was False — while the guard had refused a ~$0.21 charge
        and two sheets had skipped their remaining passes. The run WAS
        truncated and the report presented it as complete.

        Any consumer asking "did this run do all the work it set out to do?"
        must ask THIS, never ``exhausted``.
        """
        return self.refused_charges > 0 or self.exhausted

    def would_exceed(self, cost_usd: float) -> bool:
        """Before-call reservation check: would *cost_usd* blow the cap?"""
        with self._lock:
            return self._spent + float(cost_usd or 0.0) > self.max_usd + 1e-9

    def charge(self, cost_usd: float) -> float:
        """Accumulate *cost_usd*; raise :class:`BudgetExceeded` past the cap.

        The refused charge is NOT accumulated — the guard's ledger only holds
        accepted spend, so "exactly N calls charged" is auditable after an
        abort.

        Args:
            cost_usd: Actual cost of a completed API call (the ``_cost_usd``
                      result-metadata stamp).

        Returns:
            Total spend after the charge.

        Raises:
            BudgetExceeded: When the charge would exceed ``max_usd``.
            ValueError:     On negative cost.
        """
        cost = float(cost_usd or 0.0)
        if cost < 0:
            raise ValueError("BudgetGuard.charge: negative cost {}".format(cost))
        with self._lock:
            if self._spent + cost > self.max_usd + 1e-9:
                # Count the refusal BEFORE raising: this is the only durable
                # record that the cap stopped work, and every caller of this
                # method handles the exception by skipping remaining passes.
                self._refused += 1
                raise BudgetExceeded(self._spent, self.max_usd, attempted_usd=cost)
            self._spent += cost
            return self._spent


@dataclass
class EnsembleResult:
    """Outcome of an ensemble vote over N samples of one quantity.

    ``votes`` always carries the FULL sample vector (auditability
    requirement — RESEARCH §4 "persist per-item vote vectors"). ``value`` is
    the median best-estimate even when flagged, so a reviewer sees what the
    ensemble would have said.
    """

    value: Optional[float]
    votes: List[float] = field(default_factory=list)
    confidence: str = "low"          # 'high' | 'medium' | 'low'
    needs_review: bool = True
    spread: float = 0.0              # relative (max-min)/|median|; absolute when median == 0
    n_samples: int = 0
    method: str = "vote_median"      # 'vote_median' | 'tiled+vote'
    reason: Optional[str] = None     # e.g. 'budget_exhausted', 'no_samples'
    temperature_ignored: bool = False

    def to_dict(self) -> dict:
        """Plain-dict form for report persistence (vote vector included)."""
        return asdict(self)


def _spread_of(values: List[float], med: float) -> float:
    """Relative spread ``(max-min)/|median|``; absolute range when median==0."""
    rng = max(values) - min(values)
    if med == 0:
        return float(rng)
    return float(rng / abs(med))


def vote(samples: list, unit_kind: str) -> EnsembleResult:
    """Vote over *samples* for one item using the RESEARCH §4 thresholds.

    Acceptance:
      - EA (and any non-SF/LF kind): accept when
        ``max − min ≤ max(1, 10% of |median|)``.
      - SF/LF (raster fallback only): accept when relative spread
        ``(max − min)/|median| ≤ 10%``.
      - Otherwise a STRICT MAJORITY of samples individually within tolerance
        of the median still accepts at ``medium`` (self-consistency: outlier
        minority loses the vote); no majority → ``low`` + ``needs_review``.

    Confidence mapping: unanimous → ``high``; majority within tolerance →
    ``medium``; none → ``low`` + ``needs_review``. Fewer than 2 usable
    samples can never establish consensus → ``low`` + ``needs_review``.

    Args:
        samples:   Numeric sample values (non-numeric/None entries dropped).
        unit_kind: 'EA' | 'SF' | 'LF' (case-insensitive; unknown → EA rule).

    Returns:
        :class:`EnsembleResult` with the full vote vector persisted.
    """
    values: List[float] = []
    for s in samples or []:
        if s is None:
            continue
        try:
            values.append(float(s))
        except (TypeError, ValueError):
            continue

    if not values:
        return EnsembleResult(
            value=None, votes=[], confidence="low", needs_review=True,
            spread=0.0, n_samples=0, reason="no_samples",
        )

    med = float(_median(values))

    if len(values) == 1:
        # A single sample has no consensus to measure — flag it.
        return EnsembleResult(
            value=values[0], votes=list(values), confidence="low",
            needs_review=True, spread=0.0, n_samples=1,
            reason="insufficient_samples",
        )

    kind = (unit_kind or "EA").strip().upper()
    spread = _spread_of(values, med)
    rng = max(values) - min(values)

    if kind in _SPREAD_UNIT_KINDS:
        tolerance = SPREAD_TOLERANCE * abs(med)
        accepted = med != 0 and spread <= SPREAD_TOLERANCE
    else:  # EA counts (and unknown kinds — safest is the discrete rule)
        tolerance = max(EA_TOLERANCE_FLOOR, SPREAD_TOLERANCE * abs(med))
        accepted = rng <= tolerance

    unanimous = all(v == values[0] for v in values)
    within = [v for v in values if abs(v - med) <= tolerance]
    has_majority = len(within) * 2 > len(values)

    if unanimous:
        confidence, needs_review, reason = "high", False, None
    elif accepted or has_majority:
        # Majority-within-tolerance (RESEARCH §4 confidence mapping): either
        # the whole vector is inside the band, or a strict majority agrees
        # with the median and the outlier minority loses the vote.
        confidence, needs_review, reason = "medium", False, None
    else:
        confidence, needs_review, reason = "low", True, "no_majority"

    return EnsembleResult(
        value=med,
        votes=list(values),
        confidence=confidence,
        needs_review=needs_review,
        spread=spread,
        n_samples=len(values),
        reason=reason,
    )


# ── Ensemble fan-out (run_ensemble) ──────────────────────────────────────────

# Diversity ladder for self-consistency sampling (RESEARCH §4: 0.4–0.7 —
# identical t=0 runs can repeat the same error). Samples beyond three cycle.
TEMPERATURE_LADDER: Tuple[float, ...] = (0.4, 0.55, 0.7)

# Escalation size: +2 samples when the first N disagree (N=3 → 5 total).
ESCALATION_EXTRA_SAMPLES = 2

# One-time runtime probe cache (RESEARCH Open Question 3): whether the model
# honors the temperature parameter. Keyed by caller-supplied probe_key so
# different models/routes can cache independently. Values: True = temperature
# IGNORED (use prompt variation instead), False = honored.
_TEMP_PROBE_CACHE: Dict[str, bool] = {}


def reset_temperature_probe_cache() -> None:
    """Clear the cached temperature-honored probe answers (test hook)."""
    _TEMP_PROBE_CACHE.clear()


def ensemble_settings() -> dict:
    """Single source for ensemble runtime settings (consumed by 21-13 RunSettings).

    Returns:
        ``{"n": ENSEMBLE_N, "budget_usd": API_BUDGET_PER_RUN_USD}`` read from
        config (env-driven, conftest-pinned in tests).
    """
    from bobbytailor import config  # deferred: read env-derived settings at call time

    return {
        "n": int(getattr(config, "ENSEMBLE_N", 3)),
        "budget_usd": float(getattr(config, "API_BUDGET_PER_RUN_USD", 10.0)),
    }


def _call_with_supported_kwargs(fn: Callable, **kwargs):
    """Invoke *fn* passing only the kwargs its signature accepts.

    Lets injected analyzer callables declare any subset of
    ``(sample_index, temperature, prompt_variation, image, tile_index,
    tile_grid, tile_rect)`` — real wrappers close over prompt/image and take
    what they need; simple test lambdas take only ``sample_index``.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(**kwargs)
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    allowed = {k: v for k, v in kwargs.items() if k in params}
    return fn(**allowed)


def _result_cost(res) -> float:
    """Actual USD cost of a sample: the ``_cost_usd`` result-metadata stamp."""
    if isinstance(res, dict):
        try:
            return float(res.get("_cost_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _sample_value(res) -> Optional[float]:
    """Extract the numeric sample value from an analyzer result.

    Accepts a bare number, or a dict carrying one of ``value`` /
    ``count_estimate`` / ``quantity`` (the residual-path numeric fields).
    Error dicts and non-numeric results yield None (excluded from votes).
    """
    if isinstance(res, (int, float)) and not isinstance(res, bool):
        return float(res)
    if isinstance(res, dict):
        if res.get("error"):
            return None
        for key in ("value", "count_estimate", "quantity"):
            v = res.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
    return None


def _payload_fingerprint(res) -> Optional[str]:
    """Canonical fingerprint of a dict result's payload (metadata stripped).

    Used by the temperature probe: two t-varied samples with byte-identical
    payloads indicate the model ignored the temperature parameter. Non-dict
    results return None — identical scalars across temperatures are common
    legitimate agreement, not evidence of ignoring temperature.
    """
    if not isinstance(res, dict):
        return None
    payload = {k: v for k, v in res.items() if not k.startswith("_")}
    if not payload:
        return None
    try:
        return json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None


def _probe_temperature_ignored(first, second, probe_key: str) -> Optional[bool]:
    """One-time probe: did two t-varied samples produce identical payloads?

    Caches a definite True/False under *probe_key*; returns None (unknown,
    not cached) when either payload cannot be fingerprinted.
    """
    fp1, fp2 = _payload_fingerprint(first), _payload_fingerprint(second)
    if fp1 is None or fp2 is None:
        return None
    ignored = fp1 == fp2
    _TEMP_PROBE_CACHE[probe_key] = ignored
    if ignored:
        logger.info(
            "run_ensemble: model ignores temperature (probe_key=%s) — "
            "falling back to prompt variation for sample diversity", probe_key,
        )
    return ignored


def run_ensemble(
    analyze_call: Callable,
    n: Optional[int] = None,
    escalate_on_disagreement: bool = True,
    budget: Optional[BudgetGuard] = None,
    unit_kind: str = "EA",
    extra_members: Optional[Sequence[float]] = None,
    probe_key: str = "default",
) -> EnsembleResult:
    """Fan out N ensemble samples via *analyze_call* and vote (V3-ACC-03).

    Sampling protocol (RESEARCH §4):

    - N initial samples (default ``ENSEMBLE_N``, conftest-pinned to 3) via
      ``analyze_call(sample_index=i, temperature=t, prompt_variation=k)`` —
      the callable closes over prompt/image (TakeoffPipeline injection
      pattern) and may accept any subset of those kwargs.
    - Diversity via the temperature ladder ``(0.4, 0.55, 0.7)``. A one-time
      runtime probe (cached per *probe_key*) compares the first two t-varied
      payloads; when identical, the model is ignoring temperature (Open
      Question 3) and later samples get a nonzero ``prompt_variation`` so the
      caller varies prompt ordering / tile offsets instead.
    - Disagreement (vote → needs_review) with *escalate_on_disagreement*
      draws +2 more samples, then re-votes over all 5.
    - Every sample's ``_cost_usd`` is charged to *budget*; on
      :class:`BudgetExceeded` (or an already-exhausted guard) sampling stops
      and the current-best result returns with ``needs_review=True`` and
      reason ``"budget_exhausted"`` — never a silent partial (Pitfall 7).

    Args:
        analyze_call:  Injectable analyzer callable returning a number or a
                       result dict (``value``/``count_estimate``/``quantity``
                       + ``_cost_usd`` metadata).
        n:             Initial sample count (None → config ``ENSEMBLE_N``).
        escalate_on_disagreement: Draw +2 samples when the first N disagree.
        budget:        Optional :class:`BudgetGuard` charged per sample.
        unit_kind:     'EA' | 'SF' | 'LF' — selects the vote tolerance rule.
        extra_members: Additional pre-computed vote members (e.g. the
                       :func:`run_tiled_count` result) joining the samples —
                       tiling is ONE member, never the sole answer.
        probe_key:     Cache key for the temperature-honored probe (use one
                       key per model/route).

    Returns:
        :class:`EnsembleResult`; ``method`` is ``'tiled+vote'`` when
        *extra_members* were voted alongside the samples, else
        ``'vote_median'``.
    """
    settings = ensemble_settings()
    initial_n = int(n) if n else settings["n"]
    extras = [float(m) for m in (extra_members or [])]

    votes: List[float] = []
    raw_results: list = []
    temperature_ignored = _TEMP_PROBE_CACHE.get(probe_key)  # None = unprobed
    exhausted = False

    idx = 0
    target = initial_n
    while idx < target:
        if budget is not None and budget.exhausted:
            exhausted = True
            break
        temperature = TEMPERATURE_LADDER[idx % len(TEMPERATURE_LADDER)]
        # Prompt-variation fallback: nonzero once the probe says the model
        # ignores temperature (the callable varies ordering/tile offsets).
        prompt_variation = idx if temperature_ignored else 0
        res = _call_with_supported_kwargs(
            analyze_call,
            sample_index=idx,
            temperature=temperature,
            prompt_variation=prompt_variation,
        )
        if budget is not None:
            try:
                budget.charge(_result_cost(res))
            except BudgetExceeded:
                # Refused charge: the sample is NOT voted — the ledger and
                # the vote vector only ever hold paid-for work.
                exhausted = True
                break
        raw_results.append(res)
        value = _sample_value(res)
        if value is not None:
            votes.append(value)

        if temperature_ignored is None and idx == 1:
            temperature_ignored = _probe_temperature_ignored(
                raw_results[0], raw_results[1], probe_key
            )
        idx += 1

        # Escalation decision at the initial-N boundary: disagreement → +2.
        if idx == target and target == initial_n and escalate_on_disagreement:
            interim = vote(votes + extras, unit_kind)
            if interim.needs_review:
                target = initial_n + ESCALATION_EXTRA_SAMPLES
                logger.info(
                    "run_ensemble: first %d samples disagree (%s) — "
                    "escalating to %d samples", initial_n, interim.votes, target,
                )

    result = vote(votes + extras, unit_kind)
    result.method = "tiled+vote" if extras else "vote_median"
    result.temperature_ignored = bool(temperature_ignored)
    if exhausted:
        # Budget abort is NEVER a silent partial: flag with the verbatim
        # Pitfall 7 reason regardless of how well the paid samples agree.
        result.needs_review = True
        result.confidence = "low"
        result.reason = "budget_exhausted"
        logger.warning(
            "run_ensemble: budget exhausted after %d voted sample(s) — "
            "flagged needs_review (budget_exhausted)", len(votes),
        )
    return result


# ── Tiled counting (one ensemble member) ─────────────────────────────────────

# RESEARCH §4: tiles overlap 15–20% — 17.5% is the midpoint.
TILE_OVERLAP_FRAC = 0.175

# Coarse position grid the model reports detection cells on, per tile
# (grid-cell granularity is enough for overlap-band NMS — RESEARCH §4).
POSITION_GRID_CELLS = 10

# NMS radius in coarse-cell units: detections from different tiles within
# 1.5 cells of each other inside an overlap band are the same object.
_NMS_RADIUS_CELLS = 1.5


def _source_dims(page_image_or_page) -> Tuple[float, float]:
    """(width, height) of a fitz.Page (points) or PIL image (pixels)."""
    rect = getattr(page_image_or_page, "rect", None)
    if rect is not None and hasattr(page_image_or_page, "get_pixmap"):
        return float(rect.width), float(rect.height)
    size = getattr(page_image_or_page, "size", None)
    if size is not None:
        return float(size[0]), float(size[1])
    raise TypeError(
        "run_tiled_count: expected a fitz.Page or PIL.Image, got {!r}".format(
            type(page_image_or_page)
        )
    )


def _tile_rects(
    width: float, height: float, grid: Tuple[int, int], overlap_frac: float
) -> List[Tuple[int, int, Tuple[float, float, float, float]]]:
    """Grid tile rects with *overlap_frac* overlap between adjacent tiles.

    Each tile expands by half the overlap into each neighbour, so the shared
    band between two adjacent tiles is ``overlap_frac × tile_size`` wide.
    """
    cols, rows = max(1, int(grid[0])), max(1, int(grid[1]))
    tile_w, tile_h = width / cols, height / rows
    half_ow, half_oh = overlap_frac * tile_w / 2.0, overlap_frac * tile_h / 2.0
    rects = []
    for ry in range(rows):
        for cx in range(cols):
            x0 = max(0.0, cx * tile_w - half_ow)
            x1 = min(width, (cx + 1) * tile_w + half_ow)
            y0 = max(0.0, ry * tile_h - half_oh)
            y1 = min(height, (ry + 1) * tile_h + half_oh)
            rects.append((cx, ry, (x0, y0, x1, y1)))
    return rects


def _render_tile(page_image_or_page, rect: Tuple[float, float, float, float]):
    """Render one tile: render_clip_crop for pages, crop for PIL images."""
    if hasattr(page_image_or_page, "get_pixmap"):
        # Deferred import — the shared zoom primitive (21-05 decision).
        from bobbytailor.pipeline.pdf_analyzer import render_clip_crop

        return render_clip_crop(page_image_or_page, rect)
    return page_image_or_page.crop(tuple(int(round(v)) for v in rect))


def run_tiled_count(
    page_image_or_page,
    grid: Tuple[int, int],
    analyze_call: Callable,
    budget: Optional[BudgetGuard] = None,
    overlap_frac: float = TILE_OVERLAP_FRAC,
    position_grid: int = POSITION_GRID_CELLS,
) -> float:
    """Count symbols by tiling the sheet with overlap + NMS dedup (RESEARCH §4).

    Integrates the existing ``COUNT_TILING`` machinery (grid comes from
    ``accuracy_config.count_tiling_grid()``; the caller activates tiling via
    the >50-expected-instances heuristic). Tiles overlap 15–20% so boundary
    symbols are never sliced out of both tiles; detections that appear in
    BOTH tiles inside an overlap band are suppressed by position-based NMS at
    coarse grid-cell granularity. The summed count is ONE ensemble member —
    pass it to :func:`run_ensemble` via ``extra_members`` so voting
    reconciles it with whole-sheet counts (never the sole answer).

    Per-tile analyzer contract (all API access via the injected callable):
    ``analyze_call(image=..., tile_index=..., tile_grid=(cx, ry),
    tile_rect=(x0, y0, x1, y1))`` returns a dict with either

    - ``"detections"``: list of ``{"cell": [col, row]}`` coarse positions on
      the *position_grid* × *position_grid* grid over that tile (enables
      overlap dedup), or
    - a bare count (``count_estimate`` / ``quantity`` / ``value``) when the
      schema provides no positions — added as-is, dedup impossible.

    Args:
        page_image_or_page: ``fitz.Page`` (rendered via ``render_clip_crop``,
                            the shared zoom primitive) or ``PIL.Image``.
        grid:               (cols, rows) — ``accuracy_config.count_tiling_grid()``.
        analyze_call:       Injectable per-tile analyzer callable.
        budget:             Optional :class:`BudgetGuard`; every tile call's
                            ``_cost_usd`` is charged. :class:`BudgetExceeded`
                            propagates so the caller flags the item.
        overlap_frac:       Fractional tile overlap (default 17.5%).
        position_grid:      Coarse position cells per tile edge (default 10).

    Returns:
        Deduplicated total count as a float (one vote member).

    Raises:
        BudgetExceeded: When a tile charge would exceed the budget cap.
    """
    width, height = _source_dims(page_image_or_page)
    rects = _tile_rects(width, height, grid, overlap_frac)

    positional: List[Tuple[float, float, int]] = []  # (px, py, tile_index)
    fallback_total = 0.0

    for tile_index, (cx, ry, rect) in enumerate(rects):
        tile_img = _render_tile(page_image_or_page, rect)
        res = _call_with_supported_kwargs(
            analyze_call,
            image=tile_img,
            tile_index=tile_index,
            tile_grid=(cx, ry),
            tile_rect=rect,
        )
        if budget is not None:
            budget.charge(_result_cost(res))  # BudgetExceeded propagates

        detections = res.get("detections") if isinstance(res, dict) else None
        if detections:
            x0, y0, x1, y1 = rect
            tw, th = x1 - x0, y1 - y0
            for det in detections:
                cell = None
                if isinstance(det, dict):
                    cell = det.get("cell") or det.get("grid_cell")
                if not cell or len(cell) < 2:
                    fallback_total += 1.0  # positionless detection — count it
                    continue
                col, row = float(cell[0]), float(cell[1])
                positional.append((
                    x0 + (col + 0.5) * tw / position_grid,
                    y0 + (row + 0.5) * th / position_grid,
                    tile_index,
                ))
        else:
            value = _sample_value(res)
            if value is not None:
                fallback_total += value

    # Position-based NMS in the overlap bands: a detection covered by >= 2
    # tile rects that sits within the NMS radius of an already-accepted
    # detection FROM A DIFFERENT TILE is the same physical symbol seen twice.
    tile_bounds = [r for (_, _, r) in rects]
    nms_radius = _NMS_RADIUS_CELLS * max(
        (width / max(1, int(grid[0]))) / position_grid,
        (height / max(1, int(grid[1]))) / position_grid,
    )

    def _covering_tiles(px: float, py: float) -> int:
        return sum(
            1 for (bx0, by0, bx1, by1) in tile_bounds
            if bx0 <= px <= bx1 and by0 <= py <= by1
        )

    accepted_overlap: List[Tuple[float, float, int]] = []
    positional_counted = 0
    for px, py, tile_index in positional:
        if _covering_tiles(px, py) >= 2:
            duplicate = any(
                other_tile != tile_index
                and math.hypot(px - ax, py - ay) <= nms_radius
                for ax, ay, other_tile in accepted_overlap
            )
            if duplicate:
                continue
            accepted_overlap.append((px, py, tile_index))
        positional_counted += 1

    deduped = float(positional_counted) + fallback_total
    logger.info(
        "run_tiled_count: %d tiles (%dx%d, %.0f%% overlap) → %d positional "
        "(%d suppressed in overlap bands) + %.0f positionless = %.0f",
        len(rects), int(grid[0]), int(grid[1]), overlap_frac * 100,
        len(positional), len(positional) - positional_counted,
        fallback_total, deduped,
    )
    return deduped
