# Phase 14 Discovery: Multi-Project Plan Set Audit

**Date:** 2026-05-26  
**Script:** `scripts/audit_plan_sets.py`  
**Raw JSON:** `14-DISCOVERY.json`

## Summary

| Pattern | Count | Meaning |
|---------|-------|---------|
| `multi_set` | 6/7 | Folder cards under Plans — user must pick a set |
| `no_sets_found` | 1/7 | ATL 081 — no folder cards; needs **direct grid** fallback |
| `single_set` | 0/7 | None in sample (all multi or direct) |

**Conclusion:** Plan-set selection is the **default** workflow, not an edge case. Implement folder-first preview for all projects; add fallback when StackCT opens straight to the sheet grid.

## Per-project results (deduped for planning)

### Morehouse Spelman (7416168) — `multi_set`

| folder_id | Name | Sheets |
|-----------|------|--------|
| 35240700 | MSP3- ISSUE FOR BID-COMBINEDv1 | 120 |
| 35240694 | MSP3- ISSUE FOR BID-COMBINEDv2 | 180 |

Ignore aggregate row `35240651` ("Plans MSP3-…v1…v2"). Landing view shows 120 (v1 default).

### ATL 081 (7414097) — `no_sets_found`

No `[data-folder-id]` plan-set cards; landing count 0 in audit (page may need longer wait or different route). Previously synced **120** sheets via flat `get_all_page_ids`. **Fallback:** synthetic set `folder_id=0` "All drawing sheets" from grid scrape.

### Bid for Baking Social (7413793) — `multi_set`

| folder_id | Name | Sheets |
|-----------|------|--------|
| 35218877 | 2026_0515_Baking Social Permit Set Combined 1 | 22 |

(Dedupe: drop `35218810` "Plans …" duplicate parent label.)

### Athens Fire Station (7415026) — `multi_set`

| folder_id | Name | Sheets |
|-----------|------|--------|
| 35228916 | Athens Fire Station No. 3 - 100_ CD Set - Drawings - 2026-04-24 | 120 |

### LaserAway (7409312) — `multi_set`

| folder_id | Name | Sheets |
|-----------|------|--------|
| 35190393 | Exhibit A - 260138 LSA Cumming_ GA CD_5-7-26 | 43 |

### Baking Social - The Battery (7413817) — `multi_set`

| folder_id | Name | Sheets |
|-----------|------|--------|
| 35218945 | 2026_0506_PERMIT SET COMBINED_BAKING SOCIAL S_S | 45 |
| 35218946 | 2026_0515_Baking Social Permit Set Combined | 45 |

Two distinct permit sets (same count — user must pick by name/date).

### SmartServ Tennis Lab (7402786) — `multi_set`

| folder_id | Name | Sheets |
|-----------|------|--------|
| 35150627 | 202603_Interior Guide V1.0_TENNISPOT_Proofcopy (1) (1) | 27 |
| 35150626 | Smart Serve Tennis Lab Report | 27 |

## Dedupe rules (implement in `browser.get_plan_sets`)

1. Drop names in `SKIP_NAMES` (Plans, Bookmarks, Supporting Documents).
2. Drop rows where `name` starts with `"Plans "` **if** another candidate has the same `sheet_count` and `name` equals the suffix after `"Plans "`.
3. Drop rows where `name` contains two issue labels (e.g. both "v1" and "v2") — parent aggregate folder.
4. Prefer **shorter** `name` when two `folder_id` entries share the same `sheet_count` and one name is a prefix of the other.

## DOM contract

- Plan sets: clickable `[data-folder-id="{id}"]` on `#/Takeoff/{project_id}`
- Sheets: `[data-page-id]` after clicking folder (or on landing for direct-grid projects)
- Click folder before `evaluate` page list

## Tests to add

- Unit tests for dedupe function (fixture JSON from this audit)
- Integration test optional: Morehouse returns exactly 2 sets (mock DOM)
