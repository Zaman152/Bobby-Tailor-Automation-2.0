# Phase 12: Application Authentication — Research

**Researched:** 2026-05-26  
**Domain:** Flask session authentication, CSRF protection, password hashing, rate limiting  
**Confidence:** HIGH (standard stack verified against official docs and Flask 3 compatibility confirmed)

---

## Summary

Phase 12 adds full authentication to the Bobby Tailor Flask monolith running on a public VPS. Every route and `/api/*` endpoint must reject unauthenticated requests before any business logic executes. The app has a single operator — the admin — so no multi-user database is needed.

The standard Flask authentication stack (Flask-Login + Flask-Bcrypt + Flask-WTF CSRF + Flask-Limiter) is mature, well-documented, and confirmed compatible with Flask 3. Flask-Login 0.6.3+ explicitly added Flask 3 and Werkzeug 3 compatibility (CHANGES.md, released 2023-10-30).

For this single-admin monolith, the correct user store is **in-memory (no SQLite)**. The bcrypt password hash is generated once by a `seed_admin.py` script and written to `.env` as `ADMIN_PASSWORD_HASH`. At startup, a singleton `User` object is constructed from env vars. This avoids database migrations, SQLAlchemy setup, and DB file management for a single user that never changes.

Global protection via `@app.before_request` is safer than per-route `@login_required` decorators: new routes are protected by default, and nothing can slip through an omitted decorator.

**Primary recommendation:** Use `@app.before_request` guard + Flask-Login + in-memory admin from env hash + Flask-WTF CSRF (meta tag + X-CSRFToken header pattern) + Flask-Limiter (memory storage) on `/login`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `flask-login` | `>=0.6.3` | Session management, `@login_required`, `current_user` | Official Flask auth library; Flask 3 compatible since 0.6.3 |
| `flask-bcrypt` | `>=1.0.1` | bcrypt password hashing / verification | Wraps `bcrypt` with Flask config integration; `generate_password_hash` / `check_password_hash` |
| `flask-wtf` | `>=1.2.0` | CSRF protection for forms and AJAX/fetch calls | Official Pallets ecosystem; `CSRFProtect` extension protects all state-changing requests |
| `flask-limiter` | `>=3.5.0` | Rate limiting on `/login` endpoint | Decorator-based, supports in-memory storage for single-process VPS |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | already in requirements | Load `.env` including `SECRET_KEY` and `ADMIN_PASSWORD_HASH` | Already used; no change needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flask-Bcrypt | `werkzeug.security.generate_password_hash` (pbkdf2) | Werkzeug's built-in uses PBKDF2 by default; bcrypt is considered more standard for password storage; CONTEXT.md explicitly requires bcrypt |
| Flask-WTF CSRF | `flask-sec-fetch-csrf` | Sec-Fetch-Site header approach requires no JS changes but is newer and less battle-tested; Flask-WTF is the Pallets-ecosystem standard |
| In-memory User | SQLite + SQLAlchemy | SQLite adds migrations, seeding, DB file management for a single user; in-memory is correct for this use case |
| `storage_uri="memory://"` Flask-Limiter | Redis | Redis requires external service; memory is acceptable for single-process VPS; resets on restart (acceptable for login rate limiting) |

### Installation

```bash
pip install "flask-login>=0.6.3" "flask-bcrypt>=1.0.1" "flask-wtf>=1.2.0" "flask-limiter>=3.5.0"
```

Add to `requirements.txt`:
```
flask-login>=0.6.3
flask-bcrypt>=1.0.1
flask-wtf>=1.2.0
flask-limiter>=3.5.0
```

---

## Architecture Patterns

### Recommended Project Structure

The monolith style of `app.py` should be preserved. Add:

```
app.py                  # existing — add auth init, before_request guard, login/logout routes
auth.py                 # NEW — User class, LoginManager, bcrypt, limiter init
seed_admin.py           # NEW — one-time script: bcrypt hash password, write ADMIN_PASSWORD_HASH to .env
templates/login.html    # NEW — login form with CSRF token hidden field
.env                    # add SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH
.env.example            # add SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH docs
```

Do NOT create a separate Blueprint. The monolith has no blueprints and adding one just for auth introduces unnecessary complexity.

---

### Pattern 1: In-Memory Admin User (No Database)

**What:** Single `User` class with `UserMixin`. One singleton instance loaded from env at startup. `user_loader` returns the singleton or `None`.

**When to use:** Single admin, no user management, no RBAC, password set once via seed script.

```python
# auth.py
# Source: https://flask-login.readthedocs.io/en/latest/

from flask_login import UserMixin

class AdminUser(UserMixin):
    """Singleton admin user loaded from environment at startup."""

    def __init__(self, user_id: str, email: str, password_hash: str) -> None:
        self.id = user_id
        self.email = email
        self.password_hash = password_hash

# Constructed once at module load time, used by user_loader
_admin_user: AdminUser | None = None

def get_admin_user() -> AdminUser | None:
    return _admin_user

def init_admin_from_env(email: str, password_hash: str) -> None:
    global _admin_user
    _admin_user = AdminUser(user_id="1", email=email, password_hash=password_hash)
```

**Key insight:** `user_loader` receives the id stored in the session cookie. Since there is only one user with `id="1"`, the loader just checks the id and returns the singleton.

```python
# In app.py during init
@login_manager.user_loader
def load_user(user_id: str) -> AdminUser | None:
    from auth import get_admin_user
    admin = get_admin_user()
    if admin and admin.id == user_id:
        return admin
    return None
```

---

### Pattern 2: Global `before_request` Auth Guard

**What:** One `@app.before_request` function enforces auth for ALL routes. Explicit allow-list for public endpoints. New routes are protected by default.

**When to use:** "All routes require auth" requirement. Safer than per-route decorators.

```python
# In app.py
# Source: Flask-Login docs + OWASP Flask auth patterns

from flask import request, redirect, url_for, jsonify
from flask_login import current_user

PUBLIC_ENDPOINTS = {"login", "static"}

@app.before_request
def require_login() -> None:
    """Enforce authentication for all routes except login and static files."""
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login", next=request.path))
```

**Critical detail:** `request.endpoint` is `None` for 404s and before Flask routing resolves. Guard against `None`:
```python
if not request.endpoint or request.endpoint in PUBLIC_ENDPOINTS:
    return None
```

---

### Pattern 3: Flask-Login Initialization

**What:** Initialize `LoginManager`, set redirect target, configure unauthorized JSON handler for API requests.

```python
# In app.py
# Source: https://flask-login.readthedocs.io/en/latest/

from flask_login import LoginManager

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"   # redirect unauthenticated browser requests here
login_manager.session_protection = "strong"   # regenerate session id on browser change
```

**Important:** The `before_request` guard makes `login_manager.login_view` mostly redundant (it handles redirects manually), but setting it is still correct practice for Flask-Login internals.

---

### Pattern 4: Login Route

**What:** GET renders login form; POST validates credentials with bcrypt and rate limiting.

```python
# In app.py
# Source: Flask-Login docs + Flask-Limiter docs

from flask_bcrypt import Bcrypt
from flask_login import login_user, logout_user, login_required

bcrypt = Bcrypt(app)

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        admin = get_admin_user()
        
        # Always run bcrypt.check_password_hash to prevent timing attacks,
        # even when email doesn't match (constant-time comparison)
        valid = (
            admin is not None
            and email == admin.email.lower()
            and bcrypt.check_password_hash(admin.password_hash, password)
        )
        
        if valid:
            login_user(admin, remember=False)
            next_page = request.args.get("next", "")
            # Validate next URL to prevent open redirect
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            return redirect(url_for("index"))
        
        # Generic error — no user enumeration
        error = "Invalid credentials"
    
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))
```

---

### Pattern 5: Session Cookie Security Configuration

**What:** Flask config keys for session cookie security flags.

```python
# In app.py (after app = Flask(__name__))
# Source: https://flask.palletsprojects.com/en/stable/web-security/#set-cookie-options

import os

app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],         # Must be set; crash-fail if missing
    SESSION_COOKIE_HTTPONLY=True,                # JS cannot access session cookie
    SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") != "development",  # HTTPS only in prod
    SESSION_COOKIE_SAMESITE="Lax",              # Protects against CSRF from other domains
    PERMANENT_SESSION_LIFETIME=43200,            # 12 hours (seconds)
    WTF_CSRF_TIME_LIMIT=3600,                   # CSRF token valid for 1 hour
)
```

**Note on `SESSION_COOKIE_SECURE`:** Setting `True` in development (HTTP) causes session cookies to not be sent, breaking the dev experience. Use env-based toggle: `True` always in production (VPS runs behind HTTPS), `False` locally.

---

### Pattern 6: CSRF Protection for Fetch-Based SPA

**What:** Flask serves both templates. Flask-WTF generates a CSRF token accessible via `{{ csrf_token() }}` in Jinja2. JS reads from `<meta>` tag and adds `X-CSRFToken` header to all state-changing fetch calls.

**Step 1:** Register `CSRFProtect` in `app.py`:
```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
```

**Step 2:** Add meta tag to BOTH templates (`index.html` and `settings.html` — both have full page loads):
```html
<!-- Source: https://flask-wtf.readthedocs.io/en/latest/csrf/#javascript-requests -->
<meta name="csrf-token" content="{{ csrf_token() }}">
```

**Step 3:** Add a JS helper in `app.js` / `settings.js`:
```javascript
// Source: Flask-WTF official docs
function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content ?? '';
}

// Wrap all state-changing fetch calls
function apiFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const needsCsrf = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
  return fetch(url, {
    ...options,
    credentials: 'same-origin',
    headers: {
      ...(options.headers || {}),
      ...(needsCsrf ? { 'X-CSRFToken': getCsrfToken() } : {}),
    },
  });
}
```

**Step 4:** Replace all state-changing `fetch()` calls in `app.js` and `settings.js` with `apiFetch()`.

**Codebase-specific fetch calls needing CSRF headers (POST/PUT):**
- `app.js:203` — `/api/run/stackct` POST
- `app.js:246` — `/api/pdf/upload` POST (FormData)
- `app.js:323` — `/api/pdf/run` POST
- `app.js:532` — `/api/cancel/:id` POST
- `app.js:1105` — `/api/run/stackct` POST (second call)
- `settings.js:115` — `/api/settings` PUT

GET calls (`app.js:85, 114, 413, 554, 683, 698, 710, 847, 954`) do NOT need CSRF headers.

**Login route CSRF:** The login form is a plain HTML form. Include the CSRF token as a hidden input:
```html
<form method="POST">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  ...
</form>
```

---

### Pattern 7: Seed Admin Script

**What:** One-time script (run by operator on VPS setup) that bcrypt-hashes the admin password and writes `ADMIN_PASSWORD_HASH` to `.env`.

```python
# seed_admin.py
# Run once: python seed_admin.py
# Source: Flask-Bcrypt docs

import os
import sys
from pathlib import Path
from flask_bcrypt import Bcrypt
from dotenv import set_key

ADMIN_EMAIL = "admin@bobbytailor.com"
ADMIN_PASSWORD = "BobbyTheAdmin@1"
ENV_PATH = Path(__file__).resolve().parent / ".env"

bcrypt = Bcrypt()
password_hash = bcrypt.generate_password_hash(ADMIN_PASSWORD).decode("utf-8")

if not ENV_PATH.exists():
    ENV_PATH.touch()

set_key(str(ENV_PATH), "ADMIN_EMAIL", ADMIN_EMAIL)
set_key(str(ENV_PATH), "ADMIN_PASSWORD_HASH", password_hash)

print(f"Admin seeded: {ADMIN_EMAIL}")
print("ADMIN_PASSWORD_HASH written to .env — do NOT share this file")
# Never print the plaintext password
```

**WARNING:** `seed_admin.py` must NEVER log or print the plaintext password. The `ADMIN_PASSWORD` constant in the script can be changed before running but should be deleted/gitignored after production seeding.

---

### Pattern 8: Flask-Limiter Initialization

```python
# In app.py
# Source: https://github.com/alisaifee/flask-limiter

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],           # No global limit — only protect /login
    storage_uri="memory://",     # In-memory: fine for single-process VPS
)
```

Apply to login route:
```python
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def login():
    ...
```

**Note:** `storage_uri="memory://"` resets on server restart. This is acceptable for login rate limiting on a low-traffic VPS; limits on restarts are not a meaningful bypass since restart frequency is low. If Redis is available, use `storage_uri="redis://localhost:6379"` for persistence.

---

### Anti-Patterns to Avoid

- **Per-route `@login_required`:** Easy to miss a new route. Use `@app.before_request` guard instead.
- **Storing password in DB as plaintext:** Use bcrypt hash only, stored in `.env` or env var.
- **`SESSION_COOKIE_SECURE=True` in dev (HTTP):** Breaks login locally. Toggle by environment.
- **Revealing user existence in login errors:** Always use "Invalid credentials" — never "Email not found" or "Wrong password."
- **Redirecting to arbitrary `next` URL:** Validate `next` starts with `/` and not `//` to prevent open redirect.
- **Putting `SECRET_KEY` in code:** Must come from `os.environ["SECRET_KEY"]` — use `[]` not `.get()` so it crashes clearly if missing.
- **Using `flask-login`'s default `unauthorized` redirect for API routes:** It redirects to HTML login page for `/api/*` — which is useless for JS fetch calls. The `before_request` guard with `return jsonify(...), 401` solves this correctly.
- **Running `config.py`'s `validate_required_env()` before SECRET_KEY is set:** The current `config.py` validates on import. This must continue to work; add `SECRET_KEY` as a required env var there, OR just use `os.environ["SECRET_KEY"]` directly in app.py which crashes clearly if missing.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom SHA256/MD5 | `flask-bcrypt` | Bcrypt is specifically designed to be slow (work factor); SHA/MD5 are trivially crackable with rainbow tables |
| Session management | Custom session tokens in DB | `flask-login` | Handles session fixation, fresh login detection, remember-me, security levels |
| CSRF token generation | Random string + session storage | `flask-wtf CSRFProtect` | Handles HMAC signing, timing-safe comparison, token rotation |
| Rate limiting | Counter in global dict | `flask-limiter` | Thread-safe, supports multiple strategies, can upgrade to Redis without code changes |
| Open redirect validation | Regex on `next` param | Simple `startswith("/")` check per OWASP | Regex is fragile; OWASP recommended check is simpler and correct |

**Key insight:** Authentication security failures are the #1 OWASP category. Every hand-rolled component creates a new attack surface. Use the established libraries even if the app seems simple.

---

## Common Pitfalls

### Pitfall 1: `config.py` Import Side Effect Breaks App Startup

**What goes wrong:** `config.py` calls `validate_required_env()` at module import time. If `SECRET_KEY` or `ADMIN_PASSWORD_HASH` are missing, the app crashes with a confusing `ValueError` before Flask even starts.

**Why it happens:** The current `REQUIRED_ENV_VARS` list doesn't include auth vars. After adding auth, these vars become required but may not be in `.env` on fresh deploys.

**How to avoid:** 
1. Add `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` to `REQUIRED_ENV_VARS` in `config.py`.
2. Update `seed_admin.py` to also set these before the app starts.
3. Update `.env.example` with all three new vars.

**Warning signs:** App crashes at startup with `ValueError: Missing required environment variables`.

---

### Pitfall 2: API Routes Return HTML Login Redirect Instead of 401 JSON

**What goes wrong:** Flask-Login's default `unauthorized_handler` redirects to the login page (HTML). When `static/app.js` calls `/api/status/:id` without auth, it gets a 301/302 redirect to `/login` returning HTML, which `res.json()` fails to parse.

**Why it happens:** `login_manager.login_view = "login"` causes Flask-Login to redirect, which breaks JS fetch calls.

**How to avoid:** Use the `before_request` guard pattern (Pattern 2 above) which explicitly returns `jsonify({...}), 401` for `/api/*` paths before Flask-Login's default handler runs.

**Warning signs:** JS console error `SyntaxError: Unexpected token '<'` on fetch calls after session expiry.

---

### Pitfall 3: CSRF Token Missing on FormData (File Upload)

**What goes wrong:** `app.js:246` uses `fetch('/api/pdf/upload', { method: 'POST', body: form })` where `form` is a `FormData` object. You cannot add JSON headers to FormData without breaking multipart encoding. The `X-CSRFToken` header approach still works — it's a request header, not a form field.

**Why it happens:** Developers confuse CSRF token delivery mechanisms (header vs. body field).

**How to avoid:** Always use the `X-CSRFToken` header approach (not a form body field) for AJAX requests. The `apiFetch` wrapper in Pattern 6 handles this correctly. For FormData:
```javascript
// Correct — header works with FormData
fetch('/api/pdf/upload', {
  method: 'POST',
  body: form,  // FormData — no Content-Type header (browser sets multipart boundary)
  headers: { 'X-CSRFToken': getCsrfToken() },
  credentials: 'same-origin',
});
```

---

### Pitfall 4: `SESSION_COOKIE_SECURE=True` Breaks Local Development

**What goes wrong:** Login works in production but sessions are silently dropped in development (HTTP). Users can POST to `/login` successfully but the session cookie isn't sent on subsequent requests.

**Why it happens:** `SESSION_COOKIE_SECURE=True` instructs browsers to only send the cookie over HTTPS. On `http://localhost:5050` the cookie is never sent.

**How to avoid:** Toggle based on environment:
```python
SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV", "production") != "development"
```
Add `FLASK_ENV=development` to local `.env`. Production VPS does NOT set this var, defaulting to `"production"` and enabling `Secure`.

---

### Pitfall 5: bcrypt Timing Attack via Short-Circuit on Email Mismatch

**What goes wrong:** If you check `email == admin.email` first and `return False` immediately on mismatch, the response time for "wrong email" is faster than "wrong password" — enabling user enumeration via timing.

**Why it happens:** Natural short-circuit evaluation in authentication code.

**How to avoid:** Always call `bcrypt.check_password_hash()` regardless of email match. If no user found, compare against a dummy hash to equalize timing:
```python
dummy_hash = bcrypt.generate_password_hash("dummy_constant").decode("utf-8")
hash_to_check = admin.password_hash if (admin and email == admin.email.lower()) else dummy_hash
valid = admin is not None and email == admin.email.lower() and bcrypt.check_password_hash(hash_to_check, password)
```

---

### Pitfall 6: `next` Parameter Open Redirect

**What goes wrong:** Login route redirects to `request.args.get("next")` after success. An attacker can craft `https://your-app.com/login?next=https://evil.com` to redirect users to a phishing site after login.

**Why it happens:** Unvalidated redirect.

**How to avoid:**
```python
next_page = request.args.get("next", "")
if next_page and next_page.startswith("/") and not next_page.startswith("//"):
    return redirect(next_page)
return redirect(url_for("index"))
```

---

### Pitfall 7: CSRF Token Invalid After Session Expiry

**What goes wrong:** If the session expires (12-hour lifetime), the CSRF token embedded in the page meta tag becomes invalid. All subsequent fetch calls get 400 CSRF errors instead of 401 auth errors.

**Why it happens:** Flask-WTF ties CSRF token to the session. When session expires, token is invalid.

**How to avoid:** In the `before_request` guard, check auth first. If not authenticated on `/api/*`, return `401` before CSRF validation runs. Configure CSRF before `LoginManager`:
```python
# Order matters: LoginManager handles session state first
# CSRFProtect will check token after — 401 beats 400
```
Actually, `before_request` runs before Flask-WTF's CSRF check (which is also a before_request). Ensure auth guard runs first by registering it before `csrf.init_app(app)` or by checking `current_user.is_authenticated` in a before_request at lower priority. Alternatively, configure: `WTF_CSRF_CHECK_DEFAULT = False` and only validate CSRF for authenticated requests.

---

## Code Examples

### Full `auth.py` Module

```python
# auth.py
# Source: Flask-Login 0.6.3 docs, Flask-Bcrypt 1.0.1 docs

import os
import logging
from typing import Optional
from flask_login import UserMixin, LoginManager
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)

login_manager = LoginManager()
bcrypt = Bcrypt()
limiter = Limiter(
    get_remote_address,
    default_limits=[],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)


class AdminUser(UserMixin):
    """Singleton admin user; credentials loaded from environment at startup."""

    def __init__(self, user_id: str, email: str, password_hash: str) -> None:
        self.id = user_id
        self.email = email
        self.password_hash = password_hash


_admin: Optional[AdminUser] = None


def init_admin(email: str, password_hash: str) -> None:
    """Initialize singleton admin from env vars. Call once at app startup."""
    global _admin
    if not email or not password_hash:
        raise ValueError("ADMIN_EMAIL and ADMIN_PASSWORD_HASH must be set in environment")
    _admin = AdminUser(user_id="1", email=email.strip().lower(), password_hash=password_hash)
    logger.info("Admin user initialized: %s", email)


def get_admin() -> Optional[AdminUser]:
    return _admin


@login_manager.user_loader
def load_user(user_id: str) -> Optional[AdminUser]:
    admin = get_admin()
    return admin if (admin and admin.id == user_id) else None
```

### App Initialization in `app.py`

```python
# app.py additions — place after `app = Flask(__name__)`
# Source: Flask docs, Flask-Login docs, Flask-WTF docs

import os
from flask_wtf.csrf import CSRFProtect
from auth import login_manager, bcrypt, limiter, init_admin, get_admin

# Security configuration
app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") != "development",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=43200,   # 12 hours
    WTF_CSRF_TIME_LIMIT=3600,
)

# Initialize extensions
csrf = CSRFProtect(app)
login_manager.init_app(app)
login_manager.login_view = "login"
bcrypt.init_app(app)
limiter.init_app(app)

# Seed admin from environment
init_admin(
    email=os.environ["ADMIN_EMAIL"],
    password_hash=os.environ["ADMIN_PASSWORD_HASH"],
)


# Authentication guard
from flask import request, redirect, url_for, jsonify
from flask_login import current_user

PUBLIC_ENDPOINTS: frozenset = frozenset({"login", "logout", "static"})

@app.before_request
def require_login():
    """Block unauthenticated access to all routes."""
    if not request.endpoint or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login", next=request.path))
```

### Login and Logout Routes in `app.py`

```python
# app.py — login/logout routes
# Source: Flask-Login docs + OWASP auth patterns

from flask import render_template, request, redirect, url_for
from flask_login import login_user, logout_user

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def login():
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        admin = get_admin()

        # Always bcrypt-check to prevent timing-based user enumeration
        _dummy = bcrypt.generate_password_hash("__dummy__").decode()
        check_hash = admin.password_hash if (admin and email == admin.email) else _dummy
        credentials_valid = (
            admin is not None
            and email == admin.email
            and bcrypt.check_password_hash(check_hash, password)
        )

        if credentials_valid:
            login_user(admin, remember=False)
            nxt = request.args.get("next", "")
            if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("index"))

        error = "Invalid credentials"   # Generic — no user enumeration

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))
```

### `templates/login.html` Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="csrf-token" content="{{ csrf_token() }}">
  <title>Sign In — Bobby Tailor</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <div class="login-container">
    <div class="login-card">
      <div class="brand-name">Bobby Tailor</div>
      <form method="POST" action="/login">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        {% if error %}
          <p class="login-error">{{ error }}</p>
        {% endif %}
        <label for="email">Email</label>
        <input type="email" id="email" name="email" required autocomplete="username">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" required autocomplete="current-password">
        <button type="submit">Sign in</button>
      </form>
    </div>
  </div>
</body>
</html>
```

### CSRF meta tag addition to existing templates

Add to `<head>` of **both** `templates/index.html` and `templates/settings.html`:
```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

### `seed_admin.py`

```python
#!/usr/bin/env python3
"""
Seed admin credentials to .env. Run once on fresh deployment.

Usage:
    python seed_admin.py

Reads ADMIN_PASSWORD from the script constant (change before running on VPS).
Writes ADMIN_EMAIL and ADMIN_PASSWORD_HASH to .env.
NEVER logs or prints the plaintext password.
"""
from pathlib import Path
from flask_bcrypt import Bcrypt
from dotenv import set_key

ADMIN_EMAIL = "admin@bobbytailor.com"
# Change this on VPS before running, then delete from version control:
ADMIN_PASSWORD = "BobbyTheAdmin@1"
ENV_PATH = Path(__file__).resolve().parent / ".env"

_bcrypt = Bcrypt()
password_hash = _bcrypt.generate_password_hash(ADMIN_PASSWORD, rounds=12).decode("utf-8")
del ADMIN_PASSWORD  # Remove from memory ASAP

if not ENV_PATH.exists():
    ENV_PATH.touch()

set_key(str(ENV_PATH), "ADMIN_EMAIL", ADMIN_EMAIL)
set_key(str(ENV_PATH), "ADMIN_PASSWORD_HASH", password_hash)
print(f"[seed_admin] Admin seeded: {ADMIN_EMAIL}")
print("[seed_admin] ADMIN_PASSWORD_HASH written to .env")
```

### `.env.example` additions

```bash
# ──────────────────────────────────────────────────────────────────────
# Application Authentication (Phase 12)
# ──────────────────────────────────────────────────────────────────────
# Flask secret key — generate with: python -c "import secrets; print(secrets.token_hex(32))"
# REQUIRED in production. App will not start without this.
SECRET_KEY=your-random-secret-key-here

# Admin login credentials — set by running: python seed_admin.py
# Never put plaintext password here — only the bcrypt hash
ADMIN_EMAIL=admin@bobbytailor.com
ADMIN_PASSWORD_HASH=$2b$12$...bcrypt-hash-from-seed_admin.py...

# Set to "development" locally to disable Secure cookie flag (HTTP)
# Leave unset in production (defaults to secure mode)
# FLASK_ENV=development
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `werkzeug.security.generate_password_hash` (md5/sha256) | bcrypt via `flask-bcrypt` | BCrypt adoption ~2010s | bcrypt's work factor makes brute force 10,000x slower |
| Per-route `@login_required` | Global `@app.before_request` guard | Best practice evolution | Prevents auth bypass from missed decorators |
| HTTP Basic Auth | Session-based Flask-Login | Pre-2015 | Sessions support logout, CSRF, remember-me |
| Client-side session (JWT) | Server-side session (Flask default) | Ongoing | Server-side allows instant logout/revocation |
| Form POST only | Form POST + AJAX `X-CSRFToken` header | Flask-WTF 1.x | SPA-style apps can protect AJAX without form fields |

**Deprecated/outdated:**
- `flask-httpauth` with `@auth.login_required`: Designed for stateless HTTP Basic/Token auth (APIs). Wrong fit for a browser-based app with sessions and CSRF.
- `itsdangerous` token-based auth: Over-engineered for single admin; Flask session is simpler and correct.
- `session["user_id"]` manual sessions: Flask-Login handles edge cases (session fixation, fresh login, remember-me) that manual implementations miss.

---

## Open Questions

1. **`config.py` `validate_required_env()` order**
   - What we know: `config.py` is imported at `app.py` line 15, before auth init
   - What's unclear: Whether adding `SECRET_KEY` and `ADMIN_PASSWORD_HASH` to `REQUIRED_ENV_VARS` causes any startup ordering issues with the existing `config.py` structure
   - Recommendation: Add auth vars to `REQUIRED_ENV_VARS` in `config.py` — keeping all env validation in one place is better than split validation

2. **`limiter.limit()` on `/login` and the CSRF check ordering**
   - What we know: Both `before_request` and Flask-Limiter run before view function; CSRF runs in `before_request`
   - What's unclear: If rate limit triggers first (429), does the CSRF check still run and could add noise?
   - Recommendation: Rate limit decorator applies to the view function, not `before_request`. The order is: `before_request` (auth guard + CSRF) → view function (limiter check). 429 from limiter is returned from the view, not `before_request`. This ordering is fine.

3. **`REMEMBER_COOKIE_HTTPONLY` and `REMEMBER_COOKIE_SECURE`**
   - What we know: Flask-Login sets a separate "remember me" cookie if `remember=True`
   - What's unclear: We're using `remember=False`, so this is moot — but if changed later, these must be configured
   - Recommendation: Explicitly set `REMEMBER_COOKIE_HTTPONLY=True` and `REMEMBER_COOKIE_SECURE` for defense in depth, even though remember-me is disabled for now

---

## Sources

### Primary (HIGH confidence)

- Flask-Login 0.6.3 PyPI + official docs (https://flask-login.readthedocs.io/en/latest/) — user_loader, login_user, UserMixin, session_protection, Flask 3 compatibility confirmation
- Flask-Login CHANGES.md (https://github.com/maxcountryman/flask-login/blob/main/CHANGES.md) — Flask 3 compatibility added in 0.6.3 (2023-10-30)
- Flask-WTF CSRF docs (https://flask-wtf.readthedocs.io/en/latest/csrf/) — CSRFProtect, X-CSRFToken header, meta tag pattern
- Flask session cookie docs (https://flask.palletsprojects.com/en/stable/web-security/#set-cookie-options) — SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SECURE, SESSION_COOKIE_SAMESITE
- Flask-Bcrypt docs (https://flask-bcrypt.readthedocs.io/) — generate_password_hash, check_password_hash, decode('utf-8')

### Secondary (MEDIUM confidence)

- Flask-Limiter GitHub + OneUptime blog (2026-03-31) — `5 per minute;20 per hour` pattern, `storage_uri="memory://"`, decorator usage
- TestDriven.io Flask SPA Auth guide — `credentials: "same-origin"`, session cookie config table, CSRF in SPA context

### Tertiary (LOW confidence, flagged for validation)

- OWASP auth checklist (knowledgelib.io 2026) — per-account rate limiting recommendation, 5 attempts/15min threshold
- Community patterns for timing-safe auth (avoiding user enumeration via bcrypt timing)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Flask-Login/Flask-WTF/Flask-Bcrypt/Flask-Limiter all verified against official docs and confirmed Flask 3 compatible
- Architecture (in-memory user store): HIGH — correct choice for single admin; no SQLite needed; pattern is well-established
- CSRF fetch pattern: HIGH — verified against Flask-WTF official docs (X-CSRFToken header + meta tag)
- Pitfalls: MEDIUM — timing attacks and open redirects from OWASP; `before_request` ordering from Flask docs; some community-sourced

**Research date:** 2026-05-26  
**Valid until:** 2026-08-25 (90 days; Flask-Login/Flask-WTF are stable libraries)
