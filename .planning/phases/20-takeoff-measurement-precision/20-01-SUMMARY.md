---
phase: 20
plan: 01
subsystem: pdf-extraction
tags: [sheet-id, title-block, noise-filter, pymupdf, fitz, unit-tests]

dependency-graph:
  requires: []
  provides:
    - SHEET_ID_NOISE_PATTERNS (generic standards-body noise list)
    - get_title_block_text(doc, page_num) exported function
    - _sheet_name_from_doc rewritten with title-block region + noise rejection
  affects:
    - 20-02 (count-pass extraction — consumes get_title_block_text)
    - 20-00 (sheet_pass_matrix — imports get_title_block_text for classify)

tech-stack:
  added: []
  patterns:
    - Title-block region extraction (y>80%, x>55%) via PyMuPDF word bounding boxes
    - Generic noise-pattern list with context-sensitive candidate rejection

key-files:
  created:
    - tests/test_sheet_name.py
  modified:
    - pdf_analyzer.py

decisions:
  - id: D1
    decision: Noise filter applied in BOTH title-block and full-page passes
    rationale: >
      Title blocks occasionally contain spec call-outs (e.g. "ASTM E283 tested
      glazing") in the bottom-right corner.  Applying noise rejection only in
      the full-page fallback would cause false positives on such pages.
  - id: D2
    decision: _is_noise_sheet_candidate checks candidate within matched phrase context
    rationale: >
      fullmatch(pattern, "E283") fails for "ASTM\s+[A-Z]\d+" because the prefix
      is absent.  Searching page_text for noise phrases then checking whether
      the candidate string appears inside any match handles all standards formats
      without listing individual code numbers.
  - id: D3
    decision: sheet_type_hint import in get_pdf_metadata is a no-op when 20-00 absent
    rationale: >
      Plans 20-00 and 20-01 may execute independently.  Conditional import
      (try/except ImportError) keeps get_pdf_metadata backward-compatible.

metrics:
  duration: ~5 min
  completed: 2026-06-03
---

# Phase 20 Plan 01: Title-Block Sheet ID Extraction Summary

**One-liner:** Title-block region extraction + SHEET_ID_NOISE_PATTERNS replaces full-page `re.search`; E283 can no longer beat A4.0.

---

## Objective

Fix RC-1: `_sheet_name_from_doc` was running `re.search` on the full page text, allowing ASTM standard numbers (E283, A156) and other alphanumeric annotations to beat the real title-block sheet number.

---

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Title-block extraction + SHEET_ID_NOISE_PATTERNS | `39ee7ab` | pdf_analyzer.py |
| 2 | Unit tests — discipline-agnostic sheet ID cases | `f4de1e3` | tests/test_sheet_name.py |

---

## What Was Built

### `SHEET_ID_NOISE_PATTERNS` (module-level constant)

Eight generic patterns covering ASTM, NFPA, UL, IBC, ADA, ANSI, ASCE, AWC, and fractional annotations. No individual code numbers are hardcoded — adding a new standards body is a one-line change to the list.

### `get_title_block_text(doc, page_num) -> str`

Exported helper that extracts word-level text from the bottom-right quadrant (`y > height*0.80`, `x > width*0.55`) using PyMuPDF `get_text("words")` bounding boxes. Available for import by `sheet_pass_matrix.py` (20-00).

### `_is_noise_sheet_candidate(candidate, context) -> bool`

Context-aware noise check: searches `context` text for every noise pattern, then tests whether `candidate` appears inside any matched phrase. Returns `True` only when the candidate is demonstrably part of a standards reference, never for valid sheet IDs like `C-4` or `A-101`.

### Rewritten `_sheet_name_from_doc`

1. Extract title-block words → apply sheet-ID patterns + noise filter in priority order (decimal → hyphenated → three-digit).
2. If title-block pass yields nothing, scan full-page text with same noise filter.
3. Final fallback: `Page_{n}`.

### `get_pdf_metadata()` — optional `sheet_type_hint`

Conditionally imports `classify_sheet_type_from_text` from `sheet_pass_matrix`; adds `sheet_type_hint` key to each page entry when available. No-op when 20-00 has not yet been executed.

---

## Test Coverage

22 tests in `tests/test_sheet_name.py`:

- `TestNoisePatterns` (4): list structure, ASTM/NFPA present, no hardcoded E283/A156
- `TestIsNoiseSheetCandidate` (7): E283 noise, NFPA-13 noise, A4.0/C-4/A-101/S1.2/M3.1 valid
- `TestSheetNameFromDoc` (8): A4.0 beats ASTM E283, A-101 hyphen, S1.2 vs NFPA, C-4 civil, M3.1 MEP, noise-only → Page_N, G0.1 title-block priority, fallback skips ASTM
- `TestGetTitleBlockText` (2): bottom-right words present, empty when no TB words

**All 22 pass. No linter errors.**

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Noise filter applied in title-block pass, not only in fallback**

- **Found during:** Task 2 test writing
- **Issue:** Test `test_only_astm_references_returns_page_fallback` placed "ASTM E283" words inside the title-block region; the original implementation (no filter in TB pass) returned "E283" from the title block.
- **Fix:** Switched title-block pass from `re.search` (returns first match, no filter) to `re.finditer` + noise check — same filter used in both passes.
- **Files modified:** pdf_analyzer.py (`_sheet_name_from_doc`)
- **Commit:** `39ee7ab` (included in Task 1 commit, discovered and fixed before task commit)

---

## Next Phase Readiness

- 20-02 (count-pass extraction) can import `get_title_block_text` immediately.
- 20-00 (sheet_pass_matrix) can use `get_title_block_text` as its text source without re-implementing the region extraction.
- No blockers.
