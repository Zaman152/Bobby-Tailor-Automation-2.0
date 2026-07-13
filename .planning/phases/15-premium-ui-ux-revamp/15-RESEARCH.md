# Phase 15: Premium UI/UX Revamp — Research

**Date:** 2026-05-26  
**Status:** Ready for planning  
**Depends on:** Phases 8–14 (shell, reports APIs, plan sets, auth)

## Problem statement (user-reported)

The app is functionally complete but **feels like an internal tool**, not a premium estimator product:

| Pain | Current behavior | Impact |
|------|------------------|--------|
| Preview vs download | Four similar buttons on report cards (`Preview`, `Calculations`, `Raw CSV`, `{ } JSON`) — labels look like actions of the same type | Users click download expecting preview, or miss preview entirely |
| Preview navigation | Inline accordion inside card; tabs only visible after expand; switching runs collapses context | Hard to compare runs or jump Summary → Calculations → JSON |
| Data analysis | Basic HTML table, capped rows, no column resize, weak confidence/formula readability | Estimators cannot trust or audit takeoff math in-browser |
| Plan workflow | Phase 14 adds plan sets but UI is still form-like, not guided | Cognitive load on multi-set projects |
| Motion & polish | Minimal Motion on page enter; no modals, toasts, or loading skeletons | App does not feel “powerful” |

## Design direction

### Keep (do not throw away)

- **Flask + Jinja + vanilla ES modules** — no React rewrite in v1 (ARCH-01 deferred).
- **Industrial dark theme** from `Master.md` §8.1 (`--bg-base`, `--accent-construction`, DM Mono / Inter / JetBrains Mono).
- **Existing APIs** — Phase 5 preview endpoints, Phase 13/14 cache flags (`from_cache`, `syncing`, `stale`).
- **Motion library** already in `static/ui-motion.js` (Motion v11 CDN — same family as Framer Motion, **no React required**).

### Upgrade

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Design system | `design-system/bobby-tailor/MASTER.md` + per-page overrides | ui-ux-pro-max `--persist`; **override** auto light palette → dark industrial |
| Icons | Lucide (SVG sprite or CDN) | ui-ux-pro-max rule: no emoji icons |
| Components | `static/js/ui/*` primitives + **21st.dev MCP** for high-value blocks | `21st_magic_component_builder` during execute for report shell, stepper, data grid chrome |
| Tables | **Grid.js** or **Tabulator** (CDN, vanilla) | Virtualization, sort, resize, export; replaces hand-rolled `renderDataTable` |
| Preview shell | **Full-screen drawer / modal workspace** | Left: run list · Center: tab content · Right: download rail |
| Motion | Motion One + CSS `view-transition-name` where supported | Expand `ui-motion.js`: modal enter/exit, drawer slide, stagger, `prefers-reduced-motion` |
| 3D | **Optional** — login hero only (`three` r128 + low-poly grid), `pointer-events: none` | Visual premium without touching data UX; skip if perf budget fails |
| Framer (product) | **Not** Framer Motion React in v1 | User said “Framer” — deliver via **Motion One** (already started) + Framer-style easing curves |

## Reports Preview Workspace (target UX)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ← Back to Reports    Office Complex – Downtown    May 25, 2026    ● Cached │
├──────────────┬──────────────────────────────────────────────┬───────────────┤
│  RUNS        │  [Summary] [Calculations] [Raw] [JSON]      │  DOWNLOAD     │
│  ─────────   │  ─────────────────────────────────────────  │  ───────────  │
│  ● This run  │  Rich summary / data grid / JSON tree       │  ⬇ Calc CSV   │
│  ○ Older…    │  Sticky filters · totals row · formula tip  │  ⬇ Raw CSV    │
│              │                                              │  ⬇ JSON       │
│              │                                              │  ⬇ Summary    │
└──────────────┴──────────────────────────────────────────────┴───────────────┘
```

**Interaction rules:**

- Card shows **one primary CTA**: “Open preview workspace” (icon + label).
- Downloads grouped under **“Export”** menu or right rail — never mixed with preview CTA.
- URL hash or query: `#/reports?run=<folder>&tab=calculations` for shareable state.
- Keyboard: `Esc` close, `1–4` tabs, `↑↓` run list (when workspace open).

## Calculations / raw analysis requirements

From `Master.md` §7.1.2 + Phase 10 research (not fully delivered in UI):

- Sortable columns, multi-filter, debounced search (exists — **upgrade grid**)
- **Confidence color** on rows (green/yellow/red) if field present
- **Formula column** expandable or tooltip (`formula_applied`)
- Footer **totals by item_type** (aggregate visible rows)
- Export **filtered** subset CSV (client-side from grid state)
- Clear **“Showing N of M”** when API caps rows; “Load more” if backend adds pagination later

## Projects workspace (plan sets)

Guided **stepper** (not new backend):

1. Select project  
2. Choose plan set (cards from Phase 14)  
3. Select sheets (checklist + filters)  
4. Run (sticky footer with count + cost estimate placeholder)

Use same modal/drawer patterns as reports for consistency.

## Tooling during execute-phase

| Tool | When |
|------|------|
| **ui-ux-pro-max** | Wave 1 — tokens, checklist, page overrides |
| **21st.dev MCP** | Waves 2–3 — `component_builder` for preview shell, stepper, monitor header; `refiner` to polish |
| **Motion CDN** | All waves — extend `ui-motion.js` |
| **Three.js** | Wave 4 optional — login background only |
| **GitNexus** | Before editing `app.js` symbols — impact on report preview flow |

## File architecture (target)

```
static/
  style.css              # tokens v2, imports
  ui-polish.css          # glass surfaces, elevation
  ui-motion.js           # motion helpers
  js/
    ui/                  # modal, drawer, toast, icon
    reports-workspace.js # preview shell (extract from app.js)
    projects-flow.js     # stepper + plan sets
    data-grid.js         # Grid.js wrapper
  app.js                 # thinner orchestrator
templates/
  index.html             # shell + modal mount points
  partials/              # optional: report-workspace.html
design-system/bobby-tailor/
  MASTER.md
  pages/reports.md
  pages/projects.md
```

## Requirements mapping (new IDs for Phase 15)

| ID | Summary |
|----|---------|
| UX-01 | Design tokens v2 + dark industrial MASTER persisted |
| UX-02 | Shared modal/drawer/toast primitives with a11y |
| UX-03 | Reports: preview vs export actions visually distinct |
| UX-04 | Full-screen report preview workspace with run + tab navigation |
| UX-05 | Calculations/raw: production-grade grid (sort, filter, export selection) |
| UX-06 | Deep-link / restore preview tab from URL |
| UX-07 | Projects: guided stepper for plan set → sheets → run |
| UX-08 | Job monitor: timeline + sheet log polish |
| UX-09 | Motion system with reduced-motion fallback |
| UX-10 | 21st.dev pass documented for key components |
| UX-11 | Responsive 375–1440 verified |
| UX-12 | Login/settings/PDF visual parity with shell |

## Risks

| Risk | Mitigation |
|------|------------|
| `app.js` ~1.5k lines — refactor breaks CSRF/apiFetch | Extract modules incrementally; one page per plan |
| Grid CDN weight | Lazy-load when opening Calculations tab |
| 21st MCP generates React | Prompt for **vanilla HTML/CSS/JS** only; adapt output |
| Three.js on low-end VPS clients | Login only; disable via `prefers-reduced-motion` |

## Out of scope (v1)

- React / Vite migration  
- Framer Motion React components  
- Rewriting backend preview APIs (unless pagination needed)  
- Custom charting dashboard (use grid + summary stats only)

## References

- `Master.md` §8 (UI spec), §7.1.2 (report preview)  
- `.planning/phases/10-reports-job-monitor-ui/10-RESEARCH.md`  
- `static/app.js` — `renderReportCard`, `loadPreviewTab`, `loadCsvPreview`  
- `static/ui-motion.js` — Motion One already integrated
