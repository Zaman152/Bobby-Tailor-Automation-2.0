# Feature Research

**Domain:** Construction Take-off & Estimation Automation (SaaS-style)
**Researched:** May 26, 2026
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in construction take-off/estimation automation tools. Missing these = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Digital Takeoff from PDF/CAD** | Industry standard since 2020s; manual tracing is obsolete | LOW | Bobby already has this (StackCT browser automation + PDF upload). Must support multi-page sets and maintain drawing fidelity at 2x DPI |
| **Structured CSV/Excel Export** | Estimators must integrate quantities into existing cost databases and bid systems | LOW | Bobby has `calculations.csv` and `raw_items.csv`. Good. Export format must have descriptive columns (formula_applied, source_sheet, etc.) not just qty/unit |
| **Visual Audit Trail** | Every quantity must be traceable to a specific drawing location; "trust but verify" culture in construction | MEDIUM | **Gap in Bobby**: No visual markup overlays showing where measurements came from. Users download screenshot PNGs separately from CSVs. Need in-browser preview with visual linkage |
| **Multi-Sheet Project Support** | Real projects = 8–30+ sheets; tools must handle full plan sets, not single pages | LOW | Bobby has this via StackCT `page_ids` discovery. Good |
| **Plan Selection Before Run** | Don't force "all or nothing"; estimators need to pick specific sheets (e.g., only electrical, skip civil) | MEDIUM | **Critical Gap #2 in Master.md**: User-reported pain point. Bobby runs all pages immediately. Need checkbox selection UI post-project-select |
| **In-Browser Report Preview** | Download-only reports = friction; users expect sortable/filterable tables, summary views, and JSON inspection inline | MEDIUM | **Critical Gap #3**: Bobby Reports tab is download-only. Need collapsible preview with filtering by sheet/type/search |
| **Job Status Monitoring** | Background jobs must show live progress (%), current sheet being processed, and log tail (last 5–10 lines) | LOW | Bobby has `/api/status` polling. Good. Could enhance with per-sheet mini-thumbnails during processing |
| **Error Recovery & Retry** | Automated systems fail (network, API limits, bad PDFs); users expect graceful error messages and per-page retry | MEDIUM | Bobby has per-page error recovery in `scraper.py`. Good. Must sanitize error messages for end users (Gap #10) |
| **Basic Settings/Config UI** | Credentials, API keys, output paths, and model selection must be editable via UI, not `.env` file editing | MEDIUM | Bobby lacks settings page (Master §8.8). Estimators are not developers; `.env` editing is unacceptable for production use |
| **Waste Factor / Markup Support** | Construction always adds waste (10% flooring, 12% drywall, etc.); must be configurable and visible in formula output | LOW | Bobby has this in `calculator.py` ESTIMATION_TABLES. Good. Future: per-client profiles (Master Phase 4) |

### Differentiators (Competitive Advantage)

Features that set a product apart from competitors. Not expected baseline, but create measurable value when present.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **AI Vision Extraction (No Manual Training)** | Competitors like PlanSwift/STACK require manual symbol mapping per project; Claude Vision reads drawings zero-shot like a human estimator | HIGH | Bobby's core differentiator. Claude Haiku/Sonnet with cached prompt = $0.04–$0.05 per 30-page set. Competitors charge $200–$500/month subscriptions. Speed advantage: 5 minutes vs 30–60 minutes manual |
| **Cost Tracking Per Run** | Show tokens consumed, USD cost, and model used per analysis run; transparency builds trust and prevents bill shock | LOW | **Gap #6**: Bobby doesn't track this yet. Simple addition: log `response.usage` from Claude API, aggregate in `reporter.py`, display in Reports tab and `summary.txt` |
| **Schedule/Table Extraction** | Most tools focus on geometric takeoff (areas, lengths, counts); few extract structured data from embedded tables (panel schedules, door schedules, equipment lists) | MEDIUM | Bobby has this with Claude Vision's `schedules[]` extraction. Strong differentiator for MEP trades. Must ensure panel schedule rows appear in `raw_items.csv` and calculated totals in `calculations.csv` |
| **Formula Transparency** | Show exact calculation formulas in output ("245 SF × 1.10 waste = 269.5 SF"), not just final quantities; allows estimators to validate and adjust | LOW | Bobby has `formula_applied` column in `calculations.csv`. Excellent. Competitors often hide calculations in black-box assemblies |
| **Agentic Context Awareness** | AI understands drawing context: distinguishes table cells from legend text, cross-references room names across sheets, identifies drawing type automatically | VERY HIGH | Bobby lacks this (Claude Vision operates per-sheet, no cross-sheet context). Emerging differentiator in 2026 (Kreo 6.0, Togal.AI). Future enhancement: multi-sheet project context, drawing package structure analysis |
| **Sheet Type Auto-Classification & Model Routing** | Automatically detect electrical/mechanical/architectural sheets and route to appropriate extraction model (e.g., Sonnet for schedules, Haiku for floor plans) | LOW | Bobby has heuristic routing in `_pick_model()` by sheet name keywords. Good start. Could enhance with Claude Vision's `sheet_type` output to create feedback loop |
| **Canvas Stability Detection** | Replace fixed wait times with pixel-hash polling to detect when drawing finishes rendering; faster on good connections, more reliable on slow VPS | MEDIUM | **Gap #4**: Bobby uses `asyncio.sleep(5)` fixed wait. Pixel-hash polling (Master §7.2.2) = 15–20 minutes implementation, ~30% faster average takeoff time |
| **PDF Page Preview & Selection** | Upload PDF → show thumbnail grid → select specific pages before analysis (not all-or-nothing) | MEDIUM | **Gap #7**: Bobby PDF mode analyzes all pages. Need PyMuPDF thumbnail generation + checkbox UI (Master §8.6) |
| **Real-Time Collaboration (Multi-User)** | Multiple estimators work on same project simultaneously; live updates, presence indicators, comment threads | VERY HIGH | Out of scope for Bobby (single-operator tool, Master Gap #9). Enterprise differentiator for ProEst/STACK. Bobby is brownfield automation, not full platform |
| **Integrated Cost Database** | Built-in RSMeans or supplier pricing tied to takeoff items; quantities auto-populate with unit costs | VERY HIGH | Out of scope for Bobby. Bobby outputs CSVs that feed into client's existing cost systems. Full integration = months of work + ongoing database maintenance |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good on the surface but create problems in practice for construction take-off automation.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Fully Automated "Zero Touch" Takeoff** | Sales pitch: "AI does everything, no human review needed" | Estimators don't trust black boxes; construction has legal liability for bid accuracy; confidence scoring exists but AI still misreads complex details 5–15% of the time | Hybrid workflow: AI generates draft takeoff in minutes, estimator reviews/adjusts in visual interface. Bobby's approach is correct: provide transparent formulas and raw extraction for audit |
| **Real-Time Everything (Live Drawing Sync)** | Users think they want instant updates as drawings change | Adds massive complexity (WebSocket infrastructure, conflict resolution, state management); construction drawings are versioned snapshots, not live documents | Batch processing with clear version control. Bobby's timestamped run folders (`{ProjectName}_{YYYYMMDD}_{HHMMSS}/`) are correct approach. Future: diff mode to compare runs |
| **Built-In Proposal Generation** | Combine takeoff + pricing + formatted PDF proposal in one tool | Proposals are highly client-specific (branding, terms, exclusions, format); building a flexible proposal engine = another product. Most firms already have Word/Excel templates | Export structured data (CSV/JSON) that feeds into client's existing proposal workflow. Bobby does this correctly |
| **Mobile-First Design** | "I want to do takeoffs on my iPad at the job site" | Takeoff requires precision (measuring to 1/16"), large screen real estate to see drawing details, and reference to specifications. Mobile works for *reviewing* takeoffs, not creating them | Desktop-first for takeoff creation, mobile-friendly for reports/review. Bobby's Flask UI should be responsive for report viewing, but takeoff workflow is correctly desktop-focused |
| **Overly Rigid Workflows** | Enterprise tools with mandatory steps, approval gates, role-based access control | Small firms (Bobby's target: single estimator or 2–3 person teams) need flexibility; rigid workflows get abandoned when estimator needs to "just get the bid out" | Simple, flexible workflows with optional enhancements. Bobby's current "select project → run → download reports" is appropriately minimal. Settings page (Master §8.8) adds needed config without rigidity |
| **Trying to Replace Estimator Judgment** | "AI will eliminate the need for estimators" | Construction has too many project-specific variables (site conditions, labor availability, subcontractor relationships, risk assessment) that AI cannot assess. Tools that claim to "do the estimator's job" are either lying or produce dangerous bids | Position as "estimator augmentation" not "estimator replacement". Bobby correctly frames as automation of tedious measurement reading, not bid strategy. Human reviews formulas and applies domain knowledge |
| **Symbol Libraries & Manual Training** | First-gen digital takeoff tools required building symbol libraries per project (teach software "this is a door") | High setup overhead; estimators spend hours on configuration before measuring anything. Pre-trained AI (Claude Vision, Vertex AI) eliminates this | Zero-shot vision models that recognize standard construction symbols out-of-the-box. Bobby's Claude Vision approach is correct; competitors still stuck on this |
| **Excessive Customization** | Every team wants "our own unique assemblies, formulas, and categories" | Leads to fragmented, unmaintainable systems. Each customization = technical debt. Small firms lack resources to maintain complex custom configs | Provide opinionated defaults (Bobby's ESTIMATION_TABLES) with documented extension points. Future: waste factor profiles (Master Phase 4.2) as named JSON configs, not full DSL |

## Feature Dependencies

```
[Digital Takeoff] 
    └──requires──> [Claude Vision API]
    └──enables──> [Structured Export]

[Plan Selection Workflow]
    └──requires──> [get_all_page_ids() from browser.py]
    └──requires──> [UI: project → plan list → checkboxes → run selected]
    └──enhances──> [User Control & Efficiency]

[In-Browser Report Preview]
    └──requires──> [API: /api/reports/<folder>/preview/<file>]
    └──requires──> [UI: CSV → data table, JSON → tree viewer, TXT → styled HTML]
    └──enables──> [Visual Audit Trail]
    └──reduces──> [Download Friction]

[Cost Tracking]
    └──requires──> [Claude response.usage logging in claude_analyzer.py]
    └──requires──> [Aggregation in reporter.py]
    └──enables──> [Transparency & Trust]

[Settings Page]
    └──requires──> [UI form for credentials, API keys, models, output paths]
    └──requires──> [Backend: read/write .env or DB config]
    └──enables──> [Non-Technical User Access]
    └──blocks──> [Production Deployment] (without this, tool is developer-only)

[Canvas Stability Detection]
    └──requires──> [Pixel-hash polling in browser.py]
    └──replaces──> [Fixed asyncio.sleep(5)]
    └──enables──> [Faster & More Reliable Screenshots]

[Waste Factor Profiles (Future)]
    └──requires──> [JSON config file: profiles with named waste factor sets]
    └──requires──> [UI: profile selector in Settings or pre-run]
    └──enhances──> [Multi-Client Support]
```

### Dependency Notes

- **Plan Selection requires browser.py foundation**: The `get_all_page_ids()` method already exists and is reliable (DOM attribute scraping, not clicking). UI work is frontend-only; backend is 90% done.
- **In-Browser Preview is cosmetic but high-impact**: No changes to extraction logic; pure presentation layer. Unblocks user trust ("I can see what it found without downloading 4 files").
- **Settings Page is deployment blocker**: `.env` file editing is acceptable for developers, unacceptable for production users. This is the difference between "working prototype" and "shippable product".
- **Cost Tracking depends on Claude API response structure**: Simple integration (5 lines in `claude_analyzer.py`, 10 lines in `reporter.py`). No external dependencies beyond Anthropic SDK.
- **Agentic Context Awareness is future architecture**: Requires multi-sheet context window or RAG-style system. Not in Master.md scope; Phase 4+ consideration if Bobby scales to enterprise clients.

## MVP Definition

### Launch With (v1) — Master.md Phase 1–3

Minimum viable product to replace current Bobby Tailor prototype and unblock production use.

- [x] **Digital Takeoff (StackCT + PDF)** — Already exists; proven with successful Bid_for_Baking_Social run
- [x] **Claude Vision Extraction** — Core automation; Haiku/Sonnet routing working
- [x] **Structured CSV/JSON Reports** — `raw_items.csv`, `calculations.csv`, `summary.txt`, `takeoff.json`
- [x] **Multi-Sheet Projects** — StackCT page discovery and PDF multi-page handling
- [x] **Formula Transparency** — `formula_applied` column in calculations.csv
- [x] **Waste Factors** — ESTIMATION_TABLES with configurable multipliers
- [ ] **Plan Selection Workflow** — Master Gap #2; user-reported pain point; 30-minute implementation
- [ ] **In-Browser Report Preview** — Master Gap #3; download friction; 2-hour frontend work
- [ ] **Settings Page** — Master Gap #8.8; deployment blocker; 1-hour implementation
- [ ] **Sanitized Error Messages** — Master Gap #10; hide stack traces from end users
- [ ] **Fix Hardcoded .env Path** — Master §7.1.3; critical for VPS deployment

### Add After Validation (v1.x) — Master.md Phase 2–3

Features to add once core workflow is validated and user feedback collected.

- [ ] **Cost Tracking Per Run** — Transparency feature; 20-minute implementation; Master Gap #6
- [ ] **Canvas Stability Detection** — Performance optimization; 15-minute implementation; Master Gap #4
- [ ] **PDF Page Selection** — Parity with StackCT plan selection; 1-hour implementation; Master Gap #7
- [ ] **Job Monitor with Per-Sheet Progress** — UX polish; current sheet name + mini-thumbnail; Master Gap #5
- [ ] **Project List Scroll Fix** — Reliability enhancement for large StackCT accounts; Master Gap #1
- [ ] **UI/UX Overhaul** — Industrial dark theme, sidebar layout, fixed navigation; Master §8 full spec

### Future Consideration (v2+) — Master.md Phase 4

Features to defer until product-market fit is established and core use case is solid.

- [ ] **Per-Sheet Confidence Review** — Screenshot side-by-side with extracted data; manual accept/reject per item
- [ ] **Client-Specific Waste Factor Profiles** — Named JSON configs; dropdown selector in Settings
- [ ] **Scheduled Runs with Notifications** — APScheduler integration; email/Slack alerts on completion
- [ ] **Diff Mode for Plan Revisions** — Compare two runs; highlight quantity changes sheet-by-sheet
- [ ] **Excel Export with Branding** — xlsxwriter output; conditional formatting; client logo/header
- [ ] **Agentic Multi-Sheet Context** — Cross-reference room names, detect sheet relationships, auto-organize drawing packages

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| **Plan Selection Workflow** | HIGH (user-reported pain) | LOW (30 min backend + 1hr UI) | **P1** |
| **In-Browser Report Preview** | HIGH (reduces friction) | MEDIUM (2hr UI, 20min API) | **P1** |
| **Settings Page** | HIGH (deployment blocker) | LOW (1hr UI + backend) | **P1** |
| **Fix Hardcoded .env Path** | HIGH (VPS deployment critical) | LOW (5 min code change) | **P1** |
| **Sanitize Error Messages** | MEDIUM (professionalism) | LOW (15 min try/catch cleanup) | **P1** |
| **Cost Tracking** | MEDIUM (transparency) | LOW (20 min implementation) | **P2** |
| **Canvas Stability** | MEDIUM (performance) | LOW (15 min implementation) | **P2** |
| **PDF Page Selection** | MEDIUM (feature parity) | MEDIUM (1hr implementation) | **P2** |
| **Per-Sheet Progress UI** | MEDIUM (UX polish) | MEDIUM (1–2hr implementation) | **P2** |
| **Project List Scroll Fix** | LOW (edge case for large accounts) | MEDIUM (30 min + testing) | **P2** |
| **UI/UX Overhaul (Dark Theme)** | MEDIUM (aesthetics) | HIGH (4–8hr implementation) | **P2** |
| **Waste Factor Profiles** | LOW (multi-client feature) | MEDIUM (2hr implementation) | **P3** |
| **Scheduled Runs** | LOW (nice-to-have automation) | MEDIUM (2–3hr implementation) | **P3** |
| **Confidence Review UI** | LOW (power user feature) | HIGH (full day implementation) | **P3** |
| **Diff Mode** | LOW (revision tracking) | HIGH (2–3 days implementation) | **P3** |
| **Excel Export** | LOW (formatting preference) | MEDIUM (2–4hr implementation) | **P3** |
| **Agentic Multi-Sheet Context** | HIGH (future differentiator) | VERY HIGH (weeks; research-grade) | **P3** |

**Priority key:**
- **P1**: Must have for production launch (Master.md Phase 1 critical path)
- **P2**: Should have when possible; enhances core experience (Master.md Phase 2–3)
- **P3**: Nice to have; future consideration after PMF (Master.md Phase 4+)

## Competitor Feature Analysis

| Feature | ConstructConnect OST | STACK | ProEst | Togal.AI | Kreo | **Bobby Tailor** |
|---------|---------------------|-------|--------|----------|------|------------------|
| **Digital Takeoff** | ✓ PDF/CAD/BIM | ✓ PDF/CAD | ✓ PDF/CAD | ✓ PDF only | ✓ PDF/BIM | ✓ PDF + StackCT browser |
| **AI Auto-Takeoff** | ✓ Takeoff Boost (Google Cloud Vertex AI) | ✓ GPT-powered autocount | ✗ Manual only | ✓ Floor plan AI | ✓ Agentic CV | ✓ Claude Vision (zero-shot) |
| **Schedule/Table Extraction** | Limited (symbols only) | Limited | Manual | ✗ Architectural only | ✓ Advanced | ✓ Panel schedules, door schedules |
| **Cost Database Integration** | ✓ RSMeans built-in | ✓ Custom assemblies | ✓ Extensive library | ✗ Export only | ✓ BIM-linked | ✗ CSV export to client systems |
| **Multi-User Collaboration** | ✓ Cloud teams | ✓ Premium tier | ✓ Full | ✗ Single user | ✓ Full | ✗ Single operator (out of scope) |
| **In-Browser Preview** | ✓ Full visual markup | ✓ Layered plans | ✓ Dashboard | ✓ Side-by-side | ✓ 3D BIM viewer | **✗ Gap #3 (planned)** |
| **Plan Selection** | ✓ Sheet picker | ✓ Layer/zone filters | ✓ WBS selector | ✓ Drawing filter | ✓ Advanced | **✗ Gap #2 (planned)** |
| **Formula Transparency** | Partial (assembly details) | Partial (inline calcs) | ✓ Full audit trail | ✗ Black box quantities | ✓ Full provenance | ✓ `formula_applied` column |
| **Settings/Config UI** | ✓ Admin panel | ✓ Preferences | ✓ Full | ✓ Profile manager | ✓ Advanced | **✗ Gap (planned)** |
| **Mobile Support** | ✓ iOS/Android apps | ✓ Responsive web | ✓ Limited | ✗ Desktop only | ✓ Limited | ✗ Desktop-first (anti-feature) |
| **Pricing (annual)** | $3K–$5K per seat | $2K–$3K per seat | $5K–$12K per seat | $3K–$4K per seat | $2.4K–$3.6K per seat | **~$0.50–$5/project (API costs only)** |

### Competitor Insights for Bobby Tailor

**What Bobby Does Better:**
1. **Cost**: ~$0.04–$0.05 per 30-page project vs $2K–$5K annual subscriptions = 40,000x–100,000x cost advantage for occasional use (1–10 projects/month)
2. **Schedule Extraction**: Claude Vision reads panel schedules, equipment tables, door schedules natively; competitors focus on geometric takeoff only
3. **Zero Training**: No symbol library setup, no per-project configuration; works zero-shot on any construction drawing
4. **Formula Transparency**: Every calculation shows exact formula and source; competitors hide formulas in "assemblies" or black boxes

**What Competitors Do Better (and why Bobby doesn't need to):**
1. **Multi-User Collaboration**: Bobby is single-operator automation, not team platform; out of scope per Master.md
2. **Built-In Cost Databases**: Bobby targets firms with existing cost systems; CSV export is the correct integration pattern
3. **BIM/Revit Integration**: Bobby targets PDF/StackCT workflows; BIM = different market segment (enterprise GCs, not specialty subs)
4. **Mobile Apps**: Takeoff requires desktop; Bobby correctly prioritizes desktop-first (mobile report viewing = future P3)

**Critical Gaps Bobby Must Close (P1):**
- Plan selection UI (Gap #2)
- In-browser report preview (Gap #3)
- Settings page (Gap #8.8)

## Sources

### Industry Reports & Analysis
- Bluebeam Construction Takeoffs Guide 2026: https://www.bluebeam.com/resources/construction-takeoffs-guide-2026/
- Bluebeam Construction Estimating Software Guide 2026: https://www.bluebeam.com/resources/construction-estimation-software-2026/
- ZACUA Ventures AI for Construction Report 2026: https://zacuaventures.com/ai-for-construction-industry-report-2026/
- ConstructConnect Takeoff Boost Technical Deep-Dive: https://scalinglegends.com/article/constructconnect-takeoff-boost-2026/

### Product Comparisons & Reviews
- BuildVision AI: 9 Best Construction Estimating Software 2026: https://www.buildvisionai.com/best-construction-estimating-software
- Gitnux: Top 10 Best Estimate Estimating Software 2026: https://gitnux.org/best/estimate-estimating-software/
- US Tech Automations: Construction Estimating Automation Comparison 2026: https://ustechautomations.com/resources/blog/construction-estimating-automation-comparison-2026
- Nomitech: Best Cost Estimating Software 2026: https://www.nomitech.com/cost-estimating/best-cost-estimating-software-2026
- ITQlick: ProEst Reviews 2026: https://www.itqlick.com/proest
- Bidi Contracting: STACK Construction Software Review 2026: https://www.bidicontracting.com/blog/stack-construction-software-review

### AI & Automation Trends
- ConstructConnect Takeoff Boost Announcement (Google Cloud Vertex AI): https://news.constructconnect.com/industry-special-constructconnect-announces-takeoff-boost
- Kreo Software: Agentic Computer Vision for Construction Drawings: https://www.kreo.net/news-2d-takeoff/agentic-computer-vision-for-construction-drawings
- Kreo Software: AI Agentic Workflow for Takeoff & Estimating: https://www.kreo.net/solutions/ai-agentic-workflow-for-takeoff-and-estimating
- Ediphi + Togal.AI Native Integration Announcement: https://www.ediphi.com/blog/ediphi-and-togal-ai-announce-native-integration

### Anti-Patterns & Common Mistakes
- Bluebeam: Construction Estimation Complete Guide 2026: https://www.bluebeam.com/resources/the-complete-guide-to-construction-estimation-in-2026/
- Buildern: Construction Estimating Mistakes: https://buildern.com/resources/blog/construction-estimating-mistakes/
- Advantive: Why Spreadsheets Break During Peak Construction Season: https://www.advantive.com/blog/why-spreadsheets-break-peak-construction-season/
- Ediphi: Why the Preconstruction Stack Feels "Good Enough" - Until It Doesn't: https://www.ediphi.com/blog/why-the-stack-feels-good-enough
- NeDES: Most Common Quantity Takeoff Mistakes: https://nedesestimating.com/most-common-quantity-takeoff-mistakes/

### Integration Patterns
- Ediphi Excel Add-in (Last Mile) Documentation: https://help.ediphi.com/article/281-using-ediphis-excel-add-in-last-mile
- Ediphi Excel Add-in Launch Announcement: https://www.ediphi.com/blog/now-available----ediphi-excel-add-in-live-data-feed-of-your-ediphi-estimate-in-excel

---

*Feature research for: Bobby Tailor — StackCT Estimation Automation*
*Researched: May 26, 2026*
*Confidence: HIGH (verified with Context7 and official vendor documentation where applicable)*
