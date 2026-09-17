import os
import subprocess
import sys

import pytest

from forge_backend import build_app_config


def test_production_refuses_missing_secret():
    """A deployment cannot silently sign sessions with a predictable key."""
    with pytest.raises(RuntimeError, match="FORGE_SECRET_KEY"):
        build_app_config({"FORGE_ENV": "production"})


def test_production_startup_fails_without_secret():
    environment = os.environ.copy()
    environment.pop("FORGE_SECRET_KEY", None)
    environment.pop("FORGE_DATABASE_URI", None)
    environment["FORGE_ENV"] = "production"
    environment["PYTHONPATH"] = os.path.dirname(os.path.dirname(__file__))

    result = subprocess.run(
        [sys.executable, "-c", "import forge_backend"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "FORGE_SECRET_KEY" in result.stderr


@pytest.mark.parametrize("secret", ["dev-secret-change-me", "change-me", "secret", "too-short"])
def test_production_refuses_default_or_short_secret(secret):
    with pytest.raises(RuntimeError, match="FORGE_SECRET_KEY"):
        build_app_config({"FORGE_ENV": "production", "FORGE_SECRET_KEY": secret})


def test_local_development_never_uses_predictable_secret():
    config = build_app_config({"FORGE_ENV": "development"})

    assert config["SECRET_KEY"] != "dev-secret-change-me"
    assert len(config["SECRET_KEY"]) >= 32


def test_production_session_cookie_policy_is_secure():
    config = build_app_config({
        "FORGE_ENV": "production",
        "FORGE_SECRET_KEY": "a" * 32,
    })

    assert config["SESSION_COOKIE_SECURE"] is True
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_harness_uses_a_temporary_database(app):
    assert "forge.db" not in app.config["SQLALCHEMY_DATABASE_URI"]
