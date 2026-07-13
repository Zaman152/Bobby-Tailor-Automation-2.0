# Phase 12 Context — Application Authentication

## User directive (2026-05-26)

Deploying the Flask app on a public VPS requires **full protection** of all routes and APIs — no anonymous access.

## Seeded admin (must work after implementation)

| Field | Value |
|-------|-------|
| Email | `admin@bobbytailor.com` |
| Password | `BobbyTheAdmin@1` |

Store password as **bcrypt hash only** at seed time. Never log or return the plaintext password.

## Security bar

Follow OWASP-aligned practices for a Flask monolith:

- Flask-Login (or equivalent) server-side sessions
- `SECRET_KEY` from environment (required in production)
- Session cookie flags: HttpOnly, Secure (when behind HTTPS), SameSite=Lax or Strict
- CSRF on browser POST/PUT (Flask-WTF or double-submit token for SPA fetch)
- Rate limiting on `/login` (e.g. Flask-Limiter)
- Generic login failure messages
- Protect **all** `@app.route` and `/api/*` — including static job polling, settings, file preview/download
- Document auth env vars in `.env.example` and README VPS section

## Out of scope (this phase)

- Multi-user RBAC, OAuth providers, password reset email flow
- Per-user job isolation (v2 / ARCH-02)

## Codebase facts

- `app.py` — single Flask app, no auth today (~15 routes)
- `templates/index.html`, `templates/settings.html` — UI shell
- `static/app.js` — fetch calls to `/api/*` need credentials + CSRF header
- `requirements.txt` — no Flask-Login/bcrypt yet
- Master.md Gap #9 — Flask-Login single admin or HTTP basic auth
