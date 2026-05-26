import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the same directory as this file
# Fallback to cwd if project-root .env is missing
_env_path = Path(__file__).resolve().parent / ".env"
if not _env_path.exists():
    _env_path = Path.cwd() / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

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

# Preview settings
MAX_PREVIEW_ROWS = int(os.getenv("MAX_PREVIEW_ROWS", "500"))  # Cap for CSV preview

# Schedule (cron expression)
RUN_SCHEDULE = os.getenv("RUN_SCHEDULE", "0 8 * * *")  # daily at 8am

# Environment validation
REQUIRED_ENV_VARS = ["STACKCT_EMAIL", "STACKCT_PASSWORD", "ANTHROPIC_API_KEY"]

def validate_required_env() -> None:
    """Validate that all required environment variables are set.
    
    Raises:
        ValueError: If any required environment variable is missing or empty.
    """
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            f"Please set them in .env file at project root."
        )

# Validate on import
validate_required_env()
