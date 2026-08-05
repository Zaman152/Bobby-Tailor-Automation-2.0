"""Aggregator consolidation tests."""
from bobbytailor.pipeline.aggregator import aggregate_takeoff, normalize_item_name


def test_aggregate_flooring_two_sheets():
    items = [
        {"description": "flooring conf 106", "item_type": "flooring", "calculated_quantity": 100,
         "calculated_unit": "sq_ft", "source_sheet": "A1"},
        {"description": "floor tile open office", "item_type": "flooring", "calculated_quantity": 200,
         "calculated_unit": "sq_ft", "source_sheet": "A2"},
    ]
    out = aggregate_takeoff(items)
    flooring = [r for r in out if "Flooring" in r["item"]]
    assert len(flooring) == 1
    assert flooring[0]["quantity"] == 300


def test_companion_legend_suppresses_vision_duplicate():
    """An authoritative legend item is the sole source; vision dup is dropped."""
    items = [
        {"description": "Sealed Concrete", "item_type": "sealed_concrete",
         "calculated_quantity": 395673.42, "calculated_unit": "sq_ft",
         "qty_source": "plan_schedule_legend", "source_sheet": "A-101"},
        {"description": "Sealed Concrete for Warehouse", "item_type": "sealed_concrete",
         "calculated_quantity": 397556.0, "calculated_unit": "sq_ft",
         "qty_source": "room_profile", "source_sheet": "A-101"},
    ]
    out = aggregate_takeoff(items)
    sealed = [r for r in out if r["item"] == "Sealed Concrete"]
    assert len(sealed) == 1
    assert sealed[0]["quantity"] == 395673.42


def test_companion_legend_suppresses_base_name_variant():
    """Vision 'Columns' is dropped when legend reports 'Columns-H-35''."""
    items = [
        {"description": "Columns-H-35'", "item_type": "columns",
         "calculated_quantity": 132, "calculated_unit": "ea",
         "qty_source": "plan_schedule_legend", "source_sheet": "S-101"},
        {"description": "Columns", "item_type": "columns",
         "calculated_quantity": 140, "calculated_unit": "ea",
         "qty_source": "count", "source_sheet": "S-101"},
    ]
    out = aggregate_takeoff(items)
    cols = [r for r in out if r["item"].startswith("Columns")]
    assert len(cols) == 1
    assert cols[0]["item"] == "Columns-H-35'"
    assert cols[0]["quantity"] == 132


def test_companion_legend_keeps_unrelated_vision_items():
    """Suppression must not touch items the legend doesn't cover."""
    items = [
        {"description": "Bollards", "item_type": "bollard", "calculated_quantity": 28,
         "calculated_unit": "ea", "qty_source": "plan_schedule_legend",
         "source_sheet": "A-101"},
        {"description": "windows", "item_type": "general",
         "calculated_quantity": 7, "calculated_unit": "ea", "qty_source": "count",
         "source_sheet": "A-201"},
    ]
    out = aggregate_takeoff(items)
    names = {r["item"] for r in out}
    assert "Bollards" in names
    assert "Windows" in names


def test_normalize_guard_rail():
    name, unit = normalize_item_name("guard rail along parking", "general", "lf")
    assert name == "Guard Rail"
    assert unit == "LF"


def test_aggregate_empty():
    assert aggregate_takeoff([]) == []


def test_mobilization_injected_for_real_takeoff():
    """Mobilization is a universal estimating line item, added once."""
    items = [
        {"description": "sealed concrete", "item_type": "slab", "calculated_quantity": 1000,
         "calculated_unit": "SF", "source_sheet": "A-101"},
    ]
    out = aggregate_takeoff(items)
    mob = [r for r in out if r["item"] == "Mobilization"]
    assert len(mob) == 1
    assert mob[0]["quantity"] == 1
    assert mob[0]["unit"] == "EA"


def test_mobilization_not_injected_for_empty():
    assert all(r["item"] != "Mobilization" for r in aggregate_takeoff([]))


def test_mobilization_not_double_counted():
    """An explicit Mobilization note from the drawings must not be doubled."""
    items = [
        {"description": "sealed concrete", "item_type": "slab", "calculated_quantity": 1000,
         "calculated_unit": "SF", "source_sheet": "A-101"},
        {"description": "mobilization", "item_type": "", "calculated_quantity": 1,
         "calculated_unit": "EA", "source_sheet": "G-001"},
    ]
    out = aggregate_takeoff(items)
    mob = [r for r in out if r["item"] == "Mobilization"]
    assert len(mob) == 1
    assert mob[0]["quantity"] == 1


# ── Component-library alias resolution (manifest-resolve replacement) ──────────


def test_library_resolves_detected_name_via_alias():
    """A detected raw description binds to the plan's own library name+unit."""
    library = [
        {"name": "Doors-HM", "aliases": ["Hollow Metal Door"], "basis": "count",
         "unit": "EA", "source": "abbreviation"},
    ]
    items = [
        {"description": "exterior hollow metal door", "item_type": "component",
         "calculated_quantity": 3, "calculated_unit": "EA", "source_sheet": "A6"},
    ]
    out = aggregate_takeoff(items, library=library)
    names = {r["item"] for r in out if r["item"] != "Mobilization"}
    assert "Doors-HM" in names
    hm = next(r for r in out if r["item"] == "Doors-HM")
    assert hm["quantity"] == 3
    assert hm["source"] == "library"


# ── A library fallback never publishes an unflagged near-zero ─────────────────


def test_a_degenerate_library_reading_publishes_a_blank_not_a_number():
    """Crow shipped "Sealed Concrete 0.15 SF ... needs_review=False".

    The reading was a printed DETAIL DIMENSION (a 12" tapered slab at a dock
    leveler) pushed through the slab-volume calculator and published under an
    SF unit. A fabricated 0.15 SF is strictly worse than a blank: it is
    unflagged AND it occupies the row a real measurement would have filled.
    """
    library = [
        {"name": "Sealed Concrete", "aliases": ["concrete slab"], "basis": "area",
         "unit": "SF", "source": "abbreviation"},
    ]
    items = [
        {"description": "Concrete slab tapered thickness - dock leveler",
         "item_type": "concrete_slab", "calculated_quantity": 0.15,
         "calculated_unit": "SF", "source_sheet": "A-401"},
    ]
    row = next(
        r for r in aggregate_takeoff(items, library=library)
        if r["item"] == "Sealed Concrete"
    )
    assert row["quantity"] is None          # a BLANK, never the 0.15
    assert row["quantity_fmt"] == "—"
    assert row["needs_review"] is True
    assert row["measured"] is False
    assert row["provenance"] == "NOT MEASURED"
    assert row["source"] == "library_fallback_unmeasured"
    # The dropped reading is on the record, so this is not a silent deletion.
    assert any("BLANK, not a zero" in r for r in row["review_reasons"])
    assert any("0.15" in r for r in row["review_reasons"])


def test_a_degenerate_library_reading_is_not_summed_into_a_real_measurement():
    """Where the object WAS genuinely measured, the near-zero is dropped from
    the total and the survivor says so — it never quietly adds 0.15 SF."""
    library = [
        {"name": "Sealed Concrete", "aliases": ["concrete slab"], "basis": "area",
         "unit": "SF", "source": "abbreviation"},
    ]
    items = [
        {"description": "concrete slab", "item_type": "concrete_slab",
         "calculated_quantity": 395673.0, "calculated_unit": "SF",
         "source_sheet": "A-101"},
        {"description": "Concrete slab tapered thickness - dock leveler",
         "item_type": "concrete_slab", "calculated_quantity": 0.15,
         "calculated_unit": "SF", "source_sheet": "A-401"},
    ]
    row = next(
        r for r in aggregate_takeoff(items, library=library)
        if r["item"] == "Sealed Concrete"
    )
    assert row["quantity"] == 395673.0      # NOT 395673.15
    assert any("was NOT summed into this quantity" in r
               for r in row["review_reasons"])


def test_a_real_library_measurement_still_publishes_its_quantity():
    """The rule targets degenerate readings, not the library naming path: a
    measurable quantity is published (flagged as a naming hypothesis)."""
    library = [
        {"name": "Pipe Guardrail", "aliases": ["pipe guard rail"], "basis": "linear",
         "unit": "LF", "source": "abbreviation"},
    ]
    items = [
        {"description": "pipe guard rail at dock", "item_type": "component",
         "calculated_quantity": 46.2, "calculated_unit": "LF",
         "source_sheet": "A-401"},
    ]
    row = next(
        r for r in aggregate_takeoff(items, library=library)
        if r["item"] == "Pipe Guardrail"
    )
    assert row["quantity"] == 46.2
    assert row["provenance"] == "MEASURED"


def test_a_degenerate_count_is_untouched_by_the_measure_rule():
    """EA is counted, not dimensioned — the sub-one rule is about SF/LF/CY and
    must not reach a count that legitimately rounds to zero."""
    library = [
        {"name": "Doors-HM", "aliases": ["hollow metal door"], "basis": "count",
         "unit": "EA", "source": "abbreviation"},
    ]
    items = [
        {"description": "hollow metal door", "item_type": "component",
         "calculated_quantity": 0.4, "calculated_unit": "EA",
         "source_sheet": "A6"},
    ]
    row = next(
        r for r in aggregate_takeoff(items, library=library)
        if r["item"] == "Doors-HM"
    )
    assert row["source"] == "library"       # not the unmeasured blank path
    assert row["quantity"] == 0.0           # a measured zero stays a zero


def test_library_absent_leaves_naming_unchanged():
    """Empty/omitted library ⇒ prior static-map naming (additive-only)."""
    items = [
        {"description": "guard rail along ramp", "item_type": "component",
         "calculated_quantity": 40, "calculated_unit": "LF", "source_sheet": "C1"},
    ]
    base = aggregate_takeoff(items)
    with_empty = aggregate_takeoff(items, library=[])
    assert [r["item"] for r in base] == [r["item"] for r in with_empty]


def test_unnamed_geometry_still_flagged_after_library_merge():
    """Nothing skipped: a needs_review component the library can't name is
    still emitted and stays flagged for human review."""
    library = [
        {"name": "Doors-HM", "aliases": ["Hollow Metal Door"], "basis": "count",
         "unit": "EA", "source": "abbreviation"},
    ]
    items = [
        {"description": "unlabeled symbol cluster", "item_type": "component",
         "calculated_quantity": 7, "calculated_unit": "EA", "source_sheet": "A9",
         "needs_review": True, "review_reason": "no label bound"},
    ]
    out = aggregate_takeoff(items, library=library)
    unnamed = [r for r in out if r["item"] == "unlabeled symbol cluster"]
    assert len(unnamed) == 1
    assert unnamed[0]["quantity"] == 7
    assert unnamed[0]["needs_review"] is True

    # 23-03: the library entry that produced NO component is now enumerated as
    # an explicit blank rather than omitted. Before this, an expected item that
    # never appeared had no row of any kind in plans-only mode, so "we could
    # not measure your hollow-metal doors" and "this building has none" were
    # the same artifact (INV-08 §2 row S13).
    doors = [r for r in out if r["item"] == "Doors-HM"]
    assert len(doors) == 1
    assert doors[0]["quantity"] is None
    assert doors[0]["provenance"] == "NOT MEASURED"


# ---------------------------------------------------------------------------
# 23-03 — a blank is a blank; a measured zero is a measured zero.
#
# `aggregator.py:435` used to ship the defaultdict's 0.0 for a never-measured
# item and put "—" only in `quantity_fmt`, so every NUMERIC consumer —
# takeoff.json, the workbook exporter, scoring — read a blank as "the building
# has none of this" (INV-08 §2 row S12).
# ---------------------------------------------------------------------------

import pytest

from bobbytailor.pipeline.aggregator import aggregate_takeoff


class _Entry:
    def __init__(self, name, unit="EA", measure="count"):
        self.name = name
        self.unit = unit
        self.measure = measure


class _Manifest:
    """Minimal stand-in for object_manifest.Manifest."""

    def __init__(self, entries):
        self._entries = entries

    def resolve(self, description, unit=""):
        for e in self._entries:
            if e.name.lower() in str(description).lower():
                return e
        return None

    def missing(self, found_names):
        found = {str(n).strip().lower() for n in found_names}
        return [e for e in self._entries if e.name.strip().lower() not in found]


def _row(out, item):
    rows = [r for r in out if r["item"] == item]
    assert len(rows) == 1, "expected exactly one %r row, got %d" % (item, len(rows))
    return rows[0]


class TestQuantityIsOptional:
    def test_a_manifest_missing_item_is_none_not_zero(self):
        """`is None`, not falsy — 0.0 is falsy too, and that is the whole bug."""
        out = aggregate_takeoff([], manifest=_Manifest([_Entry("Bollards")]))
        row = _row(out, "Bollards")
        assert row["quantity"] is None
        assert row["quantity"] is not 0.0  # noqa: F632 — identity is the point
        assert row["provenance"] == "NOT MEASURED"
        assert row["measured"] is False
        assert row["quantity_fmt"] == "—"

    def test_a_measured_zero_stays_a_measured_zero(self):
        """A building with genuinely no CMU is a real, publishable finding.

        The old exporter said `float(qty or 0) <= 0 -> NOT MEASURED`, which made
        this row and the one above indistinguishable.
        """
        items = [
            {"description": "cmu wall north", "item_type": "cmu",
             "calculated_quantity": 0, "calculated_unit": "sq_ft",
             "source_sheet": "A-201"},
        ]
        row = _row(aggregate_takeoff(items), "CMU Wall")
        assert row["quantity"] == 0.0
        assert row["quantity"] is not None
        assert row["provenance"] == "MEASURED"
        assert row["measured"] is True

    def test_the_two_states_are_distinguishable_in_one_run(self):
        """Both rows in the same take-off — the whole point of the contract."""
        items = [
            {"description": "cmu wall north", "item_type": "cmu",
             "calculated_quantity": 0, "calculated_unit": "sq_ft",
             "source_sheet": "A-201"},
        ]
        out = aggregate_takeoff(items, manifest=_Manifest([_Entry("Bollards")]))
        assert _row(out, "CMU Wall")["quantity"] == 0.0
        assert _row(out, "Bollards")["quantity"] is None

    def test_every_row_carries_a_provenance_from_the_client_vocabulary(self):
        """C4 added STANDARD ITEM: the app-injected Mobilization convention
        used to publish as HUMAN INPUT, claiming a human vouched for a number
        the app made up."""
        items = [
            {"description": "flooring conf 106", "item_type": "flooring",
             "calculated_quantity": 100, "calculated_unit": "sq_ft",
             "source_sheet": "A1"},
            {"description": "unlabeled cluster", "item_type": "component",
             "calculated_quantity": 7, "calculated_unit": "ea",
             "source_sheet": "A9", "needs_review": True,
             "review_reason": "no label bound"},
        ]
        out = aggregate_takeoff(items, manifest=_Manifest([_Entry("Bollards")]))
        allowed = {
            "MEASURED", "HUMAN INPUT", "NEEDS REVIEW", "NOT MEASURED",
            "STANDARD ITEM",
        }
        assert {r["provenance"] for r in out} <= allowed
        assert all("measured" in r for r in out)
        assert _row(out, "Flooring")["provenance"] == "MEASURED"
        assert _row(out, "unlabeled cluster")["provenance"] == "NEEDS REVIEW"
        assert _row(out, "Mobilization")["provenance"] == "STANDARD ITEM"

    def test_no_row_pairs_a_none_quantity_with_a_measured_provenance(self):
        """The invariant the saved-run assertion checks (plan verification 2)."""
        items = [
            {"description": "flooring conf 106", "item_type": "flooring",
             "calculated_quantity": 100, "calculated_unit": "sq_ft",
             "source_sheet": "A1"},
        ]
        out = aggregate_takeoff(
            items,
            manifest=_Manifest([_Entry("Bollards"), _Entry("Lintels", "LF", "linear")]),
        )
        for r in out:
            if r["quantity"] is None:
                assert r["provenance"] in ("NOT MEASURED", "NEEDS REVIEW"), r
            if r["provenance"] == "MEASURED":
                assert r["quantity"] is not None, r

    def test_a_manifest_named_measurement_is_not_relabelled_as_human_input(self):
        """`source` is a NAMING marker — the aggregator's own docstring says
        quantity provenance is never altered here. A row the manifest NAMED but
        the geometry MEASURED must still read MEASURED."""
        items = [
            {"description": "bollards at storefront", "item_type": "component",
             "calculated_quantity": 12, "calculated_unit": "ea",
             "source_sheet": "C-101"},
        ]
        row = _row(aggregate_takeoff(items, manifest=_Manifest([_Entry("Bollards")])),
                   "Bollards")
        assert row["source"] == "manifest"
        assert row["quantity"] == 12
        assert row["provenance"] == "MEASURED"


class TestPlansOnlyCompleteness:
    """INV-08 S13: with no manifest, nothing enumerated what was expected."""

    def test_a_vocabulary_item_that_produced_nothing_gets_a_blank_row(self):
        library = [
            {"name": "Lintels", "aliases": ["LINTEL"], "basis": "linear",
             "unit": "LF", "source": "abbreviation"},
        ]
        items = [
            {"description": "flooring conf 106", "item_type": "flooring",
             "calculated_quantity": 100, "calculated_unit": "sq_ft",
             "source_sheet": "A1"},
        ]
        out = aggregate_takeoff(items, library=library)   # NO manifest
        row = _row(out, "Lintels")
        assert row["quantity"] is None
        assert row["provenance"] == "NOT MEASURED"
        assert row["unit"] == "LF"
        assert any("BLANK, not a zero" in r for r in row["review_reasons"])
        assert row["source"] == "expected_not_measured"

    def test_exactly_one_row_per_expected_item(self):
        library = [
            {"name": "Lintels", "basis": "linear", "unit": "LF"},
            {"name": "Lintels", "basis": "linear", "unit": "LF"},   # duplicate
        ]
        out = aggregate_takeoff([], library=library)
        assert len([r for r in out if r["item"] == "Lintels"]) == 1

    def test_an_item_that_WAS_measured_gets_no_blank_row(self):
        """The guarantee must not manufacture a second, contradictory row."""
        library = [{"name": "Flooring", "basis": "floor_area", "unit": "SF"}]
        items = [
            {"description": "flooring conf 106", "item_type": "flooring",
             "calculated_quantity": 100, "calculated_unit": "sq_ft",
             "source_sheet": "A1"},
        ]
        row = _row(aggregate_takeoff(items, library=library), "Flooring")
        assert row["quantity"] == 100
        assert row["provenance"] == "MEASURED"

    def test_a_library_entry_with_no_measure_basis_is_not_enumerated(self):
        """A basis is the app's own statement that it knows what measuring the
        item would MEAN. Without one its absence is noise, not a gap."""
        library = [{"name": "General Notes", "unit": "", "basis": ""}]
        out = aggregate_takeoff([], library=library)
        assert [r for r in out if r["item"] == "General Notes"] == []

    def test_a_weak_learned_expectation_is_not_enumerated(self):
        class _Learned:
            expected_items = [
                {"item_name": "Seen Once", "unit": "EA", "expectation": 0.1},
                {"item_name": "Seen Often", "unit": "EA", "expectation": 0.9},
            ]

            def lookup_name(self, _desc):
                return None

        out = aggregate_takeoff([], learned=_Learned())
        assert [r for r in out if r["item"] == "Seen Once"] == []
        assert _row(out, "Seen Often")["quantity"] is None

    def test_no_evidence_means_no_invented_rows(self):
        """Nothing expected, nothing measured -> the take-off stays empty."""
        assert aggregate_takeoff([]) == []


class TestLegendShadowLeavesATrace:
    def test_a_suppressed_duplicate_is_named_on_the_surviving_row(self):
        """S14: suppressing the duplicate is CORRECT — letting both through
        would silently SUM them — but the deletion was completely silent."""
        items = [
            {"description": "Sealed Concrete", "item_type": "sealed_concrete",
             "calculated_quantity": 395673.42, "calculated_unit": "sq_ft",
             "qty_source": "plan_schedule_legend", "source_sheet": "A-101"},
            {"description": "Sealed Concrete for Warehouse",
             "item_type": "sealed_concrete", "calculated_quantity": 397556.0,
             "calculated_unit": "sq_ft", "qty_source": "room_profile",
             "source_sheet": "A-101"},
        ]
        row = _row(aggregate_takeoff(items), "Sealed Concrete")
        assert row["quantity"] == pytest.approx(395673.42)
        reasons = " | ".join(row["review_reasons"])
        assert "suppressed" in reasons
        assert "Sealed Concrete" in reasons
        assert "NOT added to this quantity" in reasons

    def test_the_legend_row_is_not_flagged_by_the_trace(self):
        """The legend is authoritative. Recording the suppression must not
        turn the authoritative row into a review item.

        C4 corrected the provenance this asserted. The row carries no
        ``legend_origin``, so it is a legend the app read off the PLANS — a
        machine measurement. Asserting HUMAN INPUT here encoded the very
        conflation that published four machine-parsed door counts as
        human-vouched on a run with no human input of any kind.
        """
        items = [
            {"description": "Columns-H-35'", "item_type": "columns",
             "calculated_quantity": 132, "calculated_unit": "ea",
             "qty_source": "plan_schedule_legend", "source_sheet": "S-101"},
            {"description": "Columns", "item_type": "columns",
             "calculated_quantity": 118, "calculated_unit": "ea",
             "source_sheet": "S-101"},
        ]
        row = _row(aggregate_takeoff(items), "Columns-H-35'")
        assert row["quantity"] == 132
        assert row["needs_review"] is False
        assert row["provenance"] == "MEASURED"
        assert any("suppressed" in r for r in row["review_reasons"])

    def test_a_human_supplied_legend_still_publishes_as_human_input(self):
        """The other half of the contract: a companion take-off IS human input.

        Same row, same code path — the only difference is the marker the
        companion-take-off ingest stamps on its legend.
        """
        items = [
            {"description": "Columns-H-35'", "item_type": "columns",
             "calculated_quantity": 132, "calculated_unit": "ea",
             "qty_source": "plan_schedule_legend",
             "legend_origin": "human_input", "source_sheet": "S-101"},
        ]
        row = _row(aggregate_takeoff(items), "Columns-H-35'")
        assert row["quantity"] == 132
        assert row["provenance"] == "HUMAN INPUT"


class TestHumanInputIsEarned:
    """C4 — HUMAN INPUT means a human handed us the number, in a file.

    Crow's plans-only run — no manifest, no companion take-off, no human input
    of any kind — published FIVE rows as HUMAN INPUT: four door counts the app
    itself parsed off the plan's printed door schedule (`Doors - Steel 70`,
    `Doors - Hollow Metal 29`, `Door Frames - Hollow Metal 29`,
    `Doors - Aluminum 6`, all `source: plan_schedule_legend`) and its own
    injected Mobilization convention. Presenting machine-read data as
    human-vouched inverts the one distinction this vocabulary exists to draw.
    """

    @staticmethod
    def _crow_door_rows():
        """The four door rows verbatim from the saved paid run."""
        return [
            {"description": "Doors - Steel (door schedule)", "item_type": "doors",
             "calculated_quantity": 70, "calculated_unit": "EA",
             "qty_source": "plan_schedule_legend",
             "legend_origin": "plan_parsed", "source_sheet": "A-101"},
            {"description": "Doors - Hollow Metal (door schedule)",
             "item_type": "doors", "calculated_quantity": 29,
             "calculated_unit": "EA", "qty_source": "plan_schedule_legend",
             "legend_origin": "plan_parsed", "source_sheet": "A-101"},
            {"description": "Door Frames - Hollow Metal (door schedule)",
             "item_type": "doors", "calculated_quantity": 29,
             "calculated_unit": "EA", "qty_source": "plan_schedule_legend",
             "legend_origin": "plan_parsed", "source_sheet": "A-101"},
            {"description": "Doors - Aluminum (door schedule)",
             "item_type": "doors", "calculated_quantity": 6,
             "calculated_unit": "EA", "qty_source": "plan_schedule_legend",
             "legend_origin": "plan_parsed", "source_sheet": "A-101"},
        ]

    def test_a_manifest_free_run_reports_zero_human_input_rows(self):
        """THE C4 assertion. No manifest, no human input file => none, ever."""
        out = aggregate_takeoff(self._crow_door_rows())
        human = [r for r in out if r["provenance"] == "HUMAN INPUT"]
        assert human == [], [r["item"] for r in human]

    def test_the_plan_parsed_door_counts_publish_as_measured(self):
        """They are not merely 'not human input' — they are machine readings."""
        out = aggregate_takeoff(self._crow_door_rows())
        for name in (
            "Doors - Steel (door schedule)",
            "Doors - Hollow Metal (door schedule)",
            "Door Frames - Hollow Metal (door schedule)",
            "Doors - Aluminum (door schedule)",
        ):
            assert _row(out, name)["provenance"] == "MEASURED", name

    def test_an_absent_legend_origin_is_never_treated_as_human_input(self):
        """Fail-closed: an unmarked legend is plan-parsed, not human-vouched."""
        out = aggregate_takeoff([
            {"description": "Doors - Steel (door schedule)", "item_type": "doors",
             "calculated_quantity": 70, "calculated_unit": "EA",
             "qty_source": "plan_schedule_legend", "source_sheet": "A-101"},
        ])
        assert _row(
            out, "Doors - Steel (door schedule)"
        )["provenance"] == "MEASURED"

    def test_mobilization_is_a_standard_item_not_a_human_input(self):
        """Nobody measured it and nobody supplied it — the app injected it."""
        out = aggregate_takeoff(self._crow_door_rows())
        assert _row(out, "Mobilization")["provenance"] == "STANDARD ITEM"

    def test_a_companion_takeoff_legend_is_still_human_input(self):
        """The fix must not delete the class, only stop it being the default."""
        rows = self._crow_door_rows()
        rows[0] = dict(rows[0], legend_origin="human_input")
        out = aggregate_takeoff(rows)
        assert _row(
            out, "Doors - Steel (door schedule)"
        )["provenance"] == "HUMAN INPUT"
        # ...and it does not contaminate the sibling rows.
        assert _row(
            out, "Doors - Aluminum (door schedule)"
        )["provenance"] == "MEASURED"


class TestCompletenessDoesNotContradictItself:
    """A blank row must never appear for something the run DID measure.

    Caught by an existing naming-precedence test: a human had renamed the
    plan's site-cast-panel text, so the LEARNED name won and the library's own
    term for the same physical object never produced a bucket. Enumerating it
    would have told the client "your tilt-up walls were not measured" while the
    very same walls were published at 106,997 SF two rows above.
    """

    class _Learned:
        expected_items = []

        def __init__(self, mapping):
            self._m = mapping

        def lookup_name(self, desc):
            return self._m.get(str(desc).strip().lower())

    def test_a_renamed_library_object_is_not_also_reported_as_missing(self):
        library = [{"name": "Tilt Up Wall",
                    "aliases": ["site cast concrete panel"],
                    "basis": "wall_area", "unit": "SF"}]
        desc = "exterior site cast concrete panel"
        learned = self._Learned({desc: ("Internal Tilt up walls", "SF")})
        items = [{"description": desc, "item_type": "wall",
                  "calculated_quantity": 106997.0, "calculated_unit": "SF"}]
        out = aggregate_takeoff(items, learned=learned, library=library)

        assert _row(out, "Internal Tilt up walls")["quantity"] == 106997.0
        assert [r for r in out if r["item"] == "Tilt Up Wall"] == [], (
            "the same object must not be both measured and reported missing"
        )

    def test_a_library_object_nothing_resolved_to_is_still_enumerated(self):
        """The guard must not swallow the guarantee it protects."""
        library = [
            {"name": "Tilt Up Wall", "aliases": ["site cast concrete panel"],
             "basis": "wall_area", "unit": "SF"},
            {"name": "Lintels", "aliases": ["LINTEL"], "basis": "linear",
             "unit": "LF"},
        ]
        items = [{"description": "exterior site cast concrete panel",
                  "item_type": "wall", "calculated_quantity": 106997.0,
                  "calculated_unit": "SF"}]
        out = aggregate_takeoff(items, library=library)
        # Resolved and measured under its own library name.
        assert _row(out, "Tilt Up Wall")["quantity"] == 106997.0
        assert _row(out, "Tilt Up Wall")["provenance"] == "MEASURED"
        # Nothing resolved to Lintels, so the gap is stated rather than omitted.
        assert _row(out, "Lintels")["quantity"] is None
        assert _row(out, "Lintels")["provenance"] == "NOT MEASURED"


class TestUnitClassIsNotChangedByNaming:
    """C3b — canonicalising a NAME may not silently reclassify its UNIT.

    Crow published `Tilt Up Wall 5.0 SF`, item_type concrete_slab,
    formula "count", confidence high, needs_review false. The 5 was a COUNT of
    tilt-up panel symbols; "Tilt Up Wall" is a library object whose unit is SF,
    and the library's unit simply overwrote the reading's own. There is no
    conversion between "how many" and "how much", so the published number meant
    nothing — while the real 106,992 SF sat in the audit trail.
    """

    LIBRARY = [
        {"name": "Tilt Up Wall", "aliases": ["tilt-up concrete panel"],
         "basis": "wall_area", "unit": "SF", "source": "abbreviation"},
    ]

    def _panel_count_row(self, unit="EA"):
        return {
            "description": "tilt-up concrete panel", "item_type": "concrete_slab",
            "calculated_quantity": 5.0, "calculated_unit": unit,
            "formula": "count", "source_sheet": "A-101",
        }

    def test_a_count_never_publishes_under_an_area_unit(self):
        out = aggregate_takeoff([self._panel_count_row()], library=self.LIBRARY)
        row = _row(out, "Tilt Up Wall")
        assert row["quantity"] is None, "a BLANK, never 5.0 SF"
        assert row["quantity_fmt"] == "—"
        assert row["measured"] is False
        assert row["provenance"] == "NOT MEASURED"
        assert row["source"] == "unit_class_conflict_unmeasured"

    def test_the_withheld_reading_is_on_the_record_not_deleted(self):
        """A deletion and a zero read the same to a client."""
        out = aggregate_takeoff([self._panel_count_row()], library=self.LIBRARY)
        reasons = " | ".join(_row(out, "Tilt Up Wall")["review_reasons"])
        assert "BLANK, not a zero" in reasons
        assert "5.0 EA" in reasons          # what was actually read
        assert "count" in reasons           # ...and its class
        assert "area" in reasons            # ...vs the class it would publish in

    def test_a_real_measurement_of_the_same_object_keeps_its_quantity(self):
        """Where the object WAS measured in the right class, the conflicting
        reading is dropped from the total and the survivor says so."""
        items = [
            {"description": "tilt-up concrete panel wall",
             "item_type": "concrete_slab", "calculated_quantity": 106992.0,
             "calculated_unit": "SF", "source_sheet": "A-101"},
            self._panel_count_row(),
        ]
        row = _row(aggregate_takeoff(items, library=self.LIBRARY), "Tilt Up Wall")
        assert row["quantity"] == pytest.approx(106992.0)
        assert row["needs_review"] is True
        reasons = " | ".join(row["review_reasons"])
        assert "DIFFERENT measurement class" in reasons
        assert "NOT summed" in reasons

    def test_a_same_class_unit_rename_is_untouched(self):
        """SQ FT -> SF is a spelling, not a reclassification."""
        items = [{
            "description": "tilt-up concrete panel", "item_type": "concrete_slab",
            "calculated_quantity": 106992.0, "calculated_unit": "sq_ft",
            "source_sheet": "A-101",
        }]
        row = _row(aggregate_takeoff(items, library=self.LIBRARY), "Tilt Up Wall")
        assert row["quantity"] == pytest.approx(106992.0)
        assert row["unit"] == "SF"

    def test_an_unrecognised_unit_is_never_guessed_into_a_conflict(self):
        """A wrong guess would BLANK a good quantity — worse than the defect."""
        library = [
            {"name": "Novel Object", "aliases": ["novel thing"],
             "basis": "area", "unit": "ROLLS", "source": "abbreviation"},
        ]
        items = [{
            "description": "novel thing", "item_type": "component",
            "calculated_quantity": 9.0, "calculated_unit": "EA",
            "source_sheet": "A-101",
        }]
        row = _row(aggregate_takeoff(items, library=library), "Novel Object")
        assert row["quantity"] == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# 24-03 Task 1 — the canonical name FORM folds a trailing plural, and NOTHING
# else.
#
# The two saved paid Crow runs published the SAME 56-EA candidate as `Bollard`
# (source: learned) in one and `Dock Bumper` (source: library) in the other,
# with a blank `Bollards` row (source: expected_not_measured) sitting beside it
# in BOTH. A client reading that report sees a measured object next to a blank
# row for what is plausibly the same object and concludes the bollards were not
# found — strictly worse than either row alone (24-RESEARCH §4.3.4).
#
# `canonical_library_name`'s docstring is explicit that it normalises the FORM
# of one item's name and NEVER renames one item to another. That boundary is
# correct and is not being loosened here: a trailing plural is a form
# transformation of exactly the same class as the spacing/case folding the
# function already performs. A SYNONYM matcher is a rename, and is how
# `Dock Bumper` would silently become `Bollards` — a worse defect than the
# split it would appear to fix (24-RESEARCH pitfall 5). The negative test below
# is load-bearing and lives on its own so it cannot be quietly deleted
# alongside a refactor of its neighbours.
# ---------------------------------------------------------------------------

from bobbytailor.pipeline.aggregator import (  # noqa: E402
    _norm_item_key,
    _plural_stem,
    canonical_library_name,
)


def test_canonical_plural_folding_binds_the_singular_library_spelling():
    """`Bollard` is the same object as ITEM_NAME_MAP's `Bollards`.

    The map's unit is applied only because the caller supplied none — a caller
    that states a unit keeps it, exactly as before this change.
    """
    assert canonical_library_name("Bollard", "") == ("Bollards", "EA")
    assert canonical_library_name("Bollard", "LF") == ("Bollards", "LF")


def test_canonical_plural_folding_is_idempotent():
    """Folding twice equals folding once — the plural spelling is a fixed point."""
    once = canonical_library_name("Bollards", "")
    assert once == ("Bollards", "EA")
    assert canonical_library_name(once[0], "") == once


def test_canonical_never_renames_dock_bumper_into_bollards():
    """THE load-bearing negative. A synonym is not a plural.

    `Dock Bumper` matches ITEM_NAME_MAP's ``dock.*bumper`` rule, whose canonical
    form is `Dock Leveler`. Those are two different objects and the function's
    own contract forbids the rewrite. If this test ever fails, the folding rule
    has become a synonym mapper and a genuinely distinct object is disappearing
    from client reports.
    """
    assert canonical_library_name("Dock Bumper", "EA") == ("Dock Bumper", "EA")
    assert canonical_library_name("Dock Bumper", "EA")[0] != "Bollards"
    assert canonical_library_name("Dock Bumper", "EA")[0] != "Dock Leveler"


def test_canonical_never_renames_a_stem_that_differs_by_more_than_a_plural():
    """`Metal Stair` is not ITEM_NAME_MAP's `Stairs`; novel vocabulary is verbatim."""
    assert canonical_library_name("Metal Stair", "EA") == ("Metal Stair", "EA")
    assert canonical_library_name("Metal Stairs", "EA") == ("Metal Stairs", "EA")
    assert canonical_library_name("Fiber Cement Panel", "SF") == (
        "Fiber Cement Panel", "SF")
    # ...and the pre-existing spacing/case folding is untouched.
    assert canonical_library_name("Guardrail", "LF") == ("Guard Rail", "LF")


def test_canonical_folding_never_collapses_a_name_to_nothing():
    """A degenerate name is returned verbatim rather than stemmed into nothing."""
    assert canonical_library_name("S", "EA") == ("S", "EA")
    assert canonical_library_name("", "EA") == ("", "EA")
    assert canonical_library_name("  ", "EA") == ("  ", "EA")
    assert _plural_stem("") == ""
    assert _plural_stem("s") == "s"
    assert _plural_stem("as") == "as"
    assert _plural_stem("gas") == "gas"      # too short to be a plural of "ga"


def test_the_plural_stem_is_a_pure_suffix_rule_with_no_lexicon():
    """Both spellings reduce to ONE stem; a non-plural `s` ending is protected."""
    assert _plural_stem("bollards") == _plural_stem("bollard")
    assert _plural_stem("stairs") == _plural_stem("stair")
    assert _plural_stem("downspouts") == _plural_stem("downspout")
    assert _plural_stem("boxes") == _plural_stem("box")
    assert _plural_stem("arches") == _plural_stem("arch")
    # A singular that merely ENDS in s is not a plural of anything.
    assert _plural_stem("glass") == "glass"
    assert _plural_stem("truss") == "truss"
    assert _plural_stem("radius") == "radius"
    assert _plural_stem("axis") == "axis"
    # Two genuinely different words never share a stem.
    assert _plural_stem("bollard") != _plural_stem("dockbumper")


def test_norm_item_key_folds_singular_and_plural_into_one_bucket():
    """The bucket identity that decides whether two rows are ONE item."""
    assert _norm_item_key("Bollard") == _norm_item_key("Bollards")
    assert _norm_item_key("Metal Downspout") == _norm_item_key("Metal Downspouts")
    assert _norm_item_key("Metal Stair") == _norm_item_key("Metal Stairs")
    # Case and separator folding still works exactly as before.
    assert _norm_item_key("guard-rail") == _norm_item_key("Guard Rail")


def test_norm_item_key_keeps_two_genuinely_different_objects_apart():
    """The fold must not become a merge."""
    assert _norm_item_key("Dock Bumper") != _norm_item_key("Bollards")
    assert _norm_item_key("Doors-HC") != _norm_item_key("Doors-SC")
    assert _norm_item_key("CMU Wall") != _norm_item_key("CMU Paint")
    assert _norm_item_key("Glass") != _norm_item_key("Glas")
