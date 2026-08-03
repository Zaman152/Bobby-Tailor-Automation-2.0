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

    def test_every_row_carries_a_provenance_from_the_four_value_vocabulary(self):
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
        allowed = {"MEASURED", "HUMAN INPUT", "NEEDS REVIEW", "NOT MEASURED"}
        assert {r["provenance"] for r in out} <= allowed
        assert all("measured" in r for r in out)
        assert _row(out, "Flooring")["provenance"] == "MEASURED"
        assert _row(out, "unlabeled cluster")["provenance"] == "NEEDS REVIEW"

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
        turn the authoritative row into a review item."""
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
        assert row["provenance"] == "HUMAN INPUT"
        assert any("suppressed" in r for r in row["review_reasons"])


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
