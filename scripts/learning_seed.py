#!/usr/bin/env python3
"""Export / import the learning store as a versioned seed. ZERO API.

`output/learning.db` holds everything the app has learned — the vocabulary that
makes a name you corrected once stick forever, and the per-project snapshots
that make a REPEAT run reproducible. It is also gitignored, because a live
SQLite file has no business in version control.

So a fresh VPS starts knowing nothing, and every correction an estimator made
here is lost on the first deploy. This script is the bridge: export to a
readable JSON seed that IS committed, import it on the far side.

IMPORT IS ADDITIVE AND NEVER OVERWRITES. A row already present on the target is
left exactly as it is — the server's own learning always outranks a seed, or a
deploy would silently undo corrections the operator made in production.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

SEED = Path("data/learning_seed.json")
TABLES = ("learning_vocabulary", "learning_corrections",
          "learning_assumptions", "learning_project_vocabulary")


def _connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    return con


def export(db: Path, out: Path) -> int:
    if not db.exists():
        print(f"no learning store at {db}", file=sys.stderr)
        return 1
    con = _connect(db)
    have = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    payload = {"_note": "Exported by scripts/learning_seed.py. Import is additive.",
               "tables": {}}
    for t in TABLES:
        if t not in have:
            continue
        rows = [dict(r) for r in con.execute(f"SELECT * FROM {t}")]
        for r in rows:
            r.pop("id", None)          # let the target assign its own keys
        payload["tables"][t] = rows
        print(f"  {t:30s} {len(rows):5d} rows")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


def _unique_key(con, table, cols):
    """The table's OWN uniqueness, read from its indexes — never guessed.

    Guessing cost 1,503 rows on the first attempt: a plausible-looking key of
    (raw_text, canonical_name) collapsed learning_vocabulary to 149 distinct
    signatures, because the real constraint is
    (project_type, raw_pattern, canonical_name, unit) and the same pattern
    legitimately recurs under different project types and units.

    A table with no unique index (learning_corrections is an append-only log)
    returns no key, and every row is inserted — which is correct for a log.
    """
    for row in con.execute(f"PRAGMA index_list({table})"):
        name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        keys = [r[2] for r in con.execute(f"PRAGMA index_info({name})")]
        if keys and all(k in cols for k in keys):
            return keys
    return []


def _existing(con, table, cols):
    """Signatures already on the target, so an import cannot duplicate."""
    keys = _unique_key(con, table, cols)
    if not keys:
        # An append-only log (learning_corrections) declares no unique index, so
        # "already present" can only mean AN IDENTICAL ROW. Without this a second
        # import doubles the log — measured: 65 corrections became 130.
        # `id` and any timestamp are excluded: the target assigns its own id, and
        # a re-export would otherwise never match.
        keys = sorted(c for c in cols if c not in ("id", "created_at", "last_seen"))
    sel = ", ".join(keys)
    return {tuple(r) for r in con.execute(f"SELECT {sel} FROM {table}")}, keys


def import_(db: Path, seed: Path) -> int:
    if not seed.exists():
        print(f"no seed at {seed}", file=sys.stderr)
        return 1
    payload = json.loads(seed.read_text())
    db.parent.mkdir(parents=True, exist_ok=True)
    # Let the APP create its own schema — never invent one here, or the seed
    # and the runtime drift the first time a column is added. The store reads
    # its path from LEARNING_DB_PATH at import time, so it must be set before.
    import os

    os.environ["LEARNING_DB_PATH"] = str(db)
    sys.path.insert(0, "src")
    try:
        from bobbytailor.learning import store as _store

        init = getattr(_store, "init_db", None) or getattr(_store, "_init_db", None)
        if callable(init):
            init()
        else:  # older store: any read initialises the schema
            _store.load_project_vocabulary("__seed_probe__")
    except Exception as exc:  # noqa: BLE001
        print(f"could not initialise the learning store: {exc}", file=sys.stderr)
        return 1
    con = _connect(db)
    have = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    added = skipped = 0
    for table, rows in (payload.get("tables") or {}).items():
        if table not in have or not rows:
            continue
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        seen, keys = _existing(con, table, cols)
        for row in rows:
            row = {k: v for k, v in row.items() if k in cols}
            if not row:
                continue
            sig = tuple(row.get(k) for k in keys) if keys else None
            if sig is not None and sig in seen:
                skipped += 1
                continue
            names = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            con.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})",
                        list(row.values()))
            if sig is not None:
                seen.add(sig)
            added += 1
    con.commit()
    print(f"imported {added} row(s); left {skipped} existing row(s) untouched")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("export", "import"))
    ap.add_argument("--db", default="output/learning.db")
    ap.add_argument("--seed", default=str(SEED))
    a = ap.parse_args()
    return (export if a.action == "export" else import_)(Path(a.db), Path(a.seed))


if __name__ == "__main__":
    raise SystemExit(main())
