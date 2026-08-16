"""28-03 — an uncorroborated count may not publish as MEASURED.

28-01 stamped a four-valued ``count_corroboration`` verdict on every count row
the calculator emits (geometry / schedule / detail_sheet_only / none) and
deliberately made it inert: recording what backed a number is one decision, and
whether the number may be PUBLISHED is another. This module pins the second
decision, which lives here in the aggregator — the one layer that owns the
four-value client vocabulary and the difference between a blank and a zero.

What the rule is defending against is concrete and was measured, not imagined:
in the two saved paid Crow runs the ``Stairs`` row published MEASURED,
``needs_review`` false, at medium confidence — and it was ALSO the row whose
number disagreed with itself between two identical invocations. An unflagged
wrong number is worse than a blank, because a reviewer skips it.

Everything here is FREE: no paid marker, no credential, no golden comparison,
no network. The module audits itself for all four at the bottom.
"""
import ast
import inspect
from pathlib import Path

from bobbytailor.pipeline import aggregator
from bobbytailor.pipeline.aggregator import aggregate_takeoff


# ─── helpers ────────────────────────────────────────────────────────────────

def _row(rows, name):
    matches = [r for r in rows if r["item"] == name]
    assert len(matches) == 1, "expected exactly one %r row, got %r" % (
        name, [r["item"] for r in rows]
    )
    return matches[0]


def _count_item(description, corroboration=None, qty=3, **extra):
    """One calculated COUNT row, shaped as the calculator emits them.

    ``corroboration=None`` means the key is absent altogether — the shape every
    non-count row (an area, a length) has, and the shape every row in the
    pre-28-01 codebase had.
    """
    item = {
        "description": description,
        "item_type": "component",
        "calculated_quantity": qty,
        "calculated_unit": "ea",
        "source_sheet": "A-401",
        "formula": "count",
        "confidence": "medium",
        "auto_verified": True,
    }
    if corroboration is not None:
        item["count_corroboration"] = corroboration
        item["count_evidence_sheet_kind"] = "detail"
    item.update(extra)
    return item


def _buckets_of(monkeypatch, items, **kwargs):
    """Every bucket ``aggregate_takeoff`` published, captured at the publish point.

    ``_row_status`` is the single place a bucket becomes a client status, and it
    is handed the bucket itself — so spying on it reads the ACTUAL rolled-up
    record rather than a reconstruction of it. Returns ``(rows, buckets)``.
    """
    seen = []
    real = aggregator._row_status

    def spy(bucket, is_unknown):
        seen.append(bucket)
        return real(bucket, is_unknown)

    monkeypatch.setattr(aggregator, "_row_status", spy)
    rows = aggregate_takeoff(items, **kwargs)
    return rows, seen


def _bucket_for(buckets, description):
    """The captured bucket one contributing description landed in."""
    matches = [
        b for b in buckets
        if any(description in (r.get("description") or "") for r in b["source_rows"])
    ]
    assert len(matches) == 1, (
        "expected exactly one bucket carrying %r, got %d" % (description, len(matches))
    )
    return matches[0]


# ─── the roll-up: every bucket knows what corroborated its count ─────────────

def test_rollup_a_new_bucket_starts_with_no_count_verdict():
    """Distinguishable from "a count contributed and nothing backed it".

    ``None`` means no count row has reached this bucket at all. The string
    ``"none"`` means one did and nothing corroborated it. Collapsing the two
    would make every area row in the take-off look like an uncorroborated count.
    """
    assert aggregator._new_bucket()["count_corroboration"] is None


def test_rollup_combines_two_verdicts_in_one_place():
    combine = aggregator._stronger_corroboration
    # An absent verdict never overwrites a recorded one, in either order.
    assert combine(None, "geometry") == "geometry"
    assert combine("geometry", None) == "geometry"
    assert combine(None, None) is None
    # A corroborated verdict vouches for the bucket whichever side it arrives on.
    assert combine("none", "geometry") == "geometry"
    assert combine("geometry", "none") == "geometry"
    assert combine("detail_sheet_only", "schedule") == "schedule"
    assert combine("schedule", "detail_sheet_only") == "schedule"
    # Among uncorroborated verdicts the more specific one dominates, so the
    # reason a reader is shown names the sheet kind rather than shrugging.
    assert combine("none", "detail_sheet_only") == "detail_sheet_only"
    assert combine("detail_sheet_only", "none") == "detail_sheet_only"
    # A blank string is an ABSENT verdict, not an uncorroborated one.
    assert combine("geometry", "") == "geometry"
    assert combine("", None) is None
    # An unrecognised verdict is never read as corroboration.
    assert combine(None, "sounds_about_right") == "sounds_about_right"
    assert not aggregator._count_is_uncorroborated(
        {"count_corroboration": "geometry"}
    )
    assert aggregator._count_is_uncorroborated(
        {"count_corroboration": "sounds_about_right"}
    )


def test_rollup_the_precedence_is_expressed_exactly_once():
    """No second copy of the ordering can drift away from the first.

    Modelled on ``_worse_conf``: the ranking table exists once and exactly one
    function reads it.
    """
    module_src = inspect.getsource(aggregator)
    helper_src = inspect.getsource(aggregator._stronger_corroboration)
    rank_name = "_CORROBORATION" + "_RANK"
    assert module_src.count(rank_name) == 1 + helper_src.count(rank_name)


def test_rollup_the_loop_consults_that_one_helper(monkeypatch):
    """Liveness: the accumulation loop uses the shared helper, not a local copy.

    Replace the helper and the bucket's recorded verdict must move with it.
    """
    monkeypatch.setattr(
        aggregator, "_stronger_corroboration", lambda a, b: "spliced_in"
    )
    _, buckets = _buckets_of(
        monkeypatch, [_count_item("dock leveler", corroboration="geometry")]
    )
    assert _bucket_for(buckets, "dock leveler")["count_corroboration"] == "spliced_in"


def test_rollup_all_corroborated_rows_roll_up_corroborated(monkeypatch):
    _, buckets = _buckets_of(monkeypatch, [
        _count_item("dock leveler", corroboration="geometry", qty=2),
        _count_item("dock leveler", corroboration="schedule", qty=3),
    ])
    assert _bucket_for(buckets, "dock leveler")["count_corroboration"] == "geometry"


def test_rollup_one_corroborated_row_vouches_for_the_whole_bucket(monkeypatch):
    """A printed schedule or a geometry reading vouches for the OBJECT, even
    when a weaker reading of the same object also landed in the bucket."""
    _, buckets = _buckets_of(monkeypatch, [
        _count_item("dock leveler", corroboration="none", qty=2),
        _count_item("dock leveler", corroboration="schedule", qty=3),
    ])
    assert _bucket_for(buckets, "dock leveler")["count_corroboration"] == "schedule"


def test_rollup_all_uncorroborated_rows_roll_up_uncorroborated(monkeypatch):
    _, buckets = _buckets_of(monkeypatch, [
        _count_item("dock leveler", corroboration="none", qty=2),
        _count_item("dock leveler", corroboration="none", qty=3),
    ])
    bucket = _bucket_for(buckets, "dock leveler")
    assert bucket["count_corroboration"] == "none"
    assert aggregator._count_is_uncorroborated(bucket)


def test_rollup_a_bucket_with_no_count_rows_keeps_an_unset_verdict(monkeypatch):
    """Areas, lengths, blanks and the injected convention are not counts.

    Absence of the key is never read as "uncorroborated" — that is the
    difference between flagging the rows this phase is about and flagging the
    entire take-off.
    """
    rows, buckets = _buckets_of(monkeypatch, [
        {"description": "warehouse floor", "item_type": "flooring",
         "calculated_quantity": 3960.0, "calculated_unit": "sq_ft",
         "source_sheet": "A-101"},
    ])
    area = _bucket_for(buckets, "warehouse floor")
    assert area["count_corroboration"] is None
    assert not aggregator._count_is_uncorroborated(area)
    mobilization = _bucket_for(buckets, "Mobilization")
    assert mobilization["count_corroboration"] is None
    assert _row(rows, "Mobilization")["provenance"] == "STANDARD ITEM"


def test_rollup_records_the_verdict_without_moving_a_corroborated_quantity():
    """Recording is not deciding. A corroborated count publishes exactly what it
    published before the verdict existed — same number, same status, same flag."""
    without = aggregate_takeoff([_count_item("dock leveler", qty=4)])
    with_verdict = aggregate_takeoff(
        [_count_item("dock leveler", corroboration="geometry", qty=4)]
    )
    assert with_verdict == without


# ─── a detail-sheet count publishes a blank, with its reading quoted ────────

_DETAIL_ROW = dict(
    description="stair detail", corroboration="detail_sheet_only", qty=2,
    source_sheet="A-401",
)


def test_a_detail_sheet_count_never_reaches_a_published_quantity():
    """A count of stair DETAILS is not a count of stairs.

    The number is withheld rather than flagged-and-published, because the
    reading does not measure the object the row names: it measures how many
    times the object was DRAWN.
    """
    row = _row(aggregate_takeoff([_count_item(**_DETAIL_ROW)]), "Stairs")
    assert row["quantity"] is None
    assert row["quantity_fmt"] == "—"
    assert row["provenance"] == "NOT MEASURED"
    assert row["needs_review"] is True
    assert row["auto_verified"] is False
    assert row["confidence"] == "low"
    assert row["source"] == aggregator.DETAIL_SHEET_COUNT_UNMEASURED


def test_the_withheld_blank_is_still_a_row_that_quotes_what_it_withheld():
    """Withholding is not deleting. A deletion and a zero read the same to a
    client; this row says the number exists, says what it was, and says why it
    is not being published."""
    row = _row(aggregate_takeoff([_count_item(**_DETAIL_ROW)]), "Stairs")
    reason = " ".join(row["review_reasons"])
    assert "stair detail" in reason
    assert "2" in reason
    assert "A-401" in reason
    assert "BLANK, not a zero" in reason
    # A named rule on the row itself, so the audit trail shows which rule fired.
    formulas = [r.get("formula") for r in row["detail"]]
    assert "detail_sheet_count_not_measured" in formulas
    assert row["line_count"] == 0


def test_the_withheld_reason_suggests_no_count_of_its_own():
    """It may quote the reading it withheld and name the sheet. It may not
    imply what the number ought to be — writing an expected count into an
    estimator-facing message is the failure mode this phase exists to end."""
    row = _row(aggregate_takeoff([_count_item(**_DETAIL_ROW)]), "Stairs")
    reason = " ".join(row["review_reasons"])
    assert "details sheet" in reason
    assert "how many" in reason
    residue = reason.replace("A-401", "").replace("2", "")
    assert not any(ch.isdigit() for ch in residue), residue


def test_a_corroborated_reading_of_the_same_object_keeps_its_quantity():
    """The detail-sheet reading is not SUMMED into a real measurement, and the
    real measurement is not thrown away because a weaker reading existed."""
    rows = aggregate_takeoff([
        _count_item("stair detail", corroboration="geometry", qty=5,
                    source_sheet="A-101"),
        _count_item(**_DETAIL_ROW),
    ])
    row = _row(rows, "Stairs")
    assert row["quantity"] == 5
    assert row["needs_review"] is True
    reason = " ".join(row["review_reasons"])
    assert "NOT summed into this quantity" in reason
    assert "stair detail" in reason and "A-401" in reason


def test_the_withheld_marker_joins_the_existing_unmeasured_markers():
    """T-28-16: every consumer that already understands "this source means the
    row is a marker, not a measurement" understands this one, without being
    told about it individually."""
    assert aggregator.DETAIL_SHEET_COUNT_UNMEASURED in aggregator._UNMEASURED_SOURCES


def test_no_consumer_special_cases_the_new_marker():
    src = Path(aggregator.__file__).resolve().parents[1]
    named_in = sorted(
        p.relative_to(src).as_posix()
        for p in src.rglob("*.py")
        if aggregator.DETAIL_SHEET_COUNT_UNMEASURED in p.read_text()
    )
    assert named_in == ["pipeline/aggregator.py"], named_in


def test_withholding_one_count_disturbs_no_other_row():
    others = [
        {"description": "warehouse floor", "item_type": "flooring",
         "calculated_quantity": 3960.0, "calculated_unit": "sq_ft",
         "source_sheet": "A-101"},
        _count_item("Door Frames - Hollow Metal (door schedule)",
                    corroboration="schedule", qty=29,
                    qty_source="plan_schedule_legend", source_sheet="A-601"),
    ]
    before = {r["item"]: r for r in aggregate_takeoff(list(others))}
    after = {r["item"]: r for r in aggregate_takeoff(others + [_count_item(**_DETAIL_ROW)])}
    assert set(after) - set(before) == {"Stairs"}
    for name, row in before.items():
        assert after[name] == row, name


def test_the_door_schedule_count_still_publishes_measured():
    """The row this rule is most likely to damage, asserted directly: a count
    read out of a table PRINTED on the plans is corroborated BY that table."""
    row = _row(aggregate_takeoff([
        _count_item("Door Frames - Hollow Metal (door schedule)",
                    corroboration="schedule", qty=29,
                    qty_source="plan_schedule_legend", source_sheet="A-601"),
    ]), "Door Frames - Hollow Metal (door schedule)")
    assert row["quantity"] == 29
    assert row["provenance"] == "MEASURED"
    assert row["needs_review"] is False


# ─── _row_status may not call an uncorroborated count MEASURED ──────────────

def _bucket(**over):
    bucket = aggregator._new_bucket()
    bucket.update({"has_rows": True, "quantity": 4.0, "unit": "EA"})
    bucket.update(over)
    return bucket


def test_row_status_refuses_measured_for_an_uncorroborated_count():
    """The single place a bucket becomes ITEM_MEASURED, closed against the one
    thing it was letting through: a count nothing confirmed."""
    assert aggregator._row_status(
        _bucket(count_corroboration="none"), False
    ) == "NEEDS REVIEW"
    assert aggregator._row_status(
        _bucket(count_corroboration="detail_sheet_only"), False
    ) == "NEEDS REVIEW"


def test_row_status_is_unchanged_for_a_corroborated_count():
    for verdict in ("geometry", "schedule"):
        assert aggregator._row_status(
            _bucket(count_corroboration=verdict), False
        ) == "MEASURED", verdict


def test_row_status_is_unchanged_for_every_bucket_that_never_counted():
    """Areas, blanks, the injected convention and the legend cases are not
    counts and must answer exactly what they answered before this branch."""
    assert aggregator._row_status(_bucket(), False) == "MEASURED"
    assert aggregator._row_status(_bucket(), True) == "NOT MEASURED"
    assert aggregator._row_status(
        _bucket(has_rows=False, item_type="standard_line_item"), False
    ) == "STANDARD ITEM"
    assert aggregator._row_status(_bucket(has_rows=False), False) == "NOT MEASURED"
    assert aggregator._row_status(_bucket(needs_review=True), False) == "NEEDS REVIEW"


def test_row_status_still_reaches_the_plan_schedule_legend_branch():
    """The new branch is not allowed to shadow the branch below it: a
    schedule-corroborated count keeps whichever answer the legend rules give."""
    assert aggregator._row_status(
        _bucket(count_corroboration="schedule", source="plan_schedule_legend",
                legend_origin="human_input"), False
    ) == "HUMAN INPUT"
    assert aggregator._row_status(
        _bucket(count_corroboration="schedule", source="plan_schedule_legend"), False
    ) == "MEASURED"


def test_the_row_status_docstring_states_what_this_branch_prevents():
    doc = (aggregator._row_status.__doc__ or "").lower()
    # Both kinds of corroboration are named, and so is the failure that earned
    # the branch: one number, two identical runs, two different answers.
    assert "schedule" in doc and "geometry" in doc
    assert "identical" in doc
    assert "description read off a drawing" in doc


def test_an_uncorroborated_count_publishes_needs_review_end_to_end():
    row = _row(aggregate_takeoff([
        _count_item("dock leveler", corroboration="none", qty=4,
                    count_evidence_sheet_kind="floor_plan"),
    ]), "Dock Leveler")
    assert row["quantity"] == 4
    assert row["provenance"] == "NEEDS REVIEW"
    assert row["needs_review"] is True
    assert row["auto_verified"] is False
    reason = " ".join(row["review_reasons"])
    assert "no printed schedule" in reason
    assert "no counted geometry" in reason
    # It states no number of its own — the reading is already on the row.
    assert not any(ch.isdigit() for ch in reason), reason


def test_a_geometry_backed_count_still_publishes_measured_end_to_end():
    row = _row(aggregate_takeoff([
        _count_item("dock leveler", corroboration="geometry", qty=4),
    ]), "Dock Leveler")
    assert row["quantity"] == 4
    assert row["provenance"] == "MEASURED"
    assert row["needs_review"] is False
    assert row["auto_verified"] is True
    assert row["review_reasons"] == []


def test_the_injected_convention_still_publishes_as_a_standard_item():
    rows = aggregate_takeoff([_count_item("dock leveler", corroboration="none")])
    row = _row(rows, "Mobilization")
    assert row["provenance"] == "STANDARD ITEM"
    assert row["quantity"] == 1
    assert row["needs_review"] is False


def test_an_area_row_beside_an_uncorroborated_count_is_untouched():
    rows = aggregate_takeoff([
        {"description": "warehouse floor", "item_type": "flooring",
         "calculated_quantity": 3960.0, "calculated_unit": "sq_ft",
         "source_sheet": "A-101", "auto_verified": True, "confidence": "high"},
        _count_item("dock leveler", corroboration="none"),
    ])
    area = _row(rows, "Flooring")
    assert area["provenance"] == "MEASURED"
    assert area["needs_review"] is False
    assert area["review_reasons"] == []


def test_the_rules_boundary_is_a_recorded_verdict_and_this_is_it():
    """The stated limit of this rule, committed rather than left implicit.

    The decision is made on a RECORDED verdict, never re-derived here — the
    aggregator cannot see the sheet a number came off. So a count emitted by a
    producer that stamps no verdict is treated as not-a-count and still
    publishes MEASURED. That is the plan's rule ("absence is never read as
    uncorroborated"), and it is what keeps the rule from flagging every area
    and length in the take-off; the residual is the set of producers that emit
    counts without stamping one, which is a coverage question for the phase
    gate, not a decision this layer can make.
    """
    row = _row(aggregate_takeoff([_count_item("dock leveler", qty=4)]), "Dock Leveler")
    assert row["provenance"] == "MEASURED"
    assert row["needs_review"] is False


#: Calculator producers that can emit an EA row — a COUNT — and stamp no
#: corroboration verdict on it, so this layer would treat it as not-a-count and
#: could still publish it MEASURED.
#:
#: **EMPTY, and that is the point.** It held two entries when 28-03 wrote this
#: tripwire, and 29-04 shortened it to nothing by stamping both of them:
#:
#: * ``_calculate_from_measurement`` — a dimension annotation resolving to a
#:   whole EA quantity >= 1; now stamped on the ``ea`` branch only, so areas and
#:   lengths stay unstamped and the "absence is never read as uncorroborated"
#:   rule below keeps costing nothing.
#: * ``_calculate_from_civil_structures`` — catch basins / manholes / headwalls,
#:   always EA; now stamped unconditionally, since it emits nothing else.
#:
#: The tuple stays rather than being deleted: a future producer that emits a
#: count without a verdict belongs here, named, and this list is where the phase
#: gate looks.
_COUNT_PRODUCERS_THAT_STAMP_NO_VERDICT = ()

#: The producers 29-04 closed. Asserted POSITIVELY below so the shortening above
#: cannot be the whole test — an empty list asserts nothing, and a tripwire
#: retired into vacuity is worse than one left standing.
_COUNT_PRODUCERS_CLOSED_BY_29_04 = (
    "_calculate_from_measurement",
    "_calculate_from_civil_structures",
)


def test_the_residual_this_plan_does_not_close_is_named_not_implied():
    """The 28-03 tripwire, flipped by 29-04 as its own instructions directed.

    Kept under its original name because the phase-28 acceptance gate invokes
    this function by name, and because the question it asks has not changed —
    only the answer. It used to assert that two named producers emitted counts
    and recorded NO verdict, and it failed the day either was stamped; that day
    was 29-04, and the list it guards is now empty.

    What it asserts now, in both directions:

    * every producer still named in the residual list emits a count and records
      no verdict (vacuous today by construction, and the place a future
      regression would be declared);
    * every producer 29-04 closed still emits a count AND still records a
      verdict — which is what makes V4-FIX-01's universal claim true app-wide
      rather than true only of the rows 28-01 happened to reach.

    The check is on the SOURCE rather than on a return value for the same reason
    28-03 wrote it that way: it is a coverage question about which producers
    exist, and a behavioural probe can only speak for the inputs it was handed.
    The behaviour of each stamp is pinned separately, on returned rows, in
    ``tests/test_phase28_count_corroboration.py``.
    """
    from bobbytailor.pipeline import calculator
    for fn in _COUNT_PRODUCERS_THAT_STAMP_NO_VERDICT:
        src = inspect.getsource(getattr(calculator, fn))
        assert '"ea"' in src, "%s no longer emits a count at all" % fn
        assert "count_corroboration" not in src, (
            "%s now records a verdict — remove it from the residual list and "
            "say so in the phase gate" % fn
        )
    for fn in _COUNT_PRODUCERS_CLOSED_BY_29_04:
        src = inspect.getsource(getattr(calculator, fn))
        assert '"ea"' in src, "%s no longer emits a count at all" % fn
        assert "count_corroboration" in src, (
            "%s stopped recording a verdict — the counts it emits are invisible "
            "to this layer again and can publish MEASURED unbacked" % fn
        )


# ─── this module's own contract ─────────────────────────────────────────────

def test_this_module_names_no_golden_quantity_and_calls_no_paid_service():
    source = Path(__file__).read_text()
    # Assembled from halves so the check cannot find itself.
    forbidden = [
        "ANTHRO" + "PIC",
        "crow_cass" + "_golden",
        "golden" + ".csv",
        "vision_only" + "_benchmark",
        "accuracy" + "_gate",
    ]
    for token in forbidden:
        assert token not in source, (
            "this module must stay free and golden-free; found %r" % token
        )


def test_this_module_imports_nothing_that_could_reach_a_network():
    """Checked over the module's own import statements rather than by scanning
    its text — a substring scan for a networking library finds itself."""
    tree = ast.parse(Path(__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"ast", "inspect", "pathlib", "pytest", "bobbytailor"}
    assert imported <= allowed, (
        "this module must stay offline; unexpected imports %r"
        % sorted(imported - allowed)
    )
