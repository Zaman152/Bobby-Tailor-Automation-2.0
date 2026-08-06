"""THE Phase 24 determinism harness — V4-DET-05 as a detector. ZERO API.

**The requirement's literal words were not implemented, deliberately.** V4-DET-05
reads "same fixture N times asserts identical line items". ``ReplayAnalyzer``
resolves a SHA256 over ``(model, pass_type, prompt text, image count)`` and
returns that file's response verbatim — it is a *pure function of the key*.
Running one fixture N times is therefore identical **by construction** and would
detect none of the defects this phase exists to kill. Writing the requirement
verbatim would ship a gate that passes for having looked at nothing, which is
exactly what ``tests/test_phase23_acceptance.py`` rule 3 forbids.

What is implemented instead:

    Hold the geometry fixed. VARY the model's answers within schema-legal
    bounds. Assert the published take-off does not move.

Two fixture sets under ``tests/fixtures/replay/variant_a`` and ``variant_b``
carry labels reconstructed from the two saved paid Crow runs. Both drive the
SAME PDF through the SAME deterministic geometry. ``scripts/author_replay_
fixtures.py`` authored them offline and is the committed procedure for
re-authoring them when a prompt changes — every key here dies on the next
prompt edit, and a set nobody can regenerate is a trap for the next phase.

THREE RULES INHERITED FROM ``test_phase23_acceptance.py``
--------------------------------------------------------
1. Lock what SHIPPED, not what the plan predicted. The plan specified a
   ``(name, unit, quantity, measure_basis)`` tuple set. There is no
   ``measure_basis`` field anywhere in this codebase, and the full
   ``(name, unit, quantity)`` tuple set is measurably NOT invariant — a wall
   class with no printed-thickness match is still named by vision (24-02's
   documented, still-open residual). So this module asserts the invariance that
   HOLDS and asserts the residual that does not, by name. It never quietly
   drops a check.
2. Assert SETS, never a golden total. Every assertion here compares variant A
   with variant B. If both variants are wrong in the SAME way this gate
   correctly passes: it measures determinism, not accuracy, and conflating the
   two is what this phase exists to separate.
3. A check either ASSERTS or SKIPS. A missing fixture or a missing plan set
   skips with a named reason. ``ReplayAnalyzer`` raises ``KeyError`` on an
   unknown key by design — but the vector path swallows a failed pass to keep
   labels additive, so an un-hit fixture would otherwise degrade SILENTLY into
   a run with fewer names and a green gate. ``_ReplayProbe`` therefore records
   every miss and :func:`_require_no_fixture_drift` converts one into a skip.

WHAT THIS GATE DOES AND DOES NOT COVER — stated, not implied
------------------------------------------------------------
* **Ensembled passes are OUT of scope, explicitly.** After 24-08 a pass fans
  out to N samples that all carry the SAME request tuple, so a key-addressed
  replay source hands every sample the same fixture and the vote is unanimous by
  construction. The harness therefore pins the ensemble to ONE sample — the
  byte-identical single-shot path — and :func:`test_the_ensemble_is_pinned_to_
  one_sample_so_the_scope_is_honest` proves the pin is real rather than claimed.
  Voting behaviour is covered by ``tests/test_reliability_voting.py`` with
  scripted stubs that genuinely differ per sample.
* **The project naming-convention answer is FIXED across both variants**, and
  so is the naming-library variance (defect F3) it carries. That answer becomes
  the *next* request's label enum, so varying it varies the REQUEST — a
  different experiment, and one that would split the variants onto disjoint
  fixture keys. 24-05's per-project persistence is what stabilises it.

**The whole gate runs FREE.** No paid marker, no paid script name and no
credential appears anywhere in this module; :func:`test_the_whole_module_runs_
free` greps this file to prove it, and 24-10's acceptance gate greps it again.
"""
from __future__ import annotations

import json
import re
import sys
from collections import namedtuple
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scripts.author_replay_fixtures import (  # noqa: E402
    CROW_PDF,
    FIXTURE_ROOT,
    VARIANTS,
    run_project_offline,
)
from tests.replay_analyzer import ReplayAnalyzer  # noqa: E402

THIS_FILE = Path(__file__)

#: The candidate at the centre of this phase. The 56-EA cluster published as
#: `Bollard` (source: learned) in the 14:19 run and as `Dock Bumper`
#: (source: library) in the 18:13 run — one candidate, two names, nothing
#: deciding between them. It carries a RECORDED TEXT ABSENCE, so 24-07 excludes
#: it from the symbol request altogether and 24-04 routes it to the ledger.
#: Named by ID and never by its count: its quantity is read off the record the
#: producer wrote, never restated as a literal here.
FLIPPED_CANDIDATE_ID = "SYM-2"
FLIPPED_RUN_NAMES = ("bollard", "dock bumper")


# ─────────────────────────────────────────────────────────────────────────────
# Skips — loud and by name, never a silent pass
# ─────────────────────────────────────────────────────────────────────────────


def _require_plan_set():
    if not Path(CROW_PDF).exists():
        pytest.skip("the Crow plan set is not present in uploads/")


def _require_fixtures():
    for variant in VARIANTS:
        if not sorted((FIXTURE_ROOT / variant).glob("*.json")):
            pytest.skip(
                "no replay fixtures in tests/fixtures/replay/%s — author them "
                "with: python3 scripts/author_replay_fixtures.py" % variant
            )


def _require_no_fixture_drift(probe):
    """A request with no fixture SKIPS the gate. It can never pass.

    The vector path wraps each semantic/symbol pass in ``except Exception`` so a
    failed pass leaves labels absent rather than aborting the sheet. That is
    right for production and lethal for a gate: an un-hit fixture would produce
    a quieter run and a green comparison. So the miss is recorded at the seam
    and surfaced here.
    """
    if probe.misses:
        pytest.skip(
            "fixture drift: %d request(s) resolved to no fixture in %s (%s) — "
            "a prompt, schema or render changed. Re-author with: "
            "python3 scripts/author_replay_fixtures.py"
            % (len(probe.misses), probe.fixture_dir,
               ", ".join(sorted({m for m in probe.misses})[:4]))
        )


# ─────────────────────────────────────────────────────────────────────────────
# The replay seam, instrumented
# ─────────────────────────────────────────────────────────────────────────────


class _ReplayProbe:
    """``ReplayAnalyzer`` plus a hit/miss census.

    A gate must be able to prove it LOOKED at something. ``hits`` counts the
    fixtures actually consumed per key and ``misses`` records every request that
    resolved to no fixture at all.
    """

    def __init__(self, fixture_dir) -> None:
        self.fixture_dir = Path(fixture_dir)
        self._inner = ReplayAnalyzer(self.fixture_dir)
        self.hits: dict = {}
        self.misses: list = []

    def __call__(self, screenshot_path, sheet_name="", pass_type="measure",
                 model_override=None, sheet_type=None, user_hint=None,
                 output_schema=None, images=None):
        key = self._inner.key_for(
            sheet_name=sheet_name, pass_type=pass_type,
            model_override=model_override, sheet_type=sheet_type,
            user_hint=user_hint, output_schema=output_schema, images=images,
        )
        try:
            response = self._inner(
                screenshot_path, sheet_name=sheet_name, pass_type=pass_type,
                model_override=model_override, sheet_type=sheet_type,
                user_hint=user_hint, output_schema=output_schema, images=images,
            )
        except KeyError:
            self.misses.append("%s/%s" % (pass_type, key[:12]))
            raise
        self.hits[key] = self.hits.get(key, 0) + 1
        return response


# ─────────────────────────────────────────────────────────────────────────────
# THE comparison helper — used by the gate AND by the flip demonstration
# ─────────────────────────────────────────────────────────────────────────────

PublishedItemSets = namedtuple(
    "PublishedItemSets", "summary_names ledger_ids quantities calculated"
)


def _published_item_sets(report: dict) -> PublishedItemSets:
    """The four SETS a determinism claim may honestly be made about.

    Whole-blob comparison is deliberately not offered: a report carries
    timestamps, run folders and absolute paths and would differ for reasons that
    have nothing to do with determinism, producing a gate nobody can maintain.
    """
    summary_names = frozenset(
        (row.get("item") or "").strip()
        for row in report.get("takeoff_summary") or []
        if (row.get("item") or "").strip()
    )
    ledger_ids = frozenset(
        (rec.get("candidate_id") or "").strip()
        for rec in report.get("unnamed_geometry") or []
        if (rec.get("candidate_id") or "").strip()
    )
    calculated = frozenset(
        (
            (row.get("description") or "").strip(),
            (row.get("calculated_unit") or "").strip(),
            row.get("calculated_quantity"),
        )
        for row in report.get("calculated_takeoff") or []
    )
    # A multiset: two rows may legitimately carry the same number, and losing
    # that would hide a row appearing twice in one variant and once in the other.
    quantities = tuple(sorted(
        str(row.get("calculated_quantity"))
        for row in report.get("calculated_takeoff") or []
    ))
    return PublishedItemSets(summary_names, ledger_ids, quantities, calculated)


def _compare_published(a: PublishedItemSets, b: PublishedItemSets) -> list:
    """The differences between two variants' published take-offs.

    An empty list means the take-off did not move. THREE invariants are checked,
    and the ``calculated`` tuple set is deliberately NOT one of them — see
    :func:`test_the_residual_a_vision_named_wall_class_still_moves_with_its_label`,
    which asserts that residual by name rather than letting it hide here.

    This is the ONE comparison the gate makes.
    """
    diffs = []
    if a.summary_names != b.summary_names:
        diffs.append(
            "published item names moved: only-A=%s only-B=%s"
            % (sorted(a.summary_names - b.summary_names),
               sorted(b.summary_names - a.summary_names))
        )
    if a.ledger_ids != b.ledger_ids:
        diffs.append(
            "unnamed-geometry ledger moved — a candidate was named in one "
            "variant and ledgered in the other: only-A=%s only-B=%s"
            % (sorted(a.ledger_ids - b.ledger_ids),
               sorted(b.ledger_ids - a.ledger_ids))
        )
    if a.quantities != b.quantities:
        diffs.append(
            "a published QUANTITY moved when only the model's words moved: "
            "%d vs %d value(s)" % (len(a.quantities), len(b.quantities))
        )
    return diffs


# ─────────────────────────────────────────────────────────────────────────────
# The run — once per variant, shared by every test in the module
# ─────────────────────────────────────────────────────────────────────────────


def _report_for(variant: str, tmp_path) -> tuple:
    from bobbytailor.pipeline import reporter

    probe = _ReplayProbe(FIXTURE_ROOT / variant)
    extracted, estimates = run_project_offline(probe)

    out_dir = tmp_path / variant
    out_dir.mkdir(parents=True, exist_ok=True)
    prior = reporter.OUTPUT_DIR
    reporter.OUTPUT_DIR = str(out_dir)
    try:
        report = reporter.generate_report(
            "determinism-harness", extracted, estimates,
        )
    finally:
        reporter.OUTPUT_DIR = prior
    return report, probe


@pytest.fixture(scope="module")
def differential(tmp_path_factory):
    """Run the pipeline once per variant over the same PDF and geometry."""
    _require_plan_set()
    _require_fixtures()
    tmp_path = tmp_path_factory.mktemp("determinism")
    out = {}
    for variant in VARIANTS:
        report, probe = _report_for(variant, tmp_path)
        _require_no_fixture_drift(probe)
        out[variant] = (report, probe)
    return out


def _sets(differential, variant) -> PublishedItemSets:
    return _published_item_sets(differential[variant][0])


# ─────────────────────────────────────────────────────────────────────────────
# Non-vacuity: the gate must be shown to have LOOKED at something
# ─────────────────────────────────────────────────────────────────────────────


def test_every_committed_fixture_was_actually_consumed(differential):
    """A fixture nobody requests proves nothing (24-07's sequencing warning).

    Keys hash the prompt text, the schema-bearing model routing AND the image
    count — 24-07 changed all three — so a set authored against an earlier tree
    would sit on disk unread while this gate compared two runs that asked
    nothing. Presence is not consumption; the hit census is.
    """
    for variant in VARIANTS:
        _report, probe = differential[variant]
        on_disk = {p.stem for p in (FIXTURE_ROOT / variant).glob("*.json")}
        consumed = {k for k, n in probe.hits.items() if n > 0}
        assert on_disk, "no fixtures on disk for %s" % variant
        assert consumed == on_disk, (
            "%s: fixtures on disk but never requested: %s (requested but "
            "absent: %s)" % (variant, sorted(on_disk - consumed),
                             sorted(consumed - on_disk))
        )
        assert sum(probe.hits.values()) >= len(on_disk)


def test_the_two_variants_really_do_carry_different_answers():
    """The premise. Without this the differential could be one file twice."""
    _require_fixtures()
    a_dir, b_dir = (FIXTURE_ROOT / v for v in VARIANTS)
    names_a = sorted(p.name for p in a_dir.glob("*.json"))
    names_b = sorted(p.name for p in b_dir.glob("*.json"))
    assert names_a == names_b, (
        "the two variants must address the SAME keys — same prompts, same "
        "geometry, different answers"
    )
    differing = [
        n for n in names_a
        if json.loads((a_dir / n).read_text(encoding="utf-8"))["response"]
        != json.loads((b_dir / n).read_text(encoding="utf-8"))["response"]
    ]
    assert differing, "both variants carry identical answers — nothing varies"


def test_every_fixture_records_which_saved_run_it_came_from():
    """Recorded-from-reality must be tellable from invented (T-24-40)."""
    _require_fixtures()
    for variant in VARIANTS:
        for path in sorted((FIXTURE_ROOT / variant).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            prov = payload.get("provenance")
            assert isinstance(prov, dict), "%s carries no provenance" % path.name
            assert prov.get("api_calls_made") == 0
            assert prov.get("record_mode_used") is False
            # Either it names the run it was reconstructed from, or it states
            # the gap in words. Silence is not an option.
            assert prov.get("reconstructed_from_run") or prov.get("gap"), (
                "%s/%s states neither a source run nor a documented gap"
                % (variant, path.name)
            )


def test_the_ensemble_is_pinned_to_one_sample_so_the_scope_is_honest(differential):
    """The scope claim in this module's docstring, made checkable.

    After 24-08 an ensembled pass issues N requests carrying the SAME replay
    key, so N samples would read one fixture and vote unanimously by
    construction. The harness pins N=1. If the pin ever stopped working, a pass
    would show more hits than request sites and this fails — the claim cannot
    rot into a comment.
    """
    for variant in VARIANTS:
        _report, probe = differential[variant]
        per_sheet = {
            key: n for key, n in probe.hits.items()
            if json.loads(
                (FIXTURE_ROOT / variant / ("%s.json" % key)).read_text(encoding="utf-8")
            )["request"]["pass_type"] in ("semantic", "symbol_gallery")
        }
        assert per_sheet, "no per-sheet vision pass ran in %s" % variant
        assert set(per_sheet.values()) == {1}, (
            "%s: a per-sheet pass was sampled more than once (%s) — the "
            "ensemble pin is not in effect and the vote would be unanimous by "
            "construction" % (variant, per_sheet)
        )


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE
# ─────────────────────────────────────────────────────────────────────────────


def test_two_schema_legal_answer_sets_publish_the_same_takeoff(differential):
    """THE gate. Same PDF, same geometry, different answers, same take-off.

    Set equality BETWEEN THE VARIANTS — never against a golden figure.
    """
    diffs = _compare_published(
        _sets(differential, "variant_a"), _sets(differential, "variant_b")
    )
    assert diffs == [], "the published take-off moved with the model's words:\n" + "\n".join(diffs)


def test_the_unnamed_geometry_ledger_carries_the_same_candidates(differential):
    """A candidate must not be named in one variant and ledgered in the other.

    That is the same defect as a naming flip, wearing a different hat: the row
    simply disappears from the take-off instead of changing its name.
    """
    a, b = _sets(differential, "variant_a"), _sets(differential, "variant_b")
    assert a.ledger_ids, "the ledger is empty — this sheet measures unnamed geometry"
    assert a.ledger_ids == b.ledger_ids


def test_no_published_quantity_moves_when_only_the_labels_move(differential):
    """Geometry measures; vision only labels. A word may never move a number."""
    a, b = _sets(differential, "variant_a"), _sets(differential, "variant_b")
    assert a.quantities, "nothing was published — the gate would be vacuous"
    assert a.quantities == b.quantities


def test_the_candidate_that_flipped_between_the_paid_runs_is_named_in_neither(
    differential,
):
    """The phase's central defect, asserted end to end.

    The 56-EA cluster published as one name in the 14:19 run and another in the
    18:13 run. It carries a recorded text absence, so it is excluded from the
    symbol request entirely (24-07) and ledgered rather than named (24-04). It
    must be ledgered in BOTH variants, and NEITHER of the two names the paid
    runs gave it may appear in either published take-off.
    """
    for variant in VARIANTS:
        report = differential[variant][0]
        sets_ = _published_item_sets(report)
        assert FLIPPED_CANDIDATE_ID in sets_.ledger_ids, (
            "%s: %s is not in the unnamed-geometry ledger"
            % (variant, FLIPPED_CANDIDATE_ID)
        )
        published = {n.lower() for n in sets_.summary_names}
        for flipped in FLIPPED_RUN_NAMES:
            assert not any(flipped in name for name in published), (
                "%s: %r reached the published take-off — the candidate the two "
                "paid runs disagreed about is being named again"
                % (variant, flipped)
            )
        # Read the quantity off the record the producer wrote; never restate it.
        record = next(
            rec for rec in report["unnamed_geometry"]
            if rec.get("candidate_id") == FLIPPED_CANDIDATE_ID
        )
        assert record.get("quantity") and record.get("unit"), (
            "the ledger row states the candidate was MEASURED and not named; a "
            "row with no quantity would read as 'this does not exist'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# THE RESIDUAL — asserted by name, never quietly excluded
# ─────────────────────────────────────────────────────────────────────────────


def _varied_labels() -> set:
    """The labels the two variants deliberately swapped, read off the fixtures."""
    labels = set()
    for variant in VARIANTS:
        for path in (FIXTURE_ROOT / variant).glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["request"]["pass_type"] != "semantic":
                continue
            for entry in payload["response"].get("wall_classes") or []:
                if entry.get("label"):
                    labels.add(entry["label"].strip())
    return labels


def test_the_residual_a_vision_named_wall_class_still_moves_with_its_label(
    differential,
):
    """The invariance claim's boundary, stated as an assertion rather than a note.

    24-02 inverted the precedence so a printed-thickness match outranks a vision
    label — but a wall class with NO thickness match is still named by vision,
    and its own summary records that residual as deliberately unclosed. This
    harness measures it end to end: swapping the two observed wall-class labels
    between the variants swaps which class publishes under which name.

    The row's NAME set and its QUANTITY set each stay equal; only the PAIRING
    moves, and every moved row's name is one of the labels the fixtures swapped.
    Nothing else drifts with it.

    **When 24-02's residual is finally closed this test will FAIL, and that
    failure is the signal the fix worked.** Update it deliberately; do not
    "repair" it by deleting it.
    """
    a, b = _sets(differential, "variant_a"), _sets(differential, "variant_b")
    only_a, only_b = a.calculated - b.calculated, b.calculated - a.calculated
    assert only_a and only_b, (
        "the calculated take-off no longer moves with the wall-class label — "
        "24-02's residual may be closed. Verify, then update this test."
    )
    varied = _varied_labels()
    assert varied, "no wall-class label was varied — the residual is untested"
    moved_names = {name for name, _unit, _qty in only_a | only_b}
    assert moved_names <= varied, (
        "the drift is NOT confined to the labels the variants swapped: %s"
        % sorted(moved_names - varied)
    )
    assert {n for n, _u, _q in only_a} == {n for n, _u, _q in only_b}, (
        "a NAME appeared in one variant and not the other — that is beyond the "
        "documented residual"
    )
    assert sorted(q for _n, _u, q in only_a) == sorted(q for _n, _u, q in only_b), (
        "a QUANTITY moved, not merely its label — beyond the documented residual"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A missing fixture SKIPS. It can never pass.
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_fixture_skips_and_never_passes(tmp_path):
    """Point the seam at an empty directory and require a SKIP, not a green run.

    ``ReplayAnalyzer``'s ``KeyError`` on an unknown key is kept intact — a
    prompt drift must stay loud — and it is converted to a skip here at the TEST
    level, so a fresh checkout without fixtures reports "no fixtures" rather
    than a false green.
    """
    probe = _ReplayProbe(tmp_path / "empty")
    with pytest.raises(KeyError):
        probe("unused.png", sheet_name="A-101", pass_type="semantic",
              sheet_type="floor_plan", output_schema={"type": "object"})
    assert probe.misses, "a miss was not recorded — drift would go unnoticed"
    assert probe.hits == {}

    with pytest.raises(pytest.skip.Exception) as excinfo:
        _require_no_fixture_drift(probe)
    assert "fixture drift" in str(excinfo.value)

    # And a probe that hit everything does NOT skip.
    clean = _ReplayProbe(tmp_path / "empty")
    _require_no_fixture_drift(clean)


def test_an_absent_plan_set_skips_rather_than_passing(monkeypatch):
    """Rule 3, for the other fixture this gate depends on."""
    import tests.test_determinism_harness as module

    monkeypatch.setattr(module, "CROW_PDF", "/nonexistent/plans.pdf")
    with pytest.raises(pytest.skip.Exception) as excinfo:
        module._require_plan_set()
    assert "plan set" in str(excinfo.value)


# ─────────────────────────────────────────────────────────────────────────────
# The module's own contract
# ─────────────────────────────────────────────────────────────────────────────


def test_the_whole_module_runs_free():
    """No paid marker, no paid script name, no credential, anywhere in this file."""
    text = THIS_FILE.read_text(encoding="utf-8")
    # Assembled from halves on purpose. The check is a substring scan over this
    # very file, and spelling the markers out here would make the module fail
    # its own audit — the same self-defeating check 24-08 hit with its
    # temperature grep. A test my own source can trip is not a test.
    forbidden = (
        "pytest.mark." + "golden",
        "accuracy" + "_gate",
        "vision_only" + "_benchmark",
        "golden" + "_convergence",
        "ANTHROPIC" + "_API_KEY",
        "REPLAY" + "_RECORD",
    )
    hits = [token for token in forbidden if token in text]
    assert hits == [], "paid-gate markers in a free module: %s" % hits


def test_record_mode_is_off_on_every_analyzer_this_module_builds(tmp_path):
    """Fixture authoring and fixture replay both run with recording DISABLED.

    Record mode wraps the REAL analyzer and is developer-invoked only; a gate
    that could enable it is a gate that could spend money (T-24-44).
    """
    assert ReplayAnalyzer(tmp_path).record is False
    assert _ReplayProbe(tmp_path)._inner.record is False
    author_src = (ROOT / "scripts" / "author_replay_fixtures.py").read_text(
        encoding="utf-8"
    )
    assert "record=True" not in author_src


def test_this_module_asserts_no_golden_total():
    """Rule 2. Every assertion here compares variant A with variant B."""
    text = THIS_FILE.read_text(encoding="utf-8")
    # The four figures this project has already been burned by tuning toward.
    assert not re.search(r"==\s*(28|56|132|136)\b", text)
