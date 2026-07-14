"""Layer-4 tests for the durable learning store (V3-LEARN-01/02).

Round-trip, run-folder independence, distill idempotency, conflict/decay,
specificity precedence, and the SQL-injection probe (21-VALIDATION.md
layer-4 contract). Every test isolates SQLite state via a tmp_path DB
monkeypatched onto ``bobbytailor.learning.store.LEARNING_DB_PATH``.
"""
import json
import sqlite3

import pytest

from bobbytailor.learning import distill as distill_mod
from bobbytailor.learning import store
from bobbytailor.learning.distill import distill

DISTILLED_TABLES = ("learning_vocabulary", "learning_assumptions", "learning_manifests")


@pytest.fixture()
def learning_db(tmp_path, monkeypatch):
    """Point the store at an isolated tmp DB; schema re-inits per path."""
    db_path = tmp_path / "learning.db"
    monkeypatch.setattr(store, "LEARNING_DB_PATH", db_path)
    monkeypatch.setattr(store, "_initialized_for", None)
    return db_path


def record(
    scope=store.SCOPE_ITEM,
    run_id="run-001",
    project_key="proj-a",
    project_type="industrial",
    sheet_type="floor_plan",
    item_pattern="cmu wall",
    original=None,
    corrected="corrected",
    context=None,
):
    return store.record_correction(
        run_id=run_id,
        project_key=project_key,
        project_type=project_type,
        sheet_type=sheet_type,
        scope=scope,
        item_pattern=item_pattern,
        original_value=original,
        corrected_value=corrected,
        context=context,
    )


def dump_distilled_tables():
    """Sorted row tuples per distilled table, excluding autoincrement ids."""
    conn = store.get_connection()
    try:
        dumps = {}
        for table in DISTILLED_TABLES:
            query = "SELECT * FROM " + table  # fixed internal names, no user input
            # key=repr: rows may mix None (SQL NULL) with strings/numbers.
            dumps[table] = sorted((tuple(r)[1:] for r in conn.execute(query)), key=repr)
        return dumps
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Round-trip: correction retrievable by (project_type, sheet_type, scope,
#    item_pattern) — the ix_corr_lookup key.
# ---------------------------------------------------------------------------

def test_round_trip_item_correction(learning_db):
    row_id = record(
        scope=store.SCOPE_ITEM,
        item_pattern="cmu wall",
        original={"quantity": 17, "unit": "SF"},
        corrected={"quantity": 2204, "unit": "SF"},
        context={"page": 3, "provenance": "vision", "confidence": "LOW"},
    )
    assert isinstance(row_id, int) and row_id > 0

    conn = store.get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM learning_corrections
            WHERE project_type = ? AND sheet_type = ? AND scope = ? AND item_pattern = ?
            """,
            ("industrial", "floor_plan", "item", "cmu wall"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["id"] == row_id
    assert row["run_id"] == "run-001"
    assert row["project_key"] == "proj-a"
    assert json.loads(row["corrected_value"]) == {"quantity": 2204, "unit": "SF"}
    assert json.loads(row["original_value"]) == {"quantity": 17, "unit": "SF"}
    assert json.loads(row["context"])["provenance"] == "vision"
    assert row["created_at"]  # UTC ISO timestamp set by the store

    # Public helper honors the same lookup key and parses JSON values.
    hits = store.get_corrections(
        project_type="industrial", sheet_type="floor_plan", scope="item", item_pattern="cmu wall"
    )
    assert len(hits) == 1
    assert hits[0]["corrected_value"]["quantity"] == 2204


# ---------------------------------------------------------------------------
# 2. Run-folder independence: correction referencing a run whose folder never
#    existed (or was deleted) is fully retrievable — no filesystem dependency.
# ---------------------------------------------------------------------------

def test_correction_survives_run_folder_deletion(learning_db, tmp_path):
    ghost_run = "20990101_000000_ghost-project"
    assert not (tmp_path / "output" / ghost_run).exists()

    record(run_id=ghost_run, item_pattern="bollards", corrected={"quantity": 28, "unit": "EA"})

    hits = store.get_corrections(run_id=ghost_run)
    assert len(hits) == 1
    assert hits[0]["item_pattern"] == "bollards"
    assert hits[0]["corrected_value"] == {"quantity": 28, "unit": "EA"}


# ---------------------------------------------------------------------------
# 3. Distill idempotency + auditable full rebuild.
# ---------------------------------------------------------------------------

def test_distill_idempotent_and_full_rebuild_identical(learning_db):
    record(scope=store.SCOPE_NAME, run_id="r1", item_pattern="exp joint", corrected="Expansion Joint")
    record(scope=store.SCOPE_WALL_HEIGHT, run_id="r1", item_pattern=None, corrected=10.0)
    record(scope=store.SCOPE_ITEM, run_id="r2", item_pattern="bollards", corrected={"quantity": 28, "unit": "EA"})

    first = distill()
    assert first["corrections_processed"] == 3

    second = distill()
    assert second["corrections_processed"] == 0

    before = dump_distilled_tables()
    rebuild = distill(full_rebuild=True)
    assert rebuild["corrections_processed"] == 3
    assert dump_distilled_tables() == before

    # A second full rebuild is also stable.
    distill(full_rebuild=True)
    assert dump_distilled_tables() == before


# ---------------------------------------------------------------------------
# 4. Conflict/decay: contradicting vocabulary corrections.
# ---------------------------------------------------------------------------

def test_vocabulary_conflict_decay(learning_db):
    record(scope=store.SCOPE_NAME, run_id="r1", item_pattern="x-item", original="x-item", corrected="Widget Y")
    record(scope=store.SCOPE_NAME, run_id="r2", item_pattern="x-item", original="x-item", corrected="Widget Z")
    distill()

    vocab = [r for r in store.get_vocabulary("industrial") if r["raw_pattern"] == "x-item"]
    assert len(vocab) == 2
    # New value wins retrieval (max weight first)...
    assert vocab[0]["canonical_name"] == "Widget Z"
    assert vocab[0]["weight"] == pytest.approx(1.0)
    # ...and the contradicted old value decayed by x0.5.
    assert vocab[1]["canonical_name"] == "Widget Y"
    assert vocab[1]["weight"] == pytest.approx(0.5)


def test_vocabulary_confirmation_increments_weight(learning_db):
    record(scope=store.SCOPE_NAME, run_id="r1", item_pattern="hm frame", corrected="Frame-HM")
    record(scope=store.SCOPE_NAME, run_id="r2", item_pattern="hm frame", corrected="Frame-HM")
    distill()

    vocab = [r for r in store.get_vocabulary("industrial") if r["raw_pattern"] == "hm frame"]
    assert len(vocab) == 1
    assert vocab[0]["weight"] == pytest.approx(2.0)
    assert vocab[0]["canonical_name"] == "Frame-HM"


# ---------------------------------------------------------------------------
# 5. Specificity precedence: exact project_key > project_type > global.
# ---------------------------------------------------------------------------

def _seed_assumption(project_key, project_type, key, value, weight=1.0, last_seen="2026-01-01T00:00:00+00:00"):
    store.init_learning_schema()
    conn = store.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO learning_assumptions (project_key, project_type, key, value, weight, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_key, project_type, key, json.dumps(value), weight, last_seen),
        )
        conn.commit()
    finally:
        conn.close()


def test_assumption_specificity_precedence(learning_db):
    _seed_assumption(None, None, "wall_height_ft", 9.0, weight=50.0)
    _seed_assumption(None, "industrial", "wall_height_ft", 10.0, weight=20.0)
    _seed_assumption("proj-a", "industrial", "wall_height_ft", 12.0, weight=1.0)

    # Exact project_key beats a heavier project_type row and a heavier global row.
    exact = {a["key"]: a["value"] for a in store.get_assumptions("proj-a", "industrial")}
    assert exact["wall_height_ft"] == 12.0

    # Unknown project falls back to the project_type row.
    typed = {a["key"]: a["value"] for a in store.get_assumptions("proj-unknown", "industrial")}
    assert typed["wall_height_ft"] == 10.0

    # Unknown project AND type falls back to global.
    global_ = {a["key"]: a["value"] for a in store.get_assumptions("proj-unknown", "office")}
    assert global_["wall_height_ft"] == 9.0


def test_assumptions_distilled_from_scale_and_wall_height(learning_db):
    record(scope=store.SCOPE_SCALE, run_id="r1", item_pattern="a1.*", original=24.0, corrected=20.0)
    record(scope=store.SCOPE_WALL_HEIGHT, run_id="r1", item_pattern=None, original=9.0, corrected=10.0)
    distill()

    assumptions = {a["key"]: a for a in store.get_assumptions("proj-a", "industrial")}
    assert assumptions["scale_fpi:a1.*"]["value"] == 20.0
    assert assumptions["wall_height_ft"]["value"] == 10.0

    # Type-level rows exist too, so learning transfers to new projects of the type.
    transferred = {a["key"]: a["value"] for a in store.get_assumptions("brand-new-project", "industrial")}
    assert transferred["wall_height_ft"] == 10.0
    assert transferred["scale_fpi:a1.*"] == 20.0


def test_assumption_contradiction_decays_old_value(learning_db):
    record(scope=store.SCOPE_WALL_HEIGHT, run_id="r1", item_pattern=None, corrected=9.0)
    record(scope=store.SCOPE_WALL_HEIGHT, run_id="r2", item_pattern=None, corrected=10.0)
    distill()

    # Retrieval: new value wins by weight.
    assumptions = {a["key"]: a["value"] for a in store.get_assumptions("proj-a", "industrial")}
    assert assumptions["wall_height_ft"] == 10.0

    conn = store.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT value, weight FROM learning_assumptions
            WHERE project_key = ? AND key = ?
            """,
            ("proj-a", "wall_height_ft"),
        ).fetchall()
    finally:
        conn.close()
    weights = {json.loads(r["value"]): r["weight"] for r in rows}
    assert weights[10.0] == pytest.approx(1.0)
    assert weights[9.0] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Manifests: expected-item checklist aggregates.
# ---------------------------------------------------------------------------

def test_manifest_counts_and_expectation(learning_db):
    record(scope=store.SCOPE_ITEM, run_id="r1", item_pattern="bollards", corrected={"quantity": 17, "unit": "EA"})
    record(scope=store.SCOPE_ITEM, run_id="r2", item_pattern="bollards", corrected={"quantity": 28, "unit": "EA"})
    record(scope=store.SCOPE_MISSED_ITEM, run_id="r2", item_pattern=None, corrected={"item_name": "Tilt-Up Wall", "unit": "SF"})
    distill()

    manifest = {m["item_name"]: m for m in store.get_manifest("industrial")}
    assert manifest["bollards"]["seen_in_runs"] == 2
    assert manifest["bollards"]["verified_runs_total"] == 2
    assert manifest["bollards"]["unit"] == "EA"
    assert manifest["bollards"]["expectation"] == pytest.approx(1.0)
    assert manifest["Tilt-Up Wall"]["seen_in_runs"] == 1
    assert manifest["Tilt-Up Wall"]["expectation"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 6. Injection safety: learned strings are hostile input.
# ---------------------------------------------------------------------------

INJECTION_PROBE = "x'; DROP TABLE learning_corrections;--"


def test_sql_injection_probe_round_trips_literally(learning_db):
    record(scope=store.SCOPE_ITEM, item_pattern=INJECTION_PROBE, corrected=INJECTION_PROBE)
    # Push the payload through every distill path too (vocabulary + manifests).
    record(scope=store.SCOPE_NAME, run_id="r2", item_pattern=INJECTION_PROBE, corrected=INJECTION_PROBE)
    distill()

    conn = store.get_connection()
    try:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "learning_corrections" in tables  # the probe did not drop it

        row = conn.execute(
            "SELECT * FROM learning_corrections WHERE item_pattern = ? AND scope = ?",
            (INJECTION_PROBE, "item"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["item_pattern"] == INJECTION_PROBE
    assert json.loads(row["corrected_value"]) == INJECTION_PROBE

    vocab = [r for r in store.get_vocabulary("industrial") if r["raw_pattern"] == INJECTION_PROBE]
    assert len(vocab) == 1
    assert vocab[0]["canonical_name"] == INJECTION_PROBE


# ---------------------------------------------------------------------------
# Hardening: input validation and payload caps.
# ---------------------------------------------------------------------------

def test_invalid_scope_rejected(learning_db):
    with pytest.raises(ValueError):
        record(scope="not-a-scope")


def test_missing_corrected_value_rejected(learning_db):
    with pytest.raises(ValueError):
        store.record_correction(
            run_id="r1", project_key="proj-a", scope=store.SCOPE_ITEM, corrected_value=None
        )


def test_get_corrections_project_key_filter(learning_db):
    """WR-01: project_key filters at the query level, not post-hoc in Python."""
    record(project_key="proj-a", item_pattern="bollards",
           corrected={"quantity": 28, "unit": "EA"})
    for i in range(5):
        record(project_key="proj-b", run_id="rb-%d" % i,
               item_pattern="other-%d" % i, corrected={"quantity": i, "unit": "EA"})

    hits = store.get_corrections(project_key="proj-a")
    assert len(hits) == 1
    assert hits[0]["project_key"] == "proj-a"
    assert hits[0]["item_pattern"] == "bollards"

    # A limit smaller than the other project's row count still returns
    # proj-a rows — recency of OTHER projects cannot evict them.
    hits = store.get_corrections(project_key="proj-a", limit=2)
    assert len(hits) == 1
    assert hits[0]["project_key"] == "proj-a"


def test_oversized_values_rejected_never_truncated(learning_db):
    """WR-02: over-length payloads raise ValueError — truncating JSON
    mid-token would make distill install the fragment as learned data."""
    with pytest.raises(ValueError):
        record(corrected="A" * 5000)
    with pytest.raises(ValueError):
        record(item_pattern="p" * 5000, corrected="ok")
    with pytest.raises(ValueError):
        record(corrected="ok", context={"blob": "x" * 5000})

    # Nothing was inserted by any rejected call.
    conn = store.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM learning_corrections").fetchone()["c"]
    finally:
        conn.close()
    assert n == 0

    # A value at the cap is accepted and round-trips as VALID JSON.
    ok_len = store.MAX_VALUE_LEN - 2  # json.dumps adds surrounding quotes
    record(corrected="B" * ok_len)
    rows = store.get_corrections()
    assert rows[0]["corrected_value"] == "B" * ok_len


def test_distill_rejects_oversized_canonical_name(learning_db):
    """WR-02: a stuffed canonical_name (valid JSON, but absurdly long) must
    never be installed into learning_vocabulary."""
    record(
        scope=store.SCOPE_NAME,
        item_pattern="cmu wall",
        corrected={"canonical_name": "Z" * 500, "unit": "SF"},
    )
    stats = distill()
    assert stats["skipped"] >= 1
    conn = store.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM learning_vocabulary").fetchone()["c"]
    finally:
        conn.close()
    assert n == 0

    # A sane mapping still distills normally afterwards.
    record(
        scope=store.SCOPE_NAME,
        run_id="run-002",
        item_pattern="cmu wall",
        corrected={"canonical_name": "CMU Wall", "unit": "SF"},
    )
    distill()
    conn = store.get_connection()
    try:
        row = conn.execute(
            "SELECT canonical_name FROM learning_vocabulary WHERE raw_pattern = ?",
            ("cmu wall",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row["canonical_name"] == "CMU Wall"
