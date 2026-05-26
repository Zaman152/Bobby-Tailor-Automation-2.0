# Phase 08 Research: UI Shell Foundation

**Researched:** 2026-05-26
**Phase:** UI Shell Foundation
**Goal:** Industrial dark UI shell, sidebar nav, extracted static assets

---

## 1. Current State Analysis

### 1.1 Existing Files

| File | Lines | State |
|------|-------|-------|
| `templates/index.html` | 597 | Single file with inline CSS + JS |
| `static/` | — | Does not exist |

### 1.2 Current UI Architecture

```
Current Layout (Tab-based):
┌─────────────────────────────────────────────────┐
│  Header: BT Logo + Title                        │
├─────────────────────────────────────────────────┤
│  .tabs: [StackCT Projects][Upload PDF][Reports] │
├─────────────────────────────────────────────────┤
│  .container (max-width: 900px, centered)        │
│    Tab content (card-based)                     │
└─────────────────────────────────────────────────┘
```

### 1.3 Current Styling

**Colors (inline CSS ~220 lines):**
- Background: `#0f1117` (slightly lighter than target)
- Surface: `#1a1d27` (similar to target)
- Border: `#2d3148`
- Primary accent: `#2563eb` / `#3b82f6`
- Text: `#e2e8f0`, `#94a3b8`, `#64748b`

**Typography:**
- System fonts: `-apple-system, BlinkMacSystemFont, 'Segoe UI'`
- Monospace for logs: `'Menlo', 'Monaco', monospace`

**Components:**
- `.card` — rounded panels with padding
- `.tab` — pill-style tabs
- `.mode-toggle` — binary scope selector
- `.run-btn` — gradient primary buttons
- `.drop-zone` — PDF file drop area
- `.progress-card` — job status with progress bar
- `.log-box` — terminal-style log viewer
- `.report-item` — file download cards

### 1.4 Current JavaScript (~260 lines inline)

| Function | Purpose |
|----------|---------|
| `switchTab()` | Show/hide tab content |
| `setMode()` | Toggle all/specific project mode |
| `loadProjects()` / `refreshProjects()` | Fetch project dropdown |
| `runStackCT()` | POST `/api/run/stackct` |
| `onFileSelected()` / `runPDF()` | PDF upload flow |
| `startPolling()` / `pollStatus()` | Job status polling |
| `loadReports()` | Fetch reports list |
| `escHtml()` | XSS helper |

---

## 2. Target State (from Master.md)

### 2.1 Layout Structure (§8.2)

```
Target Layout (Sidebar-based):
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR (240px fixed)    │  MAIN CONTENT (flex 1)       │
│                           │                               │
│  [BT Logo + wordmark]     │  [Contextual header]          │
│                           │                               │
│  Navigation:              │  [Page content]               │
│  • Projects               │                               │
│  • PDF Upload             │                               │
│  • Reports                │                               │
│  • Settings               │                               │
│                           │                               │
│  ─────────────────────    │                               │
│  [Active Job Status]      │                               │
│  (live mini card)         │                               │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Color Palette (§8.1)

```css
--bg-base: #0b0d11;          /* Near-black base */
--bg-surface: #141720;       /* Card backgrounds */
--bg-elevated: #1c1f2e;      /* Modal/dropdown backgrounds */
--border-subtle: #252a3a;    /* Default borders */
--border-active: #3b82f6;    /* Active/focus borders */
--accent-primary: #3b82f6;   /* Blue — primary actions */
--accent-secondary: #6366f1; /* Indigo — secondary */
--accent-success: #10b981;   /* Green — done/positive */
--accent-warning: #f59e0b;   /* Amber — caution */
--accent-danger: #ef4444;    /* Red — error */
--text-primary: #f1f5f9;     /* Main text */
--text-secondary: #94a3b8;   /* Secondary/muted text */
--text-tertiary: #475569;    /* Disabled/placeholder */
--accent-construction: #f97316; /* Orange — construction accent */
```

### 2.3 Typography (§8.1)

```
Display/Headers: "DM Mono" (monospace precision)
Body: "Inter" (clean readability)
Data/Numbers: "JetBrains Mono" (aligned data)
```

Google Fonts embed:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### 2.4 File Structure (§10)

```
static/
├── app.js       ← extracted JavaScript
└── style.css    ← extracted CSS with theme tokens
```

---

## 3. Gap Analysis

| Aspect | Current | Target | Gap |
|--------|---------|--------|-----|
| Layout | Tab-based centered | Sidebar + main content | **Major rewrite** |
| CSS location | Inline in HTML | `static/style.css` | **Extract** |
| JS location | Inline in HTML | `static/app.js` | **Extract** |
| Color tokens | Hardcoded values | CSS custom properties | **Refactor** |
| Typography | System fonts | DM Mono/Inter/JetBrains | **Add fonts** |
| Nav structure | Horizontal tabs | Vertical sidebar | **Restructure** |
| Active job | Not visible in nav | Sidebar mini-card | **Add** |
| Settings nav | Not present | Sidebar item | **Add** |

---

## 4. Technical Decisions

### 4.1 Extraction Strategy

**CSS extraction:**
1. Move all `<style>` content to `static/style.css`
2. Convert hardcoded colors to CSS variables
3. Add `:root` block with theme tokens
4. Add Google Fonts `@import` or `<link>` in HTML head

**JS extraction:**
1. Move all `<script>` content to `static/app.js`
2. Wrap in DOMContentLoaded if not already
3. No module bundling needed (simple vanilla JS)

### 4.2 Layout Migration

**Approach:** Incremental restructure
1. Add sidebar HTML structure outside `.container`
2. Convert tabs to sidebar nav items
3. Keep existing page content largely intact
4. Adjust widths for sidebar-aware layout

### 4.3 Routing Strategy

**Current:** Single-page with JS-toggled divs
**Target:** Keep SPA approach (no Flask routing changes needed for shell)

Nav clicks will:
1. Update URL hash or data attribute
2. Toggle visibility of content sections
3. Apply `.active` class to current nav item

---

## 5. Dependencies

### 5.1 Phase Dependencies

- **Phase 1 (Config)**: ✅ Complete — `.env` loading works
- No other phase dependencies for UI shell

### 5.2 External Dependencies

- Google Fonts CDN (DM Mono, Inter, JetBrains Mono)
- No new Python packages required

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Existing JS relies on element IDs that change | Keep all IDs stable; only restructure containers |
| Progress card polling breaks with new layout | Progress card remains in main content area |
| Reports tab fetch on switch | `loadReports()` call remains bound to nav item |

---

## 7. Plan Mapping

| Plan | Scope | Requirements |
|------|-------|--------------|
| 08-01 | Base layout template + sidebar structure | UI-01 (partial) |
| 08-02 | Theme tokens, typography, CSS variables | UI-02 |
| 08-03 | Extract static assets, wire `<link>`/`<script>` | UI-03 |

---

*Research complete: 2026-05-26*
