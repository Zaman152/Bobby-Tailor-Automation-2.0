"""Phase 2: manifest-driven targeted counting + tiled recount."""
from object_manifest import Manifest, ManifestEntry
from takeoff_pipeline import TakeoffPipeline, _build_count_hint


def _manifest():
    return Manifest([
        ManifestEntry("Bollards", "EA", aliases=["bollard", "pipe bollard"], measure="count"),
        ManifestEntry("Columns", "EA", aliases=["column"], measure="count"),
        ManifestEntry("CMU Wall", "SF", aliases=["cmu"], measure="area"),
    ])


def test_count_hint_none_without_manifest():
    assert _build_count_hint(None) is None


def test_count_hint_lists_only_count_objects():
    hint = _build_count_hint(_manifest())
    assert hint is not None
    assert "Bollards" in hint and "Columns" in hint
    assert "pipe bollard" in hint
    # Area object must not be in the targeted-count hint.
    assert "CMU Wall" not in hint


def test_tiled_recount_recovers_missing_object(monkeypatch):
    m = _manifest()

    # Full-sheet pass missed Bollards entirely (none in components).
    full = {"components": [{"name": "Column", "quantity": 5, "unit": "ea"}]}

    # Mock analyzer: each tile reports a few bollards; columns already found so
    # they should NOT be re-added (only 'missing' objects are targeted).
    tile_counts = iter([3, 4, 2, 2])  # 2x2 grid -> sum 11

    def fake_analyzer(path, sheet, pass_type=None, model_override=None,
                      sheet_type=None, user_hint=None):
        return {"components": [
            {"name": "bollard", "quantity": next(tile_counts), "unit": "ea"},
        ]}

    pipe = TakeoffPipeline(analyzer=fake_analyzer)
    pipe._manifest = m
    monkeypatch.setattr(TakeoffPipeline, "_render_tile",
                        staticmethod(lambda *a, **k: "/tmp/__nonexistent_tile__.png"))

    out = pipe._tiled_recount(full, "x.pdf", 0, "A1", "floor_plan", None)
    bollards = [c for c in out["components"] if c["name"] == "Bollards"]
    assert bollards, out["components"]
    assert bollards[0]["quantity"] == 11
    assert bollards[0]["confidence"] == "low"
    # Columns were already found -> not targeted -> unchanged single entry.
    cols = [c for c in out["components"] if c.get("name", "").lower().startswith("column")]
    assert len(cols) == 1


def test_tiled_recount_noop_when_all_found(monkeypatch):
    m = _manifest()
    full = {"components": [
        {"name": "bollard", "quantity": 10, "unit": "ea"},
        {"name": "column", "quantity": 5, "unit": "ea"},
    ]}

    def fake_analyzer(*a, **k):
        raise AssertionError("analyzer should not be called when nothing is missing")

    pipe = TakeoffPipeline(analyzer=fake_analyzer)
    pipe._manifest = m
    monkeypatch.setattr(TakeoffPipeline, "_render_tile",
                        staticmethod(lambda *a, **k: "/tmp/__nonexistent_tile__.png"))
    out = pipe._tiled_recount(full, "x.pdf", 0, "A1", "floor_plan", None)
    assert out is full or out["components"] == full["components"]
