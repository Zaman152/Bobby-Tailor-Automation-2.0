# Reports Page — Design Overrides

> **This file overrides** `design-system/bobby-tailor/MASTER.md` for the Reports page specifically.

---

## Page Purpose

Display list of completed takeoff reports with preview/export actions. Primary user goal: **quickly preview results or download for analysis**.

## Key User Pain (from Phase 15 Research)

- **Preview vs Download confusion** — Four similar-looking buttons made it unclear which was for viewing vs downloading
- **Inline accordion preview** — Required expanding card, tabs only visible after expand
- **Weak calculations analysis** — Basic HTML table without sort, filter, or export filtered

## Design Solution

### Report Card Actions

**Primary CTA:**
- **Single "Open Preview" button** — icon (eye or maximize-2 from Lucide) + text
- Style: `btn-primary` with `--accent-construction` background
- Action: Opens full-screen report workspace (see workspace section below)

**Secondary Actions (Export Menu):**
- Grouped under **"Export ▾"** dropdown or right-aligned button group
- Style: `btn-secondary` with subtle border
- Options:
  - Calculations CSV
  - Raw CSV  
  - JSON
  - Summary TXT
- Each triggers direct download (no preview)

**Visual Hierarchy:**
```
┌─────────────────────────────────────────────────┐
│  Project Name                         [Export ▾] │
│  123 sheets • May 25, 2026 • $0.04    ─────────  │
│  ● Cached                          [Open Preview]│
└─────────────────────────────────────────────────┘
```

### Report Preview Workspace

**Layout:** Full-screen drawer (covers main content, not a modal overlay)

**Structure (3 columns):**

```
┌───────────────┬─────────────────────────────┬─────────────┐
│  RUN LIST     │  TAB CONTENT                │  EXPORT     │
│  (left 20%)   │  (center 60%)               │  (right 20%)│
├───────────────┼─────────────────────────────┼─────────────┤
│  ● This run   │  [Summary] [Calculations]   │  ⬇ Calc CSV │
│    May 25     │  [Raw] [JSON]               │  ⬇ Raw CSV  │
│               │                             │  ⬇ JSON     │
│  ○ May 24     │  Rich content area          │  ⬇ Summary  │
│  ○ May 23     │                             │             │
│               │                             │             │
│  [← Close]    │                             │             │
└───────────────┴─────────────────────────────┴─────────────┘
```

**Components:**

- **Header bar:** Project name, date, cache status, close button (top-right X)
- **Run list:** Radio-style selection, shows run date and key metadata
- **Tabs:** Horizontal tab bar (active tab highlighted with `--accent-construction` underline)
- **Content area:** Tab-specific content (summary HTML, data grid, JSON tree)
- **Export rail:** Vertical button stack, always visible, matches context (e.g., Calculations tab shows filtered CSV export)

**Keyboard shortcuts:**
- `Esc` — close workspace
- `1-4` — switch tabs
- `↑↓` — navigate run list

**URL state:**
- `?run={folder}&tab={summary|calculations|raw|json}`
- Updates on tab/run change
- Deep-linkable (restore workspace on page load if params present)

### Calculations Tab (Data Grid)

**Requirements:**
- Production-grade grid library (Grid.js or Tabulator)
- Sort by column
- Multi-column filter
- Debounced search
- Confidence color on rows (green/yellow/red if field present)
- Formula column expandable or tooltip
- Footer totals by `item_type` (aggregates visible filtered rows)
- **Export filtered** button (client-side CSV from grid state)
- Cap banner: "Showing 500 of 1,234 — Download full CSV to analyze all rows"

**Grid style:**
- Dark theme matching Bobby Tailor tokens
- Monospace font for numbers (`--font-data`)
- Row hover: subtle background lift
- Selected row: `--border-active` left border

### Tab Styles

```css
.report-tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border-subtle);
  padding: 0 24px;
}

.tab-btn {
  padding: 12px 20px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 200ms ease;
}

.tab-btn.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent-construction);
}

.tab-btn:hover:not(.active) {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.05);
}
```

### Motion

- **Workspace enter:** Slide from right (300ms ease-out)
- **Tab switch:** Fade content out/in (200ms)
- **Run switch:** Content fade (150ms)
- **Export rail buttons:** Slight scale on hover (1.02, 150ms)

### Responsive

- **Desktop (1440+):** 3-column layout as shown
- **Laptop (1024-1439):** Reduce run list to 15%, export rail to 18%
- **Tablet (768-1023):** Run list becomes dropdown above tabs, export rail sticky bottom
- **Mobile (< 768):** Full-screen tabs, run list dropdown, export in overflow menu (three-dot)

---

## Color Overrides for Reports Page

| Element | Color | Variable |
|---------|-------|----------|
| Cached pill | `#10b981` | `--accent-success` |
| Syncing pill | `#f59e0b` | `--accent-warning` |
| Stale pill | `#94a3b8` | `--text-secondary` |
| Cost display | `#4ade80` | bright green for visibility |
| Confidence green | `#10b981` | high confidence |
| Confidence yellow | `#f59e0b` | medium confidence |
| Confidence red | `#ef4444` | low confidence |

---

## Accessibility

- All icon-only buttons must have `aria-label`
- Tab navigation with keyboard (arrow keys + Enter)
- Focus trap in workspace
- Focus-visible rings (2px, `--border-active`)
- Esc to close workspace must always work

---

## Component Checklist (from ui-ux-pro-max)

- [ ] No emojis as icons (use Lucide SVG)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with 150-300ms transitions
- [ ] Text contrast ≥ 4.5:1
- [ ] Focus states visible
- [ ] `prefers-reduced-motion` respected
- [ ] No horizontal scroll on mobile
