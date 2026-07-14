#!/usr/bin/env python3
"""One-time admin credential seeding script for VPS deployment.

Generates a bcrypt hash of the admin password and writes ADMIN_EMAIL /
ADMIN_PASSWORD_HASH to the repo-root .env file, ready for Flask-Login.

The plaintext password is NEVER stored in source control (CR-01). Provide
it at seeding time via the ``ADMIN_SEED_PASSWORD`` environment variable, or
pass ``--generate`` to create a strong random password that is printed ONCE
to stdout (store it in a password manager immediately).

Usage:
    ADMIN_SEED_PASSWORD='<strong password>' python -m bobbytailor.web.seed_admin
    python -m bobbytailor.web.seed_admin --generate

Optional: ``ADMIN_SEED_EMAIL`` overrides the default admin email.
Only the bcrypt hash is written to .env — the plaintext password is never
logged or persisted by this script.
"""
import os
import secrets
import sys
from pathlib import Path

from dotenv import set_key
from flask_bcrypt import Bcrypt

DEFAULT_ADMIN_EMAIL = "admin@bobbytailor.com"
MIN_PASSWORD_LEN = 12
# Repo root is three levels up from src/bobbytailor/web/.
ENV_PATH: Path = Path(__file__).resolve().parents[3] / ".env"

_MISSING_PASSWORD_HELP = """\
ERROR: no admin password provided — nothing was seeded.

Provide the password via an environment variable (it is never stored in
source control):

    ADMIN_SEED_PASSWORD='<strong password>' python -m bobbytailor.web.seed_admin

or let the script generate a strong random password and print it once:

    python -m bobbytailor.web.seed_admin --generate
"""


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    generate = "--generate" in args

    admin_email = os.environ.get("ADMIN_SEED_EMAIL", "").strip() or DEFAULT_ADMIN_EMAIL

    password = os.environ.get("ADMIN_SEED_PASSWORD", "")
    generated = False
    if not password and generate:
        password = secrets.token_urlsafe(18)
        generated = True
    if not password:
        sys.stderr.write(_MISSING_PASSWORD_HELP)
        return 2
    if len(password) < MIN_PASSWORD_LEN:
        sys.stderr.write(
            "ERROR: ADMIN_SEED_PASSWORD must be at least %d characters — "
            "nothing was seeded.\n" % MIN_PASSWORD_LEN
        )
        return 2

    # Generate bcrypt hash at cost factor 12 for strong work factor.
    password_hash = Bcrypt().generate_password_hash(password, rounds=12).decode("utf-8")

    # Create .env if it doesn't already exist.
    ENV_PATH.touch(exist_ok=True)

    # Write credentials to .env (set_key handles quoting and updates in-place).
    set_key(str(ENV_PATH), "ADMIN_EMAIL", admin_email)
    set_key(str(ENV_PATH), "ADMIN_PASSWORD_HASH", password_hash)

    print(f"Admin seeded: {admin_email}")
    if generated:
        # Printed exactly once, only for --generate: the operator must store
        # it now — it is not persisted anywhere (only the hash reaches .env).
        print("Generated admin password (store it NOW — it is shown only once):")
        print(password)

    # Immediately drop the plaintext reference.
    del password
    return 0


if __name__ == "__main__":
    sys.exit(main())
