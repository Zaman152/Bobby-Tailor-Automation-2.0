"""Distillation job (V3-LEARN-02): corrections log → distilled learning tables.

Replays the ``learning_corrections`` append-only log into
``learning_vocabulary`` / ``learning_assumptions`` / ``learning_manifests``.
Distilled state is a **pure function of the log**: corrections are processed
strictly one-by-one in id order, every ``last_seen`` comes from the
correction's ``created_at`` (never wall-clock now), and staleness decay
triggers on new-verified-run boundaries within the log — so any incremental
watermark partitioning reproduces exactly what ``full_rebuild=True``
produces (the auditable-rebuild guarantee, RESEARCH §6).

Conflict/decay policy (RESEARCH §6):
    * confirming correction (same key, same value)  → weight + 1.0
    * contradicting correction (same key, different value) → old rows
      weight × 0.5, then the new mapping is inserted/boosted; max-weight
      row wins retrieval, ties → most recent
    * staleness: rows of a project_type not touched within its 10 most
      recent verified runs decay weight × 0.9 when a new run arrives

Idempotent-batch + stats-dict contract follows
``stackct_store.migrate_from_json_caches``. Incremental passes advance a
``last_distilled_id`` watermark in ``learning_metadata``; ``full_rebuild``
wipes the distilled tables and replays the whole log.

Only this module and ``store.py`` touch the ``learning_*`` tables. All SQL
is parameterized — learned strings are hostile input.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from bobbytailor.learning import store

logger = logging.getLogger(__name__)

VOCAB_SCOPES = (store.SCOPE_NAME, store.SCOPE_UNIT)
ASSUMPTION_SCOPES = (store.SCOPE_SCALE, store.SCOPE_WALL_HEIGHT)
MANIFEST_SCOPES = (store.SCOPE_ITEM, store.SCOPE_MISSED_ITEM)

CONFIRM_INCREMENT = 1.0
CONTRADICTION_DECAY = 0.5
STALENESS_DECAY = 0.9

#: Sanity caps on distilled vocabulary fields (21-REVIEW WR-02): a canonical
#: name is a short human-facing item label — anything longer is a stuffed or
#: corrupted payload and must never be installed as learned vocabulary
#: (it would flow into prompt hints and aggregation renames).
MAX_CANONICAL_NAME_LEN = 100
MAX_UNIT_LEN = 20
#: Rows untouched within a project_type's N most recent verified runs decay.
STALENESS_RUN_WINDOW = 10

WATERMARK_KEY = "last_distilled_id"

WALL_HEIGHT_KEY = "wall_height_ft"
SCALE_KEY_PREFIX = "scale_fpi:"


def distill(full_rebuild: bool = False) -> Dict[str, int]:
    """Update distilled tables from corrections newer than the watermark.

    ``full_rebuild=True`` wipes the distilled tables first and replays the
    entire log (identical output to any sequence of incremental passes).
    Returns a stats dict; a pass with nothing new reports
    ``{"corrections_processed": 0, ...}`` and changes nothing.
    """
    store.init_learning_schema()
    stats: Dict[str, int] = {
        "corrections_processed": 0,
        "vocabulary_updates": 0,
        "assumption_updates": 0,
        "manifest_items": 0,
        "contradiction_decays": 0,
        "stale_decays": 0,
        "skipped": 0,
        "vocabulary_rows": 0,
        "assumption_rows": 0,
        "manifest_rows": 0,
    }
    with store._write_lock:
        conn = store.get_connection()
        try:
            if full_rebuild:
                conn.execute("DELETE FROM learning_vocabulary")
                conn.execute("DELETE FROM learning_assumptions")
                conn.execute("DELETE FROM learning_manifests")
                watermark = 0
            else:
                raw = store._get_metadata(conn, WATERMARK_KEY)
                watermark = int(raw) if raw else 0

            rows = conn.execute(
                "SELECT * FROM learning_corrections WHERE id > ? ORDER BY id",
                (watermark,),
            ).fetchall()

            touched_types: Set[str] = set()
            for row in rows:
                _apply_staleness_decay(conn, row, stats)
                scope = row["scope"]
                if scope in VOCAB_SCOPES:
                    _distill_vocabulary(conn, row, stats)
                elif scope in ASSUMPTION_SCOPES:
                    _distill_assumption(conn, row, stats)
                # manifest scopes are recomputed as a pure aggregate below
                if row["project_type"]:
                    touched_types.add(row["project_type"])
                stats["corrections_processed"] += 1

            if rows:
                _recompute_manifests(conn, sorted(touched_types), stats)
                store._set_metadata(conn, WATERMARK_KEY, str(rows[-1]["id"]))
            elif full_rebuild:
                store._set_metadata(conn, WATERMARK_KEY, "0")

            stats["vocabulary_rows"] = _count(conn, "learning_vocabulary")
            stats["assumption_rows"] = _count(conn, "learning_assumptions")
            stats["manifest_rows"] = _count(conn, "learning_manifests")
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Distill pass failed — transaction rolled back")
            raise
        finally:
            conn.close()
    return stats


def _count(conn: sqlite3.Connection, table: str) -> int:
    # Table names come from a fixed internal allowlist, never user input.
    allowed = {
        "learning_vocabulary": "SELECT COUNT(*) AS c FROM learning_vocabulary",
        "learning_assumptions": "SELECT COUNT(*) AS c FROM learning_assumptions",
        "learning_manifests": "SELECT COUNT(*) AS c FROM learning_manifests",
    }
    return int(conn.execute(allowed[table]).fetchone()["c"])


def _parse_json(raw: Optional[str]) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


# ---------------------------------------------------------------------------
# Staleness decay — pure function of the log prefix up to each correction id.
# ---------------------------------------------------------------------------

def _apply_staleness_decay(conn: sqlite3.Connection, row: sqlite3.Row, stats: Dict[str, int]) -> None:
    """Decay stale rows when *row* opens a NEW verified run for its project_type.

    "Stale" = last_seen earlier than the start of the project_type's
    STALENESS_RUN_WINDOW most recent verified runs (as of this log position).
    Triggering on first-occurrence-of-run_id (not per distill pass) keeps
    incremental and full-rebuild results identical under any batching.
    """
    project_type = row["project_type"]
    prior = conn.execute(
        """
        SELECT 1 FROM learning_corrections
        WHERE id < ? AND run_id = ? AND project_type IS ?
        LIMIT 1
        """,
        (row["id"], row["run_id"], project_type),
    ).fetchone()
    if prior is not None:
        return  # run already known for this project_type — not a new-run boundary

    runs = conn.execute(
        """
        SELECT run_id, MIN(created_at) AS earliest, MAX(created_at) AS latest
        FROM learning_corrections
        WHERE project_type IS ? AND id <= ?
        GROUP BY run_id
        ORDER BY latest DESC, run_id DESC
        """,
        (project_type, row["id"]),
    ).fetchall()
    if len(runs) <= STALENESS_RUN_WINDOW:
        return
    # Anything touched at/after the window's oldest run began is fresh.
    cutoff = runs[STALENESS_RUN_WINDOW - 1]["earliest"]

    cur = conn.execute(
        "UPDATE learning_vocabulary SET weight = weight * ? WHERE project_type IS ? AND last_seen < ?",
        (STALENESS_DECAY, project_type, cutoff),
    )
    stats["stale_decays"] += cur.rowcount
    cur = conn.execute(
        "UPDATE learning_assumptions SET weight = weight * ? WHERE project_type IS ? AND last_seen < ?",
        (STALENESS_DECAY, project_type, cutoff),
    )
    stats["stale_decays"] += cur.rowcount


# ---------------------------------------------------------------------------
# Vocabulary: scope 'name' / 'unit'
# ---------------------------------------------------------------------------

def _vocab_mapping(
    conn: sqlite3.Connection, row: sqlite3.Row, raw_pattern: str
) -> Tuple[str, str]:
    """Resolve the (canonical_name, unit) a correction asserts.

    Accepts dict payloads ({"canonical_name": ..., "unit": ...}) or scalars
    (scope 'name' → canonical_name, scope 'unit' → unit). A missing side is
    inherited from the current best mapping for the key so a unit fix
    evolves the reigning name mapping instead of orphaning a default.
    """
    corrected = _parse_json(row["corrected_value"])
    canonical_name: Optional[str] = None
    unit: Optional[str] = None
    if isinstance(corrected, dict):
        canonical_name = corrected.get("canonical_name") or corrected.get("name")
        unit = corrected.get("unit")
    elif corrected is not None:
        if row["scope"] == store.SCOPE_UNIT:
            unit = str(corrected)
        else:
            canonical_name = str(corrected)

    if canonical_name is None or unit is None:
        best = conn.execute(
            """
            SELECT canonical_name, unit FROM learning_vocabulary
            WHERE project_type IS ? AND raw_pattern = ?
            ORDER BY weight DESC, last_seen DESC, id DESC
            LIMIT 1
            """,
            (row["project_type"], raw_pattern),
        ).fetchone()
        if canonical_name is None:
            canonical_name = best["canonical_name"] if best else raw_pattern
        if unit is None:
            unit = best["unit"] if best else ""
    return str(canonical_name).strip(), str(unit).strip()


def _distill_vocabulary(conn: sqlite3.Connection, row: sqlite3.Row, stats: Dict[str, int]) -> None:
    raw_pattern = row["item_pattern"]
    if not raw_pattern:
        original = _parse_json(row["original_value"])
        if isinstance(original, str) and original.strip():
            raw_pattern = original.strip()
        else:
            stats["skipped"] += 1
            return

    project_type = row["project_type"]
    canonical_name, unit = _vocab_mapping(conn, row, raw_pattern)
    seen_at = row["created_at"]

    # WR-02 sanity gate: never install an over-length / empty mapping as
    # canonical vocabulary — it would be rendered into prompt hints and used
    # to rename aggregation buckets.
    if not canonical_name or len(canonical_name) > MAX_CANONICAL_NAME_LEN or len(unit) > MAX_UNIT_LEN:
        logger.warning(
            "distill: rejected vocabulary mapping for correction id=%s — "
            "canonical_name/unit failed sanity checks (len=%d/%d)",
            row["id"], len(canonical_name or ""), len(unit or ""),
        )
        stats["skipped"] += 1
        return

    # Contradiction: same (project_type, raw_pattern) key, different mapping
    # → decay the old rows (weight × 0.5); the asserted mapping then wins by
    # weight at retrieval time.
    cur = conn.execute(
        """
        UPDATE learning_vocabulary
        SET weight = weight * ?
        WHERE project_type IS ? AND raw_pattern = ?
          AND NOT (canonical_name = ? AND unit = ?)
        """,
        (CONTRADICTION_DECAY, project_type, raw_pattern, canonical_name, unit),
    )
    stats["contradiction_decays"] += cur.rowcount

    # Confirm-or-insert. Manual upsert (SELECT → UPDATE/INSERT) instead of
    # ON CONFLICT because SQLite unique indexes treat NULL project_type
    # (= global) rows as always-distinct, which would silently skip the
    # weight increment for global vocabulary.
    existing = conn.execute(
        """
        SELECT id FROM learning_vocabulary
        WHERE project_type IS ? AND raw_pattern = ? AND canonical_name = ? AND unit = ?
        """,
        (project_type, raw_pattern, canonical_name, unit),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE learning_vocabulary SET weight = weight + ?, last_seen = ? WHERE id = ?",
            (CONFIRM_INCREMENT, seen_at, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO learning_vocabulary (project_type, raw_pattern, canonical_name, unit, weight, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_type, raw_pattern, canonical_name, unit, 1.0, seen_at),
        )
    stats["vocabulary_updates"] += 1


# ---------------------------------------------------------------------------
# Assumptions: scope 'scale' / 'wall_height'
# ---------------------------------------------------------------------------

def _assumption_key(row: sqlite3.Row) -> str:
    """RESEARCH §6 key naming: 'wall_height_ft', 'scale_fpi:<sheetname-pattern>'."""
    if row["scope"] == store.SCOPE_WALL_HEIGHT:
        return WALL_HEIGHT_KEY
    pattern = row["item_pattern"]
    if not pattern:
        context = _parse_json(row["context"])
        if isinstance(context, dict):
            pattern = context.get("sheet_name_pattern") or context.get("sheet_name")
    pattern = str(pattern).strip().lower() if pattern else "*"
    return SCALE_KEY_PREFIX + pattern


def _upsert_assumption(
    conn: sqlite3.Connection,
    project_key: Optional[str],
    project_type: Optional[str],
    key: str,
    value_json: str,
    seen_at: str,
    stats: Dict[str, int],
) -> None:
    # Contradiction decay: same scope level + key, different value.
    cur = conn.execute(
        """
        UPDATE learning_assumptions
        SET weight = weight * ?
        WHERE project_key IS ? AND project_type IS ? AND key = ? AND value != ?
        """,
        (CONTRADICTION_DECAY, project_key, project_type, key, value_json),
    )
    stats["contradiction_decays"] += cur.rowcount

    existing = conn.execute(
        """
        SELECT id FROM learning_assumptions
        WHERE project_key IS ? AND project_type IS ? AND key = ? AND value = ?
        """,
        (project_key, project_type, key, value_json),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE learning_assumptions SET weight = weight + ?, last_seen = ? WHERE id = ?",
            (CONFIRM_INCREMENT, seen_at, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO learning_assumptions (project_key, project_type, key, value, weight, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_key, project_type, key, value_json, 1.0, seen_at),
        )
    stats["assumption_updates"] += 1


def _distill_assumption(conn: sqlite3.Connection, row: sqlite3.Row, stats: Dict[str, int]) -> None:
    key = _assumption_key(row)
    value_json = row["corrected_value"]  # already json.dumps'd by record_correction
    seen_at = row["created_at"]

    # Exact-project level (most specific) — always written.
    _upsert_assumption(conn, row["project_key"], row["project_type"], key, value_json, seen_at, stats)
    # Type level (project_key NULL) — how learning transfers to NEW projects
    # of the same type; retrieval precedence keeps exact rows winning at home.
    if row["project_type"]:
        _upsert_assumption(conn, None, row["project_type"], key, value_json, seen_at, stats)


# ---------------------------------------------------------------------------
# Manifests: scope 'item' / 'missed_item' — pure aggregate per project_type
# ---------------------------------------------------------------------------

def _manifest_item(row: sqlite3.Row) -> Tuple[Optional[str], str]:
    parsed = _parse_json(row["corrected_value"])
    name: Optional[str] = None
    unit: Optional[str] = None
    if isinstance(parsed, dict):
        name = parsed.get("item_name") or parsed.get("name")
        unit = parsed.get("unit")
    if not name:
        if row["scope"] == store.SCOPE_MISSED_ITEM and isinstance(parsed, str) and parsed.strip():
            name = parsed
        else:
            name = row["item_pattern"]
    clean_name = str(name).strip() if name else None
    return (clean_name or None), (str(unit).strip() if unit else "")


def _recompute_manifests(
    conn: sqlite3.Connection, project_types: List[str], stats: Dict[str, int]
) -> None:
    """Recompute manifest aggregates from the full log for touched types.

    seen_in_runs = distinct verified runs containing the item;
    verified_runs_total = distinct runs with ANY correction for the type.
    Being a pure aggregate of the append-only log, recomputation is
    idempotent and identical between incremental and full-rebuild passes.
    """
    for project_type in project_types:
        total_row = conn.execute(
            "SELECT COUNT(DISTINCT run_id) AS c FROM learning_corrections WHERE project_type = ?",
            (project_type,),
        ).fetchone()
        verified_runs_total = int(total_row["c"])
        if verified_runs_total == 0:
            continue

        rows = conn.execute(
            """
            SELECT run_id, scope, item_pattern, corrected_value
            FROM learning_corrections
            WHERE project_type = ? AND scope IN (?, ?)
            ORDER BY id
            """,
            (project_type, store.SCOPE_ITEM, store.SCOPE_MISSED_ITEM),
        ).fetchall()

        per_item: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            item_name, unit = _manifest_item(r)
            if not item_name:
                stats["skipped"] += 1
                continue
            entry = per_item.setdefault(item_name, {"unit": "", "runs": set()})
            entry["runs"].add(r["run_id"])
            if unit:
                entry["unit"] = unit  # id order → latest non-empty unit wins

        for item_name in sorted(per_item):
            entry = per_item[item_name]
            conn.execute(
                """
                INSERT INTO learning_manifests (project_type, item_name, unit, seen_in_runs, verified_runs_total)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_type, item_name) DO UPDATE SET
                    unit = excluded.unit,
                    seen_in_runs = excluded.seen_in_runs,
                    verified_runs_total = excluded.verified_runs_total
                """,
                (
                    project_type,
                    item_name,
                    entry["unit"],
                    len(entry["runs"]),
                    verified_runs_total,
                ),
            )
            stats["manifest_items"] += 1
