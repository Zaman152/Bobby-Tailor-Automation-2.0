"""Run-start retrieval of learned context (V3-LEARN-02/03) + guardrail (V3-LEARN-04).

One query bundle per run, keyed by ``(project_key, project_type)``
(21-RESEARCH.md §6 "Retrieval + injection"), producing a
:class:`LearnedContext` injected at three seams:

    1. **Prompts** — :meth:`LearnedContext.render_prompt_hint` renders an
       expected-items + naming-conventions block into the existing
       ``user_hint`` slot (the ``_build_count_hint`` convention).
    2. **Aggregation** — :meth:`LearnedContext.lookup_name` is consulted by
       ``aggregator.normalize_item_name`` BEFORE the static ``ITEM_NAME_MAP``
       regex list (the learned table supersedes the map over time; the map is
       never deleted — it is the cold-start floor).
    3. **Calculator** — :meth:`LearnedContext.get_assumption` supplies wall
       heights and per-sheet scale priors (a scale prior is a cross-check
       that ``resolve_scale_v2`` ranks LAST, 21-07).

Anti-amplification guardrail (RESEARCH §6, LOCKED via CONTEXT — the safety
half of V3-LEARN-04): learned values may adjust *semantics* (names, units,
expected items, assumptions with no deterministic source) but must NEVER
override a quantity whose provenance is ``geometry``/``text_layer`` with
HIGH confidence. Prior human *quantity* corrections attach a ``re_verify``
flag via :func:`apply_learned_quantity_flags` — never a silent substitution
— except for the exact ``(project_key, run-identical inputs)`` re-run case,
which callers must assert explicitly via ``identical_inputs=True``.

Security invariants (phase threat model):
    * Store reads go through ``store.py`` APIs only — no SQL in this module.
    * Every learned string is hostile input (humans typed it): prompt-bound
      strings are wrapped in the ``<pdf_text>`` data delimiters (21-08
      convention) and the whole hint is capped at :data:`MAX_HINT_CHARS`.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from bobbytailor.learning import store
from bobbytailor.vision.prompts import wrap_pdf_text

logger = logging.getLogger(__name__)

#: Rendered prompt hint is hard-capped at this many characters
#: (payload-stuffing / prompt-flooding defense — threat model MEDIUM).
MAX_HINT_CHARS = 2000

#: Manifest rows join the expected-items hint only at this expectation
#: strength (seen_in_runs / verified_runs_total) or better.
MIN_EXPECTATION = 0.5

#: How many recent corrections to scan for project-scoped quantity flags and
#: project-type inference (store default page size).
_CORRECTIONS_SCAN_LIMIT = 500

#: Provenance values whose HIGH-confidence quantities learning must never
#: touch (mirrors ``bobbytailor.vision.fusion`` deterministic sources; kept
#: as literals here so learning does not import the vision package).
_PROTECTED_PROVENANCES = ("geometry", "text_layer")


def _normalize(text: Any) -> str:
    """Whitespace-collapsed, lowercased match key for learned lookups."""
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _append_reason(existing: Any, reason: str) -> str:
    """Append *reason* to a semicolon-joined review_reason string."""
    existing = str(existing or "").strip()
    if not existing:
        return reason
    if reason in existing:
        return existing
    return "%s; %s" % (existing, reason)


@dataclass
class LearnedContext:
    """One run's retrieved learning bundle (vocabulary/assumptions/manifest).

    ``vocabulary`` rows come pre-ordered by the store (weight DESC,
    last_seen DESC) so the max-weight mapping wins ties per the RESEARCH §6
    conflict policy. ``assumptions`` is already deduped by key with the
    specificity precedence exact ``project_key`` > ``project_type`` > global
    (21-04 retrieval-precedence decision).
    """

    project_key: str = ""
    project_type: str = ""
    vocabulary: List[dict] = field(default_factory=list)
    assumptions: Dict[str, dict] = field(default_factory=dict)
    expected_items: List[dict] = field(default_factory=list)
    #: Prior human quantity corrections on THIS project (scope 'item'),
    #: keyed by normalized item pattern — drives re_verify flags only.
    quantity_corrections: Dict[str, dict] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Renderer 1 — prompt hint (user_hint slot)
    # ------------------------------------------------------------------

    def render_prompt_hint(self) -> Optional[str]:
        """Expected-items + naming-conventions hint block, or None when empty.

        Cold start (empty store) returns None — no hint, identical to
        today's behavior. Learned strings are DATA, not instructions: every
        human-typed value is wrapped in the ``<pdf_text>`` delimiters and
        the whole block is capped at :data:`MAX_HINT_CHARS`. The phrasing is
        deliberately a *hint* — it must never assert unverified facts as
        ground truth (RESEARCH §6).
        """
        expected_lines: List[str] = []
        for row in self.expected_items:
            if float(row.get("expectation") or 0.0) < MIN_EXPECTATION:
                continue
            name = str(row.get("item_name") or "").strip()
            if not name:
                continue
            unit = str(row.get("unit") or "").strip()
            expected_lines.append(
                "  - %s%s (seen in %s/%s verified runs)"
                % (
                    name,
                    " [%s]" % unit if unit else "",
                    row.get("seen_in_runs", 0),
                    row.get("verified_runs_total", 0),
                )
            )

        vocab_lines: List[str] = []
        seen_raw = set()
        for row in self.vocabulary:
            raw = str(row.get("raw_pattern") or "").strip()
            canonical = str(row.get("canonical_name") or "").strip()
            if not raw or not canonical:
                continue
            key = _normalize(raw)
            if key in seen_raw:
                continue  # store ordering: max-weight mapping already listed
            seen_raw.add(key)
            unit = str(row.get("unit") or "").strip()
            vocab_lines.append(
                '  - "%s" -> "%s"%s' % (raw, canonical, " [%s]" % unit if unit else "")
            )

        if not expected_lines and not vocab_lines:
            return None

        def _assemble(n_expected: int, n_vocab: int) -> str:
            parts = [
                "LEARNED PROJECT CONTEXT — hints accumulated from previously "
                "verified runs of this project type. These are EXPECTATIONS to "
                "check against the drawing, NOT ground truth; never invent an "
                "item just because it is listed here."
            ]
            if n_expected:
                parts.append(
                    "Items previously verified for this project type:\n"
                    + wrap_pdf_text("\n".join(expected_lines[:n_expected]))
                )
            if n_vocab:
                parts.append(
                    "Known naming conventions (raw text -> canonical item name):\n"
                    + wrap_pdf_text("\n".join(vocab_lines[:n_vocab]))
                )
            return "\n".join(parts)

        # Cap at MAX_HINT_CHARS by dropping trailing lines — never by string
        # slicing, which could sever a closing </pdf_text> delimiter.
        n_expected, n_vocab = len(expected_lines), len(vocab_lines)
        hint = _assemble(n_expected, n_vocab)
        while len(hint) > MAX_HINT_CHARS and (n_expected or n_vocab):
            if n_vocab >= n_expected:
                n_vocab -= 1
            else:
                n_expected -= 1
            if not n_expected and not n_vocab:
                return None
            hint = _assemble(n_expected, n_vocab)
        return hint

    # ------------------------------------------------------------------
    # Renderer 2 — aggregation naming lookup
    # ------------------------------------------------------------------

    def lookup_name(self, raw: Any) -> Optional[Tuple[str, str]]:
        """Learned ``(canonical_name, unit)`` for *raw*, or None.

        Exact/normalized match (strip + lowercase + whitespace collapse)
        against ``raw_pattern``; the max-weight row wins (store ordering).
        """
        key = _normalize(raw)
        if not key:
            return None
        index = self._vocab_index()
        return index.get(key)

    def _vocab_index(self) -> Dict[str, Tuple[str, str]]:
        cached = getattr(self, "_vocab_index_cache", None)
        if cached is None:
            cached = {}
            for row in self.vocabulary:
                key = _normalize(row.get("raw_pattern"))
                if not key:
                    continue
                # Rows arrive weight-DESC: first mapping per key is the winner.
                if key not in cached:
                    canonical = str(row.get("canonical_name") or "").strip()
                    unit = str(row.get("unit") or "").strip()
                    if canonical:
                        cached[key] = (canonical, unit)
            object.__setattr__(self, "_vocab_index_cache", cached)
        return cached

    # ------------------------------------------------------------------
    # Renderer 3 — calculator/scale assumption read
    # ------------------------------------------------------------------

    def get_assumption(self, key: str) -> Optional[dict]:
        """Learned assumption for *key* as ``{value, weight, specificity}``.

        Backed by the store's specificity-ordered read: exact ``project_key``
        rows beat ``project_type`` rows beat global rows (RESEARCH §6).
        Returns None when nothing was learned for *key*.
        """
        return self.assumptions.get(str(key))

    def get_assumption_value(self, key: str, default: Any = None) -> Any:
        """Convenience: just the learned value for *key* (or *default*)."""
        entry = self.get_assumption(key)
        if entry is None:
            return default
        return entry.get("value", default)


def _specificity(row: Dict[str, Any]) -> str:
    if row.get("project_key"):
        return "project_key"
    if row.get("project_type"):
        return "project_type"
    return "global"


def _infer_project_type(project_key: str, corrections: List[dict]) -> Optional[str]:
    """Most recent project_type previously recorded for *project_key*.

    A repeat run of a verified project must pick up its type-level
    vocabulary/manifest at RUN START, before the pipeline's own
    ``_detect_project_type`` (which needs extracted sheets) can run.
    Corrections arrive newest-first from the store.
    """
    for row in corrections:
        if row.get("project_key") == project_key and row.get("project_type"):
            return str(row["project_type"])
    return None


def load_learned_context(
    project_key: str, project_type: Optional[str] = None
) -> LearnedContext:
    """One-query-bundle retrieval for a run (store read APIs from 21-04 only).

    When *project_type* is not yet known (run start — the detector needs
    extracted sheets), it is inferred from this project's most recent prior
    correction so repeat runs pick up their type-level vocabulary and
    expected items with zero manifest files. Cold start (empty store)
    returns an empty context whose ``render_prompt_hint()`` is None.
    """
    project_key = str(project_key or "").strip()

    # Corrections serve two purposes: project_type inference for repeat runs
    # and the project-scoped quantity-correction flags (guardrail).
    all_item_corrections = store.get_corrections(
        scope=store.SCOPE_ITEM, limit=_CORRECTIONS_SCAN_LIMIT
    )
    if not project_type:
        project_type = _infer_project_type(project_key, all_item_corrections)
    project_type = str(project_type or "").strip()

    vocabulary = store.get_vocabulary(project_type or None)
    assumptions: Dict[str, dict] = {}
    for row in store.get_assumptions(project_key or None, project_type or None):
        key = str(row.get("key") or "")
        if not key:
            continue
        assumptions[key] = {
            "value": row.get("value"),
            "weight": row.get("weight"),
            "specificity": _specificity(row),
        }
    expected_items = store.get_manifest(project_type) if project_type else []

    quantity_corrections: Dict[str, dict] = {}
    if project_key:
        for row in all_item_corrections:
            if row.get("project_key") != project_key:
                continue
            key = _normalize(row.get("item_pattern"))
            if not key or key in quantity_corrections:
                continue  # rows arrive newest-first: keep the latest per item
            quantity_corrections[key] = row

    return LearnedContext(
        project_key=project_key,
        project_type=project_type,
        vocabulary=vocabulary,
        assumptions=assumptions,
        expected_items=expected_items,
        quantity_corrections=quantity_corrections,
    )


# ---------------------------------------------------------------------------
# Anti-amplification guardrail (RESEARCH §6 verbatim policy — V3-LEARN-04)
# ---------------------------------------------------------------------------

def _corrected_quantity(correction: dict) -> Optional[float]:
    """Numeric quantity a prior human correction asserted, if any."""
    value = correction.get("corrected_value")
    if isinstance(value, dict):
        for key in ("quantity", "value", "qty", "corrected_quantity"):
            if value.get(key) is not None:
                value = value[key]
                break
        else:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _corrected_unit(correction: dict) -> Optional[str]:
    value = correction.get("corrected_value")
    if isinstance(value, dict) and value.get("unit"):
        return str(value["unit"])
    return None


def apply_learned_quantity_flags(
    items: Optional[List[dict]],
    learned: Optional[LearnedContext],
    identical_inputs: bool = False,
) -> Optional[List[dict]]:
    """Attach ``re_verify`` flags for previously human-corrected items.

    RESEARCH §6 guardrail, enforced in code: prior quantity corrections on
    this project NEVER silently substitute a fresh quantity — they attach a
    ``re_verify`` flag carrying the human's value so the item is re-checked.
    The single sanctioned exception is the exact ``(project_key,
    run-identical inputs)`` re-run case, which a caller must assert via
    ``identical_inputs=True`` (the production pipeline never does — no
    input-identity proof is plumbed today).

    Defensive hard guard (tested): a quantity whose provenance is
    ``geometry``/``text_layer`` with HIGH confidence is NEVER overwritten by
    learned data — not even on an identical-input re-run. Any such attempt
    is logged and skipped; the item keeps its deterministic value and gains
    only the re_verify flag.

    Mutates *items* in place and returns it (per-plan artifact contract).
    """
    if not items or learned is None or not learned.quantity_corrections:
        return items

    for item in items:
        if not isinstance(item, dict):
            continue
        key = _normalize(item.get("name") or item.get("description"))
        if not key:
            continue
        correction = learned.quantity_corrections.get(key)
        if correction is None:
            continue
        corrected_qty = _corrected_quantity(correction)
        if corrected_qty is None:
            continue

        try:
            current_qty = float(item.get("quantity"))
        except (TypeError, ValueError):
            current_qty = None
        if current_qty is not None and abs(current_qty - corrected_qty) < 1e-9:
            continue  # fresh value already matches the human's — nothing to flag

        provenance = str(item.get("provenance") or "").strip().lower()
        confidence = str(item.get("confidence") or "").strip().lower()
        protected = provenance in _PROTECTED_PROVENANCES and confidence == "high"

        if identical_inputs and not protected:
            # §6 exception: identical-input re-run of the same project may
            # substitute — the human corrected THIS exact extraction before.
            item["quantity"] = corrected_qty
            unit = _corrected_unit(correction)
            if unit:
                item["unit"] = unit
            item["provenance"] = "learned"
            item["learned_substitution"] = True
            item["review_reason"] = _append_reason(
                item.get("review_reason"),
                "quantity substituted from prior human correction "
                "(identical-input re-run)",
            )
            item["learned_correction"] = {
                "corrected_value": correction.get("corrected_value"),
                "corrected_at": correction.get("created_at"),
                "run_id": correction.get("run_id"),
            }
            continue

        if protected:
            # Feedback-amplification hard stop (Pitfall 8): log + skip any
            # attempt to apply a learned value over deterministic HIGH truth.
            logger.warning(
                "anti-amplification guardrail: learned correction for %r "
                "(human said %s) NOT applied over %s/HIGH quantity %s — "
                "re_verify flag attached instead",
                item.get("name"), corrected_qty, provenance, item.get("quantity"),
            )

        item["re_verify"] = True
        item["needs_review"] = True
        item["review_reason"] = _append_reason(
            item.get("review_reason"),
            "human previously corrected this item on this project — re-verify",
        )
        item["learned_correction"] = {
            "corrected_value": correction.get("corrected_value"),
            "corrected_at": correction.get("created_at"),
            "run_id": correction.get("run_id"),
        }

    return items
