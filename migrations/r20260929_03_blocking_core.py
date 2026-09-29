"""T-107 directed blocking persistence.

Additive blocking storage only. This revision does not import ownerless
legacy social rows, enable production ownership-v2, add reports/reviewer
access, or globally enable SQLite foreign keys.
"""

from pathlib import Path


REVISION = "20260929_03_blocking_core"
DOWN_REVISION = "20260928_02_owned_social_schema"
SCHEMA_MANIFEST_PATH = Path(__file__).with_name(
    "20260929_03_blocking_core.json"
)

BLOCK_TABLES = (
    "user_block",
    "block_event",
)

UPGRADE_SQL = (
    """
    CREATE TABLE user_block (
        id INTEGER NOT NULL PRIMARY KEY,
        blocker_id INTEGER NOT NULL,
        blocked_id INTEGER NOT NULL,
        active BOOLEAN NOT NULL,
        version INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        unblocked_at DATETIME,

        CONSTRAINT uq_user_block_direction
            UNIQUE (blocker_id, blocked_id),
        CONSTRAINT ck_user_block_distinct
            CHECK (blocker_id <> blocked_id),
        CONSTRAINT ck_user_block_active
            CHECK (active IN (0, 1)),
        CONSTRAINT ck_user_block_version
            CHECK (version >= 1),
        CONSTRAINT ck_user_block_unblocked_timestamp
            CHECK (
                (active = 1 AND unblocked_at IS NULL)
                OR
                (active = 0 AND unblocked_at IS NOT NULL)
            ),

        FOREIGN KEY(blocker_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(blocked_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX ix_user_block_blocker_active
    ON user_block(blocker_id, active)
    """,
    """
    CREATE INDEX ix_user_block_blocked_active
    ON user_block(blocked_id, active)
    """,
    """
    CREATE TABLE block_event (
        id INTEGER NOT NULL PRIMARY KEY,
        user_block_id INTEGER NOT NULL,
        actor_user_id INTEGER NOT NULL,
        block_version INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        previous_state TEXT NOT NULL,
        next_state TEXT NOT NULL,
        created_at DATETIME NOT NULL,

        CONSTRAINT uq_block_event_version
            UNIQUE (user_block_id, block_version),
        CONSTRAINT ck_block_event_version
            CHECK (block_version >= 1),
        CONSTRAINT ck_block_event_type
            CHECK (event_type IN ('blocked', 'unblocked')),
        CONSTRAINT ck_block_event_previous_state
            CHECK (previous_state IN ('blocked', 'unblocked')),
        CONSTRAINT ck_block_event_next_state
            CHECK (next_state IN ('blocked', 'unblocked')),
        CONSTRAINT ck_block_event_effective_change
            CHECK (previous_state <> next_state),
        CONSTRAINT ck_block_event_type_matches_state
            CHECK (
                (event_type = 'blocked' AND next_state = 'blocked')
                OR
                (event_type = 'unblocked' AND next_state = 'unblocked')
            ),

        FOREIGN KEY(user_block_id)
            REFERENCES user_block(id) ON DELETE RESTRICT,
        FOREIGN KEY(actor_user_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX ix_block_event_block_created
    ON block_event(user_block_id, created_at)
    """,
)

DOWNGRADE_SQL = (
    "DROP TABLE block_event",
    "DROP TABLE user_block",
)

CHECKSUM_PAYLOAD = {
    "revision": REVISION,
    "down_revision": DOWN_REVISION,
    "upgrade_sql": UPGRADE_SQL,
    "downgrade_sql": DOWNGRADE_SQL,
    "tables": BLOCK_TABLES,
}


def upgrade(connection):
    for statement in UPGRADE_SQL:
        connection.exec_driver_sql(statement)


def downgrade(connection):
    for statement in DOWNGRADE_SQL:
        connection.exec_driver_sql(statement)


def nonempty_tables(connection):
    nonempty = []
    for table_name in BLOCK_TABLES:
        count = connection.exec_driver_sql(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).scalar()
        if count:
            nonempty.append((table_name, int(count)))
    return nonempty


def verify(connection):
    problems = []
    invariant_queries = (
        (
            "block active/unblocked timestamp mismatch",
            """
            SELECT COUNT(*)
            FROM user_block
            WHERE NOT (
                (active = 1 AND unblocked_at IS NULL)
                OR
                (active = 0 AND unblocked_at IS NOT NULL)
            )
            """,
        ),
        (
            "block event actor differs from blocker",
            """
            SELECT COUNT(*)
            FROM block_event AS e
            JOIN user_block AS b ON b.id = e.user_block_id
            WHERE e.actor_user_id <> b.blocker_id
            """,
        ),
        (
            "block version/event history mismatch",
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    b.id,
                    b.version,
                    COUNT(e.id) AS event_count,
                    COALESCE(MAX(e.block_version), 0) AS max_version
                FROM user_block AS b
                LEFT JOIN block_event AS e ON e.user_block_id = b.id
                GROUP BY b.id
                HAVING event_count <> b.version
                   OR max_version <> b.version
            )
            """,
        ),
        (
            "block latest event/state mismatch",
            """
            SELECT COUNT(*)
            FROM user_block AS b
            LEFT JOIN block_event AS e
              ON e.user_block_id = b.id
             AND e.block_version = b.version
            WHERE e.id IS NULL
               OR e.next_state <> CASE
                   WHEN b.active = 1 THEN 'blocked'
                   ELSE 'unblocked'
               END
            """,
        ),
    )
    for label, query in invariant_queries:
        count = int(connection.exec_driver_sql(query).scalar() or 0)
        if count:
            problems.append(f"{label}: {count}")
    return problems
