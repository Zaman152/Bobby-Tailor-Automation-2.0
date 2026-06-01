# Phase 18 UAT: Linked Sheet Auto-Follow

## Pre-conditions
- Phase 17 pipeline working (manifest, two-phase capture)
- SQLite catalog populated for test project (run sync first)
- Test project has at least one sheet with a detail bubble referencing another sheet

## Checklist

### LINK-01: Catalog Matcher
- [ ] Run `python -c "from linked_sheets import match_ref_to_page; ..."` with real sheet name → correct page_id
- [ ] Ambiguous match logs WARNING with near-misses
- [ ] No-match returns None (no crash)

### LINK-02: Ref Collection
- [ ] `collect_unresolved_refs` finds refs in `cross_references[]`
- [ ] `collect_unresolved_refs` finds refs in `civil_structures[].detail_ref_sheet`
- [ ] Duplicates deduplicated

### LINK-03: AUTO_INCLUDE_LINKED_SHEETS=false
- [ ] Run with `AUTO_INCLUDE_LINKED_SHEETS=false`
- [ ] `takeoff.json` has non-empty `linked_sheets_suggested[]`
- [ ] `linked_sheets_added[]` is empty
- [ ] No extra browser session opened

### LINK-04: Full Pipeline (AUTO_INCLUDE=true)
- [ ] Select 2-3 sheets that contain cross-reference bubbles
- [ ] Job completes; job monitor shows "Adding N linked detail sheets" phase
- [ ] `takeoff.json` `linked_sheets_added` lists the auto-added page(s)
- [ ] Cross-reference entry status changes from `target_sheet_not_found` to `resolved` or `target_found_detail_missing`
- [ ] `linked_sheets_count` visible in job monitor UI

### LINK-05: MAX_LINKED_SHEETS cap
- [ ] Set `MAX_LINKED_SHEETS=1` with project having 3+ refs
- [ ] Only 1 linked sheet added; WARNING logged about truncation

### LINK-06: Partial + Cancel safety
- [ ] Cancel job during linked capture phase → partial report generated, no crash
- [ ] Failed linked capture → main report still generated from original sheets

## Sign-off
- [ ] All checklist items confirmed PASS
- Signed off by: _______________
- Date: _______________
