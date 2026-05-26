---
phase: 12
plan: "02"
subsystem: authentication
tags: [flask-login, flask-bcrypt, flask-wtf, flask-limiter, auth-guard, session, csrf, login-route]

dependency_graph:
  requires:
    - "12-01: Auth deps and admin seeding"
  provides:
    - auth.py module with AdminUser, extensions, init_admin, get_admin
    - app.py before_request guard (401 JSON for API, redirect for browser)
    - /login route with bcrypt verify and rate limiting
    - /logout POST-only route
    - templates/login.html with CSRF token and error display
  affects:
    - "12-03: Logout control in sidebar (index.html / settings.html)"

tech_stack:
  added: []
  patterns:
    - Singleton AdminUser populated once at startup from env vars
    - Timing-safe bcrypt dummy check to prevent user enumeration
    - Open-redirect guard using urlparse scheme/netloc validation
    - POST-only /logout to prevent CSRF via GET links or images
    - SESSION_COOKIE_SECURE=True unless FLASK_ENV=development

key_files:
  created:
    - auth.py
    - templates/login.html
  modified:
    - app.py

decisions:
  - id: D-12-02-A
    decision: "Timing-safe dummy bcrypt check on unknown email"
    rationale: "Prevents email enumeration via response-time difference; always runs bcrypt regardless of email match"
  - id: D-12-02-B
    decision: "logout endpoint in PUBLIC_ENDPOINTS so @login_required handles 401 itself"
    rationale: "before_request guard runs before @login_required; adding logout to PUBLIC_ENDPOINTS avoids double redirect and lets Flask-Login return its own 401"
  - id: D-12-02-C
    decision: "SESSION_COOKIE_SECURE conditional on FLASK_ENV != development"
    rationale: "Allows HTTP in local dev without disabling Secure flag in production"

metrics:
  duration: "~4 min"
  completed: "2026-05-26"
  tasks_completed: 3
  tasks_total: 3
  commits: 3
---

# Phase 12 Plan 02: Core Flask Authentication Summary

**One-liner:** Flask-Login session auth with bcrypt verify, timing-safe login route, CSRFProtect, and before_request API/browser guard.

## What Was Done

Implemented the full authentication layer for the Bobby Tailor Flask app: an `auth.py` module holding the `AdminUser` model and lazily-bound Flask extension instances, auth integration into `app.py` (security config, extension init, `before_request` guard, `/login`/`/logout` routes), and a `templates/login.html` matching the industrial dark theme with CSRF protection and error display.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Create auth.py module | 502a9ce | auth.py |
| 2 | Integrate auth into app.py | 67f656d | app.py |
| 3 | Create login.html template | a84f78a | templates/login.html |

## Verification Results

- [x] `python3 -c "from auth import AdminUser, login_manager, bcrypt, limiter, init_admin, get_admin; print('OK')"` → OK
- [x] App imports cleanly with env vars set; "Admin user initialised: admin@bobbytailor.com" logged
- [x] `curl localhost:5051/` → 302 redirect to /login
- [x] `curl localhost:5051/api/status/test` → 401 `{"error": "Authentication required"}`
- [x] GET /login → 200; response body contains `csrf_token`
- [x] POST /login wrong creds → 200 with "Invalid credentials" in response body
- [x] POST /login correct creds (admin@bobbytailor.com / BobbyTheAdmin@1) → 302 redirect to /

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| D-12-02-A | Timing-safe dummy bcrypt check on unknown email | Prevents user enumeration via response-time difference |
| D-12-02-B | logout in PUBLIC_ENDPOINTS, guarded by @login_required | Avoids double redirect; Flask-Login handles the 401 |
| D-12-02-C | SESSION_COOKIE_SECURE conditional on FLASK_ENV | Enables HTTP in dev without weakening production |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added SECRET_KEY to .env**

- **Found during:** Task 2 setup (app.py requires `os.environ["SECRET_KEY"]` — hard crash if missing)
- **Issue:** `.env` contained ADMIN_EMAIL and ADMIN_PASSWORD_HASH from 12-01 but SECRET_KEY was absent
- **Fix:** Generated a 64-char hex SECRET_KEY via `secrets.token_hex(32)` and appended to `.env`
- **Files modified:** .env (gitignored — not committed)

## Next Phase Readiness

Phase 12-03 (logout control in sidebar) can proceed immediately:
- `/logout` POST endpoint is live and CSRF-protected
- `login_required` decorator is importable from `flask_login`
- Session cookies are fully configured (HttpOnly, SameSite=Lax, Secure in prod)
