"""Offline tests for categorical majority-vote reliability (Parts B + C, and 24-08).

No API calls anywhere — the analyzer is a stub callable that yields a scripted
sequence of label lists. Pins:
- ``_voted_structured_vision_call`` majority-votes the per-candidate labels,
  makes N analyzer calls, and stops early when the BudgetGuard is exhausted;
- ``majority_vote_objects`` keeps objects present in a strict majority of
  vocabulary samples and drops the rest;
- N==1 reproduces single-shot behaviour exactly (regression guard);
- (24-08) ``_run_pass`` votes the IDENTIFICATION pass types on row identity,
  charges every sample, and is byte-identical to the single-shot path at N==1;
- (24-08) every analyzer call site is either voted or explicitly exempted.
"""
import json
from pathlib import Path

import pytest

from bobbytailor.pipeline import takeoff_pipeline as tp
from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline
from bobbytailor.vision.ensemble import BudgetExceeded, BudgetGuard
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


# ── 24-08 Part A: the corrected F9 diagnosis ──────────────────────────────────
#
# THE CORRECTION, in plain words, recorded here because a test is the only
# place a correction cannot quietly rot:
#
# 24-RESEARCH section 7.2 attributed defect F9 — `raw_line_items` swinging from
# 184 in the first saved paid run to 64 in the second — to `_run_pass` being
# un-ensembled, i.e. to single-shot nondeterminism. Its own Assumptions Log
# entry A1 recorded the competing risk (that the swing was budget truncation
# instead) and prescribed the mitigation: compare run 2's truncation record
# against the missing rows BEFORE committing to the diagnosis.
#
# That comparison was performed, free, straight from the two saved artifacts,
# and it falsifies the research's attribution. Run 2 ran under a budget cap two
# and a half times SMALLER than run 1's, reached essentially all of it, spent
# less than half as much on sheet-attributed work, and invoked one model class
# where run 1 invoked three. Budget — not sampling — is the dominant
# explanation of the swing. A1's stated risk is the actual situation.
#
# Two consequences this phase carries:
#   1. Plan 24-08 does NOT stand on F9. F9 is confounded and cannot support a
#      conclusion either way. 24-08 stands on V4-DET-04's own justification:
#      `_run_pass` is the one un-ensembled IDENTIFICATION path in plans-only
#      mode, and an un-voted identification pass can flip between runs. That is
#      true regardless of what caused F9, and it is sufficient on its own.
#   2. Fanning a pass out to N samples costs N times as much. Run 2 already
#      reached ~all of its cap while un-ensembled, so the cost pairing with
#      plan 24-05's vocabulary persistence is LOAD-BEARING, not a nicety: the
#      project-level passes 24-05 removes from a repeat run are what this
#      fan-out is allowed to consume.
#
# ONE CAVEAT, recorded honestly: a secondary detail in the research (a count of
# door-schedule rows going 7 -> 0 between the runs) did NOT reproduce under an
# independent count during planning. It is therefore NOT relied on here. This
# test asserts only the budget and cost RELATIONS, which are unambiguous in the
# artifacts.
#
# The assertions below are deliberately RELATIONS between the two runs, never
# literal dollar figures. A literal would pin a number nobody may adjust and
# would tell a future reader nothing about why. `.planning/paid-run-evidence/`
# is irreplaceable paid evidence and is READ-ONLY for this phase.

_PAID_RUN_EVIDENCE = Path(__file__).resolve().parent.parent / ".planning" / "paid-run-evidence"
_F9_RUN_1 = "VisionOnly_P23V_Crow_20260804_141952"   # the 184-line-item run
_F9_RUN_2 = "VisionOnly_P23V2_Crow_20260804_181352"  # the 64-line-item run


def _load_paid_run(dir_name: str) -> dict:
    """Read one saved paid run's takeoff.json, or SKIP with a named reason."""
    path = _PAID_RUN_EVIDENCE / dir_name / "takeoff.json"
    if not path.is_file():
        pytest.skip(
            "paid-run evidence absent: {} — the F9 correction cannot be "
            "checked without it".format(path)
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_f9_swing_is_explained_by_budget_not_sampling():
    """The two saved runs differ in BUDGET, which is what the swing tracks.

    Asserts the relations, not the figures:
      - run 2's cap was materially smaller than run 1's;
      - run 2 consumed essentially all of its cap while run 1 did not;
      - run 2's sheet-attributed API cost was materially smaller;
      - run 1 invoked more model classes than run 2.

    Together these say the two runs are not comparable on line-item count, so
    F9 cannot be attributed to single-shot nondeterminism. This test does NOT
    assert that the ensemble fixes anything — that is a different claim, proved
    offline by the voting tests below.
    """
    run1 = _load_paid_run(_F9_RUN_1)
    run2 = _load_paid_run(_F9_RUN_2)

    cap1 = float(run1["budget"]["cap_usd"])
    cap2 = float(run2["budget"]["cap_usd"])
    spent1 = float(run1["budget"]["spent_usd"])
    spent2 = float(run2["budget"]["spent_usd"])

    # 1. The caps are not the same order of generosity.
    assert cap2 * 2 < cap1, (
        "the F9 correction rests on run 2 having a materially smaller cap; "
        "caps were {} and {}".format(cap1, cap2)
    )

    # 2. Run 2 pressed against its cap; run 1 did not come close.
    util1 = spent1 / cap1
    util2 = spent2 / cap2
    assert util2 > 0.95, "run 2 did not consume ~all of its cap (util={})".format(util2)
    assert util1 < 0.75, "run 1 unexpectedly pressed its cap (util={})".format(util1)
    assert util2 > util1 * 1.5

    # 3. Less than half the sheet-attributed spend.
    cost1 = float(run1["api_usage"]["total_cost_usd"])
    cost2 = float(run2["api_usage"]["total_cost_usd"])
    assert cost2 * 2 < cost1

    # 4. Fewer model classes invoked — a further way the runs are not peers.
    models1 = run1["api_usage"]["models_used"]
    models2 = run2["api_usage"]["models_used"]
    assert sum(models1.values()) > sum(models2.values())

    # 5. The swing the research attributed to sampling is real — and sits on
    #    top of every confound above. Stated as inequality, never as counts.
    assert len(run1["raw_line_items"]) != len(run2["raw_line_items"])


# ── 24-08 Part B: _run_pass votes the IDENTIFICATION passes on row identity ───
#
# Scripted stubs only. The determinism property these pin is provable offline;
# measuring it live would cost real money and is not autonomously authorised.

_BOLLARDS = {"ITEM": "Bollards", "QTY": "24", "UNIT": "EA"}
_COLUMNS = {"ITEM": "Columns", "QTY": "12", "UNIT": "EA"}
_LADDER = {"ITEM": "Ladder", "QTY": "1", "UNIT": "EA"}


def _legend(rows):
    """One QUANTITY TAKEOFF LEGEND table carrying *rows*, as the pass returns it."""
    return [{
        "name": "QUANTITY TAKEOFF LEGEND",
        "table_purpose": "takeoff_legend",
        "use_for_takeoff": True,
        "columns": ["ITEM", "QTY", "UNIT"],
        "rows": [dict(r) for r in rows],
    }]


def _make_pass_analyzer(scripts, cost_usd=0.0):
    """Stub with ``_run_pass``'s analyzer signature, returning ``scripts[i]``.

    ``scripts[i]`` is the ``schedules`` list for the i-th call; the last script
    repeats once exhausted. Records call count and the image path each call was
    handed on ``analyzer.state``.
    """
    state = {"i": 0, "images": []}

    def analyzer(image_path, sheet_name="", pass_type="schedule",
                 model_override=None, sheet_type=None, user_hint=None, **kwargs):
        idx = min(state["i"], len(scripts) - 1)
        payload = scripts[idx]
        state["i"] += 1
        state["images"].append(image_path)
        return {
            "schedules": json.loads(json.dumps(payload)),
            "_cost_usd": cost_usd,
            "_tokens_in": 1,
            "_tokens_out": 1,
            "_model_used": "stub",
        }

    analyzer.state = state
    return analyzer


@pytest.fixture
def pin_ensemble_n(monkeypatch):
    """Pin the ensemble size `_run_pass` reads, independent of env config."""
    def _pin(n):
        monkeypatch.setattr(
            tp, "ensemble_settings", lambda: {"n": n, "budget_usd": 10.0}
        )
    return _pin


def test_run_pass_voted_at_n1_is_byte_identical_to_single_shot(pin_ensemble_n):
    """N==1 returns the raw analyzer dict, untouched — no vote metadata at all."""
    pin_ensemble_n(1)
    analyzer = _make_pass_analyzer([_legend([_BOLLARDS, _COLUMNS])])
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = pipeline._run_pass("img.png", "A-101", "schedule", None)

    assert analyzer.state["i"] == 1
    assert res == {
        "schedules": _legend([_BOLLARDS, _COLUMNS]),
        "_cost_usd": 0.0,
        "_tokens_in": 1,
        "_tokens_out": 1,
        "_model_used": "stub",
    }
    assert "_voted" not in res
    assert "_vote_samples" not in res


def test_run_pass_voted_identical_samples_equal_any_one_sample(pin_ensemble_n):
    """N>1 with agreeing reads yields one sample's answer, plus vote metadata."""
    pin_ensemble_n(3)
    one = _legend([_BOLLARDS, _COLUMNS])
    analyzer = _make_pass_analyzer([one, one, one])
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = pipeline._run_pass("img.png", "A-101", "schedule", None)

    assert analyzer.state["i"] == 3
    assert res["schedules"] == _legend([_BOLLARDS, _COLUMNS])
    assert res["_voted"] is True
    assert res["_vote_samples"] == 3


def test_run_pass_voted_majority_row_survives_minority_row_dropped(pin_ensemble_n):
    """A row in 2 of 3 reads survives; a row in 1 of 3 does not.

    The minority row is in the FIRST sample deliberately: a single-shot
    `_run_pass` would publish it, so this test cannot pass by coincidence if
    the voting is ever disabled.
    """
    pin_ensemble_n(3)
    analyzer = _make_pass_analyzer([
        _legend([_BOLLARDS, _COLUMNS, _LADDER]),
        _legend([_BOLLARDS, _COLUMNS]),
        _legend([_BOLLARDS]),
    ])
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = pipeline._run_pass("img.png", "A-101", "legend", None)

    items = [r["ITEM"] for r in res["schedules"][0]["rows"]]
    assert items == ["Bollards", "Columns"]      # Ladder (1 of 3) dropped


def test_run_pass_voted_a_tie_drops_the_row(pin_ensemble_n):
    """An exact split is not a majority — flag-don't-guess drops the row."""
    pin_ensemble_n(4)
    analyzer = _make_pass_analyzer([
        _legend([_BOLLARDS, _COLUMNS]),
        _legend([_BOLLARDS, _COLUMNS]),
        _legend([_BOLLARDS]),
        _legend([_BOLLARDS]),
    ])
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = pipeline._run_pass("img.png", "A-101", "legend", None)

    items = [r["ITEM"] for r in res["schedules"][0]["rows"]]
    assert items == ["Bollards"]                 # Columns 2-of-4 is a TIE


def test_run_pass_voted_folds_two_spellings_of_one_row_into_one(pin_ensemble_n):
    """Row identity is the AGGREGATOR's fold, so `Bollard` and `Bollards` are one row.

    The LOSING spelling is in the first sample deliberately, so a single-shot
    `_run_pass` would publish `Bollard` and this test cannot pass by coincidence.
    """
    pin_ensemble_n(3)
    singular = {"ITEM": "Bollard", "QTY": "24", "UNIT": "EA"}
    analyzer = _make_pass_analyzer([
        _legend([singular]),
        _legend([_BOLLARDS]),
        _legend([_BOLLARDS]),
    ])
    pipeline = TakeoffPipeline(analyzer=analyzer)

    res = pipeline._run_pass("img.png", "A-101", "legend", None)

    rows = res["schedules"][0]["rows"]
    assert len(rows) == 1                        # one row, not two spellings
    assert rows[0]["ITEM"] == "Bollards"         # the plurality spelling


def test_run_pass_voted_never_synthesises_a_quantity_no_sample_returned():
    """The published row is VERBATIM one sample's — never an average or a blend."""
    disagreeing = {"ITEM": "Bollards", "QTY": "26", "UNIT": "EA"}
    samples = [
        {"schedules": _legend([_BOLLARDS])},
        {"schedules": _legend([_BOLLARDS])},
        {"schedules": _legend([disagreeing])},
    ]

    out = tp._vote_schedule_rows(samples)

    quantities = [r["QTY"] for r in out[0]["rows"]]
    assert quantities == ["24"]                  # the plurality READ
    assert "25" not in quantities                # never a computed middle


def test_run_pass_voted_only_the_identification_pass_types(pin_ensemble_n):
    """count / measure / extraction stay single-shot — quantities are not voted."""
    pin_ensemble_n(3)
    for pass_type in ("count", "measure", "extraction"):
        analyzer = _make_pass_analyzer([_legend([_BOLLARDS])])
        pipeline = TakeoffPipeline(analyzer=analyzer)

        res = pipeline._run_pass("img.png", "A-101", pass_type, None)

        assert analyzer.state["i"] == 1, pass_type
        assert "_voted" not in res, pass_type


def test_run_pass_budget_charges_every_sample(pin_ensemble_n):
    """Each of the N samples is charged through the guard, not just the first."""
    pin_ensemble_n(3)
    analyzer = _make_pass_analyzer([_legend([_BOLLARDS])], cost_usd=0.10)
    pipeline = TakeoffPipeline(analyzer=analyzer)
    guard = BudgetGuard(10.0)

    pipeline._run_pass("img.png", "A-101", "schedule", None, budget=guard)

    assert analyzer.state["i"] == 3
    assert guard.spent_usd == pytest.approx(0.30)


def test_run_pass_budget_exhausted_partway_votes_over_the_paid_samples(pin_ensemble_n):
    """Room for two of three samples: sampling stops and the count is recorded."""
    pin_ensemble_n(3)
    analyzer = _make_pass_analyzer([
        _legend([_BOLLARDS, _COLUMNS]),
        _legend([_BOLLARDS, _COLUMNS]),
        _legend([_LADDER]),
    ], cost_usd=1.0)
    pipeline = TakeoffPipeline(analyzer=analyzer)
    guard = BudgetGuard(2.0)                     # exactly two $1.00 samples

    res = pipeline._run_pass("img.png", "A-101", "schedule", None, budget=guard)

    assert analyzer.state["i"] == 2              # stopped, never a third
    assert res["_vote_samples"] == 2             # the partial is DECLARED
    assert guard.spent_usd == pytest.approx(2.0)
    items = [r["ITEM"] for r in res["schedules"][0]["rows"]]
    assert items == ["Bollards", "Columns"]


def test_run_pass_budget_declines_an_extra_sample_it_cannot_afford(pin_ensemble_n):
    """No headroom for sample 2 → it is never issued, so no charge is refused.

    A REFUSED charge means the vendor was paid for a call whose result is then
    discarded. Declining the extra sample up front is strictly cheaper, and it
    cannot affect the first sample, which is always attempted.
    """
    pin_ensemble_n(3)
    analyzer = _make_pass_analyzer([_legend([_BOLLARDS])], cost_usd=1.0)
    pipeline = TakeoffPipeline(analyzer=analyzer)
    guard = BudgetGuard(1.5)                     # room for one sample, not two

    res = pipeline._run_pass("img.png", "A-101", "schedule", None, budget=guard)

    assert analyzer.state["i"] == 1
    assert guard.refused_charges == 0            # nothing paid for and binned
    assert res["_vote_samples"] == 1             # a one-sample read, declared
    assert res["schedules"] == _legend([_BOLLARDS])   # returned UNFOLDED


def test_run_pass_budget_no_paid_sample_raises_rather_than_returning_empty(pin_ensemble_n):
    """A first charge the guard refuses surfaces BudgetExceeded, never {}."""
    pin_ensemble_n(3)
    analyzer = _make_pass_analyzer([_legend([_BOLLARDS])], cost_usd=1.0)
    pipeline = TakeoffPipeline(analyzer=analyzer)
    guard = BudgetGuard(0.5)                     # cannot afford even one

    with pytest.raises(BudgetExceeded):
        pipeline._run_pass("img.png", "A-101", "schedule", None, budget=guard)

    assert analyzer.state["i"] == 1
    assert guard.refused_charges == 1            # the refusal is on the record


def test_run_pass_budget_already_exhausted_raises_before_any_call(pin_ensemble_n):
    """The pre-24-08 entry pre-check is unchanged by the ensemble wire-up."""
    pin_ensemble_n(3)
    analyzer = _make_pass_analyzer([_legend([_BOLLARDS])], cost_usd=1.0)
    pipeline = TakeoffPipeline(analyzer=analyzer)
    guard = BudgetGuard(0.0)

    with pytest.raises(BudgetExceeded):
        pipeline._run_pass("img.png", "A-101", "schedule", None, budget=guard)

    assert analyzer.state["i"] == 0


def test_run_pass_voted_cleans_up_every_sample_render(pin_ensemble_n, monkeypatch, tmp_path):
    """Each sample renders AND unlinks its own pass image — no temp leak (T-24-37)."""
    pin_ensemble_n(3)
    created = []

    def fake_render(pdf_path, page_index, scale):
        path = tmp_path / "render-{}.png".format(len(created))
        path.write_bytes(b"png")
        created.append(path)
        return str(path)

    monkeypatch.setattr(TakeoffPipeline, "_render_pdf_page", staticmethod(fake_render))
    analyzer = _make_pass_analyzer([_legend([_BOLLARDS])])
    pipeline = TakeoffPipeline(analyzer=analyzer)

    pipeline._run_pass(
        "img.png", "A-101", "legend", None, sheet_type="floor_plan",
        pdf_path="plan.pdf", page_index=0, render_scale=2.5,
    )

    assert len(created) == 3                     # one render per sample
    assert not [p for p in created if p.exists()]  # every one cleaned up
    assert analyzer.state["images"] == [str(p) for p in created]
