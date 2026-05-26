---
phase: 12-application-authentication
plan: "03"
subsystem: security
tags: [csrf, frontend, fetch, authentication, readme]

dependency-graph:
  requires: ["12-02"]
  provides: ["csrf-protection", "logout-form", "apiFetch-wrapper"]
  affects: ["all-frontend-api-calls"]

tech-stack:
  added: []
  patterns: ["CSRF meta tag pattern", "apiFetch wrapper", "credentials: same-origin"]

key-files:
  created: []
  modified:
    - templates/index.html
    - templates/settings.html
    - static/app.js
    - static/settings.js
    - README.md

decisions:
  - "apiFetch wrapper in app.js handles X-CSRFToken automatically for POST/PUT/PATCH/DELETE"
  - "settings.js uses inline getCsrfToken() + direct fetch (no shared module) to keep settings page self-contained"
  - "logout form added to sidebar in index.html and page-header area in settings.html (no sidebar)"

metrics:
  duration: "~4 min"
  completed: "2026-05-26"
---

# Phase 12 Plan 03: Frontend CSRF Protection + Logout Form + README Auth Section Summary

**One-liner:** CSRF meta tags + apiFetch wrapper on all state-changing JS calls + POST logout form with CSRF + README auth docs.

## Objective

Add CSRF protection to all frontend JavaScript fetch calls so every POST/PUT/DELETE request carries the `X-CSRFToken` header validated by Flask-WTF server-side.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add CSRF meta tags to templates | 58e5649 | templates/index.html, templates/settings.html |
| 2 | Add apiFetch helper and update app.js | f0ebdf6 | static/app.js |
| 3 | Update settings.js with CSRF header | 8b91003 | static/settings.js |
| 4 | Logout form in sidebar + README auth section | 1a9b8a2 | templates/index.html, templates/settings.html, README.md |

## What Was Built

### Task 1 — CSRF Meta Tags
- Added `<meta name="csrf-token" content="{{ csrf_token() }}">` to both `index.html` and `settings.html` heads, after the viewport meta tag
- Makes the Flask-WTF CSRF token available to JavaScript via `document.querySelector('meta[name="csrf-token"]').content`

### Task 2 — apiFetch Wrapper (app.js)
- Added `getCsrfToken()` — reads from meta tag, returns empty string if not found
- Added `apiFetch(url, options)` — automatically injects `X-CSRFToken` header on POST/PUT/PATCH/DELETE and always sets `credentials: 'same-origin'`
- Replaced all 6 POST `fetch()` calls with `apiFetch()`:
  - `/api/projects/:id/sync-plans` (POST)
  - `/api/run/stackct` (POST × 2 — "all projects" and "specific project" paths)
  - `/api/pdf/upload` (POST FormData — apiFetch correctly passes through without interfering with multipart boundary)
  - `/api/pdf/run` (POST)
  - `/api/cancel/:id` (POST)
- Added `credentials: 'same-origin'` to all GET fetch calls (projects, sheet-counts, status, reports, report previews, jobs/active, plans)

### Task 3 — settings.js CSRF
- Added `getCsrfToken()` at top of `settings.js` (self-contained page, no shared module)
- Added `X-CSRFToken: getCsrfToken()` header and `credentials: 'same-origin'` to the settings `PUT /api/settings` call
- Added `credentials: 'same-origin'` to the settings `GET /api/settings` call

### Task 4 — Logout Form + README
- `index.html` sidebar: POST logout form after Settings nav item, reusing `.nav-item` button style with logout SVG icon
- `settings.html` page header: POST logout form inline with the "← Back to App" link
- Both forms include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>` for Flask-WTF form field validation
- README: Added "Application Authentication" section covering SECRET_KEY generation, `seed_admin.py`, `FLASK_ENV=development`, Redis rate limiting for multi-worker gunicorn, and security checklist

## Verification Criteria

- [x] `index.html` has `<meta name="csrf-token">` in head
- [x] `settings.html` has `<meta name="csrf-token">` in head
- [x] `app.js` has `getCsrfToken()` and `apiFetch()` functions
- [x] All POST calls in `app.js` use `apiFetch` (0 remaining raw POST fetch calls)
- [x] `settings.js` PUT call includes `X-CSRFToken` header
- [x] Logout form present in both templates as POST with CSRF token
- [x] README documents SECRET_KEY, seed_admin.py, FLASK_ENV, rate limiting, security checklist

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `apiFetch` wrapper instead of patching each call individually | Single point of maintenance; all future fetch calls can use apiFetch without remembering CSRF |
| `settings.js` keeps its own `getCsrfToken()` copy | settings.html is a separate page; avoids dependency on app.js which is only loaded on index.html |
| Logout icon SVG inline in sidebar form button | Matches existing nav item pattern; no additional CSS class needed |
| Logout form in page-header for settings.html | settings.html has no sidebar; page-header is the natural navigation zone |

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

Phase 12 plan 03 is complete. All frontend-to-backend API calls are now CSRF-protected. The authentication system (plans 01–03) is fully implemented:
- 12-01: Auth dependencies + admin seeding
- 12-02: Flask session auth + login route + login.html
- 12-03: CSRF protection + logout form

Phase 12 complete. Phase 13 (final/remaining) can proceed.
