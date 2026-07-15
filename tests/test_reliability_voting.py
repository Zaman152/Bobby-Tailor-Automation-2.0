"""Offline tests for categorical majority-vote reliability (Parts B + C).

No API calls anywhere — the analyzer is a stub callable that yields a scripted
sequence of label lists. Pins:
- ``_voted_structured_vision_call`` majority-votes the per-candidate labels,
  makes N analyzer calls, and stops early when the BudgetGuard is exhausted;
- ``majority_vote_objects`` keeps objects present in a strict majority of
  vocabulary samples and drops the rest;
- N==1 reproduces single-shot behaviour exactly (regression guard).
"""
import pytest

from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline
from bobbytailor.vision.ensemble import BudgetGuard
from bobbytailor.vision.object_vocabulary import majority_vote_objects


def _make_analyzer(match_scripts, cost_usd=0.0):
    """Build a stub analyzer returning ``match_scripts[i]`` on the i-th call.

    Each script is the ``matches`` list for that call. Records the number of
    calls on ``analyzer.calls``.
    """
    state = {"i": 0}

    def analyzer(
        image_path,
        sheet_name="",
        pass_type="measure",
        sheet_type=None,
        output_schema=None,
        images=None,
        user_hint=None,
        model_override=None,
    ):
        idx = min(state["i"], len(match_scripts) - 1)
        matches = match_scripts[idx]
        state["i"] += 1
        return {
            "matches": list(matches),
            "_cost_usd": cost_usd,
            "_tokens_in": 1,
            "_tokens_out": 1,
            "_model_used": "stub",
        }

    analyzer.state = state
    return analyzer


def _vote(pipeline, guard=None, n=None):
    return pipeline._voted_structured_vision_call(
        "img.png", "A-101", "symbol_gallery", "floor_plan",
        {"type": "object"}, ["overlay"], guard,
        vote_key="matches", n=n,
    )


# ── Part B: _voted_structured_vision_call majority vote ───────────────────────


def test_voted_call_majority_wins_over_minority_unknown():
    """[SYM-1→Column]×2 + [SYM-1→unknown]×1 over 3 calls → Column, N=3 calls."""
    scripts = [
        [{"symbol_id": "SYM-1", "label": "Column"}],
        [{"symbol_id": "SYM-1", "label": "Column"}],
        [{"symbol_id": "SYM-1", "label": "unknown"}],
    ]
    analyzer = _make_analyzer(scripts)
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = _vote(pipeline)

    assert analyzer.state["i"] == 3               # made 3 analyzer calls
    matches = {m["symbol_id"]: m for m in res["matches"]}
    assert matches["SYM-1"]["label"] == "Column"
    assert matches["SYM-1"]["confidence"] in ("medium", "high")


def test_voted_call_all_unknown_stays_unknown():
    """3× unknown → unknown (flag-don't-guess)."""
    scripts = [[{"symbol_id": "SYM-1", "label": "unknown"}]] * 3
    analyzer = _make_analyzer(scripts)
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = _vote(pipeline)

    assert analyzer.state["i"] == 3
    match = res["matches"][0]
    assert match["symbol_id"] == "SYM-1"
    assert match["label"] == "unknown"


def test_voted_call_unanimous_is_high_confidence():
    scripts = [[{"symbol_id": "SYM-1", "label": "Bollard"}]] * 3
    analyzer = _make_analyzer(scripts)
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = _vote(pipeline)

    match = res["matches"][0]
    assert match["label"] == "Bollard"
    assert match["confidence"] == "high"


def test_voted_call_respects_budget_that_exhausts_after_one():
    """A budget covering exactly one call stops sampling after the first."""
    scripts = [
        [{"symbol_id": "SYM-1", "label": "Column"}],
        [{"symbol_id": "SYM-1", "label": "unknown"}],
        [{"symbol_id": "SYM-1", "label": "unknown"}],
    ]
    analyzer = _make_analyzer(scripts, cost_usd=1.0)
    pipeline = TakeoffPipeline(analyzer=analyzer)
    guard = BudgetGuard(1.0)  # room for exactly one $1.00 call

    res = _vote(pipeline, guard=guard)

    assert analyzer.state["i"] == 1               # stopped after the paid call
    assert res["matches"][0]["label"] == "Column"


def test_voted_call_n_le_1_is_single_shot():
    """N==1 makes exactly one call and returns the raw single-shot result."""
    scripts = [[{"symbol_id": "SYM-1", "label": "Column"}]]
    analyzer = _make_analyzer(scripts)
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = _vote(pipeline, n=1)

    assert analyzer.state["i"] == 1
    assert res["matches"] == [{"symbol_id": "SYM-1", "label": "Column"}]
    assert "_voted" not in res                     # untouched single-shot shape


def test_voted_call_preserves_scalar_fields():
    """Non-vote_key fields (e.g. main_plan_region) survive the synthetic result."""
    def analyzer(image_path, sheet_name="", pass_type="measure", sheet_type=None,
                 output_schema=None, images=None, user_hint=None, model_override=None):
        return {
            "main_plan_region": "REG-1",
            "wall_class_labels": [{"wall_class_id": "WC-1", "label": "CMU"}],
            "_cost_usd": 0.0, "_tokens_in": 1, "_tokens_out": 1, "_model_used": "stub",
        }

    pipeline = TakeoffPipeline(analyzer=analyzer)
    res = pipeline._voted_structured_vision_call(
        "img.png", "A-101", "semantic", "floor_plan",
        {"type": "object"}, ["overlay"], None,
        vote_key="wall_class_labels", n=3,
    )

    assert res["main_plan_region"] == "REG-1"
    assert res["wall_class_labels"][0]["wall_class_id"] == "WC-1"
    assert res["wall_class_labels"][0]["label"] == "CMU"
    assert res["_voted"] is True


# ── Part C: vocabulary object-presence majority vote ──────────────────────────


def test_vocab_majority_vote_keeps_present_drops_rare():
    """Object in >=2/3 samples kept; a 1/3 object dropped."""
    samples = [
        [{"name": "Columns"}, {"name": "Bollards"}],
        [{"name": "Columns"}, {"name": "Bollards"}, {"name": "Ladder"}],
        [{"name": "Columns"}],
    ]
    kept = {o["name"] for o in majority_vote_objects(samples)}
    assert kept == {"Columns", "Bollards"}         # Ladder (1/3) dropped


def test_vocab_vote_unions_aliases_and_votes_basis():
    samples = [
        [{"name": "Exposed Structure", "aliases": ["exp deck"], "basis": "roof_area"}],
        [{"name": "Exposed Structure", "aliases": ["open web joist"], "basis": "roof_area"}],
        [{"name": "Exposed Structure", "aliases": [], "basis": "count"}],
    ]
    out = majority_vote_objects(samples)
    entry = next(o for o in out if o["name"] == "Exposed Structure")
    assert set(entry["aliases"]) == {"exp deck", "open web joist"}
    assert entry["basis"] == "roof_area"           # plurality basis


def test_vocab_vote_single_sample_is_single_shot():
    """N==1 (one sample) returns the objects unchanged (regression guard)."""
    sample = [{"name": "Columns", "aliases": ["col"], "basis": "count"}]
    assert majority_vote_objects([sample]) == sample
