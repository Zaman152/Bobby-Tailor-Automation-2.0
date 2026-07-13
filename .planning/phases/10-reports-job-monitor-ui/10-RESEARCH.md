# Phase 10: Reports & Job Monitor UI — Research

## Overview

Phase 10 delivers the Reports page with in-browser preview tabs and a dedicated job monitor view. This phase depends on Phase 5 (API endpoints), Phase 7 (Shell & Navigation), and Phase 8 (Page components).

## Master Document References

### §7.1.2 — Feature 1.2: In-Browser Report Preview

**Reports tab redesign goals:**

1. Each report card expands to show:
   - **Summary tab** (default): Renders `summary.txt` content as styled HTML with color-coded categories
   - **Calculations table tab**: Interactive data table with sorting, filtering, search
   - **Raw Items tab**: Same table format for `raw_items.csv`
   - **JSON tab**: Collapsible tree viewer for `takeoff.json`

2. Calculations table requirements:
   - Column sorting (click header)
   - Filter by sheet (dropdown)
   - Filter by item type (dropdown)
   - Search box (searches description + source_text)
   - Color coding: green = high confidence, yellow = medium, red = low
   - Export selected rows as CSV

3. Backend endpoint needed:
   ```
   GET /api/reports/<run_folder>/preview/<filename>
   ```
   - Returns CSV as JSON rows
   - Returns JSON as-is
   - Returns TXT as text field

### §8.4 — Page: Active Job (Live Monitor)

**Job monitor layout:**

```
┌─── JOB MONITOR ─────────────────────────────────────────────────┐
│  Project: Office Complex – Downtown          Job: a3f9bc12       │
│  Started: 14:23:05                           Status: ● RUNNING   │
│                                                                   │
│  ████████████████████░░░░░░░░░░░  68%   [8 / 12 sheets]         │
│                                                                   │
│  Currently analyzing: E2.01 – Panel Schedule HM1                 │
│                                                                   │
│  ┌─ SHEET LOG ──────────────────────────────────────────────┐    │
│  │  ✓  A1.01  Floor Plan L1      18 meas  3 rooms  2 comp  │    │
│  │  ✓  A1.02  Floor Plan L2      21 meas  5 rooms  4 comp  │    │
│  │  ✓  A3.01  Toilet Plans        6 meas  2 rooms  0 comp  │    │
│  │  ✓  E1.01  Riser Diagram       4 meas  8 comp   0 rooms │    │
│  │  ⟳  E2.01  Panel Schedule    analyzing...               │    │
│  │  ○  M1.01  Mechanical Plan    pending                    │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─ LOG CONSOLE ────────────────────────────────────────────┐    │
│  │  [14:23:11] Logged in to StackCT                        │    │
│  │  [14:23:14] Found 12 drawing pages                      │    │
│  │  [14:23:19] A1.01: 18 measurements, 3 rooms extracted  │    │
│  │  [14:23:24] A1.01: 12 calculated takeoff items          │    │
│  │  [14:23:29] A1.02: 21 measurements, 5 rooms extracted  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  [CANCEL JOB]                                                    │
└──────────────────────────────────────────────────────────────────┘
```

**Key components:**
- Project name and job ID header
- Started time and live status indicator
- Progress bar with percentage and sheet fraction
- Currently analyzing indicator with sheet name
- Sheet log showing per-sheet status (done ✓, analyzing ⟳, pending ○)
- Per-sheet metrics: measurements, rooms, components count
- Log console with timestamped entries
- Cancel job button

### §8.5 — Page: Reports

**Report cards layout:**

```
┌─── REPORT CARDS ────────────────────────────────────────────────┐
│                                                                   │
│  ┌─ Office Complex – Downtown ──────────────────── May 25, 2026 ─┐
│  │  12 sheets  ·  847 raw items  ·  312 calculated  ·  $0.04    │
│  │                                                               │
│  │  [📊 Preview]  [📥 Calculations CSV]  [📋 Raw CSV]  [{ }]    │
│  └───────────────────────────────────────────────────────────────┘
│                                                                   │
│  ┌─ Retail Build-Out – Unit 4A ─────────────────── May 24, 2026 ─┐
│  │  8 sheets  ·  421 raw items  ·  158 calculated  ·  $0.02     │
│  │  [📊 Preview]  [📥 Calculations CSV]  [📋 Raw CSV]  [{ }]    │
│  └───────────────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────┘
```

**Report card requirements:**
- Project name and date header
- Metadata line: sheet count, raw item count, calculated count, API cost
- Action buttons: Preview, Calculations CSV, Raw CSV, JSON download

**Report Preview Panel (expandable):**

```
[Summary] [Calculations] [Raw Items] [JSON]   ← tab strip

── Calculations view ──────────────────────────────────────────────
Filter: [All Sheets ▼]  [All Types ▼]  [🔍 search...]   [Export CSV]

 item_type    │ description          │ qty    │ unit   │ sheet      │ formula
 ─────────────┼──────────────────────┼────────┼────────┼────────────┼─────────
 flooring     │ Conf Room 106        │ 269.5  │ sq_ft  │ A1.01      │ 245 × 1.10
 ceiling_grid │ Conf Room 106        │ 264.6  │ sq_ft  │ A1.01      │ 245 × 1.08
 paint        │ Paint for Conf 106   │ 4      │ gal    │ A1.01      │ ceil(562 × 2/350)
 drywall      │ Drywall Conf 106     │ 20     │ sheets │ A1.01      │ ceil(562 × 1.12/32)
──────────────────────────────────────────────────────────────────
 Totals: flooring 2,847 sq_ft │ drywall 312 sheets │ paint 89 gal
```

## Dependencies Analysis

### Phase 5 Dependencies
- `/api/reports` endpoint — lists all report runs with file metadata
- `/api/reports/<folder>/<file>` endpoint — downloads specific files
- `/api/reports/<run_folder>/preview/<filename>` endpoint — returns file content as JSON for preview

### Phase 7 Dependencies
- Sidebar navigation structure
- Main content area layout
- Active job mini-card in sidebar

### Phase 8 Dependencies
- Page shell components
- Card styling patterns
- Tab component patterns
- Button and control styling

## Technical Requirements

### Report Preview Component
1. Tab strip for Summary/Calculations/Raw/JSON views
2. Data table component with:
   - Sortable columns (click header to toggle sort)
   - Filter dropdowns for sheet and item_type
   - Search input with debounced filtering
   - Row limit with "showing X of Y" indicator
3. Summary view with styled HTML rendering
4. JSON tree viewer (collapsible nodes)

### Job Monitor Component
1. Header with project/job info and status badge
2. Progress bar component with:
   - Percentage fill
   - Text label with sheet count (8 / 12)
3. Currently analyzing indicator
4. Sheet log list with:
   - Status icon (✓/⟳/○)
   - Sheet code
   - Sheet name
   - Metrics (measurements, rooms, components)
5. Log console with:
   - Timestamp per entry
   - Auto-scroll to bottom
   - Maximum height with scroll
6. Cancel button

### API Polling Strategy
- Job status polling: 1 second interval while running
- Auto-stop polling when status is "done" or "error"
- Navigate to reports on job completion

## UI/UX Design Notes

### Color Coding
- Status done (✓): `--accent-success` (#10b981)
- Status analyzing (⟳): `--accent-primary` (#3b82f6)
- Status pending (○): `--text-tertiary` (#475569)
- High confidence rows: subtle green tint
- Medium confidence: subtle yellow tint
- Low confidence: subtle red tint

### Typography
- Sheet names: "JetBrains Mono" (data font)
- Log timestamps: "JetBrains Mono"
- Table data: "JetBrains Mono"
- Headers: "DM Mono"

### Responsive Behavior
- Sheet log scrolls independently
- Log console scrolls independently
- Preview table has horizontal scroll on narrow screens

## Implementation Approach

### 10-01: Reports Page + Preview Tabs
1. Create report cards grid layout
2. Implement expandable preview panel
3. Build tab strip component
4. Implement data table with sorting/filtering
5. Add summary view renderer
6. Add JSON tree viewer
7. Wire up preview API calls
8. Add download buttons functionality

### 10-02: Job Monitor Page/Panel
1. Create job monitor page component
2. Build progress bar component
3. Implement sheet log list
4. Build log console with auto-scroll
5. Wire up status polling
6. Handle job completion navigation
7. Implement cancel job functionality

## Risk Assessment

- **Medium Risk**: Data table performance with large row counts (> 500 rows)
  - Mitigation: Client-side pagination, virtual scrolling if needed
  
- **Low Risk**: JSON tree viewer complexity
  - Mitigation: Use existing library or simple recursive renderer

## Success Criteria Mapping

| Criterion | Plan | Implementation |
|-----------|------|----------------|
| Reports page lists runs as expandable cards with tabs | 10-01 | Report cards + preview panel |
| Each preview tab uses Phase 5 APIs | 10-01 | API integration in preview |
| Job monitor shows progress bar, current sheet, log | 10-02 | Full job monitor component |
| Download without losing preview context | 10-01 | Download buttons preserve state |
