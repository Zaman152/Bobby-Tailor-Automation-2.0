# Phase 1: Config & Safe Operations - Research

**Researched:** 2026-05-26
**Domain:** Flask API error handling, Python configuration management
**Confidence:** HIGH

## Summary

This phase addresses two fundamental production-readiness requirements: portable environment configuration and user-safe error responses. The codebase already uses project-relative `.env` loading (FOUND-01 largely complete), but currently leaks raw exception messages to API clients in multiple locations, violating FOUND-02.

Research focused on:
1. **Flask error sanitization patterns** — How to return generic user-safe error messages while logging full stack traces server-side
2. **Environment variable validation** — Best practices for ensuring `.env` completeness and catching configuration errors at startup
3. **Security considerations** — Preventing information disclosure through error messages and default configuration values

**Current state assessment:**
- `config.py` ALREADY uses `Path(__file__).resolve().parent / ".env"` — relative loading works ✓
- `.env.example` exists but needs completeness verification
- `requirements.txt` has `pillow>=10.0.0` — DEPLOY-03 satisfied ✓
- Multiple locations expose `str(e)` directly to API clients (security risk)
- `config.py` has hardcoded default `STACKCT_EMAIL = "muhammad@klouded.com"` (should fail-fast, not default to a specific email)

**Primary recommendation:** Implement centralized Flask error handlers to sanitize all exception responses, add startup validation for required environment variables, and audit `.env.example` for completeness.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | >=3.0.0 | Web framework | Already in use; provides `@app.errorhandler` decorator for centralized error handling |
| python-dotenv | >=1.0.0 | `.env` file loading | Already in use; de-facto standard for Python env var management |
| logging (stdlib) | 3.10+ | Structured logging | Built-in Python module; Flask integrates via `app.logger` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | >=2.0.0 | Config validation | **Optional upgrade** — validates env vars at startup with type checking; overkill for this v1 scope but recommended for v2 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual `os.getenv` checks | pydantic-settings | Pydantic adds type validation and auto-coercion but requires new dependency; manual checks sufficient for v1 given small config surface |
| `str(e)` exposure | Flask error handlers | No alternative — error handlers are the Flask-native solution |

**Installation:**

No new dependencies required — all tools already present in `requirements.txt`.

```bash
# Already installed:
pip install flask>=3.0.0 python-dotenv>=1.0.0
```

## Architecture Patterns

### Recommended Error Handling Structure

```
app.py
├── Error handlers (centralized)
│   ├── @app.errorhandler(HTTPException)  # For 4xx errors
│   └── @app.errorhandler(Exception)      # For 5xx errors
└── Route handlers
    └── Raise exceptions, let handlers sanitize

Other modules (scraper, claude_analyzer, project_cache)
└── Raise exceptions with context, don't format for users
```

### Pattern 1: Centralized Flask Error Handlers

**What:** Register global error handlers to intercept all exceptions and return sanitized JSON responses while logging full details.

**When to use:** All Flask API applications that return JSON (not HTML error pages).

**Example:**

```python
# Source: Flask documentation + Better Stack Community 2026
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Handle expected HTTP errors (4xx client errors)."""
    # Log at warning level for expected errors
    logger.warning(f"HTTP {e.code}: {e.description} | {request.path}")
    
    return jsonify({
        "error": e.name,
        "message": e.description  # Safe: Werkzeug descriptions are generic
    }), e.code

@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all for unexpected server errors (5xx)."""
    # Log full traceback for debugging
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    
    # Return generic message to client
    if isinstance(e, HTTPException):
        return handle_http_exception(e)
    
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred. Please try again later."
    }), 500
```

**Key insight:** The `exc_info=True` parameter in `logger.error()` automatically captures and logs the full traceback without passing it to the client.

### Pattern 2: Environment Variable Validation at Startup

**What:** Check for required environment variables before the app starts accepting requests. Fail-fast with clear error messages.

**When to use:** All production apps that depend on external configuration.

**Example:**

```python
# Source: Python configuration best practices 2026
import os
import sys

REQUIRED_ENV_VARS = [
    "STACKCT_EMAIL",
    "STACKCT_PASSWORD",
    "ANTHROPIC_API_KEY",
]

def validate_environment():
    """Verify all required environment variables are set."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Please set these in your .env file or environment.", file=sys.stderr)
        sys.exit(1)

# Call before app initialization
if __name__ == "__main__":
    validate_environment()
    app.run(debug=True, port=5050, use_reloader=False)
```

**Alternative (lightweight):** For this codebase's small config surface, manual validation is sufficient. For larger projects or v2, consider `pydantic-settings` for automatic type validation:

```python
# Optional upgrade path (not required for v1)
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    
    stackct_email: str
    stackct_password: str
    anthropic_api_key: str
    claude_model: str = "claude-haiku-4-5"

# Fails at startup if required vars missing
settings = Settings()
```

### Pattern 3: Safe Default Removal

**What:** Remove hardcoded defaults for secrets or user-specific values. Force explicit configuration.

**Current issue in `config.py`:**

```python
# UNSAFE: Hardcoded email suggests it's acceptable to run without configuration
STACKCT_EMAIL = os.getenv("STACKCT_EMAIL", "muhammad@klouded.com")
```

**Recommended:**

```python
# Safe: No default — app fails visibly if var is missing
STACKCT_EMAIL = os.getenv("STACKCT_EMAIL")
if not STACKCT_EMAIL:
    raise ValueError("STACKCT_EMAIL environment variable is required")
```

### Anti-Patterns to Avoid

- **Returning `str(e)` to API clients:** Leaks implementation details, library versions, file paths, database schemas
- **Using bare `except:` clauses:** Catches KeyboardInterrupt and system exits; use `except Exception:` instead
- **Logging secrets in error messages:** Sanitize error context before logging (e.g., mask passwords in connection strings)
- **Defaulting secrets to example values:** Forces production to override; fail-fast is safer

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Error message sanitization | Custom exception-to-message mapping | Flask `@app.errorhandler` | Built-in, handles all routes automatically |
| Structured logging | Print statements with timestamps | Python `logging` module + `logger.exception()` | Captures stack traces, supports levels, integrates with monitoring tools |
| `.env` syntax parsing | Custom file reader | `python-dotenv` | Handles quoting, escaping, comments, multi-line values |

**Key insight:** Exception handling looks simple but has many edge cases — async exceptions, custom exception types, HTTP vs. non-HTTP errors. Flask's built-in error handler system handles all of these.

## Common Pitfalls

### Pitfall 1: Leaking Stack Traces in Production

**What goes wrong:** Returning raw exception strings (`str(e)`) exposes file paths, library versions, SQL queries, internal variable names. Attackers use this for reconnaissance.

**Why it happens:** Developers test locally where stack traces are helpful, then forget to sanitize for production.

**How to avoid:**
1. Register global error handlers that log full details but return generic messages
2. Never set `FLASK_DEBUG=1` in production (enables interactive debugger)
3. Test error responses with `curl` to verify no internal details leak

**Warning signs:**
- API returns messages like `FileNotFoundError: /var/app/uploads/abc123.pdf`
- Error responses contain module names like `playwright._impl._api_types.TimeoutError`
- Traceback shows line numbers and function names

### Pitfall 2: Silent Configuration Failures

**What goes wrong:** App starts with missing `.env` values, then crashes deep in execution (e.g., on first API call) with confusing errors like `NoneType has no attribute 'split'`.

**Why it happens:** `os.getenv()` returns `None` for missing variables, which propagates until used.

**How to avoid:**
1. Validate required vars at startup (before Flask routes are registered)
2. Remove default values for secrets and user-specific configs
3. Raise `ValueError` with clear message instead of allowing `None`

**Warning signs:**
- `TypeError: expected str, got NoneType` in production logs
- App starts successfully but first request fails with config-related error
- Confusing error messages that don't mention the missing variable name

### Pitfall 3: Incomplete `.env.example`

**What goes wrong:** New developers clone the repo, copy `.env.example` to `.env`, but the app crashes because `.env.example` is missing recently added variables.

**Why it happens:** Developers add new `os.getenv()` calls but forget to update `.env.example`.

**How to avoid:**
1. Parse `config.py` and `.env.example` programmatically to verify completeness (can be a test)
2. Add a comment convention: every `os.getenv()` line must have a corresponding `.env.example` entry
3. Include descriptions in `.env.example` so purpose is clear

**Warning signs:**
- New team members report "missing variable" errors that aren't documented
- `.env.example` has variables that aren't used in `config.py` (drift)
- No descriptions for non-obvious variables (e.g., `HEADLESS=true` without explaining it's for browser automation)

### Pitfall 4: Hardcoded Sensitive Defaults

**What goes wrong:** Using a real email or partial credentials as defaults (e.g., `STACKCT_EMAIL = "muhammad@klouded.com"`) allows the app to start without proper configuration, leading to production using the wrong account.

**Why it happens:** Convenience during local development.

**How to avoid:**
1. Use placeholder values like `"your_email@example.com"` in `.env.example`
2. Require explicit configuration via validation at startup
3. Never commit real credentials or user-specific values to the repo

**Warning signs:**
- `config.py` contains real email addresses or partial API keys
- Defaults reference a specific person's account
- App runs successfully without `.env` file

## Code Examples

Verified patterns for this codebase:

### Flask Error Handler Implementation

```python
# Source: Flask Error Handling Patterns (Better Stack 2026)
# Location: app.py (add after app initialization)

@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Return JSON for HTTP errors (4xx client errors)."""
    app.logger.warning(f"HTTP {e.code}: {e.description} | Path: {request.path}")
    return jsonify({
        "error": e.name,
        "message": e.description
    }), e.code

@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all for unexpected errors (5xx)."""
    # Log full traceback for debugging
    app.logger.error(f"Unhandled exception in {request.path}: {e}", exc_info=True)
    
    # Return sanitized response
    if isinstance(e, HTTPException):
        return handle_http_exception(e)
    
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred"
    }), 500
```

### Startup Environment Validation

```python
# Source: Python production best practices 2026
# Location: app.py or config.py (run before Flask app starts)

def validate_required_env_vars():
    """Ensure all required environment variables are set."""
    required = [
        "STACKCT_EMAIL",
        "STACKCT_PASSWORD",
        "ANTHROPIC_API_KEY",
    ]
    
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Please set these in your .env file."
        )

# Call at module load time (before app.run)
validate_required_env_vars()
```

### Safe Exception Handling in Worker Functions

```python
# Source: Production exception handling patterns 2026
# Location: scraper.py, claude_analyzer.py, project_cache.py

# BEFORE (current — UNSAFE):
try:
    result = some_operation()
except Exception as e:
    logger.exception("Operation failed")
    return {"error": str(e)}  # ❌ Leaks internals

# AFTER (recommended):
try:
    result = some_operation()
except Exception as e:
    logger.exception("Operation failed")  # ✓ Full details to logs
    raise  # ✓ Let Flask error handler sanitize for client
```

**Key change:** Worker functions should raise exceptions, not format error messages. Let Flask's global error handlers decide what to show the user.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `try/except` per route | Centralized `@app.errorhandler` | Flask 1.0 (2018) | Single source of truth for error formatting |
| `os.getenv` with fallback strings | Validation at startup | 12-factor app principles | Fail-fast instead of runtime surprises |
| Plain text error pages | JSON responses with `jsonify()` | REST API best practices | Consistent machine-readable errors |
| `print()` debugging | Structured `logging` with levels | Python logging module (stdlib) | Persistent logs, integration with monitoring |

**Deprecated/outdated:**
- Returning HTML error pages from API routes (pre-2020 pattern)
- Using `app.config["SECRET_KEY"]` for non-secret config (confusing; use env vars directly)
- Accessing `os.environ` directly in route handlers (couples routes to environment; use config module)

## Open Questions

None — all requirements for this phase are well-understood and have established solutions in the Flask ecosystem.

## Verification Checklist for Planning

Before creating PLAN.md, the planner should verify:

- [ ] `config.py` environment variable list matches `.env.example` entries (no drift)
- [ ] All variables in `config.py` that use `os.getenv()` are documented in `.env.example`
- [ ] Every location that returns `{"error": str(e)}` is identified (need to audit `app.py`, `project_cache.py`, `claude_analyzer.py`)
- [ ] `config.py` default values for `STACKCT_EMAIL` are reviewed for security (should fail, not default to a real email)
- [ ] Test approach includes verifying that error responses don't leak file paths or stack traces

## Files Requiring Changes

Based on codebase analysis:

1. **`app.py`** — Add global error handlers; update `_stackct_job` and `_pdf_job` to raise instead of capturing `str(e)`
2. **`config.py`** — Remove unsafe default for `STACKCT_EMAIL`; add startup validation for required vars
3. **`project_cache.py`** — Line 90 returns `{"error": str(e)}` — remove, raise exception instead
4. **`claude_analyzer.py`** — Lines 234, 237 return `{"error": str(e)}` — remove, raise exception instead
5. **`.env.example`** — Audit for completeness vs. `config.py`; add descriptions for all variables

## Testing Approach

### Unit Testing

1. **Error handler tests:**
   - Trigger an exception in a route, assert response is `{"error": "Internal server error"}` with status 500
   - Verify logs contain full traceback but response does not
   - Test `HTTPException` returns formatted JSON with correct status code

2. **Environment validation tests:**
   - Mock `os.getenv()` to return `None` for required vars
   - Assert app startup raises `ValueError` with clear message
   - Verify app starts successfully when all vars are set

### Integration Testing

1. **API error scenarios:**
   - Upload malformed PDF, verify response is user-safe (no file paths)
   - Trigger StackCT login failure, verify response is generic
   - Test `/api/projects` with stale cache and failed refresh

2. **Configuration completeness:**
   - Parse `config.py` and `.env.example` programmatically
   - Assert every `os.getenv()` call has a corresponding `.env.example` entry
   - Assert no defaults exist for sensitive variables

### Manual Testing

1. **Production simulation:**
   - Remove `.env` file, verify app fails immediately with helpful message
   - Set `ANTHROPIC_API_KEY` to invalid value, verify error doesn't leak the key value
   - Check server logs contain full tracebacks while API responses are sanitized

## Sources

### Primary (HIGH confidence)

- Flask Error Handling Patterns — Better Stack Community, 2026
  https://betterstack.com/community/guides/scaling-python/flask-error-handling/
- Flask Documentation: Handling Application Errors — Flask 2.3.x
  https://flask-docs.readthedocs.io/en/latest/errorhandling/
- The Flask Mega-Tutorial, Part VII: Error Handling — Miguel Grinberg, 2026
  https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-vii-error-handling
- Python Env Variables: os.environ, dotenv & Pydantic — env.dev, 2026
  https://env.dev/guides/python-env-variables
- Exception Handling in Python Projects — Alok Rahul (Medium), March 2026
  https://medium.com/@alokrahuldevops/day-75-exception-handling-in-python-projects-3ea5d785a7ea

### Secondary (MEDIUM confidence)

- How to Build a Flask REST API in 12 Steps — Tech Insider, 2026
  https://tech-insider.org/flask-tutorial-rest-api-python-2026/
- Flask Structured Logging — DEV Community, 2026
  https://dev.to/ptp2308/flask-python-structured-logging-what-most-miss-in-production-45g6
- Environment Variables Containing Secrets — Sourcery Security Database, 2026
  https://sourcery.ai/vulnerabilities/environment-variables-logged-python

### Tertiary (LOW confidence)

None — all findings verified with official documentation or authoritative community sources

## Metadata

**Confidence breakdown:**
- Flask error handling patterns: **HIGH** — Official Flask documentation + multiple 2026 sources agree
- Environment variable validation: **HIGH** — Standard practice, verified with python-dotenv official docs
- Current codebase issues: **HIGH** — Directly observed in code review
- Testing approach: **MEDIUM** — Based on best practices but not specific to this codebase yet

**Research date:** 2026-05-26
**Valid until:** ~2026-08-26 (90 days — Flask error handling is stable, minimal API churn expected)
