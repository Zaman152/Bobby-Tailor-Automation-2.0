"""
Settings management module — read, validate, and persist application settings.

Security: Sensitive fields are never returned in full; password shown as ••••••••,
API keys shown as first-7...last-4 partial. Empty string updates for sensitive
fields are ignored (preserves existing value).
"""
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parent / ".env"

SENSITIVE_FIELDS = {"STACKCT_PASSWORD", "ANTHROPIC_API_KEY"}

RESTART_REQUIRED_FIELDS = {"STACKCT_EMAIL", "STACKCT_PASSWORD", "ANTHROPIC_API_KEY"}

VALID_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]

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


def _redact(key: str, value: str) -> str:
    """Return a redacted representation of a sensitive field value."""
    if not value:
        return ""
    if key == "STACKCT_PASSWORD":
        return "••••••••"
    if key == "ANTHROPIC_API_KEY":
        # Show first 7 + last 4 characters
        if len(value) > 11:
            return f"{value[:7]}...{value[-4:]}"
        return "••••••••"
    return value


def get_settings() -> Dict[str, object]:
    """Return current settings with secrets redacted.

    Returns a dict with all ALLOWED_FIELDS values.
    Sensitive fields: redacted display value + a bool {KEY}_set indicating if configured.
    """
    try:
        from dotenv import dotenv_values
        current = dotenv_values(str(ENV_PATH)) if ENV_PATH.exists() else {}
    except ImportError:
        import os
        current = {k: os.getenv(k, "") for k in ALLOWED_FIELDS}

    result: Dict[str, object] = {}
    for key in ALLOWED_FIELDS:
        value = current.get(key, "")
        if key in SENSITIVE_FIELDS:
            result[key] = _redact(key, value)
            result[f"{key}_set"] = bool(value)
        else:
            result[key] = value

    return result


def validate_settings(data: Dict) -> Tuple[bool, List[str]]:
    """Validate proposed settings values.

    Returns (is_valid, list_of_errors).
    """
    errors = []

    for key in data:
        if key not in ALLOWED_FIELDS:
            errors.append(f"Unknown setting: {key}")

    email = data.get("STACKCT_EMAIL", "")
    if email and "@" not in email:
        errors.append("STACKCT_EMAIL must be a valid email address")

    api_key = data.get("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("sk-ant-"):
        errors.append("ANTHROPIC_API_KEY must start with sk-ant-")

    for model_key in ("CLAUDE_MODEL", "CLAUDE_MODEL_SCHEDULES"):
        model = data.get(model_key, "")
        if model and model not in VALID_MODELS:
            errors.append(f"{model_key} must be one of: {', '.join(VALID_MODELS)}")

    for int_key in ("CANVAS_STABILITY_TIMEOUT", "CANVAS_STABILITY_CHECKS"):
        val = data.get(int_key, "")
        if val:
            try:
                if int(val) <= 0:
                    errors.append(f"{int_key} must be a positive integer")
            except (ValueError, TypeError):
                errors.append(f"{int_key} must be a positive integer")

    headless = data.get("HEADLESS", "")
    if headless and headless.lower() not in ("true", "false", "1", "0"):
        errors.append("HEADLESS must be true or false")

    return (len(errors) == 0, errors)


def update_settings(data: Dict) -> Tuple[bool, str, bool]:
    """Write validated settings to .env file.

    Args:
        data: Dict of setting key-value pairs to update.

    Returns:
        Tuple of (success, message, restart_required).
        Empty string for sensitive fields means 'leave unchanged'.
    """
    is_valid, errors = validate_settings(data)
    if not is_valid:
        return (False, "; ".join(errors), False)

    try:
        from dotenv import set_key
    except ImportError:
        return (False, "python-dotenv not installed", False)

    # Ensure .env file exists
    if not ENV_PATH.exists():
        ENV_PATH.touch()

    restart_required = False
    written_count = 0

    for key, value in data.items():
        if key not in ALLOWED_FIELDS:
            continue
        # Skip empty-string updates for sensitive fields (preserve existing value)
        if key in SENSITIVE_FIELDS and not str(value).strip():
            logger.debug(f"Skipping empty update for sensitive field: {key}")
            continue

        try:
            set_key(str(ENV_PATH), key, str(value), quote_mode="auto")
            written_count += 1
            if key in RESTART_REQUIRED_FIELDS:
                restart_required = True
            logger.info(f"Settings updated: {key}")
        except Exception as e:
            logger.error(f"Failed to write setting {key}: {e}")
            return (False, f"Failed to write {key}: {e}", False)

    msg = f"Saved {written_count} setting{'s' if written_count != 1 else ''}"
    return (True, msg, restart_required)
