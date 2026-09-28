"""Regression coverage for the first T-201 migration-tooling increment."""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

import forge_backend
from forge_migrations import (
    BASELINE_REVISION,
    LEDGER_TABLE,
    MigrationError,
    assert_schema_matches_baseline,
    backup_sqlite,
    initialize_baseline,
    migration_status,
    verify_database,
)


def current_schema_engine(tmp_path, name="forge-current.db"):
    database = tmp_path / name
    engine = create_engine(f"sqlite:///{database}")
    forge_backend.db.metadata.create_all(engine)
    return engine, database


def test_committed_baseline_matches_current_sqlalchemy_schema(tmp_path):
    engine, _ = current_schema_engine(tmp_path)

    snapshot = assert_schema_matches_baseline(engine)

    assert len(snapshot["tables"]) == 23
    assert "user" in snapshot["tables"]
    assert "conversation" in snapshot["tables"]
    assert LEDGER_TABLE not in snapshot["tables"]


def test_status_does_not_create_a_missing_database(tmp_path):
    database = tmp_path / "does-not-exist.db"
    engine = create_engine(f"sqlite:///{database}")

    status = migration_status(engine)

    assert status["exists"] is False
    assert status["managed"] is False
    assert status["applied"] == []
    assert not database.exists()


def test_baseline_is_explicit_checksum_valid_and_idempotent(tmp_path):
    engine, _ = current_schema_engine(tmp_path)

    before = migration_status(engine)
    assert before["managed"] is False

    assert initialize_baseline(engine) is True
    assert initialize_baseline(engine) is False

    status = migration_status(engine)
    assert status["managed"] is True
    assert status["baselineChecksumOk"] is True
    assert [row["revision"] for row in status["applied"]] == [
        BASELINE_REVISION
    ]

    # The migration ledger itself must not make the application schema
    # appear different from the frozen pre-migration baseline.
    assert_schema_matches_baseline(engine)


def test_baseline_refuses_schema_drift(tmp_path):
    engine, _ = current_schema_engine(tmp_path)

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE user ADD COLUMN unexpected_t201_column TEXT")
        )

    with pytest.raises(MigrationError, match="table differs from baseline: user"):
        initialize_baseline(engine)

    assert not inspect(engine).has_table(LEDGER_TABLE)


def test_backup_and_verification_are_non_destructive(tmp_path):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)

    with engine.connect() as connection:
        fk_before = int(
            connection.exec_driver_sql("PRAGMA foreign_keys").scalar() or 0
        )

    result = verify_database(engine)

    assert result["integrity"] == "ok"
    assert result["foreignKeyViolations"] == []
    assert result["foreignKeysEnabled"] == bool(fk_before)

    with engine.connect() as connection:
        fk_after = int(
            connection.exec_driver_sql("PRAGMA foreign_keys").scalar() or 0
        )
    assert fk_after == fk_before

    backup = tmp_path / "backup" / "forge.db"
    assert backup_sqlite(engine, backup) == backup.resolve()

    with sqlite3.connect(backup) as connection:
        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone() == ("ok",)
        assert connection.execute(
            f"SELECT COUNT(*) FROM {LEDGER_TABLE}"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='user'"
        ).fetchone() == (1,)

    with pytest.raises(MigrationError, match="Refusing to overwrite"):
        backup_sqlite(engine, backup)
