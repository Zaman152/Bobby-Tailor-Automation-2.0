#!/usr/bin/env python3
"""Per-page coverage audit (ZERO API) — the coverage ledger's oracle.

Answers one question for every page of a plans PDF: **does this page reach the
report, and if not, what was thrown away?**

It replicates exactly four pipeline decisions WITHOUT running the pipeline:

  1. ``classify_sheet_type_verbose`` on TITLE-BLOCK text only — what the PDF
     path actually classifies on;
  2. the empty-pass-list skip (``plan_passes`` -> ``[]`` => title_sheet, and
     ``run_sheet`` returns the skip sentinel);
  3. the skip veto — measurable geometry outranks a keyword;
  4. ``_DETERMINISTIC_SHEET_TYPES`` membership, i.e. whether the page reaches
     the geometry engine at all.

Because it computes what the ledger MUST contain independently of the run that
fills it, a disagreement between this probe and ``report["coverage_ledger"]``
is a bug in one of them — which is the point of having an oracle.

Usage:
    python3 scripts/coverage_probe.py "uploads/Crow - Cass White Road-Plans.pdf"
    python3 scripts/coverage_probe.py --pdf a.pdf --pdf b.pdf
    python3 scripts/coverage_probe.py --json "uploads/....pdf"
    python3 scripts/coverage_probe.py --no-veto "uploads/....pdf"

``--no-veto`` disables the skip veto so the report measures CLASSIFICATION
ALONE. That distinction is the point: the veto (plan 23-01) recovers a sheet
that a keyword wrongly discarded, so with it switched on a broken classifier
and a repaired one produce the same headline number. A change to the classifier
must be graded with the backstop removed, or it is not being graded at all.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fitz  # noqa: E402

from bobbytailor.deterministic.printed_scale import (  # noqa: E402
    extract_printed_scales,
)
from bobbytailor.deterministic.room_fill import plan_titles  # noqa: E402
from bobbytailor.pipeline.coverage import (  # noqa: E402
    MEASURED,
    MEASURED_PARTIAL,
    NOT_APPLICABLE,
    SKIPPED_CLASSIFIER,
    VISION_ONLY,
    CoverageLedger,
)
from bobbytailor.pipeline.pdf_analyzer import get_title_block_text  # noqa: E402
from bobbytailor.pipeline.sheet_pass_matrix import (  # noqa: E402
    classify_sheet_type_verbose,
    plan_passes,
)
from bobbytailor.pipeline.takeoff_pipeline import (  # noqa: E402
    _DETERMINISTIC_SHEET_TYPES,
    page_measurable_signal,
)

# The four plan sets every classification/scale change is gated on. Four
# drafting offices, four title-block conventions, four rotation/scale habits.
FOUR_SETS = {
    "moxy": "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
    "crow": "uploads/Crow - Cass White Road-Plans.pdf",
    "bobs": "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf",
    "chelsea": (
        "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
    ),
}


def audit_page(doc, index: int, no_veto: bool = False) -> Dict[str, Any]:
    """Replicate the pipeline's routing decisions for one page. Zero API.

    Args:
        no_veto: when True, the skip veto is not applied, so the reported
            dispositions describe CLASSIFICATION ALONE. ``classifier_discarded``
            is reported either way and is never affected by the veto.
    """
    page = doc[index]
    title_block_text = get_title_block_text(doc, index)

    sheet_type, type_source, keyword, context = classify_sheet_type_verbose(
        title_block_text
    )
    # What the two-source fallback WOULD say. Recorded, never acted on here —
    # see SheetCoverage.sheet_type_full_text.
    try:
        type_full_text = classify_sheet_type_verbose(
            title_block_text, page.get_text()
        )[0]
    except Exception:  # noqa: BLE001 — the annotation is never load-bearing
        type_full_text = sheet_type

    passes = plan_passes(sheet_type, title_block_text=title_block_text)
    signal = page_measurable_signal(page)

    # Raw counts for the human-readable table: how many title-shaped strings and
    # scale callouts are on the page at all, before asking what is measurable.
    raw_titles = len(plan_titles(page) or [])
    raw_scales = len(extract_printed_scales(page) or [])

    # What the CLASSIFIER alone decided, before the skip veto is consulted.
    # This column is the one plan 23-06 is graded on: the veto (plan 23-01) is a
    # backstop, and a gate that measures the backstop cannot tell a repaired
    # classifier from a broken classifier with a good safety net.
    classifier_discarded = not passes

    overruled = bool(
        not passes and (signal["plan_titles"] > 0 or signal["viewports"] > 0)
    )
    if no_veto:
        overruled = False
    effective_type = "floor_plan" if overruled else sheet_type
    skipped = bool(not passes and not overruled)
    deterministic = (not skipped) and effective_type in _DETERMINISTIC_SHEET_TYPES

    if overruled:
        disposition = MEASURED_PARTIAL
        note = "CLASSIFIER OVERRULED — %d scaled plan drawing(s) recovered" % (
            signal["plan_titles"]
        )
    elif skipped:
        measurable = sum(signal.values()) > 0
        disposition = SKIPPED_CLASSIFIER if measurable else NOT_APPLICABLE
        note = (
            "SKIPPED, and it carries measurable geometry"
            if measurable
            else "skipped — no measurable geometry (a real cover/index sheet)"
        )
    elif deterministic:
        disposition = MEASURED
        note = (
            "" if signal["plan_titles"]
            else "det-eligible but 0 room-fill titles"
        )
    else:
        disposition = VISION_ONLY
        note = "no deterministic geometry (vision-only path)"

    return {
        "page_index": index,
        "sheet_type": sheet_type,
        "type_source": type_source,
        "sheet_type_full_text": type_full_text,
        "classifier_keyword": keyword,
        "classifier_context": context,
        "passes": len(passes),
        "deterministic": deterministic,
        "titles": raw_titles,
        "scales": raw_scales,
        "measurable_signal": signal,
        "classifier_overruled": overruled,
        "classifier_discarded": classifier_discarded,
        "skipped": skipped,
        "disposition": disposition,
        "note": note,
    }


def audit_pdf(pdf_path: str, no_veto: bool = False) -> Dict[str, Any]:
    """Audit every page of *pdf_path* and build the ledger it implies."""
    doc = fitz.open(pdf_path)
    try:
        pages = [audit_page(doc, i, no_veto=no_veto)
                 for i in range(doc.page_count)]
        page_count = doc.page_count
    finally:
        doc.close()

    ledger = CoverageLedger(pages_in_source=page_count)
    for row in pages:
        ledger.register_page(
            row["page_index"],
            sheet_type=row["sheet_type"],
            type_source=row["type_source"],
            sheet_type_full_text=row["sheet_type_full_text"],
            classifier_keyword=row["classifier_keyword"],
            classifier_context=row["classifier_context"],
            classifier_overruled=row["classifier_overruled"],
            disposition=row["disposition"],
            measurable_signal=row["measurable_signal"],
        )

    histogram: Dict[str, int] = {}
    for row in pages:
        histogram[row["sheet_type"]] = histogram.get(row["sheet_type"], 0) + 1

    return {
        "pdf": pdf_path,
        "page_count": page_count,
        "no_veto": no_veto,
        "pages": pages,
        "type_histogram": histogram,
        # Pages the CLASSIFIER discarded, independent of the veto. This is the
        # column that grades a classification change (D-04).
        "pages_classifier_discarded": [
            r["page_index"] for r in pages if r["classifier_discarded"]
        ],
        "pages_skipped": [r["page_index"] for r in pages if r["skipped"]],
        "pages_overruled": [
            r["page_index"] for r in pages if r["classifier_overruled"]
        ],
        "pages_no_deterministic": [
            r["page_index"] for r in pages
            if not r["skipped"] and not r["deterministic"]
        ],
        "pages_reaching_report": sum(1 for r in pages if not r["skipped"]),
        "silent_loss_pages": ledger.silent_loss_pages(),
        "summary": ledger.summary(),
        "warnings": ledger.warnings(),
        "unaccounted_pages": ledger.assert_accounted(),
    }


def print_report(result: Dict[str, Any]) -> None:
    print("### %s — %d pages" % (Path(result["pdf"]).name, result["page_count"]))
    print("%-4s %-14s %-14s %-7s %-5s %-6s %-6s %s" % (
        "pg", "type(tb-only)", "type(+fulltext)", "passes", "det?",
        "titles", "scales", "note",
    ))
    for row in result["pages"]:
        print("%-4d %-14s %-14s %-7d %-5s %-6d %-6d %s" % (
            row["page_index"], row["sheet_type"], row["sheet_type_full_text"],
            row["passes"], "yes" if row["deterministic"] else "NO",
            row["titles"], row["scales"], row["note"],
        ))

    print("-" * 102)
    print("type histogram (title-block only, i.e. what the pipeline uses): %s"
          % result["type_histogram"])
    if result.get("no_veto"):
        print("*** --no-veto: the skip veto is DISABLED, so the counts below "
              "measure CLASSIFICATION ALONE ***")
    # Both columns are always printed. The classifier column grades a
    # classification change; the skipped column grades what the run does.
    print("pages discarded by classifier: %d  %s"
          % (len(result["pages_classifier_discarded"]),
             result["pages_classifier_discarded"]))
    print("pages skipped entirely      : %d  %s"
          % (len(result["pages_skipped"]), result["pages_skipped"]))
    print("pages recovered by the veto : %d  %s"
          % (len(result["pages_overruled"]), result["pages_overruled"]))
    print("pages with no det. geometry : %d  %s"
          % (len(result["pages_no_deterministic"]),
             result["pages_no_deterministic"]))
    print("pages that reach the report : %d of %d"
          % (result["pages_reaching_report"], result["page_count"]))
    print("silent_loss_pages           : %d  %s"
          % (len(result["silent_loss_pages"]), result["silent_loss_pages"]))
    if result["unaccounted_pages"]:
        print("!! UNACCOUNTED PAGES        : %s" % result["unaccounted_pages"])
    for line in result["warnings"]:
        print("!! %s" % line)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Per-page coverage audit of a plans PDF (zero API).",
    )
    parser.add_argument("pdfs", nargs="*", help="Plans PDF(s) to audit.")
    parser.add_argument("--pdf", action="append", default=[],
                        help="Plans PDF to audit (repeatable).")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of the table.")
    parser.add_argument(
        "--no-veto", action="store_true",
        help="Disable the skip veto, so the report measures CLASSIFICATION "
             "ALONE. Use this to grade a classifier change: with the veto on, "
             "a broken classifier and a repaired one both look fine.",
    )
    args = parser.parse_args(argv)

    targets = list(args.pdf) + list(args.pdfs)
    if not targets:
        targets = [p for p in FOUR_SETS.values() if Path(ROOT / p).exists()]
    if not targets:
        parser.error("no PDF given and none of the four plan sets are present")

    results = [audit_pdf(t, no_veto=args.no_veto) for t in targets]

    if args.json:
        payload = results[0] if len(results) == 1 else results
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    for i, result in enumerate(results):
        if i:
            print()
        print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
