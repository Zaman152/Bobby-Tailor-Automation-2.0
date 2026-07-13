#!/usr/bin/env python3
"""One-time admin credential seeding script for VPS deployment.

Run this script once on the server to generate a bcrypt hash of the admin
password and write it to the .env file. After running, the .env file will
contain ADMIN_EMAIL and ADMIN_PASSWORD_HASH ready for Flask-Login.

Usage:
    python seed_admin.py

The plaintext password is never logged, printed, or persisted — only the
bcrypt hash is written to .env.
"""

from pathlib import Path

from dotenv import set_key
from flask_bcrypt import Bcrypt

ADMIN_EMAIL: str = "admin@bobbytailor.com"
ADMIN_PASSWORD: str = "BobbyTheAdmin@1"
ENV_PATH: Path = Path(__file__).resolve().parent / ".env"

_bcrypt = Bcrypt()

# Generate bcrypt hash at cost factor 12 for strong work factor
_hash: str = _bcrypt.generate_password_hash(ADMIN_PASSWORD, rounds=12).decode("utf-8")

# Immediately remove plaintext password from memory
del ADMIN_PASSWORD

# Create .env if it doesn't already exist
ENV_PATH.touch(exist_ok=True)

# Write credentials to .env (set_key handles quoting and updates in-place)
set_key(str(ENV_PATH), "ADMIN_EMAIL", ADMIN_EMAIL)
set_key(str(ENV_PATH), "ADMIN_PASSWORD_HASH", _hash)

print(f"Admin seeded: {ADMIN_EMAIL}")
