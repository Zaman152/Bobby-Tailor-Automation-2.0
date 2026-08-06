"""THE Phase 24 acceptance gate — the phase's five requirements, runnable.

Until this module existed, this phase's acceptance lived in ten SUMMARY
documents. A summary does not survive: it cannot be re-run, it cannot fail, and
six months from now nobody can tell which of its claims still hold. Phase 23
solved that by turning every acceptance criterion into a committed command, and
this module inherits its three rules verbatim, restated in this phase's terms.

1. **Lock what SHIPPED, not what the plans predicted.** This phase falsified two
   research literals at planning time and several more during execution. Where a
   criterion was NOT delivered as written, this module says so **by name** and
   asserts the contract that WAS — it never quietly drops a check. Every such
   correction is a committed assertion here, not a sentence in a document.
2. **Assert BANDS, POSITIONS and SETS — never a golden total.** Nothing here may
   assert equality against a bollard count, a column count, a warehouse
   footprint or a percentage of correctness. Tuning anything until a total
   matches is the coincidence trap this project has already paid days for. This
   phase is judged on determinism and on honesty; the offline proxy for
   correctness is rated LOW confidence by the research, and measuring the real
   thing needs a paid run that is not autonomously authorised.
3. **A check either ASSERTS or SKIPS.** No check may pass because its fixture is
   missing — that is a gate reporting success for having looked at nothing. The
   one exception is deliberate and inverted: the paid-run evidence check FAILS
   rather than skips, because a skip would let a future cleanup delete
   irreplaceable evidence unnoticed.

**Invoked, not restated.** Where an earlier plan already owns a check, this gate
calls that module's own assertion functions against a live subject rather than
growing a second, drifting copy of its literals — exactly as
``test_phase23_acceptance.py``'s check 1 invokes the four-plan-set gate. The
determinism differential (24-09) and the analyzer call-site census (24-08) are
both invoked here, not duplicated.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

THIS_FILE = Path(__file__)

UPLOADS = ROOT / "uploads"
CROW_PDF = UPLOADS / "Crow - Cass White Road-Plans.pdf"

#: The two saved paid Crow runs. $0.98 of real spend, the ONLY artifacts proving
#: the run-to-run naming variance this phase exists to kill, and the only seed
#: material for the determinism fixtures. READ-ONLY everywhere in this module.
PAID_RUN_EVIDENCE = ROOT / ".planning" / "paid-run-evidence"
PAID_RUNS = (
    "VisionOnly_P23V_Crow_20260804_141952",   # 14:19
    "VisionOnly_P23V2_Crow_20260804_181352",  # 18:13
)

#: Our own internal handle for a piece of measured geometry. A name of this
#: shape in a client artifact is the defect 24-04 abolished: the app inventing an
#: identifier and printing it as the name of a thing to price.
CANDIDATE_ID_RE = re.compile(r"^(?:SYM-\d+|ROOM-\d+|WALL-[A-Z]+\d+)$")


def _need_crow():
    """Skip — loudly and by name — rather than pass on an absent fixture."""
    if not CROW_PDF.is_file():
        pytest.skip("the Crow plan set is not present at %s" % CROW_PDF)


def _crow_page_zero_bundle():
    """The real Crow sheet A-101, through the deterministic half, no vision.

    The analyzer is a lambda that is never called: everything asserted off this
    bundle is computed before any model is consulted.
    """
    _need_crow()
    import fitz

    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(str(CROW_PDF))
    try:
        return pipe._deterministic_bundle(
            doc[0], doc, str(CROW_PDF), 0, "A-101", "floor_plan"
        )
    finally:
        doc.close()


# ═════════════════════════════════════════════════════════════════════════════
# The determinism differential, computed ONCE for the whole module.
#
# This IS plan 24-09's harness, driven through its own helpers rather than
# reimplemented: two label variants over one fixed geometry, the same PDF, the
# same prompts, the same fixture keys. Two full offline pipeline runs are the
# dominant cost of this module, so they are paid once and read by three checks.
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def differential(tmp_path_factory):
    """24-09's two-variant differential, in the shape its own tests expect."""
    import tests.test_determinism_harness as harness

    harness._require_plan_set()
    harness._require_fixtures()
    tmp_path = tmp_path_factory.mktemp("phase24-acceptance")
    out = {}
    for variant in harness.VARIANTS:
        report, probe = harness._report_for(variant, tmp_path)
        harness._require_no_fixture_drift(probe)
        out[variant] = (report, probe)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# V4-DET-01 — TEXT-ANCHORED LABELLING
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_det_01_no_identifier_is_a_name_and_every_one_that_left_is_ledgered(
    differential,
):
    """V4-DET-01 — both halves, in one check, so neither can be satisfied alone.

    Half one: no candidate identifier of ours appears as a name in the
    take-off summary or in the calculated take-off of a freshly fused Crow
    sheet — asserted here at the ARTIFACT level, over the two real reports the
    differential produced, which is where a client would have read them. Both
    saved paid runs shipped 27 such rows out of ~79.

    Half two: the candidates that left are PRESENT in the unnamed-geometry
    ledger, carrying their measured quantity. Deletion is the shortest path to
    "no identifiers in the report" and it silently loses hundreds of counted
    symbols — a deletion and a zero read identically to a client (INV-08).

    A check that asserted only half one would pass on a run that deleted
    everything; a check that asserted only half two would pass on a run that
    ledgered a candidate AND published it. Both are asserted together.
    """
    import tests.test_determinism_harness as harness

    for variant, (report, _probe) in sorted(differential.items()):
        published = [
            (row.get("item") or "").strip()
            for row in report.get("takeoff_summary") or []
        ] + [
            (row.get("description") or "").strip()
            for row in report.get("calculated_takeoff") or []
        ]
        assert [n for n in published if n], (
            "%s published NO rows at all — half one would then be satisfied by "
            "an empty report, which is the vacuous pass rule 3 forbids"
            % variant
        )
        leaked = sorted({n for n in published if CANDIDATE_ID_RE.match(n)})
        assert leaked == [], (
            "%s published our own handle as the name of a thing to price: %s"
            % (variant, leaked)
        )

        ledger = report.get("unnamed_geometry") or []
        assert ledger, (
            "%s ledgered NOTHING. Either this sheet became fully identifiable, "
            "or the gate is deleting rows instead of relocating them — which is "
            "indistinguishable from never measuring them." % variant
        )
        assert all(rec.get("quantity") is not None for rec in ledger), (
            "%s: a ledger record lost the quantity it exists to preserve"
            % variant
        )
        assert all(rec.get("reason") for rec in ledger), (
            "%s: a ledger record does not say WHY naming failed" % variant
        )
        # And nothing is in both places at once.
        ledgered = {(rec.get("candidate_id") or "").strip() for rec in ledger}
        # The pattern above is a real recogniser, not one that matches nothing:
        # every identifier the ledger holds is a shape it catches. Without this,
        # `leaked == []` could be satisfied by a regex that had rotted.
        unrecognised = sorted(c for c in ledgered if not CANDIDATE_ID_RE.match(c))
        assert unrecognised == [], (
            "%s ledgered candidate ids the leak pattern does not recognise, so "
            "the leak check would not have caught them being published: %s"
            % (variant, unrecognised)
        )
        assert ledgered & set(published) == set(), (
            "%s: a candidate was ledgered AND published: %s"
            % (variant, sorted(ledgered & set(published)))
        )

    # The exact set partition at the sheet level — invoked, not restated. This
    # is 24-04's own both-directions assertion: every nameable candidate is
    # EITHER published OR ledgered, exactly once, never both, never neither,
    # and nothing in the ledger that was never a candidate.
    import tests.test_fusion as fusion_tests

    fusion_tests.test_no_raw_candidate_ids_reach_the_takeoff()

    # Silence the unused-import warning honestly: the harness module is what
    # produced the reports above.
    assert harness.VARIANTS


def test_v4_det_01_the_marker_chip_renders_the_anchor_when_one_exists():
    """The chip gives the model the drawing's own words to READ.

    ``overlay._draw_marker`` drew ``label = candidate_id`` and nothing else — a
    box and an identifier, which is the symbol-conveyed condition the evidence
    base measures at the bottom of its range. A recorded ABSENCE still renders
    the bare ID with no placeholder and no empty separator, so a candidate the
    drawing does not name is not decorated into looking named.
    """
    import tests.test_vision_schemas as schema_tests

    schema_tests.test_anchor_chip_carries_the_candidate_id_and_its_anchor_text()
    schema_tests.test_anchor_chip_without_an_anchor_is_the_bare_id_with_no_placeholder()
    schema_tests.test_anchor_chip_reads_the_24_01_record_or_a_bare_string()


# ═════════════════════════════════════════════════════════════════════════════
# V4-DET-02 — DETERMINISTIC WALL CLASS
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_det_02_printed_thickness_outranks_the_model_and_the_triple_set_holds():
    """V4-DET-02 — the drawing's printed thickness names a wall class.

    A stochastic reading may corroborate it and may dissent — the dissent is
    published with the evidence that beat it — but it may never rename. Fed one
    fixed bundle and the two label sets the two saved paid runs actually
    produced, the emitted ``(name, quantity, unit)`` triple SET does not move.

    The SET is the assertion. No wall area appears anywhere in it: a golden
    total here would convert a determinism check into a check of correctness and
    create pressure to tune the class choice toward a number.

    The premise is guarded too — if the two saved runs ever stopped disagreeing,
    the differential would be comparing a label set with itself.
    """
    import tests.test_fusion as fusion_tests

    fusion_tests.test_thickness_outranks_vision()
    fusion_tests.test_an_agreeing_vision_label_corroborates_the_thickness_bind()
    fusion_tests.test_wall_label_disagreement_audited()
    fusion_tests.test_the_two_recorded_runs_really_did_differ_in_the_naming_layer()
    fusion_tests.test_wall_class_label_invariance()
    # A masonry object still cannot bind the dominant-LF perimeter class AFTER
    # the inversion — the one way promoting the deterministic rule could have
    # made things worse.
    fusion_tests.test_masonry_never_dominant()


# ═════════════════════════════════════════════════════════════════════════════
# V4-DET-03 — DEPENDENCY-ORDERED SCHEMA
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_det_03_the_vector_schema_is_dependency_ordered_and_carries_no_number():
    """V4-DET-03 — a topological gap is UNEXPRESSIBLE, not merely flagged.

    ``semantic_labeling_schema`` was FLAT: ``main_plan_region`` plus
    ``wall_class_labels``, with no expressible relationship between a room and
    the walls bounding it. It is now declared skeleton-first — wall classes,
    then regions, then rooms — and every ID a room names is an enum of a level
    defined ABOVE it, so a reference to something undefined cannot be written.

    The numeric ban is asserted PROGRAMMATICALLY, over every builder the module
    exposes, discovered by introspection rather than named one by one: that is
    what stops a schema added later from shipping uncovered, which is precisely
    how a quantity field would arrive.
    """
    from bobbytailor.vision.schemas import semantic_labeling_schema

    schema = semantic_labeling_schema(["R1", "R2"], ["W1", "W2"], ["ROOM-1"])
    order = list(schema["properties"].keys())
    assert order.index("wall_classes") < order.index("regions") < order.index("rooms")
    # `required` declares the same order — it is the generation order the model
    # follows, so the two may not disagree.
    assert schema["required"] == order

    room = schema["properties"]["rooms"]["items"]["properties"]
    assert room["region_id"]["enum"] == ["R1", "R2"]
    assert room["bounding_wall_ids"]["items"]["enum"] == ["W1", "W2"]
    assert room["room_id"]["enum"] == ["ROOM-1"]
    for field in ("region_id", "room_id"):
        assert "type" not in room[field], (
            "%s degraded from an enum to a free string — an undefined "
            "reference became expressible again" % field
        )

    import tests.test_vision_schemas as schema_tests

    schema_tests.test_dependency_ordered_levels_precede_every_reference_to_them()
    schema_tests.test_dependency_ordered_still_guards_every_id_list()
    # A room that cannot cite a bounding wall answers with an EMPTY list rather
    # than inventing a reference — the present-and-empty citation 24-04's
    # orphan-room branch reads.
    schema_tests.test_dependency_ordered_a_room_may_cite_no_bounding_wall()
    # The structural ban, and the positive control that proves it is a real
    # constraint rather than a vacuous assertion.
    schema_tests.test_no_numeric_fields_anywhere_on_any_vector_path_builder()
    schema_tests.test_the_raster_path_remains_the_one_schema_permitted_a_number()


# ═════════════════════════════════════════════════════════════════════════════
# V4-DET-04 — ENSEMBLE COVERAGE
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_det_04_every_analyzer_call_site_is_voted_or_carries_an_exemption():
    """V4-DET-04 — the census, INVOKED rather than duplicated.

    Following the precedent where phase 23's check 1 invokes the four-plan-set
    gate: 24-08 owns the AST census that walks both analyzer-bearing modules and
    classifies every call site as voted-with-a-witness or explicitly exempt. A
    second copy of its literals here would drift from it.

    The census is guarded from both sides by its own tests — zero sites found is
    a FAILURE rather than a clean bill of health, and a positive control proves
    the detector really detects — and both of those guards are invoked too.

    What this does NOT claim: that the ensemble improved anything on a real
    drawing. That needs a paid run. This asserts coverage and the determinism
    property, both provable offline.
    """
    import tests.test_reliability_voting as voting

    voting.test_every_analyzer_call_site_is_voted_or_exempt_so_every_pass_is_voted()
    voting.test_the_census_detector_catches_a_newly_added_call_site()
    voting.test_the_census_exemption_list_is_explicit_and_singular()
    # A voted quantity is structurally impossible, not merely avoided: only the
    # table-reading passes are eligible, because for a count or a measure pass
    # the identification and the number arrive in one object with no seam.
    voting.test_the_identification_pass_types_are_exactly_the_table_reading_passes()


# ═════════════════════════════════════════════════════════════════════════════
# V4-DET-05 — THE DETERMINISM HARNESS, AS REFRAMED
# ═════════════════════════════════════════════════════════════════════════════


def test_v4_det_05_the_two_variant_differential_holds(differential):
    """V4-DET-05 — 24-09's gate, invoked against a live differential.

    Three invariants, every one a set equality between variant A and variant B,
    never against a golden figure: the published item-name set, the
    unnamed-geometry ledger's candidate set, and the quantity multiset — a word
    may never move a number. If both variants are wrong in the SAME way this
    correctly passes: it measures invariance, not correctness, and conflating
    the two is what this phase exists to separate.

    The non-vacuity guards are invoked with it. A fixture key hashes the prompt
    text, the model routing and the image count, all three of which 24-07 moved,
    so a set authored against an earlier tree would sit on disk unread while the
    gate compared two runs that asked nothing.
    """
    import tests.test_determinism_harness as harness

    # Non-vacuity FIRST: a green gate over an unread fixture set proves nothing.
    harness.test_every_committed_fixture_was_actually_consumed(differential)
    harness.test_the_two_variants_really_do_carry_different_answers()
    harness.test_every_fixture_records_which_saved_run_it_came_from()
    harness.test_the_ensemble_is_pinned_to_one_sample_so_the_scope_is_honest(
        differential
    )

    # The gate itself.
    harness.test_two_schema_legal_answer_sets_publish_the_same_takeoff(differential)
    harness.test_the_unnamed_geometry_ledger_carries_the_same_candidates(differential)
    harness.test_no_published_quantity_moves_when_only_the_labels_move(differential)
    harness.test_the_candidate_that_flipped_between_the_paid_runs_is_named_in_neither(
        differential
    )

    # And the gate is a proven DETECTOR: it has been seen to fail.
    harness.test_the_gate_detects_a_naming_flip(differential)
    harness.test_the_gate_detects_a_candidate_named_in_one_variant_and_ledgered_in_the_other(
        differential
    )
    harness.test_the_gate_detects_a_quantity_that_moved()
    harness.test_two_identical_reports_report_no_difference()


def test_v4_det_05_criterion_five_was_reframed_and_the_literal_wording_is_vacuous(
    tmp_path,
):
    """ROADMAP criterion 5 was **NOT implemented as written**, deliberately.

    Its literal wording is *"a determinism harness runs the same fixture N times
    and asserts identical line items."* Against ``tests/replay_analyzer.py`` that
    is **vacuous**: ``ReplayAnalyzer.__call__`` resolves a SHA256 over
    ``(model, pass_type, prompt text, image count)`` and returns that file's
    response verbatim. It is a pure function of its key, so N runs of one fixture
    are identical BY CONSTRUCTION and would detect none of the defects this
    phase exists to kill — a gate that passes for having looked at nothing,
    which rule 3 forbids.

    Rule 1 requires this to be said by name rather than quietly replaced, and to
    be PROVED rather than narrated. So the vacuity is demonstrated here: the same
    request is issued twice and the two answers are identical, with no
    determinism guarantee involved anywhere — a dict is being read off disk.

    *Delivered instead:* hold the geometry fixed, VARY the model's answers within
    schema-legal bounds, and assert the published take-off does not move. That
    contract is asserted by the check above; this one records why the criterion's
    own words are not the thing asserted.
    """
    from tests.replay_analyzer import ReplayAnalyzer

    fixtures = tmp_path / "replay"
    fixtures.mkdir()
    analyzer = ReplayAnalyzer(fixtures)
    request = dict(
        sheet_name="A-101", pass_type="semantic", model_override="pinned-model",
    )
    key = analyzer.key_for(**request)

    # The key is a pure function of the request: derived twice, identical.
    assert analyzer.key_for(**request) == key
    (fixtures / ("%s.json" % key)).write_text(
        json.dumps({"response": {"wall_class_labels": [{"label": "recorded"}]}}),
        encoding="utf-8",
    )

    answers = [analyzer("unused.png", **request) for _ in range(5)]
    assert all(a == answers[0] for a in answers), (
        "the replay source is not a pure function of its key — the reframing "
        "rests on it being one, so re-measure before editing this assertion"
    )
    assert answers[0]["wall_class_labels"][0]["label"] == "recorded"
    # Which is the whole point: five identical answers, and NOTHING about the
    # naming layer was exercised to produce them. That is why the criterion's
    # literal wording could not be the gate.

    # And the reframing is recorded where a reader will find it, not only here.
    harness_doc = (ROOT / "tests" / "test_determinism_harness.py").read_text(
        encoding="utf-8"
    )
    assert "were not implemented" in harness_doc.lower(), (
        "the harness stopped recording that it does not implement the "
        "criterion's literal wording"
    )
