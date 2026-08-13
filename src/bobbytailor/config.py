import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

# Load .env from the repo root (two levels up from src/bobbytailor/).
# Fallback to cwd if project-root .env is missing (e.g. installed non-editable).
_env_path = Path(__file__).resolve().parents[2] / ".env"
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"

# override=False — .env fills GAPS in the environment, it does not outrank it.
#
# With override=True (the old behaviour) a `docker run -e OUTPUT_DIR=...` or a
# systemd `Environment=` line was not merely lower priority, it was ERASED: any
# variable whose name appeared in .env was overwritten, and because load_dotenv
# writes through to os.environ, every later os.getenv in the process saw the
# .env value too. That is unfixable from the outside — the operator sets the
# variable the documented way and the app ignores it, silently.
#
# Consequence to state plainly (see README "Settings vs the process
# environment"): a variable that is ALSO set in the process environment can no
# longer be changed through the Settings page, because the process environment
# now wins after a restart. The supported systemd unit sets only PATH, so this
# affects nothing today.
load_dotenv(dotenv_path=_env_path, override=False)

# StackCT Credentials (set in .env file)
STACKCT_EMAIL = os.getenv("STACKCT_EMAIL", "")
STACKCT_PASSWORD = os.getenv("STACKCT_PASSWORD", "")

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Model options by cost (per 1M tokens input/output):
#   claude-haiku-4-5    → $1 / $5     (fastest, cheapest — good for structured extraction)
#   claude-sonnet-4-6   → $3 / $15    (balanced — better on complex drawings)
#   claude-opus-4-7     → $5 / $25    (most capable — use only if Haiku misses details)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
# Smarter model auto-used for schedule/panel/specification sheets where small
# tabular text matters. Falls back to CLAUDE_MODEL if unset.
CLAUDE_MODEL_SCHEDULES = os.getenv("CLAUDE_MODEL_SCHEDULES", CLAUDE_MODEL)

# Phase 21 model routing (July 2026 line-up — see 21-RESEARCH.md §5).
# All slugs are env-driven; never hardcode model names in routing logic.
#   claude-sonnet-5     → $2 / $10   (workhorse; $3/$15 from 2026-09-01)
#   claude-opus-4-8     → $5 / $25   (high-res vision class — dense tables/legends)
#   claude-fable-5      → $10 / $50  (frontier; escalation only, budget-gated)
#   claude-haiku-4-5    → $1 / $5    (classification, cheap ensemble members)
# Semantic labeling passes on floor/roof/MEP plans (overlay + crop galleries).
CLAUDE_MODEL_SEMANTIC = os.getenv("CLAUDE_MODEL_SEMANTIC", "claude-sonnet-5")
# Dense small-text structuring: legend/schedule passes + verify-retry arbitration.
CLAUDE_MODEL_DENSE = os.getenv("CLAUDE_MODEL_DENSE", "claude-opus-4-8")
# Escalation on repeated ensemble disagreement — only used when ESCALATION_ENABLED.
CLAUDE_MODEL_ESCALATION = os.getenv("CLAUDE_MODEL_ESCALATION", "claude-fable-5")
# Cheap classification passes (sheet-type triage).
CLAUDE_MODEL_CLASSIFY = os.getenv("CLAUDE_MODEL_CLASSIFY", "claude-haiku-4-5")

# Every model slug this process routes a pass through, in one place. Anything
# that needs to know "which models is this run using" reads THIS, so the answer
# cannot drift between the routing table, the Settings UI and the saved report.
MODEL_ENV_VARS = (
    "CLAUDE_MODEL",
    "CLAUDE_MODEL_SCHEDULES",
    "CLAUDE_MODEL_SEMANTIC",
    "CLAUDE_MODEL_DENSE",
    "CLAUDE_MODEL_ESCALATION",
    "CLAUDE_MODEL_CLASSIFY",
)

# ---------------------------------------------------------------------------
# Selectable models for the Settings UI
# ---------------------------------------------------------------------------
#
# This list is the single source of truth for what the Settings page may
# offer, and it is derived here rather than retyped in web/settings.py and
# again in templates/settings.html. Those three copies had already drifted,
# and the drift silently destroyed a run:
#
#   web/settings.py shipped ["claude-haiku-4-5","claude-sonnet-4-6",
#   "claude-opus-4-7"], while .env resolved CLAUDE_MODEL_SCHEDULES to a slug
#   not on that list. The <select> cannot hold a value with no matching
#   <option>, so it read back as "". validate_settings passed it (`if model
#   and model not in VALID_MODELS` — an empty string is falsey), update_settings
#   wrote it, and os.getenv(key, DEFAULT) does NOT fall back for a key that is
#   set-but-empty. One visit to Settings and one Save, and every floor-plan
#   count and measure pass on the next run called the API with model="".
#
# Two rules follow, and both are load-bearing:
#   1. the UI list is GENERATED from here (no third copy to drift), and
#   2. whatever the live environment currently resolves is ALWAYS selectable,
#      even if it is a slug this catalogue has never heard of — so upgrading a
#      model in .env can never again make it unrepresentable in the UI.
_MODEL_CATALOGUE = (
    ("claude-haiku-4-5", "Claude Haiku 4.5 — fastest, cheapest ($1/$5 per 1M tokens)"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6 — balanced ($3/$15 per 1M tokens)"),
    ("claude-sonnet-5", "Claude Sonnet 5 — workhorse ($2/$10 per 1M tokens)"),
    ("claude-opus-4-7", "Claude Opus 4.7 — most capable ($5/$25 per 1M tokens)"),
    ("claude-opus-4-8", "Claude Opus 4.8 — high-res vision ($5/$25 per 1M tokens)"),
    ("claude-fable-5", "Claude Fable 5 — frontier, escalation only ($10/$50 per 1M tokens)"),
)


def model_choices() -> List[Tuple[str, str]]:
    """(slug, label) pairs the Settings UI may offer, live values included.

    Rule 2 above: a slug that is currently configured but absent from the
    catalogue is appended rather than dropped. Dropping it is precisely how a
    working configuration got blanked.
    """
    choices = list(_MODEL_CATALOGUE)
    known = {slug for slug, _ in choices}
    for var in MODEL_ENV_VARS:
        slug = (globals().get(var) or "").strip()
        if slug and slug not in known:
            known.add(slug)
            choices.append((slug, "%s — configured in .env" % slug))
    return choices


MODEL_CHOICES = model_choices()
# Flat allowlist for validators that only need membership.
VALID_MODEL_SLUGS = [slug for slug, _ in MODEL_CHOICES]


def active_models() -> Dict[str, str]:
    """The model slug each routing variable currently resolves to.

    Recorded into every report's ``run_settings`` so "which model produced
    this number" is answerable from the artifact alone — the exact question
    24-RESEARCH Open Question 1 could not answer for the two saved paid runs.
    """
    return {var: globals().get(var, "") for var in MODEL_ENV_VARS}

# Escalation gate: Fable 5 is budget-gated OFF by default (cost abuse guard).
ESCALATION_ENABLED = os.getenv("ESCALATION_ENABLED", "false").lower() in ("1", "true", "yes")

# Whole-sheet render long-edge target in pixels. Claude downscales standard
# vision input to ~1568px long edge — rendering larger wastes tokens without
# adding model-visible detail. Detail zooms use render_clip_crop() instead.
RENDER_TARGET_PX = int(os.getenv("RENDER_TARGET_PX", "1568"))

# Phase 21 ensemble + budget guard (21-11, V3-ACC-03 / V3-PROD-02).
# Hard per-run API spend cap in USD — every ensemble/verify-retry call is
# charged against a BudgetGuard; hitting the cap flags remaining items as
# needs_review ("budget_exhausted") instead of silently truncating results.
API_BUDGET_PER_RUN_USD = float(os.getenv("API_BUDGET_PER_RUN_USD", "10.0"))
# Default ensemble size for residual vision numbers: N=3 samples, escalating
# to N=5 when the first 3 disagree (21-RESEARCH.md §4).
ENSEMBLE_N = int(os.getenv("ENSEMBLE_N", "3"))

# StackCT URLs
STACKCT_BASE_URL = "https://go.stackct.com"
STACKCT_LOGIN_URL = "https://id.stackct.com/u/login/identifier"
STACKCT_PROJECTS_URL = "https://go.stackct.com/app/#/Projects"

# Browser settings
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
PAGE_LOAD_TIMEOUT = 30000   # ms
DRAWING_LOAD_TIMEOUT = 20000  # ms - drawings can be slow to render
SCREENSHOT_DELAY = 3000       # ms - wait after navigation before screenshot
CANVAS_STABILITY_TIMEOUT = int(os.getenv("CANVAS_STABILITY_TIMEOUT", "15"))  # seconds
CANVAS_STABILITY_CHECKS = int(os.getenv("CANVAS_STABILITY_CHECKS", "2"))  # consecutive matches

# Output
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")

# StackCT catalog database (no secrets — credentials stay in .env)
STACKCT_DB_PATH = Path(OUTPUT_DIR) / "stackct.db"
STACKCT_CACHE_TTL_HOURS = int(os.getenv("STACKCT_CACHE_TTL_HOURS", "24"))

# Job history retention (Phase 19) — 0 disables pruning
JOB_HISTORY_RETENTION_DAYS: int = int(os.environ.get("JOB_HISTORY_RETENTION_DAYS", "90"))

# Preview settings
MAX_PREVIEW_ROWS = int(os.getenv("MAX_PREVIEW_ROWS", "500"))  # Cap for CSV preview

# Upload hardening (21-REVIEW WR-04): request body size cap for PDF/manifest
# uploads — Flask MAX_CONTENT_LENGTH is derived from this in create_app so a
# multi-GB POST is rejected with 413 before it is read to disk/memory.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))

# Screenshot reuse: skip blob download when a matching file already exists on disk
REUSE_SCREENSHOTS = os.getenv("REUSE_SCREENSHOTS", "true").lower() in ("1", "true", "yes")

# Linked sheet auto-follow (Phase 18)
# When true, sheets referenced via cross-references are automatically captured
# and analyzed to resolve target_sheet_not_found entries.
AUTO_INCLUDE_LINKED_SHEETS = os.getenv(
    "AUTO_INCLUDE_LINKED_SHEETS", "true"
).lower() in ("1", "true", "yes")

# Maximum linked sheets to add per run (cost/time guard)
MAX_LINKED_SHEETS = int(os.getenv("MAX_LINKED_SHEETS", "10"))

# Maximum recursive link-follow depth (v1: 1 = no recursion)
MAX_LINKED_DEPTH = int(os.getenv("MAX_LINKED_DEPTH", "1"))

# Schedule (cron expression)
RUN_SCHEDULE = os.getenv("RUN_SCHEDULE", "0 8 * * *")  # daily at 8am

# Application Authentication (Phase 12)
SECRET_KEY = os.getenv("SECRET_KEY", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

# ---------------------------------------------------------------------------
# Environment validation — scoped to the surface that actually needs a value
# ---------------------------------------------------------------------------
#
# This used to be one flat list validated AT IMPORT TIME, which made every one
# of these variables a precondition for `import bobbytailor.config` — and
# config is imported by essentially the whole package. The product we ship is
# plans-only: StackCT is not part of it. So a plans-only operator had to invent
# two fake StackCT passwords before the package would import at all, including
# for a pure offline deterministic run that makes zero API calls, and the
# failure arrived as an unexplained container-start crash. The blast radius was
# already visible in the codebase as "config stubbed (tests)" guards written to
# survive that import.
#
# The rule now: a variable is required by the SURFACE that reads it, checked
# when that surface starts, not by the act of importing a constants module.

# The web app cannot serve a single authenticated request without these:
# SECRET_KEY signs the session, and the admin pair IS the only account.
WEB_REQUIRED_ENV_VARS = [
    "SECRET_KEY",
    "ADMIN_EMAIL",
    "ADMIN_PASSWORD_HASH",
]

# Only the scrape/ surface logs into StackCT. Checked at login, not at import.
SCRAPE_REQUIRED_ENV_VARS = [
    "STACKCT_EMAIL",
    "STACKCT_PASSWORD",
]

# Checked at the first vision call. Deliberately NOT a hard precondition for
# booting the web app: the deterministic offline path is a legitimate way to
# run this product, and refusing to start would take it away.
VISION_REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
]

# Retained as the union for callers that genuinely want every surface at once
# (e.g. a pre-flight check on a box that will both scrape and analyze).
REQUIRED_ENV_VARS = (
    SCRAPE_REQUIRED_ENV_VARS + VISION_REQUIRED_ENV_VARS + WEB_REQUIRED_ENV_VARS
)


def missing_env(required: Optional[Sequence[str]] = None) -> List[str]:
    """Names from *required* that are unset or empty. Never raises."""
    names = REQUIRED_ENV_VARS if required is None else required
    return [var for var in names if not os.getenv(var)]


def validate_required_env(required: Optional[Sequence[str]] = None) -> None:
    """Raise unless every variable in *required* is set to a non-empty value.

    Args:
        required: The scoped list for the surface being started — one of
            WEB_REQUIRED_ENV_VARS / SCRAPE_REQUIRED_ENV_VARS /
            VISION_REQUIRED_ENV_VARS. Defaults to the union of all three,
            which is almost never what a single surface wants.

    Raises:
        ValueError: naming exactly the missing variables.
    """
    missing_vars = missing_env(required)
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            f"Please set them in .env file at project root."
        )
