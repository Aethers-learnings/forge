"""Regression coverage for T-201 migration tooling."""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

import forge_migrations
from forge_migrations import (
    BASELINE_REVISION,
    HEAD_REVISION,
    LEDGER_TABLE,
    MigrationError,
    assert_schema_matches_baseline,
    backup_sqlite,
    downgrade_database,
    initialize_baseline,
    migration_status,
    upgrade_database,
    verify_database,
)
from migrations import (
    r20260928_02_owned_social_schema as owned_social,
    r20260929_03_blocking_core as blocking,
)


def current_schema_engine(
    tmp_path,
    name="forge-current.db",
):
    database = tmp_path / name
    engine = create_engine(f"sqlite:///{database}")
    with forge_migrations._sqlite_write_transaction(engine) as connection:
        forge_migrations._create_frozen_baseline(connection)
    return engine, database


def test_committed_baseline_materializes_without_application_metadata(
    tmp_path,
):
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


def test_baseline_is_explicit_checksum_valid_and_idempotent(
    tmp_path,
):
    engine, _ = current_schema_engine(tmp_path)

    before = migration_status(engine)
    assert before["managed"] is False

    assert initialize_baseline(engine) is True
    assert initialize_baseline(engine) is False

    status = migration_status(engine)

    assert status["managed"] is True
    assert status["baselineChecksumOk"] is True
    assert status["headRevision"] == BASELINE_REVISION
    assert status["pendingRevisions"] == [
        owned_social.REVISION,
        blocking.REVISION,
    ]

    assert [
        row["revision"]
        for row in status["applied"]
    ] == [BASELINE_REVISION]

    assert_schema_matches_baseline(engine)


def test_baseline_refuses_schema_drift(tmp_path):
    engine, _ = current_schema_engine(tmp_path)

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE user "
                "ADD COLUMN unexpected_t201_column TEXT"
            )
        )

    with pytest.raises(
        MigrationError,
        match="table differs from baseline: user",
    ):
        initialize_baseline(engine)

    assert not inspect(engine).has_table(LEDGER_TABLE)


def test_backup_and_verification_are_non_destructive(tmp_path):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)

    with engine.connect() as connection:
        fk_before = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

    result = verify_database(engine)

    assert result["integrity"] == "ok"
    assert result["foreignKeyViolations"] == []
    assert result["foreignKeysEnabled"] == bool(
        fk_before
    )
    assert result["revision"] == BASELINE_REVISION

    with engine.connect() as connection:
        fk_after = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

    assert fk_after == fk_before

    backup = tmp_path / "backup" / "forge.db"

    assert backup_sqlite(
        engine,
        backup,
    ) == backup.resolve()

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

    with pytest.raises(
        MigrationError,
        match="Refusing to overwrite",
    ):
        backup_sqlite(engine, backup)


def test_upgrade_requires_explicit_baseline(tmp_path):
    engine, _ = current_schema_engine(tmp_path)

    with pytest.raises(
        MigrationError,
        match="not baselined",
    ):
        upgrade_database(engine)


def test_owned_social_upgrade_and_downgrade_round_trip(
    tmp_path,
):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)

    with engine.connect() as connection:
        fk_before = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

    applied = upgrade_database(engine)

    assert applied == [owned_social.REVISION, blocking.REVISION]

    status = migration_status(engine)

    assert status["headRevision"] == HEAD_REVISION
    assert status["pendingRevisions"] == []
    assert status["schemaMatchesHead"] is True

    inspector = inspect(engine)

    for table_name in owned_social.OWNED_SOCIAL_TABLES:
        assert inspector.has_table(table_name)

    for table_name in blocking.BLOCK_TABLES:
        assert inspector.has_table(table_name)

    # Legacy/shared social tables remain physically untouched
    # during this additive revision.
    for legacy_table in (
        "network_request",
        "suggested",
        "connection_npc",
        "conversation",
        "message",
    ):
        assert inspector.has_table(legacy_table)

    verified = verify_database(engine)

    assert verified["revision"] == blocking.REVISION
    assert verified["integrity"] == "ok"
    assert verified["foreignKeyViolations"] == []

    with engine.connect() as connection:
        fk_after_upgrade = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

    assert fk_after_upgrade == fk_before

    removed = downgrade_database(
        engine,
        BASELINE_REVISION,
    )

    assert removed == [blocking.REVISION, owned_social.REVISION]

    status = migration_status(engine)
    assert status["headRevision"] == BASELINE_REVISION
    assert status["schemaMatchesHead"] is True

    assert_schema_matches_baseline(engine)

    inspector = inspect(engine)

    for table_name in owned_social.OWNED_SOCIAL_TABLES:
        assert not inspector.has_table(table_name)

    for table_name in blocking.BLOCK_TABLES:
        assert not inspector.has_table(table_name)

    with engine.connect() as connection:
        fk_after_downgrade = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

    assert fk_after_downgrade == fk_before


def test_owned_social_constraints_with_fk_enforcement(
    tmp_path,
):
    engine, database = current_schema_engine(tmp_path)
    initialize_baseline(engine)
    upgrade_database(engine)
    engine.dispose()

    connection = sqlite3.connect(
        database,
        isolation_level=None,
    )

    try:
        connection.execute("PRAGMA foreign_keys=ON")

        assert connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone() == (1,)

        for user_id, username in (
            (101, "owned_a"),
            (102, "owned_b"),
            (103, "owned_c"),
        ):
            connection.execute(
                """
                INSERT INTO user (
                    id,
                    username,
                    password_hash,
                    role,
                    name
                )
                VALUES (?, ?, 'hash', 'trade', ?)
                """,
                (
                    user_id,
                    username,
                    username,
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO network_edge (
                    id,
                    user_low_id,
                    user_high_id,
                    requester_id,
                    recipient_id,
                    state,
                    version,
                    created_at,
                    requested_at,
                    updated_at,
                    changed_by_user_id
                )
                VALUES (
                    1,
                    102,
                    101,
                    102,
                    101,
                    'pending',
                    1,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    102
                )
                """
            )

        connection.execute(
            """
            INSERT INTO network_edge (
                id,
                user_low_id,
                user_high_id,
                requester_id,
                recipient_id,
                state,
                version,
                created_at,
                requested_at,
                updated_at,
                accepted_at,
                changed_by_user_id
            )
            VALUES (
                1,
                101,
                102,
                101,
                102,
                'accepted',
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                102
            )
            """
        )

        connection.execute(
            """
            INSERT INTO direct_conversation (
                id,
                public_id,
                user_low_id,
                user_high_id,
                created_by_user_id,
                created_at,
                updated_at,
                last_seq
            )
            VALUES (
                1,
                'conversation-public-id',
                101,
                102,
                101,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                0
            )
            """
        )

        connection.execute(
            """
            INSERT INTO conversation_member (
                conversation_id,
                user_id,
                joined_at,
                last_read_seq
            )
            VALUES (
                1,
                101,
                CURRENT_TIMESTAMP,
                0
            )
            """
        )

        connection.execute(
            """
            INSERT INTO conversation_member (
                conversation_id,
                user_id,
                joined_at,
                last_read_seq
            )
            VALUES (
                1,
                102,
                CURRENT_TIMESTAMP,
                0
            )
            """
        )

        with pytest.raises(
            sqlite3.IntegrityError,
            match="conversation member",
        ):
            connection.execute(
                """
                INSERT INTO conversation_member (
                    conversation_id,
                    user_id,
                    joined_at,
                    last_read_seq
                )
                VALUES (
                    1,
                    103,
                    CURRENT_TIMESTAMP,
                    0
                )
                """
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO direct_message (
                    conversation_id,
                    seq,
                    sender_id,
                    client_message_id,
                    text,
                    created_at
                )
                VALUES (
                    1,
                    1,
                    103,
                    'foreign-sender',
                    'forged',
                    CURRENT_TIMESTAMP
                )
                """
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO direct_message (
                    conversation_id,
                    seq,
                    sender_id,
                    client_message_id,
                    text,
                    created_at
                )
                VALUES (
                    1,
                    1,
                    101,
                    'too-long',
                    ?,
                    CURRENT_TIMESTAMP
                )
                """,
                ("x" * 4001,),
            )

        connection.execute(
            """
            INSERT INTO direct_message (
                conversation_id,
                seq,
                sender_id,
                client_message_id,
                text,
                created_at
            )
            VALUES (
                1,
                1,
                101,
                'valid-message-id',
                'hello',
                CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            UPDATE direct_conversation
            SET last_seq = 1
            WHERE id = 1
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO ownership_event (
                    network_edge_id,
                    conversation_id,
                    actor_user_id,
                    entity_version,
                    event_type,
                    created_at
                )
                VALUES (
                    1,
                    1,
                    101,
                    1,
                    'invalid-two-targets',
                    CURRENT_TIMESTAMP
                )
                """
            )

        unique_message_indexes = set()

        for row in connection.execute(
            "PRAGMA index_list('direct_message')"
        ).fetchall():
            if not row[2]:
                continue

            index_name = row[1]
            columns = tuple(
                info[2]
                for info in connection.execute(
                    f'PRAGMA index_info("{index_name}")'
                ).fetchall()
            )
            unique_message_indexes.add(columns)

        assert (
            "conversation_id",
            "sender_id",
            "client_message_id",
        ) in unique_message_indexes

        assert connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

    finally:
        connection.close()


def test_downgrade_refuses_owned_social_data(tmp_path):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)
    upgrade_database(engine)

    with engine.begin() as connection:
        connection.execute(text(
            """
            INSERT INTO user (
                id,
                username,
                password_hash,
                role,
                name
            )
            VALUES (
                201,
                'downgrade_a',
                'hash',
                'trade',
                'A'
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO user (
                id,
                username,
                password_hash,
                role,
                name
            )
            VALUES (
                202,
                'downgrade_b',
                'hash',
                'trade',
                'B'
            )
            """
        ))
        connection.execute(text(
            """
            INSERT INTO network_edge (
                id,
                user_low_id,
                user_high_id,
                requester_id,
                recipient_id,
                state,
                version,
                created_at,
                requested_at,
                updated_at,
                changed_by_user_id
            )
            VALUES (
                1,
                201,
                202,
                201,
                202,
                'pending',
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                201
            )
            """
        ))

    with pytest.raises(
        MigrationError,
        match="Refusing to downgrade",
    ):
        downgrade_database(
            engine,
            BASELINE_REVISION,
        )

    status = migration_status(engine)

    assert status["headRevision"] == owned_social.REVISION
    assert inspect(engine).has_table("network_edge")


def test_revision_checksum_tamper_fails_closed(tmp_path):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)
    upgrade_database(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                UPDATE {LEDGER_TABLE}
                SET checksum = 'tampered'
                WHERE revision = :revision
                """
            ),
            {"revision": owned_social.REVISION},
        )

    with pytest.raises(
        MigrationError,
        match="checksum mismatch",
    ):
        migration_status(engine)

def test_failed_baseline_rolls_back_ledger_ddl(
    tmp_path,
    monkeypatch,
):
    engine, _ = current_schema_engine(tmp_path)

    class ExplodingDateTime:
        @classmethod
        def now(cls, timezone_value):
            raise RuntimeError("injected baseline failure")

    monkeypatch.setattr(
        forge_migrations,
        "datetime",
        ExplodingDateTime,
    )

    with pytest.raises(
        RuntimeError,
        match="injected baseline failure",
    ):
        initialize_baseline(engine)

    assert not inspect(engine).has_table(LEDGER_TABLE)
    assert_schema_matches_baseline(engine)


def test_failed_upgrade_rolls_back_ddl_atomically(
    tmp_path,
    monkeypatch,
):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)

    def failing_upgrade(connection):
        connection.exec_driver_sql(
            """
            CREATE TABLE t201_atomic_upgrade_probe (
                id INTEGER PRIMARY KEY
            )
            """
        )
        raise RuntimeError("injected upgrade failure")

    monkeypatch.setattr(
        owned_social,
        "upgrade",
        failing_upgrade,
    )

    with pytest.raises(
        RuntimeError,
        match="injected upgrade failure",
    ):
        upgrade_database(engine)

    assert not inspect(engine).has_table(
        "t201_atomic_upgrade_probe"
    )

    assert_schema_matches_baseline(engine)

    status = migration_status(engine)
    assert status["headRevision"] == BASELINE_REVISION
    assert status["schemaMatchesHead"] is True


def test_failed_downgrade_rolls_back_ddl_atomically(
    tmp_path,
    monkeypatch,
):
    engine, _ = current_schema_engine(tmp_path)
    initialize_baseline(engine)
    upgrade_database(engine)

    def failing_downgrade(connection):
        connection.exec_driver_sql(
            "DROP TABLE ownership_event"
        )
        raise RuntimeError("injected downgrade failure")

    monkeypatch.setattr(
        owned_social,
        "downgrade",
        failing_downgrade,
    )

    with pytest.raises(
        RuntimeError,
        match="injected downgrade failure",
    ):
        downgrade_database(
            engine,
            BASELINE_REVISION,
        )

    assert inspect(engine).has_table("ownership_event")

    status = migration_status(engine)
    assert status["headRevision"] == owned_social.REVISION
    assert status["schemaMatchesHead"] is True

    verified = verify_database(engine)
    assert verified["revision"] == owned_social.REVISION
    assert verified["integrity"] == "ok"

