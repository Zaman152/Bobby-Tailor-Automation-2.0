"""Tests for shared deterministic plan-layer legend building.

21-15 contract: production is plans-only. ``build_deterministic_legends`` and
``build_deterministic_legends_from_run_dir`` accept explicit ``dev_*`` kwargs
only — the ``companion_present`` production parameter is gone, and the
manifest-driven footprint legend is a dev/benchmark branch.
"""
import inspect
import json
from pathlib import Path

from bobbytailor.deterministic.plan_deterministic_legends import (
    build_deterministic_legends,
    build_deterministic_legends_from_run_dir,
    inject_project_legends,
    merge_page_pdfs,
)


def test_inject_legends_prefers_floor_plan():
    legends = [{"name": "L", "rows": [{"ITEM": "X", "QTY": "1", "UNIT": "SF"}]}]
    extracted = [
        {"_sheet_type": "elevation", "_sheet_name": "A-201", "schedules": []},
        {"_sheet_type": "floor_plan", "_sheet_name": "A-101", "schedules": []},
    ]
    inject_project_legends(extracted, legends)
    assert extracted[0].get("_companion_legend_injected") is not True
    assert len(extracted[1]["schedules"]) == 1
    assert extracted[1]["_companion_legend_injected"] is True


def test_inject_legends_only_once():
    legends = [{"name": "L", "rows": [{"ITEM": "X", "QTY": "1", "UNIT": "SF"}]}]
    extracted = [
        {"_sheet_type": "floor_plan", "_sheet_name": "A-101", "schedules": []},
        {"_sheet_type": "floor_plan", "_sheet_name": "A-111", "schedules": []},
    ]
    inject_project_legends(extracted, legends)
    assert extracted[0]["_companion_legend_injected"] is True
    assert extracted[1].get("_companion_legend_injected") is not True


def test_merge_page_pdfs_single_copy(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 minimal")  # not valid pdf but merge skips small
    out = tmp_path / "out.pdf"
    # Too small — merge_page_pdfs filters < 500 bytes
    assert merge_page_pdfs([src], out) is None


# ---------------------------------------------------------------------------
# 21-15: plans-only production signature + dev-kwarg gating
# ---------------------------------------------------------------------------

def test_signatures_have_no_companion_present_param():
    """The production parameter `companion_present` is gone (renamed dev kwarg)."""
    for fn in (build_deterministic_legends, build_deterministic_legends_from_run_dir):
        params = inspect.signature(fn).parameters
        assert "companion_present" not in params, fn.__name__
        assert "manifest" not in params, fn.__name__
        assert params["dev_manifest"].default is None, fn.__name__
        assert params["dev_companion_present"].default is False, fn.__name__


def _patch_extractors(monkeypatch, calls):
    """Stub the lazy-imported door + footprint extractors with recorders."""
    from bobbytailor.deterministic import footprint_takeoff
    from bobbytailor.deterministic import schedule_extraction

    def fake_door(pdf_path):
        calls.append(("door", pdf_path))
        return {"name": "Door Schedule", "rows": [{"ITEM": "D1"}]}

    def fake_footprint(pdf_path, manifest):
        calls.append(("footprint", manifest))
        return {"name": "Footprint", "rows": [{"ITEM": "Slab"}]}

    monkeypatch.setattr(schedule_extraction, "extract_door_legend_from_pdf", fake_door)
    monkeypatch.setattr(footprint_takeoff, "extract_footprint_legend", fake_footprint)


def test_production_default_is_plans_only_no_footprint(monkeypatch):
    """Default call: door schedule only; footprint (manifest-required) never runs."""
    calls = []
    _patch_extractors(monkeypatch, calls)
    legends = build_deterministic_legends("/fake/plans.pdf")
    assert [c[0] for c in calls] == ["door"]
    assert len(legends) == 1
    assert legends[0]["name"] == "Door Schedule"


def test_dev_manifest_enables_footprint_branch(monkeypatch):
    """Explicit dev_manifest gates the footprint legend in (dev/benchmark only)."""
    calls = []
    _patch_extractors(monkeypatch, calls)
    sentinel_manifest = object()
    legends = build_deterministic_legends(
        "/fake/plans.pdf", dev_manifest=sentinel_manifest,
    )
    assert ("footprint", sentinel_manifest) in calls
    assert {l["name"] for l in legends} == {"Door Schedule", "Footprint"}


def test_dev_companion_present_skips_footprint(monkeypatch):
    """Benchmark scenario: companion carries exact areas — footprint skipped."""
    calls = []
    _patch_extractors(monkeypatch, calls)
    legends = build_deterministic_legends(
        "/fake/plans.pdf", dev_manifest=object(), dev_companion_present=True,
    )
    assert [c[0] for c in calls] == ["door"]
    assert {l["name"] for l in legends} == {"Door Schedule"}


def test_from_run_dir_reads_blobs_dir(tmp_path, monkeypatch):
    """Per-page blobs under run_dir/blobs/ are the canonical scan location."""
    import fitz

    run_dir = tmp_path / "run"
    blob_dir = run_dir / "blobs"
    blob_dir.mkdir(parents=True)
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    # Enough real content to clear merge_page_pdfs' 500-byte size filter.
    for i in range(20):
        page.insert_text((10, 10 + i * 9), f"FLOOR PLAN NOTE LINE {i}")
    doc.save(str(blob_dir / "1001.pdf"))
    doc.close()

    calls = []
    _patch_extractors(monkeypatch, calls)
    legends = build_deterministic_legends_from_run_dir(run_dir)
    assert [c[0] for c in calls] == ["door"]
    assert len(legends) == 1
    assert (run_dir / "_plans_combined.pdf").is_file()


def test_from_run_dir_falls_back_to_legacy_pdfs_dir(tmp_path, monkeypatch):
    """Resumed pre-21-15 runs (pdfs/ layout) still build legends."""
    import fitz

    run_dir = tmp_path / "run"
    pdf_dir = run_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    # Enough real content to clear merge_page_pdfs' 500-byte size filter.
    for i in range(20):
        page.insert_text((10, 10 + i * 9), f"FLOOR PLAN NOTE LINE {i}")
    doc.save(str(pdf_dir / "1001.pdf"))
    doc.close()

    calls = []
    _patch_extractors(monkeypatch, calls)
    legends = build_deterministic_legends_from_run_dir(run_dir)
    assert [c[0] for c in calls] == ["door"]
    assert len(legends) == 1
