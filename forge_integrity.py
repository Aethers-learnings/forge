"""SQLite physical-FK diagnostics and the bounded admin-removal safety seam.

No schema changes, child-row writes, or enforcement toggles. Diagnostics expose
only reference metadata, never row contents. Migrations remain schema authority.
"""

from collections import defaultdict
from contextlib import contextmanager

from sqlalchemy import select, text

from forge_migrations import LEDGER_TABLE


@contextmanager
def _removal_transaction(engine):
    with engine.connect() as connection:
        # Keep the physical handle: a failed SQLAlchemy commit may deactivate
        # its transaction marker before SQLite has ended the real transaction.
        dbapi = connection.connection.dbapi_connection
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            try:
                connection.rollback()
            finally:
                dbapi.rollback()
            raise


def foreign_key_inventory(connection):
    """Reflect each physical constraint once, preserving composite column order."""
    if connection.dialect.name != "sqlite":
        raise RuntimeError("Integrity review supports SQLite only")
    quote = connection.dialect.identifier_preparer.quote_identifier
    tables = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).scalars().all()
    result = []
    for table in tables:
        if table == LEDGER_TABLE:
            continue
        columns = {row[1]: row for row in connection.exec_driver_sql(
            f"PRAGMA table_info({quote(table)})")}
        groups = defaultdict(list)
        for row in connection.exec_driver_sql(f"PRAGMA foreign_key_list({quote(table)})"):
            groups[row[0]].append(row)
        for index, rows in sorted(groups.items()):
            rows.sort(key=lambda row: row[1])
            parent = rows[0][2]
            parent_columns = tuple(row[4] for row in rows)
            if any(column is None for column in parent_columns):
                primary_key = sorted((row[5], row[1]) for row in connection.exec_driver_sql(
                    f"PRAGMA table_info({quote(parent)})") if row[5])
                parent_columns = tuple(name for _, name in primary_key)
            child_columns = tuple(row[3] for row in rows)
            if len(child_columns) != len(parent_columns):
                raise RuntimeError("Unresolvable physical foreign key")
            result.append(dict(child_table=table, fk_index=index, child_columns=child_columns,
                               parent_table=parent, parent_columns=parent_columns,
                               nullable=tuple(not bool(columns[name][3]) for name in child_columns),
                               on_delete=rows[0][6], on_update=rows[0][5]))
    return result


def user_reference_exists(connection, target_id):
    """Check real FK rows, without guessing identity from names/legacy text.

    Call under a reserved write transaction when used for a removal decision.
    The join also supports a future composite FK that includes user.id.
    """
    quote = connection.dialect.identifier_preparer.quote_identifier
    for fk in foreign_key_inventory(connection):
        if fk["parent_table"] != "user":
            continue
        predicate = " AND ".join(
            f"c.{quote(child)} = p.{quote(parent)}"
            for child, parent in zip(fk["child_columns"], fk["parent_columns"])
        )
        if connection.execute(text(
            f"SELECT 1 FROM {quote(fk['child_table'])} AS c "
            f"JOIN {quote('user')} AS p ON {predicate} WHERE p.id=:target LIMIT 1"
        ), {"target": target_id}).first() is not None:
            return True
    return False


def foreign_key_violations(connection):
    """Return SQLite's content-free orphan identifiers (rowid may be NULL)."""
    return [dict(table=table, rowid=rowid, parent_table=parent, fk_index=index)
            for table, rowid, parent, index in
            connection.exec_driver_sql("PRAGMA foreign_key_check")]


def preflight_admin_remove(engine, user_table, actor_id, target_id):
    """Serialize authorization, physical preflight and fail-closed suspension.

    BEGIN IMMEDIATE excludes competing commits until ours finishes, but cannot
    stop an FK-OFF writer inserting a stale ID after a hard delete commits.
    Therefore even an unreferenced user is retained/suspended for now. A future
    globally enforced/verified writer boundary is a separate T-201 gate. Turning
    on FKs on just this connection would not protect the competing writer.
    """
    with _removal_transaction(engine) as connection:
        actor = connection.execute(select(user_table.c.role, user_table.c.suspended).where(
            user_table.c.id == actor_id)).mappings().first()
        if not actor or actor["suspended"] or actor["role"] != "admin":
            return {"error": "admin only", "status": 403}
        target = connection.execute(select(user_table.c.name, user_table.c.role).where(
            user_table.c.id == target_id)).mappings().first()
        if target is None:
            return {"error": "not found", "status": 404}
        if target["role"] == "admin":
            return {"error": "admin accounts can't be actioned here", "status": 400}
        linked = user_reference_exists(connection, target_id)
        connection.execute(user_table.update().where(user_table.c.id == target_id).values(suspended=True))
        note = (f"{target['name']} has linked activity — suspended instead." if linked
                else f"{target['name']} suspended instead.")
    # Return success only after the transaction has committed.
    return {"ok": True, "note": note}
