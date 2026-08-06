#!/usr/bin/env python3
"""Author the two determinism-differential replay fixture sets — ZERO API (24-09).

**Every fixture key in ``tests/replay_analyzer.py`` is a SHA256 over
``(model, pass_type, prompt text, image count)``.** All four move when a prompt,
a schema or a render changes: plan 24-07 changed the semantic schema, the symbol
prompt AND the image count on room-heavy sheets, which is why the fixtures had
to be authored last in the phase. A fixture authored against an earlier prompt
hashes to a key nothing will ever request, and the differential gate would then
pass for having looked at nothing — the exact failure
``tests/test_phase23_acceptance.py`` rule 3 forbids.

So the fixtures are not hand-typed. **This script IS the authoring procedure**,
and it is committed so the next prompt edit can regenerate them in one command
instead of stranding them::

    python3 scripts/author_replay_fixtures.py            # rewrite both sets
    python3 scripts/author_replay_fixtures.py --check    # report drift, write nothing

It works by driving the deterministic half of the pipeline over the real Crow
plan set with a *responder* analyzer: an analyzer that answers each structured
request from the saved paid runs' own observed names, records the key that
request resolved to, and writes the pair out. Because the responder is a pure
function of ``(variant, pass_type, schema)``, the key it recorded is by
construction the key the pipeline will ask for at replay time.

**No API call is made and no credential is read.** ``REPLAY_RECORD`` is never
set — the record path in ``ReplayAnalyzer`` wraps the REAL analyzer and is
developer-invoked only. Nothing here touches it.

WHAT VARIES, AND WHAT DOES NOT
------------------------------

A differential varies the ANSWER and holds the REQUEST fixed. That is not
pedantry here: the project naming-convention pass's answer becomes the label
enum of the *next* request (``run_project`` → ``_project_vocab_labels`` →
``legend_labels`` → ``symbol_gallery_schema``). Varying it would change the
symbol pass's prompt, hence its SHA256, hence which fixture is even addressed —
two experiments at once, and two disjoint key sets. So:

* **Fixed across both variants:** the PDF, the deterministic geometry, every
  prompt, every schema, the image count, and the project naming-convention
  answer (the schema-legal empty object list, which leaves ``run_project`` on
  its deterministic component library — the run-to-run-identical naming source
  harvested from the plan's own printed text).
* **Varied between the variants:** the per-sheet LABEL answers — the semantic
  pass's wall-class labels and the symbol pass's per-cluster labels — drawn
  from the two saved paid runs' own published object names.

The naming-library variance the two runs actually exhibit (24-RESEARCH defect
F3) is therefore explicitly OUT of this gate's scope, for the reason above.
Plan 24-05's per-project vocabulary persistence is what stabilises it.

PROVENANCE, AND THE GAP THAT IS RECORDED RATHER THAN INVENTED
-------------------------------------------------------------

Every fixture carries a ``provenance`` block naming the saved run it was
reconstructed from and the field of that run's output it was derived from.
Assumption A2 (24-RESEARCH) rated that recoverability MEDIUM. The honest
outcome, recorded here and in the plan summary:

* **RECOVERED.** Each run's object-name library is fully recoverable from its
  ``takeoff_summary``: the ``library`` / ``learned`` / ``expected_not_measured``
  rows ARE that run's object list, with the unit each object was expected in.
* **RECOVERED.** Which clusters a run named and which it left as a raw
  ``SYM-``/``WALL-``/``ROOM-`` identifier is readable straight off
  ``raw_line_items`` — a raw identifier in the description column is precisely
  "this run could not name it".
* **NOT RECOVERED — a documented gap.** Neither saved run records the naming
  library's ``basis`` / ``binding_hint`` / ``aliases`` / ``thickness_in`` /
  ``height_ft``, nor the raw response of the naming-convention pass. Those are
  NOT invented to complete the set: the naming-convention fixture is the
  schema-legal EMPTY object list in both variants, which is a real answer the
  pipeline already handles (it falls back to the deterministic library), and it
  is identical in both variants so it can contribute nothing to the
  differential either way.

Nothing under ``.planning/paid-run-evidence/`` is written to. It is opened
read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── The fixed inputs ─────────────────────────────────────────────────────────

CROW_PDF = ROOT / "uploads" / "Crow - Cass White Road-Plans.pdf"

#: The sheet the differential runs over. Crow's A-101 is the phase's whole
#: subject: it is the only VECTOR sheet in the set (geometry proposes, vision
#: only labels), it carries all 36 symbol clusters, all 13 wall classes and
#: every room candidate, and it is the sheet whose 56-EA candidate published as
#: ``Bollard`` in one run and ``Dock Bumper`` in the next. The remaining three
#: sheets reach the LEGACY vision path, where a pass returns identification and
#: quantity inside one object with no seam — varying those answers would vary
#: QUANTITIES, which this phase's contract forbids and which 24-08 excluded from
#: voting for exactly the same reason.
CROW_PAGE_INDEX = 0

PAID_RUN_EVIDENCE = ROOT / ".planning" / "paid-run-evidence"
RUN_DIRS = {
    "variant_a": "VisionOnly_P23V_Crow_20260804_141952",
    "variant_b": "VisionOnly_P23V2_Crow_20260804_181352",
}
RUN_LABELS = {"variant_a": "14:19 run", "variant_b": "18:13 run"}

FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "replay"
VARIANTS = ("variant_a", "variant_b")

#: A run's object library lives in the summary rows carrying one of these
#: sources. ``expected_not_measured`` is as much a library entry as ``library``
#: is — it is an object the run KNEW about and did not measure, which is exactly
#: the record 24-06's ledger exists to keep visible.
_LIBRARY_SOURCES = ("library", "learned", "expected_not_measured")

#: A description that is a bare candidate identifier means the run could not
#: name that candidate. Read as evidence, never as a name.
_RAW_ID_PREFIXES = ("SYM-", "WALL-", "ROOM-", "R-")


# ── Reading the saved runs (READ-ONLY) ───────────────────────────────────────


def _takeoff(variant: str) -> dict:
    path = PAID_RUN_EVIDENCE / RUN_DIRS[variant] / "takeoff.json"
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_present() -> bool:
    """True when both saved runs are on disk. Absence must SKIP, never pass."""
    return all(
        (PAID_RUN_EVIDENCE / RUN_DIRS[v] / "takeoff.json").exists() for v in VARIANTS
    )


def observed_object_names(variant: str) -> List[Tuple[str, str]]:
    """``[(canonical_name, unit)]`` — the run's own object library, in file order.

    Derived from ``takeoff_summary``: every row whose ``source`` is one of
    :data:`_LIBRARY_SOURCES`. That set IS the naming library the run carried,
    which is why the two runs' lists differ at all (defect F3).
    """
    out: List[Tuple[str, str]] = []
    seen = set()
    for row in _takeoff(variant).get("takeoff_summary") or []:
        if row.get("source") not in _LIBRARY_SOURCES:
            continue
        name = (row.get("item") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append((name, (row.get("unit") or "").strip()))
    return out


def observed_names_matching(variant: str, *needles: str) -> List[str]:
    """The run's own object names containing any of *needles* (case-folded).

    The differential's labels are READ from the evidence at runtime rather than
    typed into this file, so a fixture can never claim a name the run did not
    actually publish.
    """
    lowered = tuple(n.lower() for n in needles)
    return [
        name
        for name, _unit in observed_object_names(variant)
        if any(n in name.lower() for n in lowered)
    ]


def unnamed_candidate_ids(variant: str) -> List[str]:
    """Candidate IDs the run published under their RAW identifier.

    A ``raw_line_items`` description of ``SYM-6`` is the run stating, in its own
    artifact, that it measured that cluster and could not name it.
    """
    out = []
    for row in _takeoff(variant).get("raw_line_items") or []:
        desc = (row.get("description") or "").strip()
        if any(desc.startswith(p) for p in _RAW_ID_PREFIXES):
            out.append(desc)
    return sorted(set(out))


# ── The responder: one answer per request, per variant ───────────────────────


def _enum_of(schema: dict, *path: str) -> List[str]:
    """The enum list at ``properties/<p0>/items/properties/<p1>/enum``."""
    node = schema or {}
    for i, key in enumerate(path):
        node = (node.get("properties") or {}).get(key) or {}
        if i < len(path) - 1:
            node = node.get("items") or {}
    return list(node.get("enum") or [])


def semantic_answer(schema: dict, variant: str) -> dict:
    """The semantic pass's answer: region + wall-class labels, per variant.

    The two saved runs did not disagree about the wall-class label TEXT — both
    named their tilt-up class ``Tilt Up Wall``. The recorded variance is in the
    ASSIGNMENT, so the assignment is what this inverts, following the committed
    precedent of ``tests/test_fusion.py::test_wall_class_label_invariance``
    (24-02). Both names are read from the runs' own published object lists.
    """
    wall_ids = sorted(_enum_of(schema, "wall_classes", "wall_class_id"))
    region_ids = sorted(_enum_of(schema, "regions", "region_id"))

    tilt = (observed_names_matching(variant, "tilt up wall") or ["Tilt Up Wall"])[0]
    cmu = (observed_names_matching(variant, "cmu wall") or ["CMU Wall"])[0]
    # THE FLIP: the same two observed names, assigned the other way round.
    first, second = (tilt, cmu) if variant == "variant_a" else (cmu, tilt)

    wall_classes = []
    for i, cid in enumerate(wall_ids[:2]):
        wall_classes.append({
            "wall_class_id": cid,
            "label": first if i == 0 else second,
            "confidence": "medium",
        })
    # Every other wall class is ABSENT from the answer, not labelled with a
    # placeholder. Both runs published those classes under their raw WALL-TC
    # identifier, which is the run saying it could not name them.

    regions = [
        {
            "region_id": rid,
            "is_main_plan": rid == (region_ids[0] if region_ids else ""),
            "confidence": "high",
        }
        for rid in region_ids
    ]
    return {
        "wall_classes": wall_classes,
        "regions": regions,
        # Both runs published ROOM-3..6 under their raw identifiers: no room
        # was named in either run, so no room is named in either variant.
        "rooms": [],
        "confidence": "medium",
    }


def symbol_answer(schema: dict, variant: str) -> dict:
    """The symbol pass's answer: the unknown sentinel for every marked cluster.

    That is not a placeholder — it is what BOTH saved runs observably answered.
    Every symbol row in both artifacts is a raw ``SYM-`` identifier except the
    single cluster the naming LIBRARY named (``Bollard`` in one run,
    ``Dock Bumper`` in the other), and that cluster carries a recorded text
    absence, so 24-07 excludes it from this request entirely. This pass bound
    nothing in either run, and the fixture says so rather than inventing a bind.

    **Consequence, stated rather than glossed:** this pass is therefore
    IDENTICAL across the two variants and contributes nothing to the varied
    half of the differential. It is not inert — it is consumed on every run, and
    the gate asserts the excluded cluster is ledgered in both variants and named
    in neither, which is the phase's central defect asserted end to end.

    It is deliberately NOT varied by inventing two different enum labels for one
    marked cluster. The pipeline makes no claim that a marked, text-anchored
    cluster the model names differently publishes the same — the model's word is
    what names it, which is exactly why the phase's answer is to only ASK about
    candidates the drawing itself names. Varying it here would manufacture a
    failure the codebase never promised to prevent.
    """
    ids = _enum_of(schema, "matches", "symbol_id")
    labels = _enum_of(schema, "matches", "label")
    unknown = "unknown" if "unknown" in labels else (labels[-1] if labels else "")
    return {
        "matches": [
            {"symbol_id": sid, "label": unknown, "confidence": "low"}
            for sid in sorted(ids, key=lambda s: (len(s), s))
        ]
    }


def naming_conventions_answer(schema: dict, variant: str) -> dict:
    """The project naming-convention pass — the schema-legal EMPTY object list.

    Identical in both variants, deliberately. See the module docstring: this
    answer becomes the NEXT request's label enum, so varying it would vary the
    request rather than the answer, split the two variants onto disjoint fixture
    keys, and test two things at once. The empty list is a real answer the
    pipeline already handles — it leaves ``run_project`` on the deterministic
    component library harvested from the plan's own printed text.

    It is also the documented GAP: neither saved run records this pass's
    response, and the response is NOT invented to fill the hole.
    """
    return {"objects": []}


_RESPONDERS: Dict[str, Callable[[dict, str], dict]] = {
    "semantic": semantic_answer,
    "symbol_gallery": symbol_answer,
    "naming_conventions": naming_conventions_answer,
}


def _provenance(pass_type: str, variant: str) -> dict:
    common = {
        "authored_by": "scripts/author_replay_fixtures.py",
        "api_calls_made": 0,
        "record_mode_used": False,
        "variant": variant,
    }
    if pass_type == "naming_conventions":
        common.update({
            "reconstructed_from_run": None,
            "derived_from_fields": [],
            "gap": (
                "UNRECONSTRUCTABLE: neither saved paid run records this pass's "
                "response, nor the basis/binding_hint/aliases/thickness_in/"
                "height_ft its schema requires. The schema-legal EMPTY object "
                "list is used instead of an invented library, and it is "
                "IDENTICAL in both variants so it contributes nothing to the "
                "differential. Assumption A2 is NOT satisfied for this pass."
            ),
        })
        return common
    common.update({
        "reconstructed_from_run": RUN_DIRS[variant],
        "reconstructed_from_run_label": RUN_LABELS[variant],
        "gap": None,
    })
    if pass_type == "semantic":
        common["derived_from_fields"] = [
            "takeoff_summary[].item where source in %s (the run's object names)"
            % (list(_LIBRARY_SOURCES),),
            "raw_line_items[].description beginning WALL-/ROOM- (the classes "
            "and rooms the run could NOT name, which stay absent here)",
        ]
        common["note"] = (
            "Both runs named their tilt-up class the same TEXT; the recorded "
            "variance is the ASSIGNMENT, so the assignment is inverted here — "
            "the precedent committed by 24-02's "
            "test_wall_class_label_invariance."
        )
    else:
        common["derived_from_fields"] = [
            "raw_line_items[].description beginning SYM- (every symbol row in "
            "both artifacts except the library-named cluster, i.e. this pass "
            "bound nothing in either run — 'unknown' is the OBSERVED answer)",
        ]
        common["note"] = (
            "IDENTICAL across the two variants, deliberately: both runs bound "
            "nothing through this pass. The 56-EA cluster that published as "
            "Bollard in one run and Dock Bumper in the other carries a "
            "recorded text absence and is excluded from this request "
            "altogether (24-07), so no answer here can name it."
        )
    return common


# ── Driving the deterministic half ───────────────────────────────────────────


class _RecordingResponder:
    """An analyzer that answers from the evidence and records what it answered.

    It never imports, constructs or calls the real analyzer. It computes the
    request key with ``ReplayAnalyzer.key_for`` — the public derivation — so the
    key written here is the key ``ReplayAnalyzer.__call__`` will resolve at
    replay time, rather than a second implementation of the same hash that could
    drift (T-24-43).
    """

    def __init__(self, variant: str) -> None:
        from tests.replay_analyzer import ReplayAnalyzer

        self.variant = variant
        self.fixtures: Dict[str, dict] = {}
        self.unanswered: List[str] = []
        self._keyer = ReplayAnalyzer(FIXTURE_ROOT / variant)

    def __call__(
        self,
        screenshot_path: str,
        sheet_name: str = "",
        pass_type: str = "measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
    ) -> dict:
        key = self._keyer.key_for(
            sheet_name=sheet_name,
            pass_type=pass_type,
            model_override=model_override,
            sheet_type=sheet_type,
            user_hint=user_hint,
            output_schema=output_schema,
            images=images,
        )
        responder = _RESPONDERS.get(pass_type)
        if responder is None:
            # A pass this script has no evidence-backed answer for is recorded
            # as unanswered and NOT given an invented response.
            self.unanswered.append(pass_type)
            return {}
        response = responder(output_schema or {}, self.variant)
        self.fixtures[key] = {
            "request": {
                "model": self._keyer._resolve_model(
                    sheet_name, pass_type, sheet_type, model_override, output_schema
                ),
                "pass_type": pass_type,
                "sheet_name": sheet_name,
                "sheet_type": sheet_type,
                "prompt": self._keyer._prompt_text(
                    sheet_name, pass_type, sheet_type, user_hint
                ),
                "image_count": len(images) if images else 1,
            },
            "response": response,
            "provenance": _provenance(pass_type, self.variant),
        }
        return response


def crow_page_specs(pdf_path=None) -> List[dict]:
    """The ``run_project`` page spec for Crow's vector sheet.

    Built exactly the way ``pdf_analyzer.run_pdf_analysis`` builds it — the same
    sheet name and the same title-block classification — so the prompt this
    harness hashes is the prompt a real run would hash. The image path is a
    placeholder: this harness renders nothing, and every request the vector path
    issues carries images rendered from the PDF page itself.
    """
    import fitz
    from bobbytailor.pipeline.pdf_analyzer import (
        _sheet_name_from_doc,
        get_title_block_text,
    )
    from bobbytailor.pipeline.sheet_pass_matrix import classify_sheet_type_verbose

    pdf_path = str(pdf_path or CROW_PDF)
    doc = fitz.open(pdf_path)
    try:
        i = CROW_PAGE_INDEX
        title_block_text = get_title_block_text(doc, i)
        return [{
            "image_path": "%s#page_%04d" % (pdf_path, i + 1),
            "sheet_name": _sheet_name_from_doc(doc, i),
            "sheet_type_hint": classify_sheet_type_verbose(title_block_text)[0],
            "title_block_text": title_block_text,
            "full_page_text": doc[i].get_text(),
            "page_num": i + 1,
            "pdf_path": pdf_path,
            "page_index": i,
        }]
    finally:
        doc.close()


def run_project_offline(analyzer, pdf_path=None) -> Tuple[list, list]:
    """Run the pipeline over Crow's vector sheet with *analyzer*. ZERO API.

    Returns ``(all_extracted, all_estimates)`` — the two lists
    ``reporter.generate_report`` turns into the published take-off.

    The ensemble is pinned to ONE sample. That is not a convenience: a replay
    analyzer is keyed on ``(model, pass_type, prompt, image_count)``, so N
    samples of one pass address the SAME fixture and the vote is unanimous by
    construction (24-08's handover warning). Pinning N=1 takes the byte-
    identical single-shot path (24-08's `E2`) and keeps this gate honest about
    what it does and does not exercise.
    """
    from bobbytailor import config
    from bobbytailor.deterministic.plan_deterministic_legends import (
        build_deterministic_legends,
    )
    from bobbytailor.pipeline.takeoff_pipeline import RunSettings, TakeoffPipeline

    pdf = str(pdf_path or CROW_PDF)
    prior = getattr(config, "ENSEMBLE_N", 3)
    # `ensemble_settings()` reads `config.ENSEMBLE_N` at CALL time, and
    # `config.ENSEMBLE_N` is resolved from the environment at IMPORT time —
    # setting the env var here would be a no-op on an already-imported config.
    config.ENSEMBLE_N = 1
    try:
        # Threaded exactly as `pdf_analyzer.run_pdf_analysis` threads it, so the
        # prompts this harness hashes are the prompts a production run hashes.
        # This is deterministic and free — it reads the plan's printed
        # schedules, not the API.
        legends = build_deterministic_legends(pdf) or None
        pipeline = TakeoffPipeline(analyzer=analyzer, settings=RunSettings.from_env())
        extracted, estimates, _ = pipeline.run_project(
            crow_page_specs(pdf),
            project_legend_schedules=legends,
            project_key="determinism-harness",
        )
        return extracted, estimates
    finally:
        config.ENSEMBLE_N = prior


def author(variant: str, pdf_path=None) -> Dict[str, dict]:
    """Author one variant's fixture set in memory. No file is written here."""
    responder = _RecordingResponder(variant)
    run_project_offline(responder, pdf_path)
    if responder.unanswered:
        print(
            "  ! %s: %d request(s) had no evidence-backed answer and were left "
            "unfixtured: %s"
            % (variant, len(responder.unanswered), sorted(set(responder.unanswered))),
            file=sys.stderr,
        )
    return responder.fixtures


def write(variant: str, fixtures: Dict[str, dict]) -> List[Path]:
    out_dir = FIXTURE_ROOT / variant
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()
    written = []
    for key, payload in sorted(fixtures.items()):
        path = out_dir / ("%s.json" % key)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=False, default=str),
            encoding="utf-8",
        )
        written.append(path)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report drift against the committed fixtures; write nothing")
    args = ap.parse_args(argv)

    if os.environ.get("REPLAY_RECORD"):
        print("REPLAY_RECORD is set. This script never records against the real "
              "analyzer; unset it and re-run.", file=sys.stderr)
        return 2
    if not CROW_PDF.exists():
        print("missing plan set: %s" % CROW_PDF, file=sys.stderr)
        return 3
    if not evidence_present():
        print("missing paid-run evidence under %s" % PAID_RUN_EVIDENCE, file=sys.stderr)
        return 4

    drift = 0
    for variant in VARIANTS:
        print("authoring %s ..." % variant)
        fixtures = author(variant)
        if args.check:
            on_disk = {
                p.stem: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((FIXTURE_ROOT / variant).glob("*.json"))
            }
            if set(on_disk) != set(fixtures):
                print("  DRIFT: key set differs (disk=%d, computed=%d)"
                      % (len(on_disk), len(fixtures)))
                drift += 1
            else:
                for k in fixtures:
                    if on_disk[k].get("response") != fixtures[k]["response"]:
                        print("  DRIFT: response differs for %s" % k[:12])
                        drift += 1
            print("  %d request(s) computed" % len(fixtures))
        else:
            paths = write(variant, fixtures)
            print("  wrote %d fixture(s) to %s" % (len(paths), FIXTURE_ROOT / variant))
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
