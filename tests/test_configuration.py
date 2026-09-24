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
    environment.pop("FORGE_DEBUG", None)
    environment.pop("FORGE_DEMO_MODE", None)
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


@pytest.mark.parametrize(
    "secret",
    [
        "dev-secret-change-me",
        "change-me",
        "change-me-to-something-random",
        "secret",
        "too-short",
    ],
)
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


def test_debug_and_demo_mode_default_off():
    config = build_app_config({"FORGE_ENV": "development"})

    assert config["DEBUG"] is False
    assert config["FORGE_DEMO_MODE"] is False


def test_local_development_can_explicitly_enable_debug_and_demo():
    config = build_app_config({
        "FORGE_ENV": "development",
        "FORGE_DEBUG": "1",
        "FORGE_DEMO_MODE": "true",
    })

    assert config["DEBUG"] is True
    assert config["FORGE_DEMO_MODE"] is True


@pytest.mark.parametrize("name", ["FORGE_DEBUG", "FORGE_DEMO_MODE"])
def test_boolean_deployment_flags_reject_ambiguous_values(name):
    with pytest.raises(RuntimeError, match=name):
        build_app_config({
            "FORGE_ENV": "development",
            name: "definitely-maybe",
        })


@pytest.mark.parametrize("name", ["FORGE_DEBUG", "FORGE_DEMO_MODE"])
@pytest.mark.parametrize("environment", ["production", "prod", "staging", "test"])
def test_debug_and_demo_are_rejected_outside_local_development(name, environment):
    values = {
        "FORGE_ENV": environment,
        "FORGE_SECRET_KEY": "a" * 32,
        name: "1",
    }

    with pytest.raises(RuntimeError, match=name):
        build_app_config(values)


@pytest.mark.parametrize("unsafe_name", ["FORGE_DEBUG", "FORGE_DEMO_MODE"])
def test_production_import_fails_for_unsafe_runtime_modes(unsafe_name):
    environment = os.environ.copy()
    environment["FORGE_ENV"] = "production"
    environment["FORGE_SECRET_KEY"] = "a" * 32
    environment["FORGE_DEBUG"] = "0"
    environment["FORGE_DEMO_MODE"] = "0"
    environment[unsafe_name] = "1"
    environment["PYTHONPATH"] = os.path.dirname(os.path.dirname(__file__))

    result = subprocess.run(
        [sys.executable, "-c", "import forge_backend"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert unsafe_name in result.stderr


def test_seed_demo_cli_is_disabled_by_default(app):
    runner = app.test_cli_runner()

    result = runner.invoke(args=["seed-demo"])

    assert result.exit_code != 0
    assert "FORGE_DEMO_MODE" in result.output


def test_seed_demo_cli_runs_only_when_explicitly_enabled(app, monkeypatch):
    monkeypatch.setitem(app.config, "FORGE_DEMO_MODE", True)
    runner = app.test_cli_runner()

    result = runner.invoke(args=["seed-demo"])

    assert result.exit_code == 0
    assert "Seeded." in result.output



@pytest.mark.parametrize("environment", ["", "prodution", "dev", "local", "qa"])
def test_unknown_environment_names_fail_closed(environment):
    with pytest.raises(RuntimeError, match="FORGE_ENV"):
        build_app_config({
            "FORGE_ENV": environment,
            "FORGE_SECRET_KEY": "a" * 32,
        })


def test_staging_uses_deployment_security_policy():
    with pytest.raises(RuntimeError, match="FORGE_SECRET_KEY"):
        build_app_config({"FORGE_ENV": "staging"})

    config = build_app_config({
        "FORGE_ENV": "staging",
        "FORGE_SECRET_KEY": "a" * 32,
    })

    assert config["SESSION_COOKIE_SECURE"] is True
    assert config["DEBUG"] is False
    assert config["FORGE_DEMO_MODE"] is False
