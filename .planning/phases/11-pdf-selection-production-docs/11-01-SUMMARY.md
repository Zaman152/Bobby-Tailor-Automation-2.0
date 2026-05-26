# Summary: 11-01 PDF Upload Metadata + Page Checkbox UI

**Status:** Complete  
**Date:** 2026-05-26

## What was built

- `get_pdf_metadata()` in `pdf_analyzer.py` — page count, file size, sheet names
- `POST /api/pdf/upload` — uploads PDF, stores in `uploads` dict, returns metadata
- Two-step PDF flow: upload → show "filename · N pages · X MB" → page selection
- Radio: analyze all pages vs select specific pages with checkbox grid
- Select All / Select None controls

## Files modified

- `pdf_analyzer.py`, `app.py`, `templates/index.html`, `static/app.js`, `static/style.css`
