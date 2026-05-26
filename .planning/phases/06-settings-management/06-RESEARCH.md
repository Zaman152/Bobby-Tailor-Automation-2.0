# Phase 6: Settings Management - Research

**Researched:** 2026-05-26
**Domain:** Flask settings API, .env file manipulation, secret redaction
**Confidence:** HIGH

## Summary

This phase enables operators to manage StackCT credentials, Anthropic API keys, and output preferences through the web UI instead of SSH-editing `.env` files directly. The main technical challenges are:

1. **Reading/writing `.env` files safely** — Parsing, updating, and preserving structure
2. **Secret redaction in API responses** — Never returning actual passwords/API keys over the wire
3. **Hot-reloading configuration** — Changes take effect without server restart where possible
4. **Settings UI form** — Reactive form that shows masked secrets and confirms saves

**Current state assessment:**
- `config.py` uses `python-dotenv` with `load_dotenv()` — can leverage for write operations too
- `.env.example` documents all configurable variables with clear groupings
- No settings API exists yet — need `GET /api/settings` and `PUT /api/settings`
- Flask app uses `from config import X` at module level — some changes need restart

**Primary recommendation:** Use `python-dotenv` for `.env` read/write operations. Implement redaction at the API layer using a whitelist of safe-to-return fields. Settings form shows masked placeholders for secrets.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-dotenv | >=1.0.0 | `.env` file parsing and writing | Already in use; `set_key()` and `unset_key()` functions for safe .env modification |
| Flask | >=3.0.0 | API routes | Already in use; consistent with existing API patterns |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv `dotenv_values()` | >=1.0.0 | Parse `.env` without loading into environment | Reading current values for API response |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `.env` file modification | SQLite/JSON config store | Would require migration of existing setup; `.env` is already the standard for this app |
| `python-dotenv set_key()` | Manual file regex replace | `set_key()` handles edge cases (quotes, escaping, preserves comments); manual is error-prone |
| Hot-reload at runtime | Server restart after save | Hot-reload is complex for `from config import X` patterns; restart is explicit and reliable |

**Installation:**

No new dependencies required — `python-dotenv` is already in `requirements.txt`.

## Architecture Patterns

### Recommended Settings API Structure

```
app.py
├── GET  /api/settings      → Returns settings with secrets redacted
├── PUT  /api/settings      → Updates settings, writes to .env
└── POST /api/settings/test → Validates credentials without persisting

settings.py (new)
├── get_settings()          → Read .env + redact secrets
├── update_settings(data)   → Validate + write to .env
└── REDACTED_FIELDS         → List of fields to mask in responses
```

### Pattern 1: python-dotenv set_key() for Safe .env Updates

**What:** Use `dotenv.set_key()` to modify individual values in `.env` without rewriting the entire file.

**When to use:** Any time you need to programmatically update `.env` values.

**Example:**

```python
# Source: python-dotenv documentation 2026
from dotenv import set_key, dotenv_values
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"

def update_env_value(key: str, value: str) -> bool:
    """Update a single key in .env file."""
    success, key_to_set, value_set = set_key(
        dotenv_path=str(ENV_PATH),
        key_to_set=key,
        value_to_set=value,
        quote_mode="auto",  # Adds quotes if value contains spaces
        export=False        # Don't prefix with 'export'
    )
    return success

# Usage:
update_env_value("STACKCT_EMAIL", "new@example.com")
update_env_value("ANTHROPIC_API_KEY", "sk-ant-api03-...")
```

**Key insight:** `set_key()` preserves file structure, comments, and other variables. It only modifies the targeted key.

### Pattern 2: Secret Redaction in API Responses

**What:** Define a whitelist/blacklist of fields that should be masked when returned via API.

**When to use:** Any API endpoint that returns configuration containing secrets.

**Example:**

```python
# Source: OWASP API Security Guidelines 2026
from dotenv import dotenv_values

SENSITIVE_FIELDS = {
    "STACKCT_PASSWORD",
    "ANTHROPIC_API_KEY",
}

def get_settings_redacted() -> dict:
    """Return settings with sensitive values masked."""
    raw = dotenv_values(".env")
    
    result = {}
    for key, value in raw.items():
        if key in SENSITIVE_FIELDS:
            # Show that a value exists but mask the actual content
            if value:
                # Show first/last few chars for API keys to help identify
                if key == "ANTHROPIC_API_KEY" and len(value) > 12:
                    result[key] = f"{value[:7]}...{value[-4:]}"
                else:
                    result[key] = "••••••••" if value else ""
            else:
                result[key] = ""
        else:
            result[key] = value or ""
    
    return result
```

**Key insight:** For API keys, showing partial content (e.g., `sk-ant-...abcd`) helps users identify which key is configured without exposing the full secret.

### Pattern 3: Settings Validation Before Write

**What:** Validate settings before persisting to catch errors early.

**When to use:** Before writing any user-provided settings to `.env`.

**Example:**

```python
# Source: Flask input validation patterns 2026
from typing import Dict, Tuple, List

def validate_settings(data: Dict) -> Tuple[bool, List[str]]:
    """Validate settings before writing.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    # Email format (basic)
    if "STACKCT_EMAIL" in data:
        email = data["STACKCT_EMAIL"]
        if email and "@" not in email:
            errors.append("STACKCT_EMAIL must be a valid email address")
    
    # API key format (Anthropic keys start with sk-ant-)
    if "ANTHROPIC_API_KEY" in data:
        key = data["ANTHROPIC_API_KEY"]
        if key and not key.startswith("sk-ant-"):
            errors.append("ANTHROPIC_API_KEY should start with 'sk-ant-'")
    
    # Model must be valid
    if "CLAUDE_MODEL" in data:
        valid_models = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]
        if data["CLAUDE_MODEL"] not in valid_models:
            errors.append(f"CLAUDE_MODEL must be one of: {', '.join(valid_models)}")
    
    # Output dir must be writable (defer to actual write attempt)
    # Canvas stability must be positive integer
    if "CANVAS_STABILITY_TIMEOUT" in data:
        try:
            timeout = int(data["CANVAS_STABILITY_TIMEOUT"])
            if timeout < 1:
                errors.append("CANVAS_STABILITY_TIMEOUT must be >= 1")
        except (ValueError, TypeError):
            errors.append("CANVAS_STABILITY_TIMEOUT must be a number")
    
    return len(errors) == 0, errors
```

### Pattern 4: Partial Updates (PATCH semantics)

**What:** Allow updating only the fields that changed, not requiring full settings object.

**When to use:** Settings forms where user may only change one field.

**Example:**

```python
# Source: REST API best practices 2026
@app.route("/api/settings", methods=["PUT"])
def update_settings():
    """Update settings - only provided fields are changed."""
    data = request.get_json() or {}
    
    if not data:
        return jsonify({"error": "No settings provided"}), 400
    
    # Validate only the fields being changed
    is_valid, errors = validate_settings(data)
    if not is_valid:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    
    # Update only provided fields
    env_path = Path(__file__).resolve().parent / ".env"
    for key, value in data.items():
        # Skip empty strings for sensitive fields (means "don't change")
        if key in SENSITIVE_FIELDS and value == "":
            continue
        set_key(str(env_path), key, value)
    
    return jsonify({
        "success": True,
        "message": "Settings saved. Restart server to apply credential changes.",
        "settings": get_settings_redacted()
    })
```

**Key insight:** Empty strings for password fields mean "leave unchanged" — the UI should send empty string if the masked field wasn't edited.

### Anti-Patterns to Avoid

- **Returning raw secrets in GET response:** Never return `STACKCT_PASSWORD` or `ANTHROPIC_API_KEY` values
- **Regex file manipulation:** Don't use regex to edit `.env`; `set_key()` handles edge cases
- **Storing secrets in JSON/SQLite:** `.env` is already secure (gitignored, standard pattern)
- **Accepting arbitrary keys:** Whitelist allowed settings keys to prevent injection
- **Hot-reloading sensitive config:** Credential changes should require restart for security

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| `.env` file parsing | Custom parser | `dotenv_values()` | Handles quotes, escapes, multiline |
| `.env` file writing | String manipulation | `set_key()` | Preserves structure, handles edge cases |
| Secret masking | Per-endpoint masking | Centralized `get_settings_redacted()` | Single source of truth for sensitive fields |

## Common Pitfalls

### Pitfall 1: Returning Unredacted Secrets

**What goes wrong:** API returns actual password/API key values, which can be logged, cached, or intercepted.

**Why it happens:** Developer returns raw config values without filtering.

**How to avoid:**
1. Always use `get_settings_redacted()` never raw `dotenv_values()`
2. Define `SENSITIVE_FIELDS` set and check every response
3. Log warning if a sensitive field is about to be returned (defensive programming)

**Warning signs:**
- API response contains full `ANTHROPIC_API_KEY` value
- Browser network tab shows password in plain text

### Pitfall 2: Overwriting .env on Empty Input

**What goes wrong:** User submits form without entering new password; server overwrites password with empty string.

**Why it happens:** Form sends empty string, server interprets as "set to empty".

**How to avoid:**
1. UI sends `null` or omits field entirely if not changed
2. Server ignores empty strings for sensitive fields
3. Use placeholder text like "Enter new password to change"

**Warning signs:**
- Settings save succeeds but credentials stop working
- `.env` shows `STACKCT_PASSWORD=` (empty value)

### Pitfall 3: Corrupt .env After Concurrent Writes

**What goes wrong:** Two simultaneous settings saves corrupt the `.env` file.

**Why it happens:** Race condition in file writes without locking.

**How to avoid:**
1. Use file locking or single-threaded settings writes
2. `set_key()` uses atomic write pattern internally (helps but not bulletproof)
3. Settings page should be single-user anyway (operator tool)

**Warning signs:**
- `.env` file has duplicate keys or truncated content
- Server fails to start after settings change

### Pitfall 4: Hot-Reload Breaking Imports

**What goes wrong:** Config change doesn't take effect because `from config import X` happened at module import time.

**Why it happens:** Python imports are cached; re-reading `.env` doesn't update already-imported values.

**How to avoid:**
1. Document which settings require restart (all credential/API key changes)
2. Return `"restart_required": true` in API response for those fields
3. Non-sensitive settings (like `OUTPUT_DIR`) can be re-read dynamically if needed

**Warning signs:**
- User changes API key but old key is still used
- Settings show new value but behavior uses old value

## Code Examples

### Settings Module Implementation

```python
# settings.py (new file)
"""Settings management — .env read/write with secret redaction."""
from pathlib import Path
from typing import Dict, Tuple, List
from dotenv import dotenv_values, set_key

ENV_PATH = Path(__file__).resolve().parent / ".env"

SENSITIVE_FIELDS = {
    "STACKCT_PASSWORD",
    "ANTHROPIC_API_KEY",
}

ALLOWED_FIELDS = {
    "STACKCT_EMAIL",
    "STACKCT_PASSWORD",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "CLAUDE_MODEL_SCHEDULES",
    "HEADLESS",
    "CANVAS_STABILITY_TIMEOUT",
    "CANVAS_STABILITY_CHECKS",
    "OUTPUT_DIR",
    "RUN_SCHEDULE",
}

VALID_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]

RESTART_REQUIRED_FIELDS = {
    "STACKCT_EMAIL",
    "STACKCT_PASSWORD",
    "ANTHROPIC_API_KEY",
}


def get_settings() -> Dict[str, str]:
    """Read settings from .env with secrets redacted."""
    raw = dotenv_values(str(ENV_PATH))
    
    result = {}
    for key in ALLOWED_FIELDS:
        value = raw.get(key, "")
        
        if key in SENSITIVE_FIELDS:
            if value:
                if key == "ANTHROPIC_API_KEY" and len(value) > 12:
                    result[key] = f"{value[:7]}...{value[-4:]}"
                else:
                    result[key] = "••••••••"
                result[f"{key}_set"] = True
            else:
                result[key] = ""
                result[f"{key}_set"] = False
        else:
            result[key] = value or ""
    
    return result


def validate_settings(data: Dict) -> Tuple[bool, List[str]]:
    """Validate settings before writing."""
    errors = []
    
    # Reject unknown keys
    unknown = set(data.keys()) - ALLOWED_FIELDS
    if unknown:
        errors.append(f"Unknown settings: {', '.join(unknown)}")
    
    # Email format
    if "STACKCT_EMAIL" in data and data["STACKCT_EMAIL"]:
        if "@" not in data["STACKCT_EMAIL"]:
            errors.append("STACKCT_EMAIL must be a valid email")
    
    # API key format
    if "ANTHROPIC_API_KEY" in data and data["ANTHROPIC_API_KEY"]:
        if not data["ANTHROPIC_API_KEY"].startswith("sk-ant-"):
            errors.append("ANTHROPIC_API_KEY should start with 'sk-ant-'")
    
    # Model validation
    for model_key in ["CLAUDE_MODEL", "CLAUDE_MODEL_SCHEDULES"]:
        if model_key in data and data[model_key]:
            if data[model_key] not in VALID_MODELS:
                errors.append(f"{model_key} must be one of: {', '.join(VALID_MODELS)}")
    
    # Numeric fields
    for num_key in ["CANVAS_STABILITY_TIMEOUT", "CANVAS_STABILITY_CHECKS"]:
        if num_key in data and data[num_key]:
            try:
                val = int(data[num_key])
                if val < 1:
                    errors.append(f"{num_key} must be >= 1")
            except (ValueError, TypeError):
                errors.append(f"{num_key} must be a number")
    
    return len(errors) == 0, errors


def update_settings(data: Dict) -> Tuple[bool, str, bool]:
    """Update settings in .env file.
    
    Returns:
        (success, message, restart_required)
    """
    is_valid, errors = validate_settings(data)
    if not is_valid:
        return False, f"Validation failed: {'; '.join(errors)}", False
    
    restart_required = False
    
    for key, value in data.items():
        if key not in ALLOWED_FIELDS:
            continue
        
        # Empty string for sensitive fields = don't change
        if key in SENSITIVE_FIELDS and value == "":
            continue
        
        set_key(str(ENV_PATH), key, str(value), quote_mode="auto")
        
        if key in RESTART_REQUIRED_FIELDS:
            restart_required = True
    
    return True, "Settings saved", restart_required
```

### Settings API Routes

```python
# In app.py - add after existing routes
from settings import get_settings, update_settings

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Return current settings with secrets redacted."""
    return jsonify(get_settings())


@app.route("/api/settings", methods=["PUT"])
def api_update_settings():
    """Update settings - partial updates supported."""
    data = request.get_json() or {}
    
    if not data:
        return jsonify({"error": "No settings provided"}), 400
    
    success, message, restart_required = update_settings(data)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({
        "success": True,
        "message": message,
        "restart_required": restart_required,
        "settings": get_settings()
    })
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Admin SSH to edit `.env` | Web UI settings page | 2024+ | Non-technical operators can manage credentials |
| Full secret return + client masking | Server-side redaction | Always | Secrets never leave server |
| Full config replacement | Partial updates with `set_key()` | python-dotenv 0.10+ | Preserves comments, structure |

## Open Questions

None — the scope is well-defined and uses established patterns.

## Files Requiring Changes

1. **`settings.py`** (new) — Settings read/write logic with redaction
2. **`app.py`** — Add `GET /api/settings` and `PUT /api/settings` routes
3. **`templates/settings.html`** (new, Phase 8) — Settings form UI

## Testing Approach

### Unit Testing

1. **Redaction tests:**
   - `get_settings()` returns `"••••••••"` for `STACKCT_PASSWORD`
   - `get_settings()` returns partial API key like `"sk-ant-...abcd"`
   - `get_settings()` never returns full sensitive values

2. **Validation tests:**
   - Rejects invalid email format
   - Rejects invalid API key prefix
   - Rejects unknown settings keys
   - Accepts valid settings

3. **Write tests:**
   - `update_settings()` modifies `.env` file correctly
   - Empty string for password field doesn't overwrite
   - Returns `restart_required: true` for credential changes

### Integration Testing

1. **API tests:**
   - `GET /api/settings` returns 200 with redacted values
   - `PUT /api/settings` with valid data returns success
   - `PUT /api/settings` with invalid data returns 400 with errors

### Manual Testing

1. **Settings roundtrip:**
   - Open Settings page, verify current values shown (masked for secrets)
   - Change email, save, verify `.env` updated
   - Change password, verify old password still works until restart
   - Restart server, verify new password is active

## Sources

### Primary (HIGH confidence)

- python-dotenv Documentation — set_key() and dotenv_values()
  https://saurabh-kumar.com/python-dotenv/
- OWASP API Security — Sensitive Data Exposure
  https://owasp.org/API-Security/
- Flask REST API Patterns 2026
  https://flask.palletsprojects.com/en/2.3.x/patterns/

## Metadata

**Confidence breakdown:**
- python-dotenv set_key(): **HIGH** — Official documentation, widely used
- Secret redaction pattern: **HIGH** — Standard security practice
- Validation approach: **HIGH** — Established Flask patterns
- Hot-reload limitations: **HIGH** — Understood Python import behavior

**Research date:** 2026-05-26
**Valid until:** ~2026-08-26 (90 days)
