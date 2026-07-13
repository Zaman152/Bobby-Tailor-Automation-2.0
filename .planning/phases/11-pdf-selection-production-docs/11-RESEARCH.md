# Phase 11 Research: PDF Selection & Production Docs

**Created:** 2026-05-26
**Phase Goal:** PDF mode matches StackCT selectivity; production deployment is documented end-to-end

---

## 1. Current State Analysis

### 1.1 PDF Upload & Analysis — Current Implementation

**`pdf_analyzer.py`** provides direct-PDF mode:
- Converts each PDF page to PNG at 2x zoom using PyMuPDF (`fitz`)
- Extracts sheet name from page text via regex patterns
- Sends each image to Claude for vision extraction
- Applies estimation tables and generates report

**Key function signature:**
```python
def run_pdf_analysis(pdf_path: str, project_name: str = "PDF Project",
                     progress_callback=None) -> dict
```

**Current limitations:**
- Processes ALL pages — no page selection parameter
- No page metadata returned after upload (count/size shown client-side only)
- No thumbnail preview of pages

### 1.2 Upload Route — Current Implementation

**`app.py` route `/api/run/pdf`:**
- Accepts multipart form with `file` (PDF) and optional `project_name`
- Saves to `uploads/` with UUID prefix
- Immediately starts background job processing ALL pages
- Returns `job_id` for polling

**Missing:**
- Separate "upload + inspect" vs "run" endpoints
- Page count / file size metadata endpoint
- `selected_pages` parameter to filter analysis

### 1.3 UI — Current Implementation

**`templates/index.html` PDF tab:**
- Drop zone for PDF file
- Shows filename and file size after selection (client-side only)
- Project name input
- Single "Analyze PDF" button triggers full job

**Missing per Master.md §8.6:**
- Page count display after upload
- Page selection UI with checkboxes/thumbnails
- "Analyze all pages" vs "Select pages" radio toggle
- Thumbnail grid for page selection

### 1.4 README.md — Current State

Current README covers:
- Basic setup (`pip install`, `playwright install`)
- VPS deployment (Ubuntu apt deps, gunicorn command)
- Chromium launch flags (`--no-sandbox`, `--disable-dev-shm-usage`)
- `.env` tuning (`CANVAS_STABILITY_TIMEOUT`, `CANVAS_STABILITY_CHECKS`)
- Docker alternative with `shm_size`
- Troubleshooting (browser crashes, blank screenshots)

**Gaps vs Master.md §11:**
- No systemd service file example
- No nginx reverse proxy section
- Environment variables reference could match Master.md §11.3 format

---

## 2. Dependencies

### 2.1 Phase 8: UI Shell Foundation

Phase 11 assumes the UI shell (Phase 8) provides:
- Fixed sidebar navigation layout
- Industrial dark theme CSS
- Separated `static/app.js` and `static/style.css`

**If Phase 8 is incomplete:** Phase 11 can still add PDF page selection UI within current `templates/index.html` structure; refactoring to external CSS/JS can happen later.

### 2.2 Phase 4: StackCT Plan Selection UX Pattern

Phase 4 establishes:
- "Select All / Select None" checkbox controls
- Sheet type filter UI pattern
- Checkbox grid/list for page selection

**Applicable to PDF mode:**
- Same UX pattern: checkbox list after upload
- Same "Analyze all" vs "Select specific" toggle

**If Phase 4 is incomplete:** Phase 11 can implement the pattern independently (simple checkbox list) and Phase 4 can follow the same pattern later.

---

## 3. Requirements Mapping

| Requirement | Description | Plan |
|-------------|-------------|------|
| **PDF-01** | User can upload a construction PDF for analysis | 11-01 (existing, enhance with metadata) |
| **PDF-02** | User can select specific pages before starting PDF analysis | 11-01 (UI), 11-02 (backend) |
| **PDF-03** | PDF page selection shows page count and file size after upload | 11-01 |
| **DEPLOY-02** | README includes VPS gunicorn + Playwright deps instructions | 11-03 |

---

## 4. Technical Approach

### 4.1 Plan 11-01: PDF Upload Metadata + Page Checkbox UI

**Backend changes:**
1. New endpoint `/api/pdf/upload` — accepts PDF, saves to uploads/, returns:
   ```json
   {
     "upload_id": "abc12345",
     "filename": "Office_Plans.pdf",
     "page_count": 24,
     "file_size_bytes": 19300000,
     "pages": [
       {"page_num": 1, "sheet_name": "A001"},
       {"page_num": 2, "sheet_name": "A002"},
       ...
     ]
   }
   ```
2. Helper function `_get_pdf_metadata(pdf_path)` extracts page count and sheet names

**Frontend changes:**
1. After file drop/select, call `/api/pdf/upload` instead of direct `/api/run/pdf`
2. Display: `"Office_Plans.pdf · 24 pages · 18.4 MB"`
3. Radio toggle: "○ Analyze all 24 pages" / "● Select pages:"
4. Checkbox list for pages (or paginated if >20 pages)
5. "Analyze PDF" button sends `upload_id` + `selected_pages` array

### 4.2 Plan 11-02: Pass Selected Pages to pdf_analyzer

**Backend changes:**
1. Modify `/api/run/pdf` (or new `/api/pdf/run`) to accept:
   ```json
   {
     "upload_id": "abc12345",
     "project_name": "Office Complex",
     "selected_pages": [1, 3, 5, 7]  // 1-indexed, optional (null = all)
   }
   ```
2. Modify `run_pdf_analysis()` signature:
   ```python
   def run_pdf_analysis(pdf_path: str, project_name: str = "PDF Project",
                        selected_pages: list[int] | None = None,
                        progress_callback=None) -> dict
   ```
3. Filter page iteration: `for i in (selected_pages or range(total))`

### 4.3 Plan 11-03: README VPS Deployment Section

**Enhancements:**
1. Add systemd service file example (`bobby-tailor.service`)
2. Add nginx reverse proxy config snippet
3. Ensure environment variables table matches Master.md §11.3
4. Add section headers matching Master.md structure

---

## 5. File Inventory

| File | Changes |
|------|---------|
| `pdf_analyzer.py` | Add `selected_pages` parameter to `run_pdf_analysis()` |
| `app.py` | Add `/api/pdf/upload` endpoint; modify `/api/run/pdf` for upload_id + selected_pages |
| `templates/index.html` | Add page selection UI after upload (checkbox list, radio toggle) |
| `README.md` | Add systemd example, nginx snippet, environment table |

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Large PDFs (100+ pages) slow to extract metadata | `_get_pdf_metadata()` only reads page count and first few lines of text per page — no rendering |
| Page thumbnails would require rendering each page | Defer thumbnails to v2; use text-only page list with sheet names for v1 |
| Upload endpoint holds file in memory | Current approach saves to disk immediately — acceptable |
| Phase 4/8 not complete | Phase 11 can work standalone in current template structure |

---

## 7. Success Criteria Validation

| Criterion | How to Verify |
|-----------|---------------|
| User can upload a construction PDF and start analysis from the PDF Upload page | Upload PDF, see metadata, click Analyze |
| After upload, user selects specific pages before analysis starts | Checkbox UI appears, selecting subset runs only those pages |
| UI shows page count and file size immediately after upload | Displayed as "filename · N pages · X.X MB" |
| README documents Hostinger VPS setup | README has gunicorn command, systemd service, Playwright deps, .env vars, headless Chrome flags |

---

*Research complete: 2026-05-26*
