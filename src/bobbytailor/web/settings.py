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

# Repo root is three levels up from src/bobbytailor/web/; fall back to cwd
# if the root .env is missing (e.g. installed non-editable).
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
if not ENV_PATH.exists():
    ENV_PATH = Path.cwd() / ".env"

SENSITIVE_FIELDS = {"STACKCT_PASSWORD", "ANTHROPIC_API_KEY"}

RESTART_REQUIRED_FIELDS = {"STACKCT_EMAIL", "STACKCT_PASSWORD", "ANTHROPIC_API_KEY"}

# Generated from config.py, never retyped. A hardcoded copy here shipped
# ["claude-haiku-4-5","claude-sonnet-4-6","claude-opus-4-7"] while .env
# resolved CLAUDE_MODEL_SCHEDULES to a slug that list did not contain — and a
# <select> cannot hold a value with no matching <option>, so the form read
# back "" and Save wrote it. See config.MODEL_CHOICES for the full chain.
#
# Imported as a module attribute rather than by-value so a test (or a reload
# after a Settings write) sees the current catalogue.
def _valid_models() -> List[str]:
    from bobbytailor import config

    return list(config.VALID_MODEL_SLUGS)


# Kept as a module-level name for callers that read it directly; the function
# above is what validate_settings uses, so a change in config is picked up.
VALID_MODELS = _valid_models()

# Fields where writing an empty string is destructive rather than meaningful.
# `os.getenv(key, DEFAULT)` does NOT fall back for a key that is set-but-empty,
# so blanking any of these silently disables the thing it configures — a blank
# CLAUDE_MODEL_SCHEDULES calls the API with model="".
MODEL_FIELDS = {"CLAUDE_MODEL", "CLAUDE_MODEL_SCHEDULES"}

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

    valid_models = _valid_models()
    for model_key in sorted(MODEL_FIELDS):
        model = data.get(model_key, "")
        if model and model not in valid_models:
            errors.append(f"{model_key} must be one of: {', '.join(valid_models)}")

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


def _current_values() -> Dict[str, str]:
    """Raw (unredacted) current .env values, for comparison only."""
    try:
        from dotenv import dotenv_values

        return dict(dotenv_values(str(ENV_PATH))) if ENV_PATH.exists() else {}
    except ImportError:  # pragma: no cover — python-dotenv is a hard dep
        import os

        return {k: os.getenv(k, "") for k in ALLOWED_FIELDS}


def update_settings(data: Dict) -> Tuple[bool, str, bool]:
    """Write validated settings to .env file.

    Args:
        data: Dict of setting key-value pairs to update.

    Returns:
        Tuple of (success, message, restart_required).
        Empty string for sensitive fields means 'leave unchanged'.

    An empty string is NEVER written over an existing non-empty value. That
    write is what turned one Settings visit into a broken run: the page PUTs
    every field on every Save, so a field the form could not represent arrived
    as "" and overwrote a working configuration. Because `os.getenv(key,
    DEFAULT)` does not fall back for a set-but-empty key, the result was not
    "reverted to default" — it was model="" on every floor-plan pass.
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

    existing = _current_values()

    # Refuse LOUDLY when a blank would destroy a configured value. Refusing the
    # whole write rather than skipping the one field is deliberate: this defect
    # was invisible for as long as it was because every layer failed quietly,
    # and an operator who is told "your model selection would have been erased"
    # can fix the form; one who is told nothing cannot.
    destructive = sorted(
        key
        for key, value in data.items()
        if key in ALLOWED_FIELDS
        and key not in SENSITIVE_FIELDS
        and not str(value).strip()
        and str(existing.get(key, "")).strip()
    )
    if destructive:
        return (
            False,
            "Refusing to erase configured value(s): %s. A blank is not a "
            "reset — an empty variable disables the setting rather than "
            "restoring its default. Clear it in .env directly if that is "
            "really what you want." % ", ".join(destructive),
            False,
        )

    restart_required = False
    written_count = 0

    for key, value in data.items():
        if key not in ALLOWED_FIELDS:
            continue
        # Skip empty-string updates for sensitive fields (preserve existing value)
        if key in SENSITIVE_FIELDS and not str(value).strip():
            logger.debug(f"Skipping empty update for sensitive field: {key}")
            continue
        # A blank for a field that is already blank is a no-op, not an error —
        # the form PUTs every field, and refusing here would make Settings
        # unusable on a fresh install where most values are unset.
        if not str(value).strip() and not str(existing.get(key, "")).strip():
            logger.debug(f"Skipping no-op empty update: {key}")
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
