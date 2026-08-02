# Documentation Audit — Bobby Tailor Automation 2.0

**Date:** 2026-08-02 · **Method:** read-only spot-checks of every claim against current code (file/line citations throughout). No files modified other than this document.

## TL;DR

The two operational docs (README.md, docs/DEPLOYMENT.md) are LIVE and ~90% accurate, but the README contains four concretely wrong claims today: a nonexistent API route (`GET /api/jobs/<job_id>`), two wrong env-var defaults (`CLAUDE_MODEL_SCHEDULES`, `CLAUDE_MODEL_CLASSIFY`), a Python-version claim (3.10+) that contradicts the actual 3.9 runtime pinned in pyproject.toml, plus a stale pre-Phase-21 cost claim (~$0.05/run). docs/PIPELINE-GROUND-TRUTH.md is the live, protected accuracy R&D log (14 sections, last commit 2026-07-17). Master.md is **fully subsumed** by Masterv2.md (first 1,660 lines byte-identical; Master.md ends at line 1,663) — both are legacy planning documents from May 2026 that describe a pre-`src/` architecture and belong in an archive folder. AGENTS.md and CLAUDE.md are byte-identical copies (both 2,698 B, same commit `cb5dbbe`). `.env.example` is missing **9 environment variables the code actually reads** (notably `TAKEOFF_ACCURACY_MODE`, `COUNT_TILING`, and the four `RunSettings` toggles) but contains zero stale/unread variables.

---

## (a) Per-document verdicts

| Document | Size | Last commit | Verdict | Evidence summary |
|---|---|---|---|---|
| `README.md` | 24,518 B | 2026-07-15 `d9949d5` | **LIVE** (needs 4 corrections + a split) | Primary onboarding doc; 12 of 16 spot-checked claims verified true against code (below); 4 wrong today |
| `docs/DEPLOYMENT.md` | 8,464 B | 2026-07-15 `d9949d5` | **LIVE** (2 small corrections) | Operational contract; env tables mostly match `src/bobbytailor/config.py`; two inaccuracies noted below |
| `docs/PIPELINE-GROUND-TRUTH.md` | 32,754 B | 2026-07-17 `3f54cec` | **LIVE — PROTECTED** | Actively appended accuracy R&D log; §14 added in the latest doc commit (`3f54cec` "docs: the room-measurement engine… (§14)"). Section list below |
| `Master.md` | 67,684 B | 2026-05-26 `09fdde6` | **ARCHIVE** | Fully contained in Masterv2.md: `diff` of the first 1,660 lines of both files is empty; Master.md is 1,663 lines total and contains no "ADDENDUM" heading. Zero unique content |
| `Masterv2.md` | 110,497 B | 2026-07-13 `a715681` | **ARCHIVE** (keep as historical reference) | v2.0 planning doc + Addendum v2.1 (lines 1667–2643). Describes pre-Phase-21 architecture: §10 "File & Folder Structure (Target State)" predates the `src/bobbytailor` package layout; its actionable delta was already extracted into `.planning/MASTERv2-GAP-ANALYSIS.md`. Still cited by planning docs — archive, do not delete |
| `AGENTS.md` | 2,698 B | 2026-07-15 `cb5dbbe` | **LIVE (duplicate)** | `diff AGENTS.md CLAUDE.md` → identical; same size, same mtime, same commit. Content = GitNexus agent instructions. Intentional multi-agent convention (Cursor/Codex read AGENTS.md, Claude Code reads CLAUDE.md), but the duplication has no sync mechanism — they *will* drift |
| `CLAUDE.md` | 2,698 B | 2026-07-15 `cb5dbbe` | **LIVE** | Read by Claude Code every session; identical twin of AGENTS.md |
| `.planning/CURSOR-POWERUP.md` | 1,249 B | — | **STALE** | Setup log dated 2026-05-26 plus 12 append-only "Last re-index" timestamp lines, latest 2026-06-04 (lines 23–46). No current operational value; inside protected `.planning/` so archive in place, don't delete |
| `.planning/MASTERv2-GAP-ANALYSIS.md` | 5,476 B | — | **STALE (historical)** | Dated 2026-05-26; maps Masterv2 gaps → "Phase 16 (new)". The roadmap is now deep in Phase 21 (per `pyproject.toml` comments, `config.py` "Phase 21 model routing", `.planning/ROADMAP.md`). Its job is done — historical record only |
| `.planning/milestone-UAT.md` | 1,905 B | — | **STALE (historical)** | UAT snapshot for Phases 1–11, dated 2026-05-26, tests a UI (inline accordion preview) that Phase 15 has since replaced with the Reports workspace (`static/js/reports-workspace.js`) |
| `design-system/bobby-tailor/` (MASTER.md + pages/reports.md + pages/projects.md) | 3 files | 2026-05-26 `26e2150` | **LIVE (reference)** | Dark-industrial token spec (`--accent-construction: #f97316`, `--bg-base: #0b0d11`) is genuinely in force: `static/ui-polish.css` uses `var(--accent-construction)` at lines 248, 564, 1109, 1272, 1283, 1315 and `#0b0d11` at line 249. Unchanged since May but still the UI contract |
| `.env.example` | 7,252 B | 2026-07-15 `174266a` | **LIVE (drifted)** | 31 variable entries, all read by code (no stale vars), but 9 code-read vars are missing — full list in §(d) |

### docs/PIPELINE-GROUND-TRUTH.md section list (protected — for orientation only)

1. Real accuracy achieved (Crow Cass, plans-only, manifest-free) · 2. What the system is · 3. Complete PDF-upload workflow · 4. How vision + geometry fusion works · 5. Where the gaps are (honest) · 6. Where human intervention is still needed · 7. Best solution / revised architecture · 8. Generalization test (2026-07-15) — DECISIVE: does NOT yet generalize · 9. Opus reader fix + measurement-engine frontier · 10. "136 Columns" was COINCIDENTAL · 11. Scale R&D (2026-07-16) — two systemic scale bugs · 12. MOXY run (2026-07-17) — honest 4% (1/24) · 13. Moxy document study — why 100% is blocked · 14. Room-measurement engine — Gyp Ceiling 0 → 7.0% · 12b. Why manifest + scale did not produce 100%

(Note: section "12b" is numbered out of order after §14 — cosmetic only.)

---

## README spot-checks that PASSED (claims verified against code)

1. **Package layout** — all 8 claimed subpackages exist: `src/bobbytailor/{config.py,pipeline,deterministic,vision,learning,scrape,stores,devtools,web}` (`ls` verified); blueprints `auth, projects, runs, reports, verify, settings, jobs` all present in `src/bobbytailor/web/blueprints/`.
2. **`app.py` "5-line wrapper" / `app:app`** — `app.py` is exactly 5 lines: `from bobbytailor.web.app import create_app; app = create_app()`, dev server on port 5050. "Only Python files at repo root are the two entry points" — confirmed (`app.py`, `main.py` only).
3. **CLI flags** — `main.py` accepts `--project-id`, `--project-name`, `--schedule` (main.py:35–37).
4. **Scripts** — `scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`, `scripts/setup_golden_fixtures.sh`, `scripts/golden_convergence.py` all exist; gate header confirms "Crow Cass + Bob's Discount gate hard; Chelsea + Moxy tracked" and the $5–15 cost estimate (accuracy_gate.sh:8–16, 27–30).
5. **Chromium flags** — `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-blink-features=AutomationControlled` present in `src/bobbytailor/scrape/browser.py:110–112`.
6. **REUSE_SCREENSHOTS mechanics** — the ">1 000 bytes → `shutil.copy2`" claim is literal code: `scraper.py:454–456` and `716–718` (`stat().st_size > 1000` then `shutil.copy2`).
7. **Output filenames** — `takeoff.json`, `raw_items.csv`, `calculations.csv`, `summary.txt` written per run in `src/bobbytailor/pipeline/reporter.py:183–187`.
8. **`POST /api/run/stackct`** exists (`runs.py:41`) with `analyze_only` + `manifest_dir` support (`jobs_runtime.py:164–180, 204, 268–276`) and returns `{"job_id": ...}` (`runs.py:120`).
9. **Tests/fixtures** — `tests/test_takeoff_generalization.py`, `tests/test_golden_takeoff.py`, and `tests/fixtures/{crow_cass,bobs_discount,chelsea,moxy,generalization,synthetic,replay}` all exist.
10. **LEARNING_DB_PATH default** — `{OUTPUT_DIR}/learning.db` with env override, exactly as documented (`src/bobbytailor/learning/store.py:94–97`).
11. **Admin seeding** — `python -m bobbytailor.web.seed_admin` with `ADMIN_SEED_PASSWORD` / `ADMIN_SEED_EMAIL` / `--generate` (seed_admin.py:51–53).
12. **ESTIMATION_TABLES** — lives at `src/bobbytailor/pipeline/calculator.py:19` with the keys shown in the README sample (`flooring` waste 1.10, `drywall` sheet 32 sf / waste 1.12, `paint` 350 sf/gal 2 coats — verified verbatim at calculator.py:19–40).

## (b) README claims that are WRONG today

| # | README claim (line) | Reality | Severity |
|---|---|---|---|
| 1 | "**Job object (`GET /api/jobs/<job_id>`)**: `mode_detail` …" (README:532) | **No such route.** Registered job routes are `/api/jobs/active` (jobs.py:67), `/api/jobs/history` (jobs.py:87), `/api/jobs/history/<job_id>` (jobs.py:106). The frontend polls `active` and `history/<job_id>` (static/app.js:1228, 2142) | HIGH — API reference documents a 404 |
| 2 | Env table: `CLAUDE_MODEL_SCHEDULES` default = `claude-sonnet-4-6` (README:142) | Default is **fallback to `CLAUDE_MODEL`** (config.py:25: `os.getenv("CLAUDE_MODEL_SCHEDULES", CLAUDE_MODEL)`). docs/DEPLOYMENT.md:57 has this one right | MEDIUM — operator would assume Sonnet runs on schedules by default; actually Haiku does |
| 3 | Env table: `CLAUDE_MODEL_CLASSIFY` default = `CLAUDE_MODEL` (README:156) | Default is **hardcoded `"claude-haiku-4-5"`** (config.py:40) — it does NOT follow `CLAUDE_MODEL` if the operator changes it. **docs/DEPLOYMENT.md:60 repeats the same error** | LOW-MEDIUM (same wrong claim in two docs) |
| 4 | "System requirements … Python 3.10+" (README:109) | `pyproject.toml:11` pins `requires-python = ">=3.9"` with an explicit note (lines 9–10): "the deployment/test runtime is Python 3.9 (macOS system python)". Memory/Phase-21 notes confirm 3.9 is the actual runtime | MEDIUM — contradicts the pinned support floor |
| 5 | "With Haiku (default) + prompt caching, a 30-page project runs ~$0.05" (README:681) | Pre-Phase-21 claim. Current default routing sends semantic passes to `claude-sonnet-5` and dense passes to `claude-opus-4-8` (config.py:34–36), and the README's own accuracy-gate section (README:92) says a full run costs low single-digit USD. Unverifiable as written; almost certainly stale | LOW — but sets wrong cost expectations |
| 6 | (docs/DEPLOYMENT.md:30–31, related) "`bobbytailor/config.py` is the single reader" of env | Seven other modules read env directly: `web/app.py:44–64` (`SECRET_KEY`, `FLASK_ENV`, `ADMIN_*`), `web/auth.py:33` (`RATE_LIMIT_STORAGE_URI`), `web/settings.py:65`, `web/seed_admin.py:51–53`, `learning/store.py:94`, `pipeline/takeoff_pipeline.py:157–196`, `pipeline/accuracy_config.py:13–35` | LOW — architectural claim, not operationally dangerous |

Also worth noting (not "wrong", but confusing): the README duplicates the entire VPS deployment guide that docs/DEPLOYMENT.md declares itself the owner of — two env tables to keep in sync is exactly how errors #2/#3 diverged between the files.

## (c) Proposed professional docs/ structure

Two audiences: a **new engineer** (needs architecture, contracts, test strategy) and an **operator** (needs install, run, recover, back up). Proposal (all moves, no deletions; legacy files go to an archive dir, not the trash):

```
README.md                     ← SLIM: what it is, 10-line quickstart, links. Move VPS/auth/API
                                content out; kill the duplicated env table (link DEPLOYMENT.md)
docs/
├── DEPLOYMENT.md             ← keep as THE operator doc (already the best-written doc in the repo);
│                               fix #3/#6 above; absorb README's VPS/nginx/systemd/auth sections
├── PIPELINE-GROUND-TRUTH.md  ← protected, unchanged (accuracy R&D log)
├── ARCHITECTURE.md           ← NEW (engineer): package map, pipeline stages, fusion/provenance
│                               rules, entry-point parity — much of this exists in README's
│                               "How it works" + "Package layout"; lift it out
├── API.md                    ← NEW: the real route list (runs, jobs, reports, verify, projects,
│                               settings blueprints) — corrected /api/jobs/* paths
├── CONFIGURATION.md          ← NEW: one authoritative env-var table generated against config.py +
│                               the 7 out-of-config readers; supersedes the two drifting tables
├── TESTING.md                ← NEW (engineer): offline suite vs golden vs accuracy gate; which
│                               ones cost money (accuracy_gate.sh $5–15) and must never run in CI
│                               without credentials/intent
└── archive/
    ├── Masterv2.md           ← moved from root (historical planning source-of-truth)
    ├── Master.md             ← moved from root, or deleted outright (0 unique lines vs Masterv2)
    └── (optionally) .planning historical docs stay where they are — .planning/ is protected
design-system/                ← keep at root or move to docs/design/; still the live UI token spec
AGENTS.md / CLAUDE.md         ← keep both names (different tools read each) but make one canonical;
                                on next edit, regenerate the other or use a symlink if tooling allows
```

Rationale highlights:
- **One env table, one owner.** Errors #2 and #3 exist because README and DEPLOYMENT each maintain their own table. CONFIGURATION.md (or DEPLOYMENT.md alone) should be the only table; README links to it.
- **README as front door only.** At 24.5 KB covering setup→deployment→auth→API→ops→testing→cost, it is doing the work of five docs and drifts in five places.
- **Operator recovery paths** (analyze_only, partial reports, budget exhaustion, learning-DB backup) are already excellent in DEPLOYMENT.md §"Error recovery" — keep them there, delete the README duplicates.

## (d) .env.example drift list

Method: extracted the 31 variable names from `.env.example` (values not inspected) and diffed against every `os.getenv`/`os.environ` read in `src/bobbytailor/` (grep across the package; readers are config.py plus the 7 modules listed in (b)#6).

**Missing from .env.example (code reads them; operator cannot discover them from the template):**

| Variable | Read at | Default | Notes |
|---|---|---|---|
| `TAKEOFF_ACCURACY_MODE` | `pipeline/accuracy_config.py:13` | `high` | Documented in README:666 and DEPLOYMENT.md:48 — but absent from the template |
| `COUNT_TILING` | `pipeline/accuracy_config.py:30` | off | In DEPLOYMENT.md:49 table; absent from template |
| `COUNT_TILING_GRID` | `pipeline/accuracy_config.py:35` | `2x2` | Same |
| `DETERMINISTIC_ENABLED` | `pipeline/takeoff_pipeline.py:191` | `true` | RunSettings toggle — in no doc and no template |
| `LEARNING_ENABLED` | `pipeline/takeoff_pipeline.py:193` | `true` | Same |
| `VERIFY_RETRY_ENABLED` | `pipeline/takeoff_pipeline.py:195` | `true` | Same |
| `RASTER_FORCE` | `pipeline/takeoff_pipeline.py:196` | `false` | Same |
| `MAX_PREVIEW_ROWS` | `config.py:84` | `500` | In BOTH README:147 and DEPLOYMENT.md:80 env tables, yet missing from the template |
| `ADMIN_SEED_EMAIL` / `ADMIN_SEED_PASSWORD` | `web/seed_admin.py:51–53` | — | Transient one-shot seeding vars; omitting is defensible but deserves a comment in the template pointing at seed_admin |

**Stale variables in .env.example: none.** All 31 present entries were traced to a live read: config.py covers 27 of them; `FLASK_ENV` → `web/app.py:46`; `RATE_LIMIT_STORAGE_URI` → `config.py:114` + `web/auth.py:33`; `LEARNING_DB_PATH` → `learning/store.py:94`; `MAX_LINKED_DEPTH` → `config.py:105`.

**Cosmetic:** config.py:21's price-comment references `claude-opus-4-7` while the dense-pass default is `claude-opus-4-8` (config.py:36) — comment drift only.

---

## Cleanup recommendations (no protected paths; all reversible)

| Action | Path | Justification |
|---|---|---|
| DELETE (or ARCHIVE if sentimental) | `Master.md` | 0 unique lines vs Masterv2.md (diff-verified); 67 KB of root-level noise |
| ARCHIVE → `docs/archive/` | `Masterv2.md` | Historical planning source; still referenced by `.planning/MASTERv2-GAP-ANALYSIS.md`, so keep the file, move the location |
| ARCHIVE in place (`.planning/` is protected — no move proposed) | `.planning/CURSOR-POWERUP.md`, `.planning/MASTERv2-GAP-ANALYSIS.md`, `.planning/milestone-UAT.md` | All three are completed-milestone historical records (May–June 2026) |
| UNSURE — investigate before touching | `MagicMock/` at repo root | A directory named `MagicMock` (mtime Jul 15) is almost certainly test-mock leakage into the working tree, but it was out of this audit's scope — verify no test writes/reads it deliberately before deleting |
| FIX (edit, not delete) | `README.md` #1–#5, `docs/DEPLOYMENT.md` #3/#6, `.env.example` 9 missing vars | Per tables above |
