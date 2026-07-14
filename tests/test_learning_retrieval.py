"""Layer-4 tests for learned-context retrieval + injection (V3-LEARN-02/03/04).

Covers the 21-VALIDATION.md layer-4 contract for plan 21-16:
retrieval bundle round-trips, the three injection seams (prompt hint,
aggregation naming, calculator/scale assumptions), the anti-amplification
guardrail (BLOCKING — a HIGH-confidence geometry quantity survives a
contradicting learned value unchanged), and the repeat-run application of
corrections (roadmap success criterion 4 at test level).

SQLite state is isolated per test via a tmp_path DB monkeypatched onto
``bobbytailor.learning.store.LEARNING_DB_PATH`` (test_learning_store
pattern). Pipeline runs use canned analyzers — zero API calls.
"""
import pytest

from bobbytailor.learning import store
from bobbytailor.learning.distill import distill
from bobbytailor.learning.retrieval import (
    MAX_HINT_CHARS,
    LearnedContext,
    apply_learned_quantity_flags,
    load_learned_context,
)

PROJECT_KEY = "crow-cass-white-road"
PROJECT_TYPE = "industrial"


@pytest.fixture()
def learning_db(tmp_path, monkeypatch):
    """Point the store at an isolated tmp DB; schema re-inits per path."""
    db_path = tmp_path / "learning.db"
    monkeypatch.setattr(store, "LEARNING_DB_PATH", db_path)
    monkeypatch.setattr(store, "_initialized_for", None)
    return db_path


def seed_name_correction(
    raw="conc masonry unit wall",
    canonical="CMU Wall (Verified)",
    unit="SF",
    project_key=PROJECT_KEY,
    project_type=PROJECT_TYPE,
    run_id="run-001",
):
    """Record a name correction and distill it into learning_vocabulary."""
    store.record_correction(
        run_id=run_id,
        project_key=project_key,
        project_type=project_type,
        sheet_type="floor_plan",
        scope=store.SCOPE_NAME,
        item_pattern=raw,
        original_value=raw,
        corrected_value={"canonical_name": canonical, "unit": unit},
    )
    distill()


def seed_quantity_correction(
    item_pattern="cmu wall",
    original=None,
    corrected=None,
    project_key=PROJECT_KEY,
    project_type=PROJECT_TYPE,
    run_id="run-001",
):
    store.record_correction(
        run_id=run_id,
        project_key=project_key,
        project_type=project_type,
        sheet_type="floor_plan",
        scope=store.SCOPE_ITEM,
        item_pattern=item_pattern,
        original_value=original or {"quantity": 17, "unit": "SF"},
        corrected_value=corrected or {"quantity": 2204, "unit": "SF"},
    )
    distill()


# ---------------------------------------------------------------------------
# 1. LearnedContext bundle — cold start + retrieval round-trip
# ---------------------------------------------------------------------------


def test_context_cold_start_is_silent(learning_db):
    """Empty store → empty context, render_prompt_hint() None (no behavior change)."""
    ctx = load_learned_context(PROJECT_KEY, PROJECT_TYPE)
    assert isinstance(ctx, LearnedContext)
    assert ctx.render_prompt_hint() is None
    assert ctx.lookup_name("cmu wall") is None
    assert ctx.get_assumption("wall_height_ft") is None
    assert ctx.quantity_corrections == {}


def test_context_bundle_vocabulary_and_hint(learning_db):
    """Seeded corrections round-trip into vocabulary, manifest, and the hint."""
    seed_name_correction()
    seed_quantity_correction()  # scope 'item' → manifest row for the type

    ctx = load_learned_context(PROJECT_KEY, PROJECT_TYPE)
    assert ctx.project_type == PROJECT_TYPE
    # Normalized exact match: whitespace/case-insensitive.
    assert ctx.lookup_name("  CONC   Masonry  UNIT wall ") == (
        "CMU Wall (Verified)", "SF",
    )
    # Miss → None (static ITEM_NAME_MAP remains the fallback downstream).
    assert ctx.lookup_name("totally unseen thing") is None

    hint = ctx.render_prompt_hint()
    assert hint is not None
    assert "LEARNED PROJECT CONTEXT" in hint
    assert "CMU Wall (Verified)" in hint
    assert "<pdf_text>" in hint and "</pdf_text>" in hint
    assert "ground truth" in hint  # hint phrasing must not assert facts as truth


def test_context_assumption_specificity_precedence(learning_db):
    """Exact project_key assumption beats the project_type-level row (21-04)."""
    # Another project of the same type learned 12 ft → type-level row.
    store.record_correction(
        run_id="run-b1",
        project_key="other-project",
        project_type=PROJECT_TYPE,
        scope=store.SCOPE_WALL_HEIGHT,
        corrected_value=12.0,
    )
    # This project learned 24 ft → exact + type rows.
    store.record_correction(
        run_id="run-a1",
        project_key=PROJECT_KEY,
        project_type=PROJECT_TYPE,
        scope=store.SCOPE_WALL_HEIGHT,
        corrected_value=24.0,
    )
    distill()

    ctx = load_learned_context(PROJECT_KEY, PROJECT_TYPE)
    entry = ctx.get_assumption("wall_height_ft")
    assert entry is not None
    assert float(entry["value"]) == 24.0
    assert entry["specificity"] == "project_key"

    # A brand-new project of the same type inherits the type-level value.
    ctx_new = load_learned_context("brand-new-project", PROJECT_TYPE)
    entry_new = ctx_new.get_assumption("wall_height_ft")
    assert entry_new is not None
    assert entry_new["specificity"] == "project_type"


def test_context_infers_project_type_on_repeat_run(learning_db):
    """Run-start retrieval (type unknown) recovers the type from prior corrections."""
    seed_name_correction()
    seed_quantity_correction()

    ctx = load_learned_context(PROJECT_KEY, project_type=None)
    assert ctx.project_type == PROJECT_TYPE
    assert ctx.lookup_name("conc masonry unit wall") is not None
    assert ctx.render_prompt_hint() is not None
