"""Isolated Flask test harness for Forge.

The production module currently owns its Flask application, so test collection
sets its configuration before importing it. Each test receives a new temporary
SQLite database and all tables are dropped afterwards.
"""
import os
import shutil
import sys
import tempfile

import pytest


_test_database = tempfile.NamedTemporaryFile(
    suffix=".db", dir=os.path.dirname(__file__), delete=False
)
_test_database.close()
_test_profile_images = tempfile.mkdtemp(
    prefix="forge-profile-images-", dir=os.path.dirname(__file__)
)
os.environ["FORGE_SECRET_KEY"] = "test-secret-key-with-at-least-thirty-two-characters"
os.environ["FORGE_DATABASE_URI"] = f"sqlite:///{_test_database.name}"
os.environ["FORGE_ENV"] = "test"
os.environ["FORGE_PROFILE_IMAGE_DIR"] = _test_profile_images
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import forge_backend  # noqa: E402  (environment must be configured first)


@pytest.fixture(autouse=True)
def isolated_database():
    """Create only the schema needed by a test and remove its data after it."""
    with forge_backend.app.app_context():
        forge_backend.db.drop_all()
        forge_backend.db.create_all()
        forge_backend._failed_logins.clear()
        yield
        forge_backend.db.session.remove()
        forge_backend.db.drop_all()


@pytest.fixture()
def app():
    forge_backend.app.config.update(TESTING=True)
    return forge_backend.app


@pytest.fixture()
def client(app):
    return app.test_client()


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_test_database.name)
    except FileNotFoundError:
        pass
    shutil.rmtree(_test_profile_images, ignore_errors=True)
