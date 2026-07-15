"""Durable learning store (V3-LEARN-01).

SQLite persistence for human corrections so they survive run-folder
deletion and accumulate what manifests used to provide. Four tables per
21-RESEARCH.md §6 (normative schema):

    learning_corrections  — append-only log of every human action
    learning_vocabulary   — distilled raw-pattern → canonical-name/unit map
    learning_assumptions  — distilled wall heights, scale priors, defaults
    learning_manifests    — auto-generated expected-item checklists

Plus ``learning_metadata`` holding ``learning_schema_version`` and the
distillation watermark.

Security invariants (ASVS L1, phase threat model):
    * This module (with ``distill.py``) is the ONLY code allowed to touch
      the ``learning_*`` tables. Endpoints call it, never raw SQL.
    * 100%% parameterized queries — every learned string is hostile input
      (humans type it; it flows back into prompts/aggregation).
    * JSON values stored via ``json.dumps`` only; values whose serialized
      form exceeds ``MAX_VALUE_LEN`` chars are REJECTED with ``ValueError``
      (payload-stuffing defense). Rejection, never truncation: a JSON
      payload cut mid-token would be re-read as a raw-text scalar and could
      silently become learned vocabulary (21-REVIEW WR-02).

Connection/lock/init patterns follow ``stores/stackct_store.py`` (Row
factory, WAL, module write lock) and ``stores/job_store.py`` (lazy
double-checked schema init).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bobbytailor.config import OUTPUT_DIR

# ---------------------------------------------------------------------------
# Scope enum (string constants) — the only values record_correction accepts.
# ---------------------------------------------------------------------------
SCOPE_ITEM = "item"                # quantity correction on an extracted item
SCOPE_SCALE = "scale"              # drawing-scale fix (feet-per-inch)
SCOPE_WALL_HEIGHT = "wall_height"  # wall-height assumption fix
SCOPE_NAME = "name"                # item rename (raw → canonical)
SCOPE_MISSED_ITEM = "missed_item"  # human added an item the system missed
SCOPE_UNIT = "unit"                # unit-of-measure fix

VALID_SCOPES = frozenset(
    {SCOPE_ITEM, SCOPE_SCALE, SCOPE_WALL_HEIGHT, SCOPE_NAME, SCOPE_MISSED_ITEM, SCOPE_UNIT}
)

# ---------------------------------------------------------------------------
# Vocabulary provenance (learning_vocabulary.source).
# ---------------------------------------------------------------------------
#: A human-authored/confirmed mapping (distilled from corrections). Default —
#: pre-migration rows and every ``distill`` insert are 'human'.
SOURCE_HUMAN = "human"
#: An AI-generated mapping persisted by :func:`record_ai_manifest` (the Opus
#: naming manifest). Ranks BELOW human rows in retrieval regardless of weight.
SOURCE_AI = "ai"

#: Initial weight for an AI-manifest vocabulary row — deliberately below a
#: single human confirmation (1.0) so a human vote always outweighs it AND the
#: source-first retrieval ordering makes human authoritative for the same
#: raw_pattern (RESEARCH §6 conflict policy, human-wins invariant).
AI_MANIFEST_WEIGHT = 0.5
#: Modest per-run bump when the same AI mapping recurs — capped below 1.0 so an
#: accumulated AI dictionary never numerically overtakes a human confirmation.
AI_MANIFEST_BUMP = 0.1
AI_MANIFEST_WEIGHT_CAP = 0.99

#: Sanity caps mirrored from ``distill`` (WR-02): an AI-manifest object name is
#: a short human-facing item label — anything longer is a stuffed/corrupted
#: payload and must never be installed as learned vocabulary.
MAX_AI_CANONICAL_NAME_LEN = 100
MAX_AI_UNIT_LEN = 20

#: Serialized JSON values (and item_pattern) longer than this are REJECTED
#: on write — defense against payload stuffing through the correction UI.
#: Rejected, never truncated: truncation corrupts the stored JSON mid-token
#: and distillation would install the fragment as learned data (WR-02).
MAX_VALUE_LEN = 2000

SCHEMA_VERSION = "1"
SCHEMA_VERSION_KEY = "learning_schema_version"

# Dedicated learning.db (not stackct.db) — isolates migration risk per
# RESEARCH §6 parenthetical; CONTEXT grants discretion. Env override for
# tests/deployments; the store owns its own env read (config.py untouched).
_env_db_path = os.getenv("LEARNING_DB_PATH")
LEARNING_DB_PATH = (
    Path(_env_db_path).expanduser() if _env_db_path else Path(OUTPUT_DIR) / "learning.db"
)

_write_lock = threading.Lock()
#: Path the schema was initialized for — re-inits automatically when tests
#: monkeypatch LEARNING_DB_PATH to a tmp DB (double-checked under the lock).
_initialized_for: Optional[str] = None

# Column definitions verbatim from 21-RESEARCH.md §6.
# Two deliberate mechanical adjustments (documented in 21-04-SUMMARY.md):
#   * IF NOT EXISTS on every CREATE so lazy init is re-runnable (the
#     stackct_store/job_store SCHEMA_SQL convention).
#   * learning_vocabulary UNIQUE includes canonical_name+unit: the §6
#     conflict/decay policy requires a decayed old mapping and the new
#     mapping to COEXIST for the same (project_type, raw_pattern) so
#     max-weight retrieval can arbitrate — a 2-column UNIQUE would make
#     that state unrepresentable.
SCHEMA_SQL = """
-- every human action, append-only (audit + decay computation)
CREATE TABLE IF NOT EXISTS learning_corrections (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  run_id TEXT NOT NULL,               -- surviving reference even after run folder deletion
  project_key TEXT NOT NULL,          -- normalized project name / stackct id
  project_type TEXT,                  -- industrial / hotel / retail ... (existing detector)
  sheet_type TEXT,                    -- floor_plan / schedule / ...
  scope TEXT NOT NULL,                -- 'item' | 'scale' | 'wall_height' | 'name' | 'missed_item' | 'unit'
  item_pattern TEXT,                  -- normalized item key (lowercased canonical-ish name)
  original_value TEXT,                -- JSON: what the system said
  corrected_value TEXT NOT NULL,      -- JSON: what the human said
  context TEXT                        -- JSON: page, viewport, provenance, confidence at time of correction
);
CREATE INDEX IF NOT EXISTS ix_corr_lookup ON learning_corrections(project_type, sheet_type, scope, item_pattern);
-- project-scoped retrieval (guardrail flags + project_type inference must
-- not degrade as the GLOBAL log grows — 21-REVIEW WR-01)
CREATE INDEX IF NOT EXISTS ix_corr_project ON learning_corrections(project_key);

-- distilled, retrievable state (rebuilt/updated from corrections)
CREATE TABLE IF NOT EXISTS learning_vocabulary (
  id INTEGER PRIMARY KEY,
  project_type TEXT,                  -- NULL = global
  raw_pattern TEXT NOT NULL,          -- what extraction produces (regex-safe literal or token set)
  canonical_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,   -- votes; incremented per confirming correction
  last_seen TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'human', -- 'human' (distilled correction) | 'ai' (Opus manifest)
  UNIQUE(project_type, raw_pattern, canonical_name, unit)
);

CREATE TABLE IF NOT EXISTS learning_assumptions (   -- wall heights, waste factors, default scales...
  id INTEGER PRIMARY KEY,
  project_key TEXT,                   -- exact project beats project_type beats global
  project_type TEXT,
  key TEXT NOT NULL,                  -- 'wall_height_ft', 'scale_fpi:sheetname-pattern', ...
  value TEXT NOT NULL,                -- JSON
  weight REAL NOT NULL DEFAULT 1.0,
  last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_manifests (     -- auto-generated expected-item checklists
  id INTEGER PRIMARY KEY,
  project_type TEXT NOT NULL,
  item_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  seen_in_runs INTEGER NOT NULL DEFAULT 1,   -- how many verified runs contained it
  verified_runs_total INTEGER NOT NULL,      -- denominator for expectation strength
  UNIQUE(project_type, item_name)
);

CREATE TABLE IF NOT EXISTS learning_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    """Open a connection to the learning DB (Row factory, FK on, WAL)."""
    LEARNING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LEARNING_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_metadata(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM learning_metadata WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def _set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO learning_metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, _utc_now()),
    )


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, column_def: str
) -> None:
    """Idempotently ALTER TABLE ADD COLUMN, guarded by a PRAGMA existence check.

    ``table``/``column``/``column_def`` come from a fixed internal call site
    (never user input); PRAGMA table_info and ALTER TABLE cannot be
    parameterized for identifiers, so they are interpolated from these
    trusted literals only. Safe on an existing DB — adds the column with its
    DEFAULT (back-filling every existing row) exactly once, no-ops thereafter.
    """
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(%s)" % table).fetchall()
    }
    if column in existing:
        return
    conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, column_def))


def _ensure_schema() -> None:
    """Lazy double-checked schema init (job_store pattern), keyed by DB path.

    Guarded by the ``learning_schema_version`` metadata key so future schema
    bumps can hook targeted migrations here (stackct_store v1→v2 precedent).
    """
    global _initialized_for
    current_path = str(LEARNING_DB_PATH)
    if _initialized_for == current_path:
        return
    with _write_lock:
        if _initialized_for == current_path:
            return
        conn = get_connection()
        try:
            conn.executescript(SCHEMA_SQL)
            # Additive column migrations — guarded by a PRAGMA existence check
            # so an existing pre-migration learning.db upgrades WITHOUT data
            # loss and re-init stays idempotent (no version bump required for
            # an additive DEFAULT'd column; the CREATE above already carries it
            # for fresh DBs, the ALTER only fires on legacy DBs).
            _add_column_if_missing(
                conn,
                "learning_vocabulary",
                "source",
                "TEXT NOT NULL DEFAULT '%s'" % SOURCE_HUMAN,
            )
            version = _get_metadata(conn, SCHEMA_VERSION_KEY)
            if version is None:
                conn.execute(
                    "INSERT INTO learning_metadata (key, value, updated_at) VALUES (?, ?, ?)",
                    (SCHEMA_VERSION_KEY, SCHEMA_VERSION, _utc_now()),
                )
            elif version != SCHEMA_VERSION:
                # Future migrations dispatch on the stored version here
                # (stackct_store.init_schema v1→v2 mechanism). v1 is current.
                _set_metadata(conn, SCHEMA_VERSION_KEY, SCHEMA_VERSION)
            conn.commit()
        finally:
            conn.close()
        _initialized_for = current_path


def init_learning_schema() -> None:
    """Public alias forcing schema creation (idempotent)."""
    _ensure_schema()


def _check_len(text: str, field: str) -> str:
    """Reject over-length payloads — never truncate (WR-02)."""
    if len(text) > MAX_VALUE_LEN:
        raise ValueError(
            "%s exceeds MAX_VALUE_LEN (%d > %d chars) — correction rejected. "
            "Oversized payloads are refused rather than truncated: a JSON "
            "fragment cut mid-token would be silently installed as learned "
            "data." % (field, len(text), MAX_VALUE_LEN)
        )
    return text


def _serialize(value: Any, field: str = "value") -> str:
    """JSON-encode a correction value; over-length payloads are rejected."""
    return _check_len(json.dumps(value, default=str), field)


def _deserialize(raw: Optional[str]) -> Any:
    """Parse a stored JSON value; legacy/pre-fix payloads fall back to raw text."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def record_correction(
    run_id: str,
    project_key: str,
    project_type: Optional[str] = None,
    sheet_type: Optional[str] = None,
    scope: str = SCOPE_ITEM,
    item_pattern: Optional[str] = None,
    original_value: Any = None,
    corrected_value: Any = None,
    context: Optional[Dict[str, Any]] = None,
) -> int:
    """Append one human correction to the durable log. Returns the row id.

    ``original_value``/``corrected_value``/``context`` are arbitrary
    JSON-serializable payloads; they are stored via ``json.dumps``. A payload
    whose serialized form exceeds MAX_VALUE_LEN raises ``ValueError`` — it is
    rejected, never truncated (WR-02). The row survives run-folder deletion —
    ``run_id`` is a plain string reference, never a filesystem dependency.
    """
    if scope not in VALID_SCOPES:
        raise ValueError(
            "Invalid correction scope %r — expected one of %s"
            % (scope, sorted(VALID_SCOPES))
        )
    if not run_id or not project_key:
        raise ValueError("run_id and project_key are required")
    if corrected_value is None:
        raise ValueError("corrected_value is required (learning_corrections.corrected_value is NOT NULL)")

    _ensure_schema()
    row = {
        "created_at": _utc_now(),
        "run_id": str(run_id),
        "project_key": str(project_key),
        "project_type": project_type,
        "sheet_type": sheet_type,
        "scope": scope,
        "item_pattern": _check_len(str(item_pattern), "item_pattern") if item_pattern is not None else None,
        "original_value": _serialize(original_value, "original_value") if original_value is not None else None,
        "corrected_value": _serialize(corrected_value, "corrected_value"),
        "context": _serialize(context, "context") if context is not None else None,
    }
    with _write_lock:
        conn = get_connection()
        try:
            cur = conn.execute(
                """
                INSERT INTO learning_corrections (
                    created_at, run_id, project_key, project_type, sheet_type,
                    scope, item_pattern, original_value, corrected_value, context
                ) VALUES (
                    :created_at, :run_id, :project_key, :project_type, :sheet_type,
                    :scope, :item_pattern, :original_value, :corrected_value, :context
                )
                """,
                row,
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def _normalize_pattern(text: Any) -> str:
    """Whitespace-collapsed, lowercased raw_pattern key (mirrors retrieval)."""
    return " ".join(str(text or "").split()).strip().lower()


def record_ai_manifest(
    project_key: Optional[str],
    project_type: Optional[str],
    objects: Optional[List[Dict[str, Any]]],
    ts: Optional[str] = None,
) -> int:
    """Persist an AI-generated naming manifest into ``learning_vocabulary``.

    The Opus naming pass (``vision.object_vocabulary`` / the merged project
    vocabulary) builds a per-run manifest that today lives ONLY in memory and
    is regenerated every run. This upserts each manifest object into
    ``learning_vocabulary`` with ``source='ai'`` so the app accumulates a
    growing autonomous naming dictionary that future runs reuse.

    For each object, every one of {canonical name} ∪ {aliases} becomes a
    ``raw_pattern`` (normalized/lowercased) mapping to the object's canonical
    name + unit, at a MODEST weight (:data:`AI_MANIFEST_WEIGHT`, below a single
    human confirmation at 1.0). Idempotent via the UNIQUE constraint: a
    recurring AI mapping bumps its weight slightly (capped below 1.0) and
    refreshes ``last_seen``; a first sighting inserts a fresh row.

    Human-wins invariant: an existing ``source='human'`` row for the same
    (project_type, raw_pattern, canonical_name, unit) is NEVER overwritten or
    re-weighted — the human mapping is left exactly as distilled. (Retrieval
    additionally ranks any human row for the same raw_pattern first, so a
    human's canonical name overrides the AI's regardless of weight.)

    ``ts`` is the ``last_seen`` timestamp (accepted like ``record_correction``
    derives ``created_at``); defaults to UTC now. Returns the number of rows
    inserted or updated. ``project_type=None`` writes global (NULL) rows.
    """
    if not objects:
        return 0
    _ensure_schema()
    seen_at = ts or _utc_now()
    project_type = project_type if project_type else None

    written = 0
    with _write_lock:
        conn = get_connection()
        try:
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                canonical = str(obj.get("canonical_name") or obj.get("name") or "").strip()
                unit = str(obj.get("unit") or "").strip()
                # WR-02 sanity gate — never install an over-length/empty mapping
                # (it would flow into prompt hints and aggregation renames).
                if (
                    not canonical
                    or len(canonical) > MAX_AI_CANONICAL_NAME_LEN
                    or len(unit) > MAX_AI_UNIT_LEN
                ):
                    continue

                raw_patterns: List[str] = []
                seen_keys = set()
                candidates = [canonical]
                aliases = obj.get("aliases")
                if isinstance(aliases, list):
                    candidates.extend(a for a in aliases if isinstance(a, str))
                for cand in candidates:
                    key = _normalize_pattern(cand)
                    if not key or len(key) > MAX_VALUE_LEN or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    raw_patterns.append(key)

                for raw_pattern in raw_patterns:
                    existing = conn.execute(
                        """
                        SELECT id, source FROM learning_vocabulary
                        WHERE project_type IS ? AND raw_pattern = ?
                          AND canonical_name = ? AND unit = ?
                        """,
                        (project_type, raw_pattern, canonical, unit),
                    ).fetchone()
                    if existing is not None:
                        # Human mapping is authoritative — leave it untouched.
                        if existing["source"] == SOURCE_HUMAN:
                            continue
                        conn.execute(
                            """
                            UPDATE learning_vocabulary
                            SET weight = MIN(weight + ?, ?), last_seen = ?
                            WHERE id = ?
                            """,
                            (
                                AI_MANIFEST_BUMP,
                                AI_MANIFEST_WEIGHT_CAP,
                                seen_at,
                                existing["id"],
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO learning_vocabulary (
                                project_type, raw_pattern, canonical_name, unit,
                                weight, last_seen, source
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                project_type,
                                raw_pattern,
                                canonical,
                                unit,
                                AI_MANIFEST_WEIGHT,
                                seen_at,
                                SOURCE_AI,
                            ),
                        )
                    written += 1
            conn.commit()
        finally:
            conn.close()
    return written


def get_corrections(
    project_type: Optional[str] = None,
    sheet_type: Optional[str] = None,
    scope: Optional[str] = None,
    item_pattern: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = 500,
    project_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query the append-only log by the ix_corr_lookup key (all filters optional).

    ``project_key`` filters at the SQL level (ix_corr_project index) so a
    project's corrections never fall out of the recency window because of
    OTHER projects' activity (21-REVIEW WR-01).

    Returned dicts carry parsed ``original_value``/``corrected_value``/
    ``context`` (JSON-decoded; raw text fallback for legacy payloads).
    """
    _ensure_schema()
    clauses: List[str] = []
    params: List[Any] = []
    if project_key is not None:
        clauses.append("project_key = ?")
        params.append(project_key)
    if project_type is not None:
        clauses.append("project_type = ?")
        params.append(project_type)
    if sheet_type is not None:
        clauses.append("sheet_type = ?")
        params.append(sheet_type)
    if scope is not None:
        clauses.append("scope = ?")
        params.append(scope)
    if item_pattern is not None:
        clauses.append("item_pattern = ?")
        params.append(item_pattern)
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)

    query = "SELECT * FROM learning_corrections"
    if clauses:
        query = query + " WHERE " + " AND ".join(clauses)
    query = query + " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 5000)))

    conn = get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    results: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["original_value"] = _deserialize(d.get("original_value"))
        d["corrected_value"] = _deserialize(d.get("corrected_value"))
        d["context"] = _deserialize(d.get("context"))
        results.append(d)
    return results


def get_vocabulary(project_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Learned naming map for a project type (plus global NULL rows).

    Precedence (RESEARCH §6 conflict policy + human-wins invariant):
    ``source='human'`` rows rank BEFORE ``source='ai'`` rows regardless of
    weight — a human's canonical name always overrides the AI manifest for the
    same raw_pattern. Within a source tier the max-weight mapping wins; ties
    break by most-recent ``last_seen``. Both human AND ai rows are returned so
    the accumulated AI dictionary is reused when no human row exists.
    """
    _ensure_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, project_type, raw_pattern, canonical_name, unit, weight, last_seen, source
            FROM learning_vocabulary
            WHERE project_type = ? OR project_type IS NULL
            ORDER BY (source = ?) DESC, weight DESC, last_seen DESC, id DESC
            """,
            (project_type, SOURCE_HUMAN),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _assumption_tier(row: sqlite3.Row) -> int:
    """Specificity tier: 0 = exact project_key, 1 = project_type, 2 = global."""
    if row["project_key"] is not None:
        return 0
    if row["project_type"] is not None:
        return 1
    return 2


def get_assumptions(
    project_key: Optional[str], project_type: Optional[str]
) -> List[Dict[str, Any]]:
    """Learned assumptions deduped by key with specificity precedence.

    Exact ``project_key`` rows beat ``project_type`` rows beat global rows;
    within a tier the max-weight row wins, ties go to the most recent
    (RESEARCH §6). One row per key is returned, ``value`` JSON-parsed.
    """
    _ensure_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, project_key, project_type, key, value, weight, last_seen
            FROM learning_assumptions
            WHERE (project_key = ?)
               OR (project_key IS NULL AND project_type = ?)
               OR (project_key IS NULL AND project_type IS NULL)
            """,
            (project_key, project_type),
        ).fetchall()
    finally:
        conn.close()

    best: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        candidate = dict(r)
        candidate["_tier"] = _assumption_tier(r)
        current = best.get(candidate["key"])
        if current is None:
            best[candidate["key"]] = candidate
            continue
        # Lower tier (more specific) wins; then higher weight; then most recent.
        cand_rank = (
            candidate["_tier"],
            -candidate["weight"],
            _invert_text_order(candidate["last_seen"]),
            -candidate["id"],
        )
        cur_rank = (
            current["_tier"],
            -current["weight"],
            _invert_text_order(current["last_seen"]),
            -current["id"],
        )
        if cand_rank < cur_rank:
            best[candidate["key"]] = candidate

    results: List[Dict[str, Any]] = []
    for entry in sorted(best.values(), key=lambda e: (e["_tier"], -e["weight"], e["key"])):
        entry = dict(entry)
        entry.pop("_tier", None)
        entry["value"] = _deserialize(entry["value"])
        results.append(entry)
    return results


def _invert_text_order(text: Optional[str]) -> str:
    """Map ISO timestamps so LATER sorts SMALLER inside an ascending tuple compare."""
    if not text:
        return "￿"
    # Invert each character code within the BMP; ISO-8601 sorts lexicographically.
    return "".join(chr(0xFFFF - ord(c)) for c in text)


def get_manifest(project_type: str) -> List[Dict[str, Any]]:
    """Expected-item checklist for a project type with expectation strength.

    ``expectation`` = seen_in_runs / verified_runs_total — how consistently
    verified runs of this project type contained the item.
    """
    _ensure_schema()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, project_type, item_name, unit, seen_in_runs, verified_runs_total
            FROM learning_manifests
            WHERE project_type = ?
            ORDER BY CAST(seen_in_runs AS REAL) / MAX(verified_runs_total, 1) DESC, item_name ASC
            """,
            (project_type,),
        ).fetchall()
    finally:
        conn.close()

    results: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        total = d.get("verified_runs_total") or 0
        d["expectation"] = (d["seen_in_runs"] / total) if total > 0 else 0.0
        results.append(d)
    return results
