"""Physical migration-HEAD experiments; never change application FK policy."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError

import forge_backend as forge
from forge_integrity import foreign_key_inventory, foreign_key_violations
from forge_migrations import (HEAD_REVISION, MigrationError, initialize_fresh_database,
                              verify_application_database, verify_database, schema_snapshot,
                              BASELINE_REVISION, downgrade_database, upgrade_database,
                              backup_sqlite)
from fk_review_fixtures import populate, snapshot


def physical_inventory():
    engine = create_engine("sqlite://")
    try:
        initialize_fresh_database(engine)
        with engine.connect() as connection:
            return foreign_key_inventory(connection)
    finally:
        engine.dispose()


FKS = physical_inventory()


def fk_id(fk):
    return fk["child_table"] + "." + "+".join(fk["child_columns"])


def test_exact_inventory_and_clean_schema(app):
    with forge.db.engine.connect() as connection:
        assert len(schema_snapshot(connection)["tables"]) == 31
        actual = foreign_key_inventory(connection)
        assert actual == FKS and len(actual) == 42
        assert sum(fk["parent_table"] == "user" for fk in actual) == 28
        assert sum(fk["on_delete"] == "RESTRICT" for fk in actual) == 22
        assert sum(fk["on_delete"] == "NO ACTION" for fk in actual) == 20
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
        assert foreign_key_violations(connection) == []
    assert verify_database(forge.db.engine)["revision"] == HEAD_REVISION


def test_all_fixture_references_are_valid_even_with_enforcement_on(app):
    with forge.db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        populate(connection)
        connection.commit()
        assert foreign_key_violations(connection) == []
        # The verifier checks semantic invariants in addition to physical FKs.
    assert verify_application_database(forge.db.engine)["headRevision"] == HEAD_REVISION


@pytest.mark.parametrize("fk", FKS, ids=fk_id)
@pytest.mark.parametrize("enforced", [False, True], ids=["off", "on"])
def test_every_physical_parent_delete(fk, enforced, app):
    with forge.db.engine.connect() as connection:
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enforced else 'OFF'}")
        populate(connection)
        connection.commit()
        quote = connection.dialect.identifier_preparer.quote_identifier
        child_columns = ", ".join(quote(c) for c in fk["child_columns"])
        nonnull = " AND ".join(f"{quote(c)} IS NOT NULL" for c in fk["child_columns"])
        values = connection.exec_driver_sql(
            f"SELECT {child_columns} FROM {quote(fk['child_table'])} WHERE {nonnull} LIMIT 1").one()
        predicate = " AND ".join(f"{quote(c)}=?" for c in fk["parent_columns"])
        sql = f"DELETE FROM {quote(fk['parent_table'])} WHERE {predicate}"
        before = snapshot(connection)
        if enforced:
            with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
                connection.exec_driver_sql(sql, tuple(values))
            connection.rollback()
            assert snapshot(connection) == before
            assert foreign_key_violations(connection) == []
        else:
            connection.exec_driver_sql(sql, tuple(values))
            connection.commit()
            assert any(row["table"] == fk["child_table"] and row["fk_index"] == fk["fk_index"]
                       for row in foreign_key_violations(connection))
        # This test owns the connection; never return an FK-ON handle to the app pool.
        connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")


def test_invalid_insert_and_content_free_orphan_diagnostics(app):
    with forge.db.engine.connect() as connection:
        sql = "INSERT INTO notification (id,user_id,type,text) VALUES (1,999,'test',?)"
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
            connection.exec_driver_sql(sql, ("private fixture",))
        connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql(sql, ("private fixture",))
        connection.commit()
        assert foreign_key_violations(connection) == [
            dict(table="notification", rowid=1, parent_table="user", fk_index=0)]
    for verifier in (verify_database, verify_application_database):
        with pytest.raises(MigrationError, match="foreign_key_check") as error:
            verifier(forge.db.engine)
        assert "private fixture" not in str(error.value)


def test_enabling_inside_transaction_is_noop(app):
    with forge.db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
        connection.exec_driver_sql(
            "INSERT INTO notification (user_id,type,text) VALUES (999,'test','private fixture')")
        assert foreign_key_violations(connection)
        connection.rollback()
        assert foreign_key_violations(connection) == []


def test_connection_pool_state_is_per_handle_and_new_handles_default_off(app):
    engine = forge.db.engine
    with engine.connect() as first, engine.connect() as second:
        first.exec_driver_sql("PRAGMA foreign_keys=ON")
        assert first.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert second.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
        first.rollback()
        first.exec_driver_sql("PRAGMA foreign_keys=OFF")
    engine.dispose()
    with engine.connect() as fresh:
        assert fresh.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0


def test_begin_immediate_alone_cannot_make_hard_delete_safe(app):
    """An authenticated/stale FK-off writer may insert after removal commits."""
    engine = forge.db.engine
    with engine.begin() as connection:
        populate(connection, {"user"})
    ready, attempted = Event(), Event()
    def child_writer():
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT id FROM user WHERE id=1").scalar() == 1
            connection.rollback()
            ready.set()
            assert attempted.wait(5)
            connection.exec_driver_sql(
                "INSERT INTO notification (user_id,type,text) VALUES (1,'test','private fixture')")
            connection.commit()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(child_writer)
        assert ready.wait(5)
        with engine.connect() as removal:
            removal.exec_driver_sql("BEGIN IMMEDIATE")
            attempted.set()
            assert removal.exec_driver_sql("SELECT count(*) FROM notification").scalar() == 0
            removal.exec_driver_sql("DELETE FROM user WHERE id=1")
            removal.commit()
        pending.result(timeout=5)
    with engine.connect() as connection:
        assert foreign_key_violations(connection) == [
            dict(table="notification", rowid=1, parent_table="user", fk_index=0)]


def test_orm_delete_does_not_cascade_or_null_children(app):
    with forge.db.engine.begin() as connection:
        populate(connection)
        before = snapshot(connection)
    statements = []
    def trace(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(forge.db.engine, "before_cursor_execute", trace)
    try:
        target = forge.db.session.get(forge.User, 1)
        forge.db.session.delete(target)
        forge.db.session.commit()
    finally:
        event.remove(forge.db.engine, "before_cursor_execute", trace)
    writes = [sql for sql in statements if sql.lstrip().upper().startswith(("DELETE", "UPDATE"))]
    assert len(writes) == 1 and writes[0].startswith("DELETE FROM user")
    with forge.db.engine.connect() as connection:
        assert snapshot(connection) == before
        assert foreign_key_violations(connection)


def test_demo_seed_is_fk_clean_with_enforcement_on(app):
    # Connect event is scoped to this disposable test engine, then removed.
    def enable(dbapi, record):
        dbapi.execute("PRAGMA foreign_keys=ON")
    engine = forge.db.engine
    forge.db.session.remove()
    engine.dispose()
    event.listen(engine, "connect", enable)
    try:
        assert forge.seed_demo_data()
        with engine.connect() as connection:
            assert foreign_key_violations(connection) == []
    finally:
        forge.db.session.remove()
        event.remove(engine, "connect", enable)
        engine.dispose()


def test_generated_canonical_evidence_has_no_schema_drift(app):
    from scripts.review_foreign_keys import ROOT, generated_evidence
    with forge.db.engine.connect() as connection:
        evidence = generated_evidence(connection)
    assert evidence in (ROOT / "agent/FK_ADMIN_REVIEW.md").read_text()


def test_fk_on_init_empty_downgrade_upgrade_backup_restore(tmp_path):
    path = tmp_path / "fk-on-migrations.db"
    engine = create_engine(f"sqlite:///{path}")
    def enable(dbapi, record):
        dbapi.execute("PRAGMA foreign_keys=ON")
    event.listen(engine, "connect", enable)
    try:
        initialize_fresh_database(engine)
        assert verify_database(engine)["foreignKeysEnabled"] is True
        downgrade_database(engine, BASELINE_REVISION)
        upgrade_database(engine)
        assert verify_database(engine)["foreignKeyViolations"] == []
        with engine.begin() as connection:
            populate(connection)
        copy = backup_sqlite(engine, tmp_path / "restored-copy.db")
        restored = create_engine(f"sqlite:///{copy}")
        try:
            assert verify_application_database(restored)["headRevision"] == HEAD_REVISION
            with restored.connect() as connection:
                assert foreign_key_violations(connection) == []
        finally:
            restored.dispose()
    finally:
        engine.dispose()
