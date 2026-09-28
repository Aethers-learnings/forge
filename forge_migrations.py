"""Explicit, conservative SQLite migration support for Forge.

T-201 foundation only:
- freezes the pre-migration schema as a committed manifest;
- can explicitly baseline a matching existing database;
- records applied revisions in a small migration ledger;
- verifies integrity without changing FK enforcement;
- creates SQLite-consistent backups.

Nothing in this module runs migrations automatically at application startup.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
from sqlalchemy import inspect, text


BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BASE_DIR / "migrations"
BASELINE_PATH = MIGRATIONS_DIR / "baseline_schema.json"
BASELINE_REVISION = "20260928_01_pre_migrations"
LEDGER_TABLE = "forge_schema_migrations"


class MigrationError(RuntimeError):
    """Raised when migration safety checks fail."""


def _canonical_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _checksum(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sorted_records(records):
    return sorted(records, key=_canonical_json)


def _sqlite_database_path(engine):
    if engine.url.get_backend_name() != "sqlite":
        raise MigrationError(
            "T-201 currently supports only Forge's approved SQLite database."
        )

    database = engine.url.database
    if not database or database == ":memory:":
        return None

    return Path(database).expanduser().resolve()


def schema_snapshot(engine):
    """Return a deterministic SQLite schema description.

    The migration ledger is intentionally excluded: it tracks migrations and
    is not part of the application-domain baseline.
    """
    inspector = inspect(engine)
    tables = {}

    for table_name in sorted(inspector.get_table_names()):
        if table_name == LEDGER_TABLE or table_name.startswith("sqlite_"):
            continue

        columns = []
        for column in inspector.get_columns(table_name):
            columns.append({
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": bool(column["nullable"]),
                "default": (
                    None
                    if column.get("default") is None
                    else str(column.get("default"))
                ),
            })

        primary_key = inspector.get_pk_constraint(table_name) or {}

        unique_constraints = []
        for constraint in inspector.get_unique_constraints(table_name):
            unique_constraints.append({
                "name": constraint.get("name"),
                "columns": list(constraint.get("column_names") or []),
            })

        foreign_keys = []
        for foreign_key in inspector.get_foreign_keys(table_name):
            foreign_keys.append({
                "name": foreign_key.get("name"),
                "columns": list(
                    foreign_key.get("constrained_columns") or []
                ),
                "referred_schema": foreign_key.get("referred_schema"),
                "referred_table": foreign_key.get("referred_table"),
                "referred_columns": list(
                    foreign_key.get("referred_columns") or []
                ),
                "options": dict(foreign_key.get("options") or {}),
            })

        indexes = []
        for index in inspector.get_indexes(table_name):
            indexes.append({
                "name": index.get("name"),
                "columns": list(index.get("column_names") or []),
                "unique": bool(index.get("unique")),
            })

        tables[table_name] = {
            "columns": columns,
            "primary_key": list(
                primary_key.get("constrained_columns") or []
            ),
            "unique_constraints": _sorted_records(unique_constraints),
            "foreign_keys": _sorted_records(foreign_keys),
            "indexes": _sorted_records(indexes),
        }

    return {"tables": tables}


def load_baseline():
    if not BASELINE_PATH.exists():
        raise MigrationError(
            f"Committed baseline manifest is missing: {BASELINE_PATH}"
        )

    try:
        baseline = json.loads(BASELINE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(
            f"Could not read baseline manifest: {exc}"
        ) from exc

    if baseline.get("revision") != BASELINE_REVISION:
        raise MigrationError(
            "Baseline revision does not match the migration tooling."
        )

    if not isinstance(baseline.get("schema"), dict):
        raise MigrationError("Baseline manifest has no valid schema.")

    return baseline


def baseline_checksum():
    return _checksum(load_baseline()["schema"])


def _schema_difference(expected, actual):
    expected_tables = set(expected["tables"])
    actual_tables = set(actual["tables"])

    missing = sorted(expected_tables - actual_tables)
    extra = sorted(actual_tables - expected_tables)

    if missing or extra:
        pieces = []
        if missing:
            pieces.append("missing tables: " + ", ".join(missing))
        if extra:
            pieces.append("unexpected tables: " + ", ".join(extra))
        return "; ".join(pieces)

    for table_name in sorted(expected_tables):
        if expected["tables"][table_name] != actual["tables"][table_name]:
            return f"table differs from baseline: {table_name}"

    return "schema differs from baseline"


def assert_schema_matches_baseline(engine):
    path = _sqlite_database_path(engine)
    if path is not None and not path.exists():
        raise MigrationError(
            f"Database file does not exist: {path}"
        )

    expected = load_baseline()["schema"]
    actual = schema_snapshot(engine)

    if actual != expected:
        raise MigrationError(
            "Refusing to baseline database because "
            + _schema_difference(expected, actual)
            + "."
        )

    return actual


def migration_status(engine):
    path = _sqlite_database_path(engine)

    # Status must not create a missing SQLite file merely by inspecting it.
    if path is not None and not path.exists():
        return {
            "exists": False,
            "managed": False,
            "database": str(path),
            "applied": [],
            "baselineChecksumOk": None,
        }

    inspector = inspect(engine)
    if not inspector.has_table(LEDGER_TABLE):
        return {
            "exists": True,
            "managed": False,
            "database": str(path) if path is not None else ":memory:",
            "applied": [],
            "baselineChecksumOk": None,
        }

    with engine.connect() as connection:
        rows = connection.execute(text(
            f"""
            SELECT revision, checksum, applied_at
            FROM {LEDGER_TABLE}
            ORDER BY applied_at, revision
            """
        )).mappings().all()

    applied = [
        {
            "revision": row["revision"],
            "checksum": row["checksum"],
            "appliedAt": row["applied_at"],
        }
        for row in rows
    ]

    baseline_row = next(
        (
            row
            for row in applied
            if row["revision"] == BASELINE_REVISION
        ),
        None,
    )

    return {
        "exists": True,
        "managed": True,
        "database": str(path) if path is not None else ":memory:",
        "applied": applied,
        "baselineChecksumOk": (
            None
            if baseline_row is None
            else baseline_row["checksum"] == baseline_checksum()
        ),
    }


def initialize_baseline(engine):
    """Explicitly adopt an existing database only if it matches exactly."""
    assert_schema_matches_baseline(engine)
    expected_checksum = baseline_checksum()

    with engine.begin() as connection:
        connection.execute(text(
            f"""
            CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
                revision TEXT PRIMARY KEY NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        ))

        rows = connection.execute(text(
            f"""
            SELECT revision, checksum
            FROM {LEDGER_TABLE}
            ORDER BY revision
            """
        )).mappings().all()

        unknown = [
            row["revision"]
            for row in rows
            if row["revision"] != BASELINE_REVISION
        ]
        if unknown:
            raise MigrationError(
                "Migration ledger contains unknown revisions: "
                + ", ".join(unknown)
            )

        existing = next(
            (
                row
                for row in rows
                if row["revision"] == BASELINE_REVISION
            ),
            None,
        )

        if existing:
            if existing["checksum"] != expected_checksum:
                raise MigrationError(
                    "Baseline migration checksum does not match the "
                    "committed manifest."
                )
            return False

        connection.execute(
            text(
                f"""
                INSERT INTO {LEDGER_TABLE}
                    (revision, checksum, applied_at)
                VALUES
                    (:revision, :checksum, :applied_at)
                """
            ),
            {
                "revision": BASELINE_REVISION,
                "checksum": expected_checksum,
                "applied_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return True


def verify_database(engine):
    """Verify baseline and SQLite integrity without changing enforcement."""
    assert_schema_matches_baseline(engine)

    with engine.connect() as connection:
        foreign_keys_before = int(
            connection.exec_driver_sql("PRAGMA foreign_keys").scalar() or 0
        )

        integrity_rows = [
            row[0]
            for row in connection.exec_driver_sql(
                "PRAGMA integrity_check"
            ).fetchall()
        ]

        foreign_key_violations = [
            list(row)
            for row in connection.exec_driver_sql(
                "PRAGMA foreign_key_check"
            ).fetchall()
        ]

        foreign_keys_after = int(
            connection.exec_driver_sql("PRAGMA foreign_keys").scalar() or 0
        )

    if integrity_rows != ["ok"]:
        raise MigrationError(
            "SQLite integrity_check failed: "
            + "; ".join(str(value) for value in integrity_rows)
        )

    if foreign_keys_before != foreign_keys_after:
        raise MigrationError(
            "Verification unexpectedly changed foreign-key enforcement."
        )

    return {
        "integrity": "ok",
        "foreignKeyViolations": foreign_key_violations,
        "foreignKeysEnabled": bool(foreign_keys_after),
    }


def backup_sqlite(engine, destination):
    """Create a consistent SQLite backup without overwriting an existing file."""
    source = _sqlite_database_path(engine)
    if source is None:
        raise MigrationError("Cannot back up an in-memory SQLite database.")
    if not source.exists():
        raise MigrationError(f"Database file does not exist: {source}")

    destination = Path(destination).expanduser().resolve()

    if destination == source:
        raise MigrationError("Backup destination must differ from source.")
    if destination.exists():
        raise MigrationError(
            f"Refusing to overwrite existing backup: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(source) as source_db:
            with sqlite3.connect(destination) as destination_db:
                source_db.backup(destination_db)

        with sqlite3.connect(destination) as backup_db:
            integrity = backup_db.execute(
                "PRAGMA integrity_check"
            ).fetchone()

        if not integrity or integrity[0] != "ok":
            raise MigrationError(
                "Backup was created but failed SQLite integrity_check."
            )
    except Exception:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise

    return destination


def register_migration_commands(app, db):
    """Register explicit operator commands; none run at normal startup."""

    @app.cli.command("db-status")
    def db_status_command():
        """Show migration state without changing the database."""
        try:
            click.echo(json.dumps(
                migration_status(db.engine),
                indent=2,
                sort_keys=True,
            ))
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

    @app.cli.command("db-baseline")
    @click.option(
        "--confirm-current-schema",
        is_flag=True,
        help="Required acknowledgement before writing the baseline ledger.",
    )
    def db_baseline_command(confirm_current_schema):
        """Adopt an exact-match existing schema into migration tracking."""
        if not confirm_current_schema:
            raise click.ClickException(
                "Refusing to modify migration state without "
                "--confirm-current-schema."
            )

        try:
            created = initialize_baseline(db.engine)
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(
            "Baseline recorded."
            if created
            else "Baseline was already recorded and checksum-valid."
        )

    @app.cli.command("db-verify")
    def db_verify_command():
        """Run baseline, integrity, and FK diagnostics without mutation."""
        try:
            click.echo(json.dumps(
                verify_database(db.engine),
                indent=2,
                sort_keys=True,
            ))
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

    @app.cli.command("db-backup")
    @click.argument("destination")
    def db_backup_command(destination):
        """Create a consistent SQLite backup at DESTINATION."""
        try:
            result = backup_sqlite(db.engine, destination)
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(str(result))
