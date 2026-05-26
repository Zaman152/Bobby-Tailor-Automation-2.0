# Phase 08 Verification: UI Shell Foundation

**Phase:** 08 — UI Shell Foundation
**Goal:** Industrial dark UI shell, sidebar nav, extracted static assets
**Requirements:** UI-01, UI-02, UI-03

---

## Success Criteria (from ROADMAP.md)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| 1 | Fixed sidebar navigation lists Projects, PDF Upload, Reports, and Settings | Visual inspection + click each nav item |
| 2 | Visual design matches Master.md dark palette (DM Mono, Inter, JetBrains Mono) | Compare colors, inspect fonts in DevTools |
| 3 | Inline scripts and styles from `index.html` live in `static/app.js` and `static/style.css` | File existence + Network tab |

---

## Pre-Verification Checklist

Before running verification:

- [ ] All 3 plans executed (08-01, 08-02, 08-03)
- [ ] Flask server running (`python app.py`)
- [ ] Browser DevTools open

---

## Criterion 1: Sidebar Navigation

### Checks

| Check | Expected | Pass |
|-------|----------|------|
| Sidebar visible at 240px width | Fixed left panel | ☐ |
| Logo/brand in sidebar header | "BT" logo + "Bobby Tailor" text | ☐ |
| Nav item: Projects | Icon + "Projects" text, clickable | ☐ |
| Nav item: PDF Upload | Icon + "PDF Upload" text, clickable | ☐ |
| Nav item: Reports | Icon + "Reports" text, clickable | ☐ |
| Nav item: Settings | Icon + "Settings" text, clickable | ☐ |
| Active state on current page | Highlighted background/text | ☐ |
| Click Projects → shows projects page | Content switches correctly | ☐ |
| Click PDF Upload → shows PDF page | Content switches correctly | ☐ |
| Click Reports → shows reports page | Content switches, `loadReports()` called | ☐ |
| Click Settings → shows settings page | Placeholder content visible | ☐ |
| Job mini-card slot in sidebar footer | `#sidebarJobCard` element exists | ☐ |

---

## Criterion 2: Theme and Typography

### Color Checks

| Element | Expected Color | Token | Pass |
|---------|----------------|-------|------|
| Body background | #0b0d11 | `--bg-base` | ☐ |
| Card background | #141720 | `--bg-surface` | ☐ |
| Elevated elements | #1c1f2e | `--bg-elevated` | ☐ |
| Borders | #252a3a | `--border-subtle` | ☐ |
| Primary buttons | #3b82f6 | `--accent-primary` | ☐ |
| Success badges | #10b981 | `--accent-success` | ☐ |
| Error badges | #ef4444 | `--accent-danger` | ☐ |
| Primary text | #f1f5f9 | `--text-primary` | ☐ |
| Secondary text | #94a3b8 | `--text-secondary` | ☐ |

### Typography Checks

| Element | Expected Font | Token | Pass |
|---------|---------------|-------|------|
| Body text | Inter | `--font-body` | ☐ |
| Headings (h1, h2) | DM Mono | `--font-display` | ☐ |
| Log box | JetBrains Mono | `--font-data` | ☐ |
| Code snippets | JetBrains Mono | `--font-data` | ☐ |

### Font Loading Check

1. Open Network tab, filter by "Font"
2. Verify loaded:
   - [ ] DM Mono (400, 500)
   - [ ] Inter (400, 500, 600)
   - [ ] JetBrains Mono (400, 500)

---

## Criterion 3: Static Asset Extraction

### File Checks

| File | Exists | Size (approx) | Pass |
|------|--------|---------------|------|
| `static/style.css` | Yes | 5-10 KB | ☐ |
| `static/app.js` | Yes | 6-12 KB | ☐ |

### Network Checks

1. Hard refresh page (Cmd+Shift+R)
2. Check Network tab:
   - [ ] `style.css` loads with 200 status
   - [ ] `app.js` loads with 200 status
   - [ ] No 404 errors

### HTML Check

- [ ] `templates/index.html` has no `<style>` block (except possibly empty/comment)
- [ ] `templates/index.html` has no `<script>` block (except external reference)
- [ ] `<link rel="stylesheet" href="...style.css">` present in `<head>`
- [ ] `<script src="...app.js">` present before `</body>`

---

## Functional Regression Tests

Ensure existing functionality still works after refactor:

| Test | Steps | Expected | Pass |
|------|-------|----------|------|
| Project load | Navigate to Projects | Dropdown populates | ☐ |
| Mode toggle | Click "Specific Project" | Dropdown appears | ☐ |
| Run StackCT | Select project, click Run | Job starts, progress shows | ☐ |
| PDF upload | Navigate to PDF, drop file | File name shown | ☐ |
| Run PDF | Upload file, click Analyze | Job starts | ☐ |
| Reports load | Navigate to Reports | Report list loads | ☐ |
| Report download | Click download button | File downloads | ☐ |
| Job polling | Start any job | Progress updates every 2s | ☐ |

---

## Console Error Check

- [ ] No JavaScript errors in console
- [ ] No 404 resource errors
- [ ] No CORS errors

---

## Accessibility Spot Check

| Check | Pass |
|-------|------|
| Focus visible on interactive elements | ☐ |
| Sufficient color contrast (text vs background) | ☐ |
| Keyboard navigation works for nav items | ☐ |

---

## Sign-Off

| Criterion | Status | Verified By | Date |
|-----------|--------|-------------|------|
| 1. Sidebar Navigation | ☐ Pending | | |
| 2. Theme & Typography | ☐ Pending | | |
| 3. Static Assets | ☐ Pending | | |

**Phase 08 Complete:** ☐ No / ☐ Yes

---

*Verification checklist created: 2026-05-26*
