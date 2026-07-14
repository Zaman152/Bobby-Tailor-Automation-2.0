"""Ensemble voting / tiled dedup / budget guard tests (21-11, V3-ACC-03 + V3-PROD-02).

All analyzer access is via stub callables — ZERO real API calls (validation
layer 3). Pins the variance-killer behavior: the historical 397,500-vs-
1,131,112 SF run-to-run failure can never silently pass through a vote, and
the budget cap flags instead of silently truncating (Pitfall 7).
"""
from pathlib import Path

import pytest
from PIL import Image

from bobbytailor.vision.ensemble import (
    BudgetExceeded,
    BudgetGuard,
    EnsembleResult,
    ensemble_settings,
    reset_temperature_probe_cache,
    run_ensemble,
    run_tiled_count,
    vote,
)


@pytest.fixture(autouse=True)
def _fresh_probe_cache():
    """Each test gets an unprobed temperature cache (module-level cache)."""
    reset_temperature_probe_cache()
    yield
    reset_temperature_probe_cache()


# ── 1. vote() threshold matrix ───────────────────────────────────────────────


def test_vote_ea_unanimous_high():
    r = vote([10, 10, 10], "EA")
    assert r.value == 10
    assert r.confidence == "high"
    assert r.needs_review is False


def test_vote_ea_within_tolerance_medium():
    # max−min = 1 ≤ max(1, 10% of 12) → accepted, not unanimous → medium
    r = vote([12, 12, 13], "EA")
    assert r.value == 12
    assert r.confidence == "medium"
    assert r.needs_review is False


def test_vote_ea_off_by_one_accepted():
    # ±1 disagreement on small counts is the tolerance floor, never review
    r = vote([10, 11, 10], "EA")
    assert r.value == 10
    assert r.needs_review is False


def test_vote_ea_disagreement_needs_review():
    # median 9, tol max(1, 0.9)=1; spread 11 and no majority band → review
    r = vote([5, 9, 16], "EA")
    assert r.needs_review is True
    assert r.confidence == "low"
    assert r.value == 9  # best-estimate median still reported for the reviewer


def test_vote_sf_spread_over_ten_percent_flagged():
    r = vote([100, 400, 1100], "SF")
    assert r.needs_review is True
    assert r.confidence == "low"


def test_vote_sf_tight_spread_accepted():
    # spread (105-100)/102 ≈ 4.9% ≤ 10% → accepted medium
    r = vote([100.0, 105.0, 102.0], "SF")
    assert r.needs_review is False
    assert r.confidence == "medium"
    assert r.value == 102.0


def test_vote_historical_variance_pair_can_never_pass():
    # The named V3-ACC-03 failure: 397,500 SF vs 1,131,112 SF on identical
    # runs. Any vote containing this pair MUST flag for review.
    r = vote([397500, 1131112], "SF")
    assert r.needs_review is True
    r3 = vote([397500, 1131112, 512000], "SF")
    assert r3.needs_review is True
    assert sorted(r3.votes) == [397500.0, 512000.0, 1131112.0]


def test_vote_edge_cases_flagged_not_silently_passed():
    empty = vote([], "EA")
    assert empty.value is None and empty.needs_review is True
    single = vote([42], "SF")
    assert single.value == 42 and single.needs_review is True
    assert single.confidence == "low"


def test_vote_vector_persisted_and_serializable():
    r = vote([7, 7, 8], "EA")
    assert r.votes == [7.0, 7.0, 8.0]  # full vector, auditability requirement
    d = r.to_dict()
    assert d["votes"] == [7.0, 7.0, 8.0]
    assert d["n_samples"] == 3
    assert set(d) >= {
        "value", "votes", "confidence", "needs_review", "spread",
        "n_samples", "method",
    }


# ── 2. run_ensemble fan-out + escalation ─────────────────────────────────────


def test_run_ensemble_agreeing_stub_makes_exactly_three_calls():
    calls = []

    def stub(sample_index, temperature, prompt_variation):
        calls.append((sample_index, temperature))
        return {"value": 12, "_cost_usd": 0.01}

    r = run_ensemble(stub, probe_key="agree3")
    assert len(calls) == 3
    assert [c[0] for c in calls] == [0, 1, 2]
    # Temperature ladder applied for diversity (RESEARCH §4: 0.4–0.7)
    assert [c[1] for c in calls] == [0.4, 0.55, 0.7]
    assert r.value == 12 and r.confidence == "high" and not r.needs_review
    assert r.votes == [12.0, 12.0, 12.0]
    assert r.method == "vote_median"


def test_run_ensemble_disagreement_escalates_to_exactly_five_calls():
    values = [10, 30, 90, 30, 30]  # first 3 disagree → +2 → majority at 30
    calls = []

    def stub(sample_index):
        calls.append(sample_index)
        return {"value": values[sample_index], "_cost_usd": 0.01}

    r = run_ensemble(stub, probe_key="escalate5")
    assert len(calls) == 5
    assert r.value == 30 and r.confidence == "medium" and not r.needs_review
    # Full 5-sample vote vector persisted in the result
    assert r.votes == [10.0, 30.0, 90.0, 30.0, 30.0]
    assert r.n_samples == 5


def test_run_ensemble_no_escalation_when_disabled():
    calls = []

    def stub(sample_index):
        calls.append(sample_index)
        return {"value": [10, 30, 90][sample_index], "_cost_usd": 0.01}

    r = run_ensemble(stub, escalate_on_disagreement=False, probe_key="noesc")
    assert len(calls) == 3
    assert r.needs_review is True  # disagreement flagged, never silent


def test_run_ensemble_tiled_member_joins_vote():
    def stub(sample_index):
        return {"value": 100, "_cost_usd": 0.01}

    r = run_ensemble(
        stub, unit_kind="EA", extra_members=[102.0], probe_key="tiledmember"
    )
    assert r.method == "tiled+vote"
    assert 102.0 in r.votes and len(r.votes) == 4
    assert r.needs_review is False  # majority of whole-sheet samples wins


# ── 3. Tiled counting dedup ──────────────────────────────────────────────────


def test_tiled_dedup_suppresses_overlap_duplicates_exactly():
    # 200x100 image, 2x1 grid, 20% overlap → tile rects (0..110) and
    # (90..200); overlap band x∈[90,110]. One symbol sits in the band and is
    # detected by BOTH tiles; two more are unique. Deduped total must be 3.
    img = Image.new("RGB", (200, 100), "white")
    seen_tiles = []

    def stub(image, tile_index, tile_grid, tile_rect):
        seen_tiles.append((tile_index, tile_grid, tuple(round(v) for v in tile_rect)))
        if tile_index == 0:
            # cell 2 → x≈27.5 (unique); cell 9 → x≈104.5 (in overlap band)
            return {"detections": [{"cell": [2, 5]}, {"cell": [9, 5]}], "_cost_usd": 0.01}
        # cell 0 → x≈95.5 (same band symbol, seen again); cell 5 → x≈150.5
        return {"detections": [{"cell": [0, 5]}, {"cell": [5, 5]}], "_cost_usd": 0.01}

    guard = BudgetGuard(1.0)
    total = run_tiled_count(img, (2, 1), stub, budget=guard, overlap_frac=0.2)
    assert total == 3.0
    assert seen_tiles[0][2] == (0, 0, 110, 100)  # 20% overlap expansion
    assert seen_tiles[1][2] == (90, 0, 200, 100)
    assert abs(guard.spent_usd - 0.02) < 1e-9  # every tile call charged


def test_tiled_count_no_dedup_outside_overlap_band():
    # Two nearby detections in the SAME tile / outside any overlap band are
    # distinct objects — NMS must not merge them.
    img = Image.new("RGB", (200, 100), "white")

    def stub(image, tile_index):
        if tile_index == 0:
            return {"detections": [{"cell": [2, 5]}, {"cell": [3, 5]}], "_cost_usd": 0.0}
        return {"detections": [], "_cost_usd": 0.0}

    assert run_tiled_count(img, (2, 1), stub, overlap_frac=0.2) == 2.0


def test_tiled_count_positionless_fallback_sums_counts():
    img = Image.new("RGB", (200, 100), "white")

    def stub(image, tile_index):
        return {"count_estimate": 4, "_cost_usd": 0.0}

    # No positions → no dedup possible; plain per-tile sum
    assert run_tiled_count(img, (2, 1), stub) == 8.0


# ── 4. Budget guard ──────────────────────────────────────────────────────────


def test_budget_guard_refuses_charge_past_cap():
    g = BudgetGuard(10.0)
    g.charge(4.0)
    g.charge(4.0)
    with pytest.raises(BudgetExceeded) as exc:
        g.charge(4.0)
    # Refused charge NOT accumulated: exactly 2 calls charged
    assert g.spent_usd == 8.0
    assert abs(g.remaining - 2.0) < 1e-9
    assert exc.value.spent_usd == 8.0
    assert exc.value.cap_usd == 10.0
    assert exc.value.attempted_usd == 4.0


def test_run_ensemble_budget_exhausted_flags_never_truncates_silently():
    guard = BudgetGuard(10.0)
    calls = []

    def stub(sample_index):
        calls.append(sample_index)
        return {"value": 12, "_cost_usd": 4.0}  # $4/call against a $10 cap

    r = run_ensemble(stub, budget=guard, probe_key="budget")
    # Third call's charge raises → sampling stops
    assert len(calls) == 3
    # Exactly 2 calls charged (the refused third is not on the ledger)
    assert guard.spent_usd == 8.0
    assert r.needs_review is True
    assert r.reason == "budget_exhausted"
    assert r.confidence == "low"
    assert len(r.votes) == 2  # only paid-for samples are voted
    assert r.value == 12  # current-best still reported for the reviewer


def test_run_ensemble_skips_all_calls_when_budget_already_exhausted():
    guard = BudgetGuard(0.0)

    def stub(sample_index):  # pragma: no cover - must never run
        raise AssertionError("no API call may be made on an exhausted budget")

    r = run_ensemble(stub, budget=guard, probe_key="preexhausted")
    assert r.value is None
    assert r.needs_review is True
    assert r.reason == "budget_exhausted"


def test_run_tiled_count_propagates_budget_exceeded():
    img = Image.new("RGB", (200, 100), "white")
    guard = BudgetGuard(0.01)

    def stub(image, tile_index):
        return {"detections": [{"cell": [2, 5]}], "_cost_usd": 0.01}

    with pytest.raises(BudgetExceeded):
        run_tiled_count(img, (2, 1), stub, budget=guard)


# ── 5. Temperature-ignore fallback (RESEARCH open question 3) ────────────────


def test_temperature_ignored_switches_to_prompt_variation():
    kwargs_seen = []

    def stub(sample_index, temperature, prompt_variation):
        kwargs_seen.append((sample_index, temperature, prompt_variation))
        # Identical payload regardless of temperature → model ignores it
        return {"value": 7, "_cost_usd": 0.0}

    r = run_ensemble(stub, probe_key="probe-ignore")
    # First two samples probe with t-variation only (prompt_variation=0)
    assert kwargs_seen[0] == (0, 0.4, 0)
    assert kwargs_seen[1] == (1, 0.55, 0)
    # Probe detects identical payloads → third sample varies the prompt
    assert kwargs_seen[2][2] == 2
    assert r.temperature_ignored is True


def test_temperature_honored_keeps_prompt_variation_zero():
    def stub(sample_index, prompt_variation):
        return {"value": 20 + sample_index, "_cost_usd": 0.0, "_pv": prompt_variation}

    kwargs_seen = []

    def wrapper(sample_index, temperature, prompt_variation):
        kwargs_seen.append(prompt_variation)
        return stub(sample_index, prompt_variation)

    run_ensemble(wrapper, probe_key="probe-honored")
    assert kwargs_seen == [0, 0, 0]


# ── Config + injection-pattern assertions ────────────────────────────────────


def test_ensemble_settings_reader():
    s = ensemble_settings()
    assert s["n"] == 3  # conftest-pinned ENSEMBLE_N
    assert s["budget_usd"] == 10.0  # conftest-pinned API_BUDGET_PER_RUN_USD


def test_no_direct_anthropic_client_usage_in_ensemble():
    # Acceptance criterion (21-11 Task 2): ALL API access goes through the
    # injected callable — ensemble.py must never touch the client directly.
    import bobbytailor.vision.ensemble as mod

    source = Path(mod.__file__).read_text()
    assert "client.messages" not in source
    assert "import anthropic" not in source
    assert "from anthropic" not in source


def test_ensemble_result_dataclass_contract():
    r = EnsembleResult(value=5.0, votes=[5.0], confidence="low",
                       needs_review=True, spread=0.0, n_samples=1)
    d = r.to_dict()
    assert d["value"] == 5.0 and d["method"] == "vote_median"
