"""28-05 — one measured region backs one published row per building layer.

The defect, measured in both saved paid Crow runs and identical in each: the
397,600 SF building footprint publishes THREE times.

    Exposed Structure  397,600 SF  plan_schedule_legend  MEASURED
    Sealed Concrete    397,600 SF  plan_schedule_legend  MEASURED
    Concrete Pad       397,600 SF  library               NEEDS REVIEW

An estimator who sums the SF column prices the building three times. Two of the
three rows are golden-correct and both must survive — they are genuinely
different building layers (the sealed-concrete floor finish and the exposed roof
structure) through one plan area, which is phase 23's D1 exception and is NOT
being taken back. The third never measured a slab; it inherited the footprint
because its measure basis is area-shaped, and the report already says so in its
own words on the neighbouring row: *"NOT reconciled by name: 1 measured row(s)
share this unit (SF) and measure basis (floor_area) and were named by a
hypothesis rather than by printed evidence — 'Concrete Pad'."*

What made this hard to fix honestly is that the region identity was DROPPED
between fusion and the published row, so the only thing left to tell the three
rows apart was that their numbers were equal. Arbitrating on numeric equality is
a coincidence rule, and this phase rejects those: two genuinely distinct regions
that happen to measure the same area must both publish. So the region is
threaded end to end first, and the rule keys on it.

Everything here is FREE: no paid marker, no credential, no golden comparison, no
network. The module audits itself for all four at the bottom.
"""
import ast
import inspect
from pathlib import Path

import pytest

from bobbytailor.pipeline import aggregator
from bobbytailor.pipeline.aggregator import aggregate_takeoff
from bobbytailor.pipeline.calculator import (
    _calculate_from_component,
    _calculate_from_measurement,
)
from bobbytailor.vision import fusion
from bobbytailor.vision.fusion import (
    NAME_SOURCE_VOCABULARY_BASIS,
    _NAME_AUTHORITY,
    _arbitrate_one_area_one_item,
    _fuse_project_area_items,
    _share_rank,
)


# ─── helpers ────────────────────────────────────────────────────────────────

#: The Crow footprint, to the tenth of a square foot the run recorded. Used as
#: an INPUT here, never as an expected answer — no assertion below compares a
#: published number against a golden figure.
CROW_FOOTPRINT_SF = 397600.0

#: The six floor/roof-shaped objects Crow's vocabulary offered, which is how one
#: measured footprint came to back six line items at once (INV-00 §4).
CROW_FOOTPRINT_VOCABULARY = {
    "Canopy": {"basis": "roof_area", "unit": "SF"},
    "Concrete Pad": {"basis": "floor_area", "unit": "SF"},
    "Exposed Structure": {"basis": "roof_area", "unit": "SF"},
    "Sealed Concrete": {"basis": "floor_area", "unit": "SF"},
    "Vapor Barrier": {"basis": "floor_area", "unit": "SF"},
}


def _footprint_components(vocabulary=None, area_sf=CROW_FOOTPRINT_SF):
    """Whatever `_fuse_project_area_items` emits for a measured footprint."""
    components: list = []
    _fuse_project_area_items(
        {"footprint": {"area_sf": area_sf, "confidence": "high"}},
        CROW_FOOTPRINT_VOCABULARY if vocabulary is None else vocabulary,
        components,
    )
    return components


def _row(rows, name):
    matches = [r for r in rows if r["item"] == name]
    assert len(matches) == 1, "expected exactly one %r row, got %r" % (
        name, [r["item"] for r in rows]
    )
    return matches[0]


def _legend_row(name, qty, unit="SF"):
    """A row the PLAN'S OWN printed schedule named and quantified.

    This is the shape `_calculate_from_schedule` emits for an authoritative
    take-off legend, which is how `Exposed Structure` and `Sealed Concrete`
    reached the published report in both saved runs.
    """
    return {
        "item_type": "schedule_item",
        "description": name,
        "quantity": qty,
        "unit": unit,
        "raw_unit": unit,
        "formula": "authoritative plan schedule (%s %s)" % (qty, unit),
        "qty_source": "plan_schedule_legend",
        "legend_origin": "plan_parsed",
        "count_corroboration": "schedule",
        "source_sheet": "A-101",
        "confidence": "high",
        "needs_review": False,
    }


def _detected_row(name, qty, region_ref=None, unit="SF", **extra):
    """A row fusion measured and the calculator carried through.

    ``region_ref=None`` means the key is ABSENT, which is the shape of every row
    measured on no particular region — and the shape every row in the pre-28-05
    codebase had.
    """
    item = {
        "item_type": "concrete_slab",
        "description": name,
        "quantity": qty,
        "unit": unit,
        "raw_unit": unit,
        "formula": "count",
        "source_sheet": "A-101",
        "confidence": "high",
        "needs_review": False,
    }
    if region_ref is not None:
        item["region_ref"] = region_ref
    item.update(extra)
    return item


def _library(*names, basis="floor_area", unit="SF"):
    """A component library that will name these rows, so their published
    ``source`` is ``library`` — the marker the codebase already uses for "this
    row's NAME is a hypothesis"."""
    return [
        {"name": n, "aliases": [n], "basis": basis, "unit": unit} for n in names
    ]


# ═══ Task 1 — the stamp and the region survive, and move nothing ════════════


def test_every_footprint_row_carries_the_stamp_naming_who_named_it():
    """The vocabulary named a CLASS of object; nothing on the sheet named this
    region. Recording that is the whole of task 1."""
    components = _footprint_components()
    assert len(components) == len(CROW_FOOTPRINT_VOCABULARY)
    assert {c["name_source"] for c in components} == {
        NAME_SOURCE_VOCABULARY_BASIS
    }
    assert {c["region_ref"] for c in components} == {"footprint"}


def test_the_stamp_is_registered_rather_than_falling_to_the_unknown_default():
    """An unregistered marker scores as "nobody recorded who named this", which
    is precisely the state task 1 exists to end."""
    assert NAME_SOURCE_VOCABULARY_BASIS in _NAME_AUTHORITY


def test_the_stamp_outranks_nothing_it_did_not_outrank_before():
    """Below every printed authority and below a learned verbatim string.

    A vocabulary basis is a statement that an object of this class exists in the
    project. It is never a statement that THIS region is that object.
    """
    rank = _NAME_AUTHORITY[NAME_SOURCE_VOCABULARY_BASIS]
    for printed in ("vision", "plan_schedule_legend", "schedule", "text_layer",
                    "naming_library", "library", "learned"):
        assert rank > _NAME_AUTHORITY[printed], printed


def test_the_stamp_does_not_move_the_crow_footprint_anchor():
    """The stamp is INERT here, and that is the point: a behaviour change hidden
    inside a plumbing task is unreviewable.

    The anchor of the footprint region decides which rows are suppressed against
    it, and `_reinstate_orphaned_supersessions` re-checks supersessions whose
    superseder died — so an anchor that quietly moved would ripple two
    arbitrations away from here.
    """
    stamped = _footprint_components()
    # The same six rows as they were emitted BEFORE task 1: no name_source at
    # all, so `_share_rank` fell to the unknown-source default for every one.
    unstamped = [
        {k: v for k, v in c.items() if k != "name_source"} for c in stamped
    ]
    assert all("name_source" not in c for c in unstamped)

    def anchor(group):
        return sorted(group, key=_share_rank)[0]["name"]

    assert anchor(stamped) == anchor(unstamped)
    assert [c["name"] for c in sorted(stamped, key=_share_rank)] == [
        c["name"] for c in sorted(unstamped, key=_share_rank)
    ]


def test_the_stamp_does_not_move_a_single_suppression_on_the_crow_fan_out():
    """The whole arbitration, not just its first sort key: same survivors, same
    layers, same rejections, same reasons."""
    def arbitrate(components):
        rejected: list = []
        _arbitrate_one_area_one_item(components, rejected)
        return (
            sorted((c["name"], c.get("building_layer")) for c in components),
            sorted((r["answer"], r["reason"], r["detail"]) for r in rejected),
        )

    stamped = _footprint_components()
    unstamped = [
        {k: v for k, v in c.items() if k != "name_source"} for c in stamped
    ]
    assert arbitrate(stamped) == arbitrate(unstamped)


def test_the_calculator_carries_the_region_a_stamped_component_recorded():
    """`provenance` has been carried through this seam since 23-C3 with a
    comment saying downstream consumers cannot do their job without it. The
    region identity was being nulled at the same seam, for want of the same
    line."""
    component = _footprint_components()[0]
    row = _calculate_from_component(component, "A-101", "plan")
    assert row is not None
    assert row["region_ref"] == component["region_ref"]
    assert row["name_source"] == component["name_source"]


def test_a_region_the_component_never_recorded_is_absent_not_empty():
    """A blank region reference would group every regionless row in the project
    into one enormous "region"."""
    row = _calculate_from_component(
        {"name": "Bollards", "quantity": 5, "unit": "EA"}, "A-101", "plan",
    )
    assert row is not None
    assert "region_ref" not in row
    assert "name_source" not in row


def test_the_measurement_entry_point_carries_the_region_too():
    """Both calculator entry points, or half the report loses its provenance
    without anything failing."""
    row = _calculate_from_measurement(
        {"value": "1000", "unit": "sf", "description": "sealed concrete",
         "region_ref": "fill:FILL-2", "name_source": "room_fill"},
        "A-101", "plan",
    )
    assert row is not None
    assert row["region_ref"] == "fill:FILL-2"
    assert row["name_source"] == "room_fill"


def test_the_aggregator_reads_the_stamp_by_value_and_the_two_agree():
    """`pipeline.aggregator` must not import `vision.fusion` — the dependency
    runs the other way. The string is carried by VALUE, exactly as fusion
    carries `text_anchor.KIND_TAG`, and this is the test that fails if the two
    ever diverge."""
    assert (
        aggregator._NAME_SOURCE_VOCABULARY_BASIS == NAME_SOURCE_VOCABULARY_BASIS
    )


def test_the_bucket_a_stamped_row_lands_in_records_both_facts():
    """The seam the two fields were dying at is the bucket, not the row.

    What the bucket DOES with them is task 2's decision; task 1 only has to
    stop dropping them, and this is the assertion that says they arrived.
    """
    bucket = aggregator._new_bucket()
    assert bucket["region_ref"] == ""
    assert bucket["name_source"] == ""


def test_the_stamp_is_kept_out_of_the_symbol_group_naming_gate():
    """`NAME_WORTHY_SOURCES` is 24-04's gate on what may name a SYMBOL GROUP. A
    vocabulary-basis name is never a symbol group's name, and widening that gate
    to register a marker would loosen an unrelated rule."""
    assert NAME_SOURCE_VOCABULARY_BASIS not in fusion.NAME_WORTHY_SOURCES


# ═══ Task 2 — a hypothesis may not claim a layer it did not measure ═════════


def _crow_fan_out():
    """The three-row fan-out, rebuilt from the shape both saved runs recorded.

    Five calculated rows, not three, because that is what actually reached the
    aggregator: the plan's own authoritative legend named and quantified
    `Exposed Structure` and `Sealed Concrete`, and fusion ALSO bound each of
    them — and `Concrete Pad` — to the measured footprint. The two legend rows
    shadowed their detected twins, which is why both published rows carry the
    review reason *"a separate reading of this item was suppressed as a
    duplicate of the authoritative legend row"* verbatim in the saved artifact.
    """
    return [
        _legend_row("Exposed Structure", CROW_FOOTPRINT_SF),
        _legend_row("Sealed Concrete", CROW_FOOTPRINT_SF),
        _detected_row("Exposed Structure", CROW_FOOTPRINT_SF,
                      region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS),
        _detected_row("Sealed Concrete", CROW_FOOTPRINT_SF,
                      region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS),
        _detected_row("Concrete Pad", CROW_FOOTPRINT_SF,
                      region_ref="footprint",
                      name_source=NAME_SOURCE_VOCABULARY_BASIS),
    ]


def _crow_rows():
    return aggregate_takeoff(
        _crow_fan_out(),
        library=_library("Exposed Structure", "Sealed Concrete", "Concrete Pad"),
    )


def test_the_crow_fan_out_resolves_to_two_published_rows_and_one_blank():
    """The defect, and the whole of the fix.

    Before this rule the same five inputs published THREE numbers of the same
    area, and an estimator who summed the SF column priced the building three
    times. Both golden-correct rows keep their quantities — they are different
    building layers through one plan area and phase 23's D1 admits them. The
    third publishes a blank: its name is a hypothesis, and it never measured a
    slab.
    """
    rows = _crow_rows()
    published = {
        r["item"]: r["quantity"] for r in rows
        if r["quantity"] is not None and r["unit"] == "SF"
    }
    assert published == {
        "Exposed Structure": CROW_FOOTPRINT_SF,
        "Sealed Concrete": CROW_FOOTPRINT_SF,
    }
    pad = _row(rows, "Concrete Pad")
    assert pad["quantity"] is None
    assert pad["source"] == aggregator.REGION_SHARED_HYPOTHESIS_UNMEASURED
    assert pad["needs_review"] is True
    assert pad["provenance"] == "NOT MEASURED"


def test_the_blank_names_the_rows_that_hold_the_region_and_the_area_it_withheld():
    """A deletion and a zero read identically to a client; so does a blank with
    no explanation. The row has to say what was withheld and who holds the
    region, or a reviewer cannot tell a suppressed duplicate from a measurement
    the app never made."""
    pad = _row(_crow_rows(), "Concrete Pad")
    reason = " ".join(pad["review_reasons"])
    assert "Exposed Structure" in reason and "Sealed Concrete" in reason
    assert "footprint" in reason
    assert str(int(CROW_FOOTPRINT_SF)) in reason
    assert "BLANK, not a zero" in reason
    assert "hypothesis" in reason and "INHERITED" in reason
    withheld = [
        d for d in pad["detail"]
        if d["formula"] == "region_shared_hypothesis_not_measured"
    ]
    assert len(withheld) == 1
    assert "Exposed Structure" in withheld[0]["description"]


def test_the_legend_row_inherits_the_region_of_the_reading_it_shadowed():
    """Without this the fan-out is invisible: the two rows an estimator sees are
    legend rows, which record no region of their own, and the group would be a
    group of one."""
    rows = _crow_rows()
    for name in ("Exposed Structure", "Sealed Concrete"):
        reason = " ".join(_row(rows, name)["review_reasons"])
        assert "suppressed as a duplicate of the authoritative legend row" in reason
    # ...and the proof that the region travelled with it: remove the two
    # detected twins and nothing has a region to contend over, so the
    # hypothesis publishes its number exactly as it did before this rule.
    without_twins = [
        i for i in _crow_fan_out()
        if i.get("qty_source") or i["description"] == "Concrete Pad"
    ]
    rows = aggregate_takeoff(
        without_twins,
        library=_library("Exposed Structure", "Sealed Concrete", "Concrete Pad"),
    )
    assert _row(rows, "Concrete Pad")["quantity"] == CROW_FOOTPRINT_SF


def test_two_equal_quantities_on_different_regions_both_publish():
    """T-28-26. The rule keys on the RECORDED REGION IDENTITY, never on the
    numbers. Two genuinely distinct regions that happen to measure the same area
    are two measurements, and an arbitration that could not tell them apart
    would be deciding by coincidence."""
    rows = aggregate_takeoff(
        [
            _legend_row("Sealed Concrete", 1716.7),
            _detected_row("Sealed Concrete", 1716.7, region_ref="fill:FILL-2",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
            _detected_row("Concrete Pad", 1716.7, region_ref="fill:FILL-9",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
        ],
        library=_library("Sealed Concrete", "Concrete Pad"),
    )
    assert _row(rows, "Sealed Concrete")["quantity"] == 1716.7
    assert _row(rows, "Concrete Pad")["quantity"] == 1716.7


def test_a_lone_hypothesis_on_its_region_keeps_its_quantity():
    """This rule resolves CONTENTION over one region. It does not demote a row
    for being a hypothesis — that flag already exists and says so."""
    rows = aggregate_takeoff(
        [_detected_row("Concrete Pad", CROW_FOOTPRINT_SF, region_ref="footprint",
                       name_source=NAME_SOURCE_VOCABULARY_BASIS)],
        library=_library("Concrete Pad"),
    )
    pad = _row(rows, "Concrete Pad")
    assert pad["quantity"] == CROW_FOOTPRINT_SF
    assert pad["source"] == "library"


def test_a_region_held_only_by_hypotheses_is_left_alone():
    """No arbiter, no arbitration.

    A region every row inherited has nothing on it that the plan named, so
    picking a winner among them by any other means would be exactly the emergent
    sharing INV-00 §4 forbids. This is also D1's three-layer share on a run with
    no legend, and it must survive untouched.
    """
    rows = aggregate_takeoff(
        [
            _detected_row("Sealed Concrete", CROW_FOOTPRINT_SF,
                          region_ref="footprint",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
            _detected_row("Exposed Structure", CROW_FOOTPRINT_SF,
                          region_ref="footprint",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
            _detected_row("Concrete Pad", CROW_FOOTPRINT_SF,
                          region_ref="footprint",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
        ],
        library=_library("Sealed Concrete", "Exposed Structure", "Concrete Pad"),
    )
    for name in ("Sealed Concrete", "Exposed Structure", "Concrete Pad"):
        assert _row(rows, name)["quantity"] == CROW_FOOTPRINT_SF, name


def test_a_row_that_recorded_no_region_is_never_touched():
    """Most of the take-off records no region at all. An absent region groups
    with nothing — it must never be read as an empty-string region that every
    regionless row shares."""
    rows = aggregate_takeoff(
        [
            _legend_row("Sealed Concrete", CROW_FOOTPRINT_SF),
            _detected_row("Concrete Pad", CROW_FOOTPRINT_SF),
            _detected_row("Vapor Barrier", CROW_FOOTPRINT_SF),
        ],
        library=_library("Sealed Concrete", "Concrete Pad", "Vapor Barrier"),
    )
    assert _row(rows, "Concrete Pad")["quantity"] == CROW_FOOTPRINT_SF
    assert _row(rows, "Vapor Barrier")["quantity"] == CROW_FOOTPRINT_SF


def test_a_different_unit_on_the_same_region_is_a_different_measurement():
    """A perimeter and an area are both backed by the footprint and neither is a
    duplicate of the other."""
    rows = aggregate_takeoff(
        [
            _legend_row("Sealed Concrete", CROW_FOOTPRINT_SF),
            _detected_row("Sealed Concrete", CROW_FOOTPRINT_SF,
                          region_ref="footprint",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
            _detected_row("Building Perimeter", 2972.0, region_ref="footprint",
                          unit="LF", item_type="linear",
                          name_source=NAME_SOURCE_VOCABULARY_BASIS),
        ],
        library=_library("Sealed Concrete")
        + _library("Building Perimeter", basis="linear", unit="LF"),
    )
    assert _row(rows, "Building Perimeter")["quantity"] == 2972.0


def test_the_rule_never_compares_two_quantities():
    """T-28-26, asserted against the code rather than against a case.

    A case-by-case test proves the rule did not compare numbers on THAT input.
    This proves it cannot: no comparison anywhere in the rule mentions a
    quantity, so there is no input on which it could start deciding by
    coincidence.
    """
    source = inspect.getsource(aggregator._withhold_region_sharing_hypotheses)
    tree = ast.parse(source.lstrip())
    compares = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)]
    for node in compares:
        rendered = ast.dump(node)
        assert "quantity" not in rendered, ast.dump(node)

    # ...and the rule READS a quantity exactly once, in the line that quotes the
    # withheld number back to the reader. Counted as syntax rather than as text,
    # so the prose above it is free to say the word.
    def _reads_a_quantity(node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return (
                node.func.attr == "get"
                and bool(node.args)
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "quantity"
            )
        if isinstance(node, ast.Subscript):
            index = getattr(node, "slice", None)
            return isinstance(index, ast.Constant) and index.value == "quantity"
        return False

    reads = [n for n in ast.walk(tree) if _reads_a_quantity(n)]
    assert len(reads) == 1, [ast.dump(n) for n in reads]


def test_the_new_marker_joins_the_existing_unmeasured_markers():
    """T-28-25: every consumer that already understands "this source means the
    row is a marker, not a measurement" understands this one, without being told
    about it individually."""
    assert (
        aggregator.REGION_SHARED_HYPOTHESIS_UNMEASURED
        in aggregator._UNMEASURED_SOURCES
    )


def test_no_consumer_special_cases_the_new_marker():
    src = Path(aggregator.__file__).resolve().parents[1]
    named_in = sorted(
        p.relative_to(src).as_posix()
        for p in src.rglob("*.py")
        if aggregator.REGION_SHARED_HYPOTHESIS_UNMEASURED in p.read_text()
    )
    assert named_in == ["pipeline/aggregator.py"], named_in


def test_withholding_one_row_disturbs_no_other():
    """The rest of the take-off is not collateral."""
    others = [
        {"description": "doors - steel", "item_type": "doors",
         "calculated_quantity": 70, "calculated_unit": "ea",
         "source_sheet": "A-601", "formula": "count",
         "count_corroboration": "schedule", "confidence": "high"},
    ]
    rows = aggregate_takeoff(
        _crow_fan_out() + others,
        library=_library("Exposed Structure", "Sealed Concrete", "Concrete Pad"),
    )
    doors = [r for r in rows if r["item"].lower().startswith("doors")]
    assert len(doors) == 1 and doors[0]["quantity"] == 70


# ═══ Module self-audit — this file spends nothing ═══════════════════════════


def _module_source_under_audit() -> str:
    """This module's source with the two audit tests themselves removed.

    A guard that searches for a string has to state that string, so a guard
    which scanned its own body would always find its own evidence and fail. The
    two audit functions are excised by their own source text rather than by a
    line range, so the exclusion cannot drift as the file grows.
    """
    source = Path(__file__).read_text()
    for audit in (test_this_module_runs_free, test_this_module_asserts_no_golden_total):
        source = source.replace(inspect.getsource(audit), "")
    return source


def test_this_module_runs_free():
    """No paid marker, no credential, no network, no golden comparison."""
    source = _module_source_under_audit()
    for forbidden in ("ANTHROPIC_API_KEY", "mark.golden", "accuracy_gate",
                      "vision_only_benchmark", "golden_convergence",
                      "requests.", "httpx.", "urllib"):
        assert forbidden not in source, forbidden


def test_this_module_asserts_no_golden_total():
    """The footprint appears as an INPUT and never as an expected answer.

    The golden floor area for this building is a number this file does not
    contain, and the assertion below is what keeps it that way: a test that
    watched a published number move toward a golden figure would be tuning to
    golden, which is the practice this phase exists to end.
    """
    source = _module_source_under_audit()
    assert "395,673" not in source and "395673" not in source
