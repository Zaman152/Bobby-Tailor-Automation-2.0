"""Layer-4 tests for AI-manifest persistence + reuse (learn-ai-manifest).

The Opus naming manifest must PERSIST into ``learning_vocabulary`` with
``source='ai'`` and be REUSED on future runs, so the app accumulates a
growing autonomous naming dictionary instead of regenerating the whole
manifest with Opus every run. Human corrections must OUTRANK AI-generated
names for the same raw_pattern.

Covers:
    * additive, idempotent ``source`` column migration (legacy DB upgrades);
    * ``record_ai_manifest`` writes ``source='ai'`` rows at weight < 1.0,
      one per {canonical name} ∪ {aliases}, idempotent on repeat;
    * precedence — a distilled human correction outranks the AI row in
      ``lookup_name`` / retrieval for the same raw_pattern;
    * retrieval returns AI rows when no human row exists (dictionary reuse);
    * run wiring — ``run_project`` persists the built vocabulary once, and a
      store failure is swallowed (the run continues).

SQLite state is isolated per test via a tmp_path DB monkeypatched onto
``bobbytailor.learning.store.LEARNING_DB_PATH`` (test_learning_store pattern).
Zero API calls — canned analyzers only.
"""
import sqlite3

import pytest

from bobbytailor.learning import store
from bobbytailor.learning.distill import distill
from bobbytailor.learning.retrieval import load_learned_context
from bobbytailor.pipeline import takeoff_pipeline
from bobbytailor.pipeline.takeoff_pipeline import RunSettings, TakeoffPipeline

PROJECT_KEY = "crow-cass-white-road"
PROJECT_TYPE = "industrial"


@pytest.fixture()
def learning_db(tmp_path, monkeypatch):
    """Point the store at an isolated tmp DB; schema re-inits per path."""
    db_path = tmp_path / "learning.db"
    monkeypatch.setattr(store, "LEARNING_DB_PATH", db_path)
    monkeypatch.setattr(store, "_initialized_for", None)
    return db_path


# ---------------------------------------------------------------------------
# 1. Additive, idempotent migration of the `source` column.
# ---------------------------------------------------------------------------

# The learning_vocabulary schema as it existed BEFORE the source column —
# used to simulate an existing pre-migration learning.db.
_PRE_MIGRATION_VOCAB_SQL = """
CREATE TABLE learning_vocabulary (
  id INTEGER PRIMARY KEY,
  project_type TEXT,
  raw_pattern TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  last_seen TEXT NOT NULL,
  UNIQUE(project_type, raw_pattern, canonical_name, unit)
);
"""


def _vocab_columns(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(learning_vocabulary)")}
    finally:
        conn.close()


def test_migration_adds_source_column_to_legacy_db(learning_db):
    """An existing pre-migration DB gains `source` defaulting 'human'; the
    legacy row is preserved (no data loss) and re-init is idempotent."""
    # Build the OLD schema by hand and insert a legacy row (no source column).
    conn = sqlite3.connect(str(learning_db))
    try:
        conn.executescript(_PRE_MIGRATION_VOCAB_SQL)
        conn.execute(
            """
            INSERT INTO learning_vocabulary
                (project_type, raw_pattern, canonical_name, unit, weight, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("industrial", "cmu wall", "CMU Wall", "SF", 3.0, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()
    assert "source" not in _vocab_columns(learning_db)

    # First init runs the additive ALTER; the column appears, back-filled.
    store.init_learning_schema()
    assert "source" in _vocab_columns(learning_db)

    rows = store.get_vocabulary("industrial")
    legacy = [r for r in rows if r["raw_pattern"] == "cmu wall"]
    assert len(legacy) == 1
    assert legacy[0]["canonical_name"] == "CMU Wall"   # data preserved
    assert legacy[0]["weight"] == pytest.approx(3.0)
    assert legacy[0]["source"] == store.SOURCE_HUMAN   # default back-fill

    # Idempotent: re-init (fresh initialization flag) does not error or dup.
    store._initialized_for = None
    store.init_learning_schema()
    assert "source" in _vocab_columns(learning_db)
    assert len(store.get_vocabulary("industrial")) == 1


def test_fresh_db_has_source_column(learning_db):
    """A brand-new DB carries the source column straight from CREATE TABLE."""
    store.init_learning_schema()
    assert "source" in _vocab_columns(learning_db)


# ---------------------------------------------------------------------------
# 2. record_ai_manifest — writes source='ai' rows at weight < 1.0.
# ---------------------------------------------------------------------------

def _sample_manifest():
    return [
        {"name": "Bollard", "aliases": ["BOL", "Bollards"], "unit": "EA", "basis": "count"},
        {"canonical_name": "CMU Wall", "aliases": ["conc masonry unit wall"], "unit": "SF"},
    ]


def _rows_by_pattern(project_type=PROJECT_TYPE):
    conn = store.get_connection()
    try:
        rows = conn.execute(
            "SELECT raw_pattern, canonical_name, unit, weight, source "
            "FROM learning_vocabulary WHERE project_type IS ?",
            (project_type,),
        ).fetchall()
        return {r["raw_pattern"]: dict(r) for r in rows}
    finally:
        conn.close()


def test_record_ai_manifest_writes_ai_rows(learning_db):
    written = store.record_ai_manifest(
        PROJECT_KEY, PROJECT_TYPE, _sample_manifest(),
        ts="2026-02-02T00:00:00+00:00",
    )
    # 3 patterns for Bollard (name + 2 aliases) + 2 for CMU (name + 1 alias).
    assert written == 5

    rows = _rows_by_pattern()
    # Every alias maps back to the object's canonical name, lowercased key.
    assert rows["bollard"]["canonical_name"] == "Bollard"
    assert rows["bol"]["canonical_name"] == "Bollard"
    assert rows["bollards"]["canonical_name"] == "Bollard"
    assert rows["cmu wall"]["canonical_name"] == "CMU Wall"
    assert rows["conc masonry unit wall"]["canonical_name"] == "CMU Wall"

    # source='ai' at a MODEST weight, strictly below a human confirmation (1.0).
    for r in rows.values():
        assert r["source"] == store.SOURCE_AI
        assert r["weight"] < 1.0
        assert r["weight"] == pytest.approx(store.AI_MANIFEST_WEIGHT)
    assert rows["bollard"]["unit"] == "EA"
    assert rows["cmu wall"]["unit"] == "SF"


def test_record_ai_manifest_idempotent(learning_db):
    """A second call does not duplicate rows; it bumps weight (capped < 1.0)."""
    store.record_ai_manifest(PROJECT_KEY, PROJECT_TYPE, _sample_manifest())
    first = _rows_by_pattern()
    store.record_ai_manifest(PROJECT_KEY, PROJECT_TYPE, _sample_manifest())
    second = _rows_by_pattern()

    assert set(first) == set(second)             # no new rows
    assert len(second) == 5
    for pattern, row in second.items():
        # Modest bump, still below a single human vote.
        assert row["weight"] == pytest.approx(
            store.AI_MANIFEST_WEIGHT + store.AI_MANIFEST_BUMP
        )
        assert row["weight"] < 1.0

    # Many repeats never let the AI weight overtake a human confirmation.
    for _ in range(50):
        store.record_ai_manifest(PROJECT_KEY, PROJECT_TYPE, _sample_manifest())
    capped = _rows_by_pattern()
    for row in capped.values():
        assert row["weight"] <= store.AI_MANIFEST_WEIGHT_CAP < 1.0


def test_record_ai_manifest_empty_and_junk_noop(learning_db):
    assert store.record_ai_manifest(PROJECT_KEY, PROJECT_TYPE, None) == 0
    assert store.record_ai_manifest(PROJECT_KEY, PROJECT_TYPE, []) == 0
    # Unnamed / over-length objects are skipped (WR-02 sanity gate).
    junk = [{"aliases": ["x"]}, {"name": "Z" * 500, "unit": "SF"}]
    assert store.record_ai_manifest(PROJECT_KEY, PROJECT_TYPE, junk) == 0
    assert _rows_by_pattern() == {}


# ---------------------------------------------------------------------------
# 3. Precedence — human OUTRANKS ai for the same raw_pattern.
# ---------------------------------------------------------------------------

RAW = "conc masonry unit wall"


def test_human_correction_outranks_ai(learning_db):
    """A distilled human correction wins retrieval over the AI row for the
    same raw_pattern — even though the AI row was written first."""
    # AI manifest names it one way…
    store.record_ai_manifest(
        PROJECT_KEY, PROJECT_TYPE,
        [{"name": "CMU Wall (AI)", "aliases": [RAW], "unit": "SF"}],
    )
    # …then a human corrects it to a different canonical name.
    store.record_correction(
        run_id="run-1", project_key=PROJECT_KEY, project_type=PROJECT_TYPE,
        sheet_type="floor_plan", scope=store.SCOPE_NAME,
        item_pattern=RAW, original_value=RAW,
        corrected_value={"canonical_name": "CMU Wall (Verified)", "unit": "SF"},
    )
    distill()

    # store ordering: the human mapping ranks first for this pattern.
    ctx = load_learned_context(PROJECT_KEY, PROJECT_TYPE)
    canonical, unit = ctx.lookup_name(RAW)
    assert canonical == "CMU Wall (Verified)"   # human wins
    assert unit == "SF"

    # The human row is source='human' and ranks ahead of any ai row.
    ranked = [
        r for r in store.get_vocabulary(PROJECT_TYPE)
        if r["raw_pattern"] == RAW
    ]
    assert ranked[0]["source"] == store.SOURCE_HUMAN
    assert ranked[0]["canonical_name"] == "CMU Wall (Verified)"


def test_human_row_never_overwritten_by_ai(learning_db):
    """record_ai_manifest never re-weights or overwrites a human row for the
    identical (raw_pattern, canonical_name, unit) mapping."""
    store.record_correction(
        run_id="run-1", project_key=PROJECT_KEY, project_type=PROJECT_TYPE,
        sheet_type="floor_plan", scope=store.SCOPE_NAME,
        item_pattern=RAW, original_value=RAW,
        corrected_value={"canonical_name": "CMU Wall", "unit": "SF"},
    )
    distill()
    before = _rows_by_pattern()[RAW]
    assert before["source"] == store.SOURCE_HUMAN

    # The AI manifest asserts the SAME mapping — the human row is left as-is.
    store.record_ai_manifest(
        PROJECT_KEY, PROJECT_TYPE,
        [{"name": "CMU Wall", "aliases": [RAW], "unit": "SF"}],
    )
    after = _rows_by_pattern()[RAW]
    assert after["source"] == store.SOURCE_HUMAN
    assert after["weight"] == pytest.approx(before["weight"])   # not bumped


# ---------------------------------------------------------------------------
# 4. Retrieval returns AI rows when no human row exists (dictionary reuse).
# ---------------------------------------------------------------------------

def test_retrieval_returns_ai_row_when_no_human(learning_db):
    store.record_ai_manifest(
        PROJECT_KEY, PROJECT_TYPE,
        [{"name": "Exposed Structure", "aliases": ["EXP STRUCT"], "unit": "SF"}],
    )
    ctx = load_learned_context(PROJECT_KEY, PROJECT_TYPE)
    assert ctx.lookup_name("exp struct") == ("Exposed Structure", "SF")
    assert ctx.lookup_name("Exposed Structure") == ("Exposed Structure", "SF")


# ---------------------------------------------------------------------------
# 5. Run wiring — run_project persists the built vocabulary once, non-fatally.
# ---------------------------------------------------------------------------

class CannedAnalyzer:
    """Canned legacy-path analyzer — benign for every pass; records calls."""

    def __init__(self):
        self.calls = []

    def __call__(
        self,
        image_path,
        sheet_name="",
        pass_type="measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
        **kwargs,
    ):
        self.calls.append(pass_type)
        return {
            "sheet_title": "WAREHOUSE FLOOR PLAN",
            "components": [{"name": "bollard", "quantity": 5, "unit": "EA"}],
            "measurements": [], "_cost_usd": 0.0,
            "_tokens_in": 1, "_tokens_out": 1, "_model_used": "canned",
        }


# Plan text the deterministic component-library harvests a project vocabulary
# from (abbreviations + door schedule + bollard keynote) — no vector PDF /
# naming pass needed, so run_project builds a non-empty _project_vocabulary.
_PLAN_TEXT = (
    "ABBREVIATIONS:\n"
    "HM = HOLLOW METAL\n"
    "CMU = CONCRETE MASONRY UNIT\n"
    "BOL = BOLLARD\n\n"
    "DOOR SCHEDULE\n"
    "101 HM 3070\n"
    "102 HM 3070\n\n"
    "KEYNOTES:\n"
    "1. PROVIDE BOLLARD AT EACH OVERHEAD DOOR\n"
    "2. CMU WALL 8 INCH\n"
)


def _run(analyzer, project_key, settings=None):
    pipeline = TakeoffPipeline(analyzer=analyzer, settings=settings or RunSettings())
    result = pipeline.run_project(
        [{"image_path": "a2.png", "sheet_name": "A2.1",
          "sheet_type_hint": "floor_plan", "full_page_text": _PLAN_TEXT}],
        project_key=project_key,
    )
    return pipeline, result


def test_run_project_persists_ai_manifest(learning_db):
    """A run builds a project vocabulary → it is persisted as source='ai'
    rows that a subsequent retrieval returns."""
    analyzer = CannedAnalyzer()
    pipeline, (extracted, _est, _ptype) = _run(analyzer, "proj-ai")
    assert extracted
    assert getattr(pipeline, "_project_vocabulary", None)  # vocabulary built

    # AI rows now live in the store for reuse on the NEXT run.
    conn = store.get_connection()
    try:
        rows = conn.execute(
            "SELECT raw_pattern, canonical_name, source FROM learning_vocabulary "
            "WHERE source = ?",
            (store.SOURCE_AI,),
        ).fetchall()
    finally:
        conn.close()
    assert rows, "expected the built vocabulary to be persisted as source='ai'"
    by_pattern = {r["raw_pattern"]: r for r in rows}
    assert "bollards" in by_pattern
    assert all(r["source"] == store.SOURCE_AI for r in rows)


def test_run_project_ai_manifest_failure_is_non_fatal(learning_db, monkeypatch):
    """A store failure during AI-manifest persistence must NEVER break a run."""
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated store failure")

    monkeypatch.setattr(takeoff_pipeline, "record_ai_manifest", _boom)

    analyzer = CannedAnalyzer()
    pipeline, (extracted, _est, _ptype) = _run(analyzer, "proj-ai-fail")
    # Run completed and returned extraction despite the persistence failure.
    assert extracted
    assert getattr(pipeline, "_project_vocabulary", None)


def test_run_project_skips_ai_manifest_when_learning_disabled(learning_db):
    analyzer = CannedAnalyzer()
    _run(analyzer, "proj-disabled", settings=RunSettings(learning_enabled=False))
    store.init_learning_schema()  # learning-disabled run never touches the store
    conn = store.get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM learning_vocabulary WHERE source = ?",
            (store.SOURCE_AI,),
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n == 0
