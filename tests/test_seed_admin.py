"""seed_admin must never contain or persist a plaintext credential (CR-01).

Regression tests for the 21-REVIEW CR-01 fix: the admin seeding script reads
the password from ADMIN_SEED_PASSWORD (or generates one with --generate),
fails loudly when absent, and writes only the bcrypt hash to .env.
"""
from pathlib import Path

from bobbytailor.web import seed_admin


def test_import_has_no_side_effects_and_no_module_level_password():
    # The old script seeded .env at IMPORT time from a hardcoded literal.
    assert not hasattr(seed_admin, "ADMIN_PASSWORD")
    assert callable(seed_admin.main)


def test_source_contains_no_plaintext_password():
    src = Path(seed_admin.__file__.replace(".pyc", ".py")).read_text()
    assert "BobbyTheAdmin" not in src


def test_missing_password_fails_loudly(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ADMIN_SEED_PASSWORD", raising=False)
    monkeypatch.setattr(seed_admin, "ENV_PATH", tmp_path / ".env")
    rc = seed_admin.main([])
    assert rc == 2
    assert not (tmp_path / ".env").exists()
    assert "ADMIN_SEED_PASSWORD" in capsys.readouterr().err


def test_short_password_rejected(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ADMIN_SEED_PASSWORD", "short")
    monkeypatch.setattr(seed_admin, "ENV_PATH", tmp_path / ".env")
    rc = seed_admin.main([])
    assert rc == 2
    assert not (tmp_path / ".env").exists()
    assert "at least" in capsys.readouterr().err


def test_env_password_seeds_hash_not_plaintext(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    monkeypatch.setenv("ADMIN_SEED_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("ADMIN_SEED_EMAIL", "ops@example.com")
    monkeypatch.setattr(seed_admin, "ENV_PATH", env_file)
    rc = seed_admin.main([])
    assert rc == 0
    content = env_file.read_text()
    assert "ops@example.com" in content
    assert "ADMIN_PASSWORD_HASH" in content
    # Only the bcrypt hash is persisted — never the plaintext.
    assert "correct horse battery staple" not in content
    assert "$2b$12$" in content


def test_generate_prints_password_once_and_stores_only_hash(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.delenv("ADMIN_SEED_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_SEED_EMAIL", raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr(seed_admin, "ENV_PATH", env_file)
    rc = seed_admin.main(["--generate"])
    assert rc == 0
    out_lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
    generated = out_lines[-1]
    assert len(generated) >= seed_admin.MIN_PASSWORD_LEN
    content = env_file.read_text()
    assert generated not in content  # only the hash lands in .env
    assert "ADMIN_PASSWORD_HASH" in content
