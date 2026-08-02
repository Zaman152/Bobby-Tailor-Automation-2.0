# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Bobby Tailor
**Generated:** 2026-05-26 23:00:28
**Category:** SaaS (General)

---

## Global Rules

### Color Palette — Dark Industrial

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Base Background | `#0b0d11` | `--bg-base` |
| Surface | `#1a1d24` | `--surface-primary` |
| Surface Glass | `rgba(26, 29, 36, 0.6)` | `--surface-glass` |
| Accent/CTA | `#f97316` | `--accent-construction` |
| Primary Text | `#f1f5f9` | `--text-primary` |
| Secondary Text | `#94a3b8` | `--text-secondary` |
| Border Subtle | `#2d3139` | `--border-subtle` |
| Success | `#4ade80` | `--accent-success` |

**Color Notes:** Dark industrial with construction orange accent — NOT the light glassmorphism palette

### Typography

- **Display Font:** DM Mono (for brand, headings)
- **Body Font:** Inter (UI text, paragraphs)
- **Data Font:** JetBrains Mono (logs, calculations, code blocks)
- **Mood:** industrial, precise, technical, professional, construction-focused
- **Google Fonts:** Already loaded in templates/index.html

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
```

**Font Variables:**
- `--font-display: 'DM Mono', monospace;`
- `--font-body: 'Inter', system-ui, sans-serif;`
- `--font-data: 'JetBrains Mono', monospace;`

### Spacing Variables

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.2)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.3)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.4)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.5)` | Full-screen drawers |

**Note:** Darker shadows for dark theme compared to light glassmorphism defaults

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: var(--accent-construction);
  color: white;
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
  border: none;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 2px solid var(--border-subtle);
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-weight: 500;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-secondary:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}
```

### Cards

```css
.card {
  background: var(--bg-surface);
  border-radius: var(--radius-lg);
  padding: 24px;
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-sm);
  transition: all 200ms ease;
}

.card:hover {
  border-color: var(--border-active);
  box-shadow: var(--shadow-md);
}
```

### Glass Cards

```css
.card-glass {
  background: var(--surface-glass);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-lg);
}
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  color: var(--text-primary);
  border-radius: var(--radius-md);
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: var(--border-active);
  outline: none;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
}

.modal {
  background: var(--bg-elevated);
  color: var(--text-primary);
  border-radius: var(--radius-lg);
  padding: 32px;
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Industrial Dark SaaS

**Keywords:** Dark background, construction theme, technical precision, data-focused, professional estimator tool, glass surfaces

**Best For:** B2B SaaS, construction software, data-heavy dashboards, technical tools, professional estimators

**Key Effects:** Backdrop blur for glass surfaces, subtle borders, elevation shadows, construction orange accents

### Icon System

**Library:** Lucide Icons (https://lucide.dev/)
**Format:** SVG sprite or CDN
**Usage:** Replace text-only buttons with icon + text combinations

```html
<!-- Example Lucide icon usage -->
<svg class="icon" width="18" height="18">
  <use href="/static/icons/lucide-sprite.svg#file-text"/>
</svg>
```

### Page Pattern

**Pattern Name:** Dark SaaS Dashboard

- **Conversion Strategy:** Information-first, fast access to data, clear hierarchy. Sidebar navigation, main content area, optional detail panels.
- **CTA Placement:** Context-dependent (primary actions in top-right of content areas, destructive actions require confirmation)
- **Section Order:** 1. Navigation (sidebar), 2. Page header with title, 3. Main content (cards/tables/forms), 4. Optional detail drawers/modals

---

## Anti-Patterns (Do NOT Use)

- ❌ Light backgrounds by default (this is a DARK industrial theme)
- ❌ Excessive animation that distracts from data
- ❌ Bright or neon colors except for construction orange accent

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile
