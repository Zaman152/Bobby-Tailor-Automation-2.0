# Projects Page — Design Overrides

> **This file overrides** `design-system/bobby-tailor/MASTER.md` for the Projects page specifically.

---

## Page Purpose

Guided workflow for selecting StackCT project → plan set → sheets → run. Supports both single-set and multi-set projects.

## Key User Pain (from Phase 15 Research)

- **Phase 14 added plan sets but UI still form-like, not guided** — Cognitive load on multi-set projects
- **No visual indication of multi-step flow** — Users unsure if they're in step 1 or 3 of selection

## Design Solution

### Stepper UI

**When to show:** Only when `mode=specific` (not "All Projects" mode)

**Visual:** Horizontal stepper above project list

```
┌──────────────────────────────────────────────────┐
│  ① Project  →  ② Plan Set  →  ③ Sheets  →  ④ Run │
│  ──────────────────────────────────────────────── │
```

**States:**
- **Active step:** Bold, `--accent-construction` circle fill
- **Completed step:** `--accent-success` circle, checkmark icon
- **Future step:** `--text-tertiary` circle, dim label
- **Current step indicator:** Larger circle with subtle pulse

**Responsive:** 
- Desktop: Horizontal with labels
- Mobile: Wrap to 2 rows or vertical stack

### Step Screens

**Step 1: Select Project**
- Standard project list (card grid)
- On project select → advance to Step 2

**Step 2: Choose Plan Set**
- **Auto-skip:** If project has only 1 plan set, auto-select and advance to Step 3
- **Multi-set:** Radio card picker
  - Each card shows: folder name, sheet count, version label if available
  - Selected card: `--border-active` border, slight scale
  - Cache status pill (if stale, show "Sync" button inline)
  - Breadcrumb shown above: "Project: {name}"
  - Back button: "← Change Project" (hidden if auto-skipped)

**Step 3: Select Sheets**
- Same as current sheet checklist
- Breadcrumb: "Project: {name} • Plan Set: {folder}"
- Back button: "← Change Plan Set"
- Search/filter UI at top
- Skeleton loaders during `syncing` (not plain spinner)
- Sheet cards: checkbox, thumbnail, page number, plan name

**Step 4: Run**
- Not a separate screen
- Sticky footer bar appears once ≥1 sheet selected
- Bar content: `Run {N} sheets from {planSet} • Est. cost: $—` + [Start Run] button
- Button disabled when 0 sheets selected
- Bar animates in from bottom (slide + fade)

### Plan Set Cards

```css
.plan-set-card {
  background: var(--bg-elevated);
  border: 2px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: all 200ms ease;
  position: relative;
}

.plan-set-card.selected {
  border-color: var(--border-active);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  transform: scale(1.02);
}

.plan-set-card:hover:not(.selected) {
  border-color: var(--text-secondary);
  transform: translateY(-2px);
}

.plan-set-header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  margin-bottom: 12px;
}

.plan-set-name {
  font-family: var(--font-display);
  font-size: 16px;
  color: var(--text-primary);
  font-weight: 500;
}

.sheet-count-badge {
  background: rgba(249, 115, 22, 0.2);
  color: var(--accent-construction);
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 500;
}
```

### Sticky Run Footer

```css
.run-footer {
  position: fixed;
  bottom: 0;
  left: 240px; /* sidebar width */
  right: 0;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border-subtle);
  padding: 16px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 -4px 12px rgba(0,0,0,0.3);
  z-index: 100;
}

.run-footer-info {
  font-size: 15px;
  color: var(--text-secondary);
}

.run-footer-info strong {
  color: var(--text-primary);
  font-weight: 600;
}

.run-footer .btn-primary {
  min-width: 160px;
  padding: 14px 32px;
  font-size: 16px;
}

.run-footer .btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

### Skeleton Loaders

**During syncing:** Replace spinner text with animated skeleton cards

```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--bg-surface) 25%,
    var(--bg-elevated) 50%,
    var(--bg-surface) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
  border-radius: var(--radius-md);
}

@keyframes skeleton-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton-card {
  height: 120px;
  margin-bottom: 12px;
}
```

### Toast Notifications

**Trigger events:**
- Plan set sync completes: `ui.toast.success("Plan sets updated")`
- Network error: `ui.toast.error("Failed to load plan sets. Check connection.")`
- Sync in progress: `ui.toast.info("Syncing plan sets… (this may take a moment)")`

**Position:** Top-right, stacked vertically, max 3 visible at once

### Motion

- **Stepper progress:** Active step circle pulse (subtle, 2s infinite)
- **Plan set cards:** Stagger reveal (50ms delay each)
- **Footer slide-in:** From bottom (300ms ease-out) when first sheet selected
- **Breadcrumb update:** Fade old/new text (200ms)

### Responsive

- **Desktop (1024+):** 3-column plan set cards, full stepper horizontal
- **Tablet (768-1023):** 2-column plan set cards, stepper wraps if needed
- **Mobile (< 768):** 1-column, stepper vertical or icon-only with labels below

---

## Color Overrides for Projects Page

| Element | Color | Variable |
|---------|-------|----------|
| Stepper active | `#f97316` | `--accent-construction` |
| Stepper complete | `#10b981` | `--accent-success` |
| Stepper inactive | `#475569` | `--text-tertiary` |
| Cache pill (stale) | `#f59e0b` | `--accent-warning` |
| Cache pill (syncing) | `#3b82f6` | `--accent-primary` |
| Sheet count badge | Orange tint | `rgba(249, 115, 22, 0.2)` background |

---

## Accessibility

- Stepper announces current step via `aria-current="step"`
- Plan set cards keyboard selectable (Space to select)
- Footer "Start Run" button announces sheet count via `aria-label`
- Back buttons always visible and labeled clearly
- Focus trap NOT needed (not modal)

---

## Component Checklist

- [ ] Stepper step numbers are `<span>` with `role="status"` when active
- [ ] Plan set cards use `<button>` or `<label>` with radio input (not just `<div>`)
- [ ] Sticky footer animates in smoothly (not instant pop)
- [ ] Skeleton loaders respect `prefers-reduced-motion` (static gradient fallback)
- [ ] Toast auto-dismiss after 5s (or user dismiss)
