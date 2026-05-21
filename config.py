import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the same directory as this file
_env_path = Path("/Users/macbook/Desktop/Bobby Tailor/.env")
load_dotenv(dotenv_path=_env_path, override=True)

# StackCT Credentials (set in .env file)
STACKCT_EMAIL = os.getenv("STACKCT_EMAIL", "muhammad@klouded.com")
STACKCT_PASSWORD = os.getenv("STACKCT_PASSWORD", "")

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-opus-4-7"  # Best vision model for drawing analysis

# StackCT URLs
STACKCT_BASE_URL = "https://go.stackct.com"
STACKCT_LOGIN_URL = "https://id.stackct.com/u/login/identifier"
STACKCT_PROJECTS_URL = "https://go.stackct.com/app/#/Projects"

# Browser settings
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
PAGE_LOAD_TIMEOUT = 30000   # ms
DRAWING_LOAD_TIMEOUT = 20000  # ms - drawings can be slow to render
SCREENSHOT_DELAY = 3000       # ms - wait after navigation before screenshot

# Output
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")

# Schedule (cron expression)
RUN_SCHEDULE = os.getenv("RUN_SCHEDULE", "0 8 * * *")  # daily at 8am
