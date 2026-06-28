"""Phase 4: measurement hint + manifest-driven wall height."""
from object_manifest import Manifest, ManifestEntry
from takeoff_pipeline import _build_measure_hint, _manifest_wall_height
from calculator import _calculate_from_room


def _manifest():
    return Manifest([
        ManifestEntry("CMU Wall", "SF", aliases=["cmu"], measure="area",
                      assumptions={"height_ft": 24.0}),
        ManifestEntry("Gas Piping", "LF", aliases=["gas line"], measure="length"),
        ManifestEntry("Bollards", "EA", measure="count"),
    ])


def test_measure_hint_none_without_manifest():
    assert _build_measure_hint(None) is None


def test_measure_hint_lists_area_and_length_only():
    hint = _build_measure_hint(_manifest())
    assert hint is not None
    assert "CMU Wall" in hint
    assert "Gas Piping" in hint
    assert "height_ft=24" in hint
    # Count object excluded from the measure hint.
    assert "Bollards" not in hint


def test_manifest_wall_height_uses_max_assumption():
    assert _manifest_wall_height(_manifest()) == 24.0


def test_manifest_wall_height_default_without_manifest():
    assert _manifest_wall_height(None) == 9.0


def test_room_wall_area_uses_supplied_height():
    rows_default = _calculate_from_room(
        {"name": "Rm", "area": "400", "notes": "paint walls"}, "A1", "auto", 9.0)
    rows_tall = _calculate_from_room(
        {"name": "Rm", "area": "400", "notes": "paint walls"}, "A1", "auto", 24.0)

    def _paint_qty(rows):
        r = next(x for x in rows if x["item_type"] == "paint")
        return r["raw_value"]  # wall_area fed into the paint formula

    # Taller walls -> larger wall area fed to the paint estimate.
    assert _paint_qty(rows_tall) > _paint_qty(rows_default)
