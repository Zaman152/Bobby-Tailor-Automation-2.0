"""29-14 — a --repro pair is two runs of ONE project, not two projects.

The reproducibility gate reported rows appearing and disappearing between
identical Bob's runs. They were not appearing and disappearing; they were being
RENAMED, and a name-keyed diff cannot tell those apart:

    run A   'Gypsum Board Ceiling / Soffit'   56046.7 SF
    run B   'Gypsum Board Ceiling'            56046.7 SF

Same measurement, different label. Likewise 'Suspended Acoustical Ceiling' vs
'Suspended Acoustic Ceiling Grid', and 'Exhaust Fan and Curb' vs 'Exhaust Fan'.

The cause was in the HARNESS, not the engine. ``run_vision`` built the project
name as ``f"VisionOnly {name}{run_tag}"``, so run 2 ran under a DIFFERENT
project key and 24-05's vocabulary snapshot — which exists precisely so a
repeat run reuses the object list the first run derived — could not be reused.
The AI naming pass therefore re-derived every object name from scratch. The
learning store still carries the evidence: both
``VisionOnly Bobs_Plans_Manifest`` (29 objects) and
``VisionOnly Bobs_Plans_Manifest run2`` (27 objects) were written on
2026-08-17.

So the gate was measuring COLD-START naming variance on every pair, never the
repeat run a customer actually performs. These tests pin both halves: the
harness asks about one project, and the store hands the same names back.

Free. No API, no fixtures, no paid marker.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from bobbytailor.learning.store import (
    VOCAB_KIND_NAMING_CONVENTIONS,
    load_project_vocabulary,
    save_project_vocabulary,
)

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "scripts" / "vision_only_benchmark.py"

_PROBE_KEY = "ZZ Phase29 Repro Probe"


def _clear_probe():
    db = ROOT / "output" / "learning.db"
    if not db.exists():
        return
    try:
        con = sqlite3.connect(str(db))
        con.execute(
            "DELETE FROM learning_project_vocabulary WHERE project_key=?",
            (_PROBE_KEY,),
        )
        con.commit()
        con.close()
    except sqlite3.Error:
        pass


# ── the harness half ─────────────────────────────────────────────────────────


def test_the_repro_pair_runs_under_one_project_name():
    """``run_tag`` may label output; it may NOT key the project.

    This is the whole defect in one line. Restoring the tag here makes run 2 a
    different project again, the vocabulary snapshot stops being reused, and the
    gate goes back to measuring cold-start naming variance.
    """
    src = BENCH.read_text(encoding="utf-8")
    call = re.search(r"project_name=f\"VisionOnly \{name\}([^\"]*)\"", src)
    assert call is not None, "the project_name call site moved — re-read run_vision"
    assert call.group(1) == "", (
        "project_name carries %r. A --repro pair must be two runs of the SAME "
        "project, or 24-05's vocabulary snapshot cannot be reused and the gate "
        "measures naming variance instead of reproducibility." % call.group(1)
    )


def test_the_decoy_probe_asks_about_the_same_project():
    """The isolation probe must name the project the run actually uses."""
    src = BENCH.read_text(encoding="utf-8")
    probe = re.search(r"discover_manifest_path\(f\"VisionOnly \{name\}([^\"]*)\"\)", src)
    assert probe is not None, "the decoy discovery probe moved"
    assert probe.group(1) == "", (
        "the decoy probe asks about %r while the run uses the untagged name — "
        "the tripwire would then test a project that never runs" % probe.group(1)
    )


# ── the store half ───────────────────────────────────────────────────────────


def test_a_second_run_of_one_project_gets_the_first_run_s_names():
    """The mechanism the harness was defeating, asserted directly."""
    _clear_probe()
    try:
        first = [
            {"canonical_name": "Gypsum Board Ceiling / Soffit",
             "aliases": ["gyp ceiling"], "basis": "area"},
            {"canonical_name": "Suspended Acoustical Ceiling",
             "aliases": ["act"], "basis": "area"},
        ]
        saved = save_project_vocabulary(
            _PROBE_KEY, first, kind=VOCAB_KIND_NAMING_CONVENTIONS
        )
        assert saved == 2, "the snapshot did not store; reuse cannot be asserted"

        reloaded = [
            o.get("canonical_name")
            for o in load_project_vocabulary(
                _PROBE_KEY, VOCAB_KIND_NAMING_CONVENTIONS
            )
        ]
        assert reloaded == [o["canonical_name"] for o in first], (
            "a repeat run of the SAME project did not get the first run's names "
            "back — reuse is what makes a repeat run reproducible"
        )
    finally:
        _clear_probe()


def test_a_different_project_key_gets_nothing_back():
    """Scoping is what the fix depends on, and it must stay exact.

    If a near-miss key inherited a snapshot, the harness bug would have been
    invisible — run 2 would have reused run 1's vocabulary despite the tag.
    """
    _clear_probe()
    try:
        save_project_vocabulary(
            _PROBE_KEY, [{"canonical_name": "Roof Curb", "basis": "count"}],
            kind=VOCAB_KIND_NAMING_CONVENTIONS,
        )
        assert load_project_vocabulary(
            _PROBE_KEY + " run2", VOCAB_KIND_NAMING_CONVENTIONS
        ) == [], "a tagged key inherited another project's snapshot"
    finally:
        _clear_probe()
