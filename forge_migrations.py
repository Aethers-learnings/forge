"""Explicit, conservative SQLite migration support for Forge.

T-201 explicit SQLite migration support:
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
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import click
from sqlalchemy import inspect, text

from migrations import (
    r20260928_02_owned_social_schema as owned_social_schema,
)


BASE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = BASE_DIR / "migrations"
BASELINE_PATH = MIGRATIONS_DIR / "baseline_schema.json"
BASELINE_REVISION = "20260928_01_pre_migrations"
LEDGER_TABLE = "forge_schema_migrations"

MIGRATION_MODULES = (
    owned_social_schema,
)

REVISION_MODULES = {
    module.REVISION: module
    for module in MIGRATION_MODULES
}

REVISION_ORDER = (
    BASELINE_REVISION,
    *(module.REVISION for module in MIGRATION_MODULES),
)

HEAD_REVISION = REVISION_ORDER[-1]


class MigrationError(RuntimeError):
    """Raised when migration safety checks fail."""


@contextmanager
def _sqlite_write_transaction(engine):
    """Use a real SQLite transaction for schema-changing operations.

    Python's sqlite3 legacy transaction behavior does not reliably issue
    BEGIN for DDL. An explicit BEGIN IMMEDIATE ensures CREATE/DROP changes,
    migration-ledger writes, and their verification commit or roll back
    together.
    """
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            if connection.in_transaction():
                connection.rollback()
            raise


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


def _load_revision_manifest(module):
    path = module.SCHEMA_MANIFEST_PATH

    if not path.exists():
        raise MigrationError(
            f"Committed schema manifest is missing: {path}"
        )

    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(
            f"Could not read schema manifest {path}: {exc}"
        ) from exc

    if payload.get("revision") != module.REVISION:
        raise MigrationError(
            f"Schema manifest revision mismatch for "
            f"{module.REVISION}."
        )

    if not isinstance(payload.get("schema"), dict):
        raise MigrationError(
            f"Schema manifest for {module.REVISION} "
            f"has no valid schema."
        )

    return payload


def _expected_schema_for_revision(revision):
    if revision == BASELINE_REVISION:
        return load_baseline()["schema"]

    module = REVISION_MODULES.get(revision)

    if module is None:
        raise MigrationError(
            f"Unknown migration revision: {revision}"
        )

    return _load_revision_manifest(module)["schema"]


def revision_checksum(revision):
    if revision == BASELINE_REVISION:
        return baseline_checksum()

    module = REVISION_MODULES.get(revision)

    if module is None:
        raise MigrationError(
            f"Unknown migration revision: {revision}"
        )

    return _checksum({
        "migration": module.CHECKSUM_PAYLOAD,
        "schema": _load_revision_manifest(module)["schema"],
    })


def _read_ledger_rows(engine):
    with engine.connect() as connection:
        rows = connection.execute(text(
            f"""
            SELECT revision, checksum, applied_at
            FROM {LEDGER_TABLE}
            """
        )).mappings().all()

    return [dict(row) for row in rows]


def _validate_ledger_rows(rows):
    if not rows:
        raise MigrationError(
            "Migration ledger exists but contains no baseline revision."
        )

    by_revision = {
        row["revision"]: row
        for row in rows
    }

    unknown = sorted(
        set(by_revision) - set(REVISION_ORDER)
    )

    if unknown:
        raise MigrationError(
            "Migration ledger contains unknown revisions: "
            + ", ".join(unknown)
        )

    applied = [
        revision
        for revision in REVISION_ORDER
        if revision in by_revision
    ]

    expected_prefix = list(
        REVISION_ORDER[:len(applied)]
    )

    if (
        len(applied) != len(rows)
        or applied != expected_prefix
    ):
        raise MigrationError(
            "Migration ledger is not a contiguous ordered "
            "revision history."
        )

    validated = []

    for revision in applied:
        row = by_revision[revision]
        expected_checksum = revision_checksum(revision)

        if row["checksum"] != expected_checksum:
            raise MigrationError(
                f"Migration checksum mismatch for {revision}."
            )

        validated.append({
            "revision": revision,
            "checksum": row["checksum"],
            "appliedAt": row["applied_at"],
        })

    return validated


def _assert_schema_matches_revision_bind(bind, revision):
    expected = _expected_schema_for_revision(revision)
    actual = schema_snapshot(bind)

    if actual != expected:
        raise MigrationError(
            f"Schema does not match revision {revision}: "
            + _schema_difference(expected, actual)
            + "."
        )

    return actual


def _integrity_result(connection):
    integrity_rows = [
        row[0]
        for row in connection.exec_driver_sql(
            "PRAGMA integrity_check"
        ).fetchall()
    ]

    if integrity_rows != ["ok"]:
        raise MigrationError(
            "SQLite integrity_check failed: "
            + "; ".join(
                str(value)
                for value in integrity_rows
            )
        )

    foreign_key_violations = [
        list(row)
        for row in connection.exec_driver_sql(
            "PRAGMA foreign_key_check"
        ).fetchall()
    ]

    if foreign_key_violations:
        raise MigrationError(
            "SQLite foreign_key_check failed: "
            + repr(foreign_key_violations[:10])
        )

    return foreign_key_violations


def _verify_revision_modules(connection, applied_revisions):
    for revision in applied_revisions:
        if revision == BASELINE_REVISION:
            continue

        module = REVISION_MODULES[revision]
        problems = module.verify(connection)

        if problems:
            raise MigrationError(
                f"Revision {revision} invariant check failed: "
                + "; ".join(problems)
            )

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

    # Status must not create a missing SQLite file merely by
    # inspecting it.
    if path is not None and not path.exists():
        return {
            "exists": False,
            "managed": False,
            "database": str(path),
            "applied": [],
            "baselineChecksumOk": None,
            "headRevision": None,
            "pendingRevisions": list(REVISION_ORDER),
            "schemaMatchesHead": None,
        }

    inspector = inspect(engine)

    if not inspector.has_table(LEDGER_TABLE):
        return {
            "exists": True,
            "managed": False,
            "database": (
                str(path)
                if path is not None
                else ":memory:"
            ),
            "applied": [],
            "baselineChecksumOk": None,
            "headRevision": None,
            "pendingRevisions": list(REVISION_ORDER),
            "schemaMatchesHead": (
                schema_snapshot(engine)
                == _expected_schema_for_revision(
                    BASELINE_REVISION
                )
            ),
        }

    applied = _validate_ledger_rows(
        _read_ledger_rows(engine)
    )

    head_revision = applied[-1]["revision"]
    head_index = REVISION_ORDER.index(head_revision)

    return {
        "exists": True,
        "managed": True,
        "database": (
            str(path)
            if path is not None
            else ":memory:"
        ),
        "applied": applied,
        "baselineChecksumOk": True,
        "headRevision": head_revision,
        "pendingRevisions": list(
            REVISION_ORDER[head_index + 1:]
        ),
        "schemaMatchesHead": (
            schema_snapshot(engine)
            == _expected_schema_for_revision(head_revision)
        ),
    }

def initialize_baseline(engine):
    """Explicitly adopt an existing database only if it matches exactly."""
    assert_schema_matches_baseline(engine)
    expected_checksum = baseline_checksum()

    with _sqlite_write_transaction(engine) as connection:
        _assert_schema_matches_revision_bind(
            connection,
            BASELINE_REVISION,
        )

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
    """Verify managed schema/integrity without changing enforcement."""
    path = _sqlite_database_path(engine)

    if path is not None and not path.exists():
        raise MigrationError(
            f"Database file does not exist: {path}"
        )

    inspector = inspect(engine)
    managed = inspector.has_table(LEDGER_TABLE)

    if managed:
        applied = _validate_ledger_rows(
            _read_ledger_rows(engine)
        )
        head_revision = applied[-1]["revision"]
        applied_revisions = [
            row["revision"]
            for row in applied
        ]
    else:
        head_revision = BASELINE_REVISION
        applied_revisions = [BASELINE_REVISION]

    with engine.connect() as connection:
        _assert_schema_matches_revision_bind(
            connection,
            head_revision,
        )

        foreign_keys_before = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

        foreign_key_violations = _integrity_result(
            connection
        )

        _verify_revision_modules(
            connection,
            applied_revisions,
        )

        foreign_keys_after = int(
            connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
            or 0
        )

    if foreign_keys_before != foreign_keys_after:
        raise MigrationError(
            "Verification unexpectedly changed "
            "foreign-key enforcement."
        )

    return {
        "integrity": "ok",
        "foreignKeyViolations": foreign_key_violations,
        "foreignKeysEnabled": bool(foreign_keys_after),
        "managed": managed,
        "revision": head_revision,
    }


def upgrade_database(engine, target_revision=None):
    """Apply ordered additive revisions to an explicitly baselined DB."""
    path = _sqlite_database_path(engine)

    if path is not None and not path.exists():
        raise MigrationError(
            f"Database file does not exist: {path}"
        )

    if not inspect(engine).has_table(LEDGER_TABLE):
        raise MigrationError(
            "Database is not baselined. Run db-baseline "
            "after verifying the current schema first."
        )

    applied = _validate_ledger_rows(
        _read_ledger_rows(engine)
    )
    current_revision = applied[-1]["revision"]

    target_revision = (
        target_revision
        or HEAD_REVISION
    )

    if target_revision not in REVISION_ORDER:
        raise MigrationError(
            f"Unknown target revision: {target_revision}"
        )

    current_index = REVISION_ORDER.index(
        current_revision
    )
    target_index = REVISION_ORDER.index(
        target_revision
    )

    if target_index < current_index:
        raise MigrationError(
            "Target revision is behind the current revision; "
            "use db-downgrade instead."
        )

    applied_now = []

    for revision in REVISION_ORDER[
        current_index + 1:
        target_index + 1
    ]:
        module = REVISION_MODULES[revision]

        if module.DOWN_REVISION != current_revision:
            raise MigrationError(
                f"Revision chain mismatch at {revision}."
            )

        with _sqlite_write_transaction(engine) as connection:
            _assert_schema_matches_revision_bind(
                connection,
                current_revision,
            )

            foreign_keys_before = int(
                connection.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar()
                or 0
            )

            module.upgrade(connection)

            _assert_schema_matches_revision_bind(
                connection,
                revision,
            )

            _integrity_result(connection)
            _verify_revision_modules(
                connection,
                (
                    *(
                        row["revision"]
                        for row in applied
                    ),
                    *applied_now,
                    revision,
                ),
            )

            foreign_keys_after = int(
                connection.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar()
                or 0
            )

            if (
                foreign_keys_before
                != foreign_keys_after
            ):
                raise MigrationError(
                    f"Revision {revision} unexpectedly "
                    "changed foreign-key enforcement."
                )

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
                    "revision": revision,
                    "checksum": revision_checksum(
                        revision
                    ),
                    "applied_at": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    ),
                },
            )

        applied_now.append(revision)
        current_revision = revision

    return applied_now


def downgrade_database(engine, target_revision):
    """Remove empty revisions only; never discard owned live data."""
    path = _sqlite_database_path(engine)

    if path is not None and not path.exists():
        raise MigrationError(
            f"Database file does not exist: {path}"
        )

    if not inspect(engine).has_table(LEDGER_TABLE):
        raise MigrationError(
            "Database is not managed by Forge migrations."
        )

    applied = _validate_ledger_rows(
        _read_ledger_rows(engine)
    )

    current_revision = applied[-1]["revision"]

    if target_revision not in REVISION_ORDER:
        raise MigrationError(
            f"Unknown target revision: {target_revision}"
        )

    current_index = REVISION_ORDER.index(
        current_revision
    )
    target_index = REVISION_ORDER.index(
        target_revision
    )

    if target_index > current_index:
        raise MigrationError(
            "Target revision is ahead of the current revision; "
            "use db-upgrade instead."
        )

    removed = []

    while current_index > target_index:
        revision = REVISION_ORDER[current_index]
        module = REVISION_MODULES[revision]
        down_revision = module.DOWN_REVISION

        with _sqlite_write_transaction(engine) as connection:
            _assert_schema_matches_revision_bind(
                connection,
                revision,
            )

            nonempty = module.nonempty_tables(
                connection
            )

            if nonempty:
                detail = ", ".join(
                    f"{name}={count}"
                    for name, count in nonempty
                )
                raise MigrationError(
                    f"Refusing to downgrade {revision}; "
                    f"owned data exists: {detail}."
                )

            foreign_keys_before = int(
                connection.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar()
                or 0
            )

            module.downgrade(connection)

            _assert_schema_matches_revision_bind(
                connection,
                down_revision,
            )

            _integrity_result(connection)

            foreign_keys_after = int(
                connection.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar()
                or 0
            )

            if (
                foreign_keys_before
                != foreign_keys_after
            ):
                raise MigrationError(
                    f"Downgrade of {revision} unexpectedly "
                    "changed foreign-key enforcement."
                )

            connection.execute(
                text(
                    f"""
                    DELETE FROM {LEDGER_TABLE}
                    WHERE revision = :revision
                    """
                ),
                {"revision": revision},
            )

        removed.append(revision)
        current_revision = down_revision
        current_index -= 1

    return removed

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
    """Register explicit operator commands; none run at startup."""

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
        help=(
            "Required acknowledgement before writing "
            "the baseline ledger."
        ),
    )
    def db_baseline_command(confirm_current_schema):
        """Adopt an exact-match existing schema into tracking."""
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
            else (
                "Baseline was already recorded "
                "and checksum-valid."
            )
        )

    @app.cli.command("db-upgrade")
    @click.option(
        "--to",
        "target_revision",
        default=HEAD_REVISION,
        show_default=True,
    )
    @click.option(
        "--confirm-schema-change",
        is_flag=True,
        help="Required acknowledgement before applying DDL.",
    )
    def db_upgrade_command(
        target_revision,
        confirm_schema_change,
    ):
        """Apply ordered revisions to an explicitly baselined DB."""
        if not confirm_schema_change:
            raise click.ClickException(
                "Refusing to change schema without "
                "--confirm-schema-change."
            )

        try:
            applied = upgrade_database(
                db.engine,
                target_revision,
            )
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

        if applied:
            click.echo(
                "Applied revisions: "
                + ", ".join(applied)
            )
        else:
            click.echo("Database already at requested revision.")

    @app.cli.command("db-downgrade")
    @click.option(
        "--to",
        "target_revision",
        required=True,
    )
    @click.option(
        "--confirm-empty-owned-schema",
        is_flag=True,
        help=(
            "Required acknowledgement; downgrade still "
            "refuses any owned-social data."
        ),
    )
    def db_downgrade_command(
        target_revision,
        confirm_empty_owned_schema,
    ):
        """Remove only empty later revisions."""
        if not confirm_empty_owned_schema:
            raise click.ClickException(
                "Refusing to downgrade without "
                "--confirm-empty-owned-schema."
            )

        try:
            removed = downgrade_database(
                db.engine,
                target_revision,
            )
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

        if removed:
            click.echo(
                "Removed revisions: "
                + ", ".join(removed)
            )
        else:
            click.echo("Database already at requested revision.")

    @app.cli.command("db-verify")
    def db_verify_command():
        """Run schema/integrity/FK diagnostics without mutation."""
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
            result = backup_sqlite(
                db.engine,
                destination,
            )
        except MigrationError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(str(result))
