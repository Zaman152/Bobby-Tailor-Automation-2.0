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
never touches ``client.messages`` directly, so tests stub it with zero API
spend.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, field
from statistics import median as _median
from typing import List, Optional

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
