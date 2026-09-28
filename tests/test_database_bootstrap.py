"""Issue #16: migration authority and non-mutating application startup."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import MetaData, create_engine, inspect
from flask_sqlalchemy import SQLAlchemy

import forge_migrations as migrations
from migrations import r20260928_02_owned_social_schema as owned

ROOT = Path(__file__).resolve().parents[1]


def file_state(path):
    """Include sidecars where present; never connect to a real instance DB."""
    return {
        suffix: (candidate.stat().st_size, candidate.stat().st_mtime_ns,
                 hashlib.sha256(candidate.read_bytes()).hexdigest())
        for suffix in ("", "-wal", "-shm", "-journal")
        if (candidate := Path(str(path) + suffix)).exists()
    }


def application_process(path, environment="development", code="import forge_backend", args=None):
    env = dict(os.environ, FORGE_DATABASE_URI=f"sqlite:///{path}",
               FORGE_ENV=environment, FORGE_SECRET_KEY="s" * 40,
               FORGE_DEBUG="0", FORGE_DEMO_MODE="0",
               FORGE_UPLOAD_DIR=str(path.parent / "uploads"),
               FORGE_PROFILE_IMAGE_DIR=str(path.parent / "images"))
    return subprocess.run([sys.executable, *(args or ["-c", code])],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)


def database_at(tmp_path, state="head"):
    path = tmp_path / "isolated.db"
    engine = create_engine(f"sqlite:///{path}")
    if state in {"unmanaged", "behind", "operator_head"}:
        with migrations._sqlite_write_transaction(engine) as connection:
            migrations._create_frozen_baseline(connection)
        if state != "unmanaged":
            migrations.initialize_baseline(engine)
        if state == "operator_head":
            migrations.upgrade_database(engine)
    else:
        migrations.initialize_fresh_database(engine)
        with engine.begin() as connection:
            if state == "drift":
                connection.exec_driver_sql("ALTER TABLE user ADD COLUMN surprise TEXT")
            elif state == "checksum":
                connection.exec_driver_sql(
                    f"UPDATE {migrations.LEDGER_TABLE} SET checksum='tampered'"
                )
            elif state == "trigger":
                connection.exec_driver_sql(f"DROP TRIGGER {owned.OWNED_SOCIAL_TRIGGERS[0]}")
            elif state == "trigger_body":
                name = owned.OWNED_SOCIAL_TRIGGERS[0]
                connection.exec_driver_sql(f"DROP TRIGGER {name}")
                connection.exec_driver_sql(
                    f"CREATE TRIGGER {name} BEFORE INSERT ON conversation_member "
                    "BEGIN SELECT 1; END"
                )
            elif state == "extra_view":
                connection.exec_driver_sql("CREATE VIEW surprise AS SELECT * FROM user")
            elif state == "baseline_check":
                connection.exec_driver_sql("DROP TABLE suggested")
                connection.exec_driver_sql(
                    'CREATE TABLE suggested (id INTEGER NOT NULL PRIMARY KEY, '
                    'name VARCHAR(120) NOT NULL, role VARCHAR(120) NOT NULL, '
                    'color VARCHAR(16), status VARCHAR(16), CHECK (id > 100))'
                )
            elif state == "check_body":
                connection.exec_driver_sql("DROP TABLE direct_message")
                statement = next(sql for sql in owned.UPGRADE_SQL
                                 if "CREATE TABLE direct_message" in sql)
                connection.exec_driver_sql(statement.replace("<= 4000", "<= 4001"))
            elif state == "ledger_shape":
                connection.exec_driver_sql(
                    f"ALTER TABLE {migrations.LEDGER_TABLE} ADD COLUMN surprise TEXT"
                )
    engine.dispose()
    return engine, path


@pytest.mark.parametrize("state", ["unmanaged", "operator_head"])
@pytest.mark.parametrize("command", ["db-status", "db-verify"])
def test_inspection_cli_preserves_existing_non_wal_database(tmp_path, state, command):
    _, path = database_at(tmp_path, state)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    before = file_state(path)
    result = application_process(
        path, args=["-m", "flask", "--app", "forge_backend", command]
    )
    assert result.returncode == 0, result.stderr
    assert file_state(path) == before
    assert set(file_state(path)) == {""}  # no WAL/SHM/journal sidecar
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


@pytest.mark.parametrize("memory", [False, True])
def test_fresh_bootstrap_head_is_independent_of_orm(tmp_path, monkeypatch, memory):
    def forbid(*args, **kwargs):
        pytest.fail("ORM metadata must not initialize application schema")
    monkeypatch.setattr(MetaData, "create_all", forbid)
    monkeypatch.setattr(SQLAlchemy, "create_all", forbid)
    engine = create_engine("sqlite://" if memory else f"sqlite:///{tmp_path / 'new.db'}")
    try:
        migrations.initialize_fresh_database(engine)
        status = migrations.migration_status(engine)
        assert status["headRevision"] == migrations.HEAD_REVISION
        assert status["pendingRevisions"] == []
        assert len(status["applied"]) == len(migrations.REVISION_ORDER)
        assert set(owned.OWNED_SOCIAL_TABLES) <= set(inspect(engine).get_table_names())
        assert migrations.verify_database(engine)["foreignKeysEnabled"] is False
        migrations.verify_application_database(engine)
    finally:
        engine.dispose()


def test_fresh_bootstrap_physical_constraints(tmp_path):
    _, path = database_at(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")  # isolated constraint test only
        for user_id in (1, 2, 3):
            conn.execute("INSERT INTO user (id,username,password_hash,role,name) "
                         "VALUES (?,?,'hash','trade','name')", (user_id, str(user_id)))
        conn.execute("INSERT INTO direct_conversation VALUES "
                     "(1,'opaque',1,2,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,0)")
        for member in (1, 2):
            conn.execute("INSERT INTO conversation_member "
                         "(conversation_id,user_id,joined_at,last_read_seq) "
                         "VALUES (1,?,CURRENT_TIMESTAMP,0)", (member,))
        with pytest.raises(sqlite3.IntegrityError, match="conversation member"):
            conn.execute("INSERT INTO conversation_member "
                         "(conversation_id,user_id,joined_at,last_read_seq) "
                         "VALUES (1,3,CURRENT_TIMESTAMP,0)")
        with pytest.raises(sqlite3.IntegrityError, match="conversation member"):
            conn.execute("UPDATE conversation_member SET user_id=3 WHERE user_id=2")
        insert = "INSERT INTO direct_message VALUES (1,?,1,?,?,CURRENT_TIMESTAMP)"
        conn.execute(insert, (1, 'retry-id', 'hello'))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (2, 'retry-id', 'duplicate'))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (2, 'other-id', 'x' * 4001))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO direct_message VALUES "
                         "(1,2,3,'forged','hello',CURRENT_TIMESTAMP)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO direct_conversation VALUES "
                         "(2,'other',1,2,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,0)")


@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
@pytest.mark.parametrize("state", ["head", "operator_head"])
def test_current_head_import_has_no_database_mutation(tmp_path, environment, state):
    _, path = database_at(tmp_path, state)
    before = file_state(path)
    result = application_process(path, environment)
    assert result.returncode == 0, result.stderr
    assert file_state(path) == before


@pytest.mark.parametrize("state,diagnostic", [
    ("unmanaged", "db-baseline"), ("behind", "db-upgrade"),
    ("drift", "Schema does not match"), ("checksum", "checksum mismatch"),
    ("trigger", "missing triggers"), ("trigger_body", "physical schema"),
    ("extra_view", "physical schema"), ("ledger_shape", "physical schema"),
    ("check_body", "physical schema"),
    ("baseline_check", "physical schema"),
])
def test_refused_startup_is_read_only(tmp_path, state, diagnostic):
    _, path = database_at(tmp_path, state)
    before = file_state(path)
    result = application_process(path, "production")
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert "db-status" in result.stderr
    assert file_state(path) == before


def test_missing_and_empty_persistent_databases_fail_closed(tmp_path):
    path = tmp_path / "missing.db"
    result = application_process(path)
    assert result.returncode != 0 and "db-init" in result.stderr
    assert not path.exists()
    path.touch()
    before = file_state(path)
    result = application_process(path)
    assert result.returncode != 0 and "unmanaged" in result.stderr
    assert file_state(path) == before
    engine = create_engine(f"sqlite:///{path}")
    with pytest.raises(migrations.MigrationError, match="existing database"):
        migrations.initialize_fresh_database(engine)
    assert file_state(path) == before


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_bootstrap_rolls_back_every_revision_and_ledger(tmp_path, monkeypatch, failure):
    engine = create_engine(f"sqlite:///{tmp_path / 'interrupted.db'}")
    upgrade = owned.upgrade
    def interrupt(connection):
        upgrade(connection)
        raise failure("injected after revision DDL")
    monkeypatch.setattr(owned, "upgrade", interrupt)
    with pytest.raises(failure):
        migrations.initialize_fresh_database(engine)
    assert inspect(engine).get_table_names() == []
    assert not migrations.migration_status(engine)["managed"]
    with pytest.raises(migrations.MigrationError):
        migrations.verify_application_database(engine)
    engine.dispose()


def test_cli_initialization_confirmation_and_recovery_commands(tmp_path):
    path = tmp_path / "new.db"
    cli = ["-m", "flask", "--app", "forge_backend"]
    no_confirm = application_process(path, args=cli + ["db-init"])
    assert no_confirm.returncode != 0 and "--confirm-schema-change" in no_confirm.stderr
    assert not path.exists()
    status = application_process(path, args=cli + ["db-status"])
    assert status.returncode == 0 and '"exists": false' in status.stdout
    assert not path.exists()
    created = application_process(path, args=cli + ["db-init", "--confirm-schema-change"])
    assert created.returncode == 0, created.stderr
    before = file_state(path)
    repeated = application_process(path, args=cli + ["db-init", "--confirm-schema-change"])
    assert repeated.returncode != 0 and "existing database" in repeated.stderr
    assert file_state(path) == before
    assert application_process(path).returncode == 0


def test_baseline_upgrade_cli_remain_explicit_when_startup_refuses(tmp_path):
    _, path = database_at(tmp_path, "unmanaged")
    cli = ["-m", "flask", "--app", "forge_backend"]
    for args in (["db-baseline", "--confirm-current-schema"],
                 ["db-upgrade", "--confirm-schema-change"]):
        result = application_process(path, args=cli + args)
        assert result.returncode == 0, result.stderr
    assert application_process(path).returncode == 0


@pytest.mark.parametrize("entry", ["script", "flask-run"])
def test_server_entrypoints_verify_before_serving(tmp_path, entry):
    _, path = database_at(tmp_path, "behind")
    if entry == "script":
        code = "import runpy; runpy.run_path('forge_backend.py', run_name='__main__')"
    else:
        code = "from flask.cli import cli; cli.main(args=['--app','forge_backend','run'])"
    before = file_state(path)
    result = application_process(path, code=code)
    assert result.returncode != 0 and "db-upgrade" in result.stderr
    assert file_state(path) == before


def test_local_demo_seeding_after_initialization_only(tmp_path):
    _, path = database_at(tmp_path)
    cli = ["-m", "flask", "--app", "forge_backend", "seed-demo"]
    denied = application_process(path, args=cli)
    assert denied.returncode != 0 and "FORGE_DEMO_MODE" in denied.stderr
    code = """
import os
os.environ['FORGE_DEMO_MODE'] = '1'
from flask.cli import cli
cli.main(args=['--app', 'forge_backend', 'seed-demo'])
"""
    seeded = application_process(path, code=code)
    assert seeded.returncode == 0 and "Seeded." in seeded.stdout, seeded.stderr
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM user").fetchone()[0] > 0
        assert conn.execute(f"SELECT count(*) FROM {migrations.LEDGER_TABLE}").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM network_edge").fetchone()[0] == 0
    missing = tmp_path / 'uninitialized.db'
    failed = application_process(missing, code=code)
    assert failed.returncode != 0 and "db-init" in failed.stderr
    assert not missing.exists()


def test_deployment_rejects_memory_database():
    engine = create_engine("sqlite://")
    with pytest.raises(migrations.MigrationError, match="persistent"):
        migrations.prepare_application_database(engine, "staging")
    assert inspect(engine).get_table_names() == []
    engine.dispose()


def test_process_termination_does_not_commit_partial_bootstrap(tmp_path):
    path = tmp_path / "killed.db"
    code = """
import os, signal
from sqlalchemy import create_engine
import forge_migrations as migrations
from migrations import r20260928_02_owned_social_schema as owned
upgrade = owned.upgrade
def terminate(connection):
    upgrade(connection)
    os.kill(os.getpid(), signal.SIGKILL)
owned.upgrade = terminate
migrations.initialize_fresh_database(create_engine(os.environ['FORGE_DATABASE_URI']))
"""
    result = application_process(path, code=code)
    assert result.returncode < 0
    # Let SQLite recover only this test-owned file, then inspect the result.
    engine = create_engine(f"sqlite:///{path}")
    assert inspect(engine).get_table_names() == []
    assert migrations.migration_status(engine)["managed"] is False
    engine.dispose()
    assert application_process(path).returncode != 0


def test_wal_startup_observes_uncheckpointed_commits_without_writing(tmp_path):
    _, path = database_at(tmp_path)
    with sqlite3.connect(path) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(f"UPDATE {migrations.LEDGER_TABLE} SET checksum='bad-in-wal'")
        writer.commit()
        before = file_state(path)
        result = application_process(path)
        assert result.returncode != 0 and "checksum mismatch" in result.stderr
        after = file_state(path)
        # Shared-memory read locks are SQLite bookkeeping, not database writes.
        for suffix in ("", "-wal"):
            assert after[suffix] == before[suffix]
