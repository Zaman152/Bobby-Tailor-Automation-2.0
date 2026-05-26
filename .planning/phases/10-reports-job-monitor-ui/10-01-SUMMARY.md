# Summary: 10-01 Reports Page + Preview Tabs

**Status:** Complete  
**Date:** 2026-05-26

## What was built

- Reports page with search, refresh, and expandable report cards
- Card metadata: sheets, raw/calculated counts, API cost (from takeoff.json)
- Preview panel with Summary / Calculations / Raw / JSON tabs via Phase 5 preview API
- Sortable, filterable, searchable CSV tables with row-cap notice
- Collapsible JSON tree viewer
- Download buttons open files in new tab without closing preview

## Files modified

- `templates/index.html` — Reports page structure
- `static/style.css` — Reports & preview styles
- `static/app.js` — Reports module
- `app.py` — `raw_items_count`, `calculated_count` on list_reports

## Verification

- [x] Expandable cards with 4 preview tabs
- [x] Phase 5 preview endpoints used
- [x] Downloads preserve preview context
