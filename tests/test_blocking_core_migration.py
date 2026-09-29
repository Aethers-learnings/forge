"""Focused T-107 blocking migration coverage."""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect

import forge_migrations
from migrations import r20260929_03_blocking_core as blocking


def test_blocking_revision_is_current_head(tmp_path):
    database = tmp_path / "blocking-head.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        forge_migrations.initialize_fresh_database(engine)
        status = forge_migrations.migration_status(engine)
        assert status["headRevision"] == blocking.REVISION
        assert status["pendingRevisions"] == []
        assert set(blocking.BLOCK_TABLES) <= set(inspect(engine).get_table_names())
        result = forge_migrations.verify_database(engine)
        assert result["revision"] == blocking.REVISION
        assert result["integrity"] == "ok"
    finally:
        engine.dispose()


def test_blocking_database_constraints(tmp_path):
    database = tmp_path / "blocking-constraints.db"
    engine = create_engine(f"sqlite:///{database}")
    forge_migrations.initialize_fresh_database(engine)
    engine.dispose()
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        for user_id in (101, 102, 103):
            connection.execute(
                "INSERT INTO user (id,username,password_hash,role,name) "
                "VALUES (?,?, 'hash','trade','User')",
                (user_id, f"user-{user_id}"))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO user_block (blocker_id,blocked_id,active,version,created_at,updated_at) "
                "VALUES (101,101,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.execute(
            "INSERT INTO user_block (id,blocker_id,blocked_id,active,version,created_at,updated_at) "
            "VALUES (1,101,102,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.execute(
            "INSERT INTO user_block (id,blocker_id,blocked_id,active,version,created_at,updated_at) "
            "VALUES (2,102,101,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO user_block (blocker_id,blocked_id,active,version,created_at,updated_at) "
                "VALUES (101,102,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        connection.execute(
            "INSERT INTO block_event (user_block_id,actor_user_id,block_version,event_type,previous_state,next_state,created_at) "
            "VALUES (1,101,1,'blocked','unblocked','blocked',CURRENT_TIMESTAMP)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO block_event (user_block_id,actor_user_id,block_version,event_type,previous_state,next_state,created_at) "
                "VALUES (1,101,1,'blocked','unblocked','blocked',CURRENT_TIMESTAMP)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM user WHERE id=101")
    finally:
        connection.close()
