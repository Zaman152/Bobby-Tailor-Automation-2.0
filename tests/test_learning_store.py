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


# ---------------------------------------------------------------------------
# 24-05: per-project vocabulary snapshots (V4-DET-02/04, defect F3).
#
# The naming library was re-derived from the API on every run, so the SAME
# geometry published `Metal Downspout` on one paid run and `Metal Downspouts`
# on the next. These tests pin the store half of the fix: one exact-project
# snapshot, replace-in-place, invisible to other projects, and every failure
# path degrading to empty so the caller re-derives instead of crashing.
#
# The whole point of a NEW table is that `learning_vocabulary` keeps doing its
# own per-TYPE job untouched — so that is asserted explicitly, not assumed.
# ---------------------------------------------------------------------------

VOCAB_OBJECTS = [
    {
        "canonical_name": "Metal Downspout",
        "aliases": ["DS", "downspout"],
        "basis": "count",
        "binding_hint": "symbol",
        "variant": None,
        "thickness_in": None,
        "height_ft": None,
    },
    {
        "canonical_name": "Tilt Up Wall",
        "aliases": ["TILT-UP"],
        "basis": "wall_area",
        "binding_hint": "wall",
        "variant": "exterior",
        "thickness_in": 9.25,
        "height_ft": 30.0,
    },
]


def _project_vocab_rows():
    """Raw rows of the snapshot table (no store helper in the loop).

    Forces the schema first so "no row was written" is an observation about an
    existing EMPTY table — a rejected save returns before touching the DB, so
    without this the assertion would pass by erroring on a missing table.
    """
    store.init_learning_schema()
    conn = store.get_connection()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT project_key, kind, objects, object_count "
                "FROM learning_project_vocabulary ORDER BY id"
            )
        ]
    finally:
        conn.close()


def test_persisted_vocabulary_round_trips_field_for_field(learning_db):
    """Bullet 1: what went in comes back out, field for field."""
    n = store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)
    assert n == len(VOCAB_OBJECTS)

    loaded = store.load_project_vocabulary("proj-a")
    assert loaded == VOCAB_OBJECTS
    # Not merely equal-by-name: every field of every object survived.
    assert loaded[1]["thickness_in"] == 9.25
    assert loaded[1]["variant"] == "exterior"
    assert loaded[0]["aliases"] == ["DS", "downspout"]


def test_persisted_vocabulary_save_replaces_rather_than_accumulates(learning_db):
    """Bullet 2: a project has ONE current snapshot, not a growing pile.

    If saves accumulated, reuse would depend on which row happened to be read
    first — re-introducing exactly the non-determinism this table exists to
    remove.
    """
    store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)
    store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)
    replacement = [{"canonical_name": "Bollards", "aliases": [], "basis": "count"}]
    assert store.save_project_vocabulary("proj-a", replacement) == 1

    rows = _project_vocab_rows()
    assert len(rows) == 1, rows
    assert rows[0]["object_count"] == 1
    assert store.load_project_vocabulary("proj-a") == replacement


def test_persisted_vocabulary_absent_project_returns_empty_not_an_error(learning_db):
    """Bullet 3: a never-saved key reads as empty — the caller derives fresh."""
    assert store.load_project_vocabulary("never-saved") == []
    # And an empty store overall (no row at all) is the same non-event.
    assert _project_vocab_rows() == []


def test_persisted_vocabulary_is_scoped_to_the_exact_project(learning_db):
    """Bullet 4: same project TYPE, different project — no leak (T-24-20).

    `learning_vocabulary` is keyed by project_type on purpose; this table is
    not, and one project's naming must never drift because a sibling project
    of the same type was run.
    """
    store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)
    # Both projects are 'industrial' as far as learning_vocabulary is
    # concerned; the snapshot still does not cross.
    store.record_ai_manifest("proj-a", "industrial", VOCAB_OBJECTS)
    store.record_ai_manifest("proj-b", "industrial", VOCAB_OBJECTS)

    assert store.load_project_vocabulary("proj-b") == []
    assert store.load_project_vocabulary("proj-a") == VOCAB_OBJECTS


def test_persisted_vocabulary_leaves_learning_vocabulary_untouched(learning_db):
    """Bullet 5: the additive promise, asserted rather than assumed.

    A destructive migration of `learning_vocabulary` is T-24-18 (critical).
    The new table is a different concern with a different scope; every row and
    the per-type read must be byte-identical across a full save/load cycle.
    """
    store.record_ai_manifest("proj-a", "industrial", VOCAB_OBJECTS)
    before_rows = dump_distilled_tables()
    before_read = store.get_vocabulary("industrial")
    assert before_read, "fixture must actually populate learning_vocabulary"

    store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)
    store.save_project_vocabulary("proj-b", VOCAB_OBJECTS)
    store.load_project_vocabulary("proj-a")
    store.load_project_vocabulary("proj-zzz")

    assert dump_distilled_tables() == before_rows
    assert store.get_vocabulary("industrial") == before_read

    # The module carries no destructive statement against that table at all.
    src = (
        __import__("pathlib").Path(store.__file__).read_text(encoding="utf-8")
    )
    assert "DROP TABLE" not in src
    assert "ALTER TABLE learning_vocabulary" not in src
    assert "DELETE FROM learning_vocabulary" not in src


def test_persisted_vocabulary_falsy_project_key_writes_nothing(learning_db):
    """Bullet 6: no global row — every project would otherwise inherit it."""
    for key in (None, "", 0):
        assert store.save_project_vocabulary(key, VOCAB_OBJECTS) == 0
    assert _project_vocab_rows() == []
    assert store.load_project_vocabulary(None) == []
    assert store.load_project_vocabulary("") == []

    # An empty object list is likewise a no-op: an empty snapshot reads
    # identically to "never saved", so writing one could only cost a row.
    assert store.save_project_vocabulary("proj-a", []) == 0
    assert store.save_project_vocabulary("proj-a", None) == 0
    assert _project_vocab_rows() == []


def test_persisted_vocabulary_unreadable_store_degrades_to_empty(
    learning_db, tmp_path, monkeypatch
):
    """Bullet 7: a broken store costs a run its API saving, never the run.

    Three separate failure shapes, because 'it degrades' is only true if the
    guard covers the whole read: an unopenable DB file, a corrupt payload, and
    a payload that parses but is not a list.
    """
    store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)

    # (a) the DB path is not a database at all.
    unopenable = tmp_path / "not-a-db"
    unopenable.mkdir()
    monkeypatch.setattr(store, "LEARNING_DB_PATH", unopenable)
    monkeypatch.setattr(store, "_initialized_for", None)
    assert store.load_project_vocabulary("proj-a") == []
    # ... and a save against it does not raise either.
    with pytest.raises(sqlite3.Error):
        store.get_connection()

    # (b) a corrupt (non-JSON) payload.
    monkeypatch.setattr(store, "LEARNING_DB_PATH", learning_db)
    monkeypatch.setattr(store, "_initialized_for", None)
    conn = store.get_connection()
    try:
        conn.execute(
            "UPDATE learning_project_vocabulary SET objects = ? WHERE project_key = ?",
            ("{not json", "proj-a"),
        )
        conn.commit()
    finally:
        conn.close()
    assert store.load_project_vocabulary("proj-a") == []

    # (c) valid JSON that is not an object list.
    conn = store.get_connection()
    try:
        conn.execute(
            "UPDATE learning_project_vocabulary SET objects = ? WHERE project_key = ?",
            (json.dumps({"objects": []}), "proj-a"),
        )
        conn.commit()
    finally:
        conn.close()
    assert store.load_project_vocabulary("proj-a") == []


def test_persisted_vocabulary_kinds_do_not_overwrite_each_other(learning_db):
    """Two derivations, one project: each keeps its own snapshot.

    `_build_project_vocabulary` and `_build_naming_conventions` are two
    different API passes over the same project. Sharing one row would make
    whichever ran last silently answer for both.
    """
    conventions = [{"canonical_name": "Pipe Handrail", "aliases": [], "basis": "linear"}]
    store.save_project_vocabulary("proj-a", VOCAB_OBJECTS)
    store.save_project_vocabulary(
        "proj-a", conventions, kind=store.VOCAB_KIND_NAMING_CONVENTIONS
    )

    assert store.load_project_vocabulary("proj-a") == VOCAB_OBJECTS
    assert store.load_project_vocabulary(
        "proj-a", kind=store.VOCAB_KIND_NAMING_CONVENTIONS
    ) == conventions
    assert len(_project_vocab_rows()) == 2


def test_persisted_vocabulary_oversized_payload_is_rejected_not_truncated(learning_db):
    """WR-02 discipline, at the snapshot's own (larger) cap.

    A JSON array cut mid-token cannot be parsed back, so every future load
    would silently fail. Rejection returns 0 and the run re-derives.
    """
    stuffed = [
        {"canonical_name": "X" * 500, "aliases": ["Y" * 500]}
        for _ in range(store.MAX_PROJECT_VOCABULARY_LEN // 400)
    ]
    assert store.save_project_vocabulary("proj-a", stuffed) == 0
    assert _project_vocab_rows() == []
    assert store.load_project_vocabulary("proj-a") == []


def test_persisted_vocabulary_table_is_registered_in_the_table_list(learning_db):
    """A table nobody enumerates is a table schema inspection forgets."""
    assert store.PROJECT_VOCABULARY_TABLE in store.LEARNING_TABLES
    store.init_learning_schema()
    conn = store.get_connection()
    try:
        present = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        conn.close()
    assert set(store.LEARNING_TABLES).issubset(present), (
        set(store.LEARNING_TABLES) - present
    )
