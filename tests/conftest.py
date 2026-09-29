"""Isolated Flask test harness for Forge.

The production module currently owns its Flask application, so test collection
sets its configuration before importing it. Each test receives a new temporary
SQLite database initialized by the committed migrations, never ORM metadata.
"""
import atexit
import itertools
import os
import shutil
import sys
import tempfile

import pytest


_test_database_dir = tempfile.mkdtemp(prefix="forge-db-", dir=os.path.dirname(__file__))
_test_database_path = os.path.join(_test_database_dir, "test.db")
_test_database_counter = itertools.count(1)
atexit.register(shutil.rmtree, _test_database_dir, ignore_errors=True)
_test_profile_images = tempfile.mkdtemp(
    prefix="forge-profile-images-", dir=os.path.dirname(__file__)
)
_test_uploads = tempfile.mkdtemp(
    prefix="forge-uploads-", dir=os.path.dirname(__file__)
)
os.environ["FORGE_SECRET_KEY"] = "test-secret-key-with-at-least-thirty-two-characters"
os.environ["FORGE_DATABASE_URI"] = f"sqlite:///{_test_database_path}"
os.environ["FORGE_ENV"] = "test"
os.environ["FORGE_PROFILE_IMAGE_DIR"] = _test_profile_images
os.environ["FORGE_UPLOAD_DIR"] = _test_uploads
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from forge_migrations import initialize_fresh_database


def reset_test_database(path):
    # Every invocation owns a new path, so a late old connection cannot
    # attach a prior test's WAL to the next test's database.
    engine = create_engine(f"sqlite:///{path}")
    try:
        initialize_fresh_database(engine)
    finally:
        engine.dispose()


reset_test_database(_test_database_path)
import forge_backend  # noqa: E402  (environment must be configured first)


@pytest.fixture(autouse=True)
def isolated_database():
    """Create isolated database state and upload storage for every test."""
    shutil.rmtree(_test_uploads, ignore_errors=True)
    os.makedirs(_test_uploads, exist_ok=True)

    with forge_backend.app.app_context():
        forge_backend.db.session.remove()
        forge_backend.db.engine.dispose()
        path = os.path.join(_test_database_dir, f"test-{next(_test_database_counter)}.db")
        reset_test_database(path)
        engine = create_engine(f"sqlite:///{path}")
        from sqlalchemy import event
        event.listen(engine, "connect", forge_backend._set_sqlite_pragma)
        forge_backend.db._app_engines[forge_backend.app][None] = engine
        forge_backend.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
        os.environ["FORGE_DATABASE_URI"] = f"sqlite:///{path}"
        forge_backend._failed_logins.clear()
        yield
        forge_backend.db.session.remove()
        forge_backend.db.engine.dispose()

    shutil.rmtree(_test_uploads, ignore_errors=True)
    os.makedirs(_test_uploads, exist_ok=True)


@pytest.fixture()
def app():
    forge_backend.app.config.update(TESTING=True)
    return forge_backend.app


@pytest.fixture()
def client(app):
    return app.test_client()


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_test_database_path)
    except FileNotFoundError:
        pass
    shutil.rmtree(_test_database_dir, ignore_errors=True)
    shutil.rmtree(_test_profile_images, ignore_errors=True)
    shutil.rmtree(_test_uploads, ignore_errors=True)
