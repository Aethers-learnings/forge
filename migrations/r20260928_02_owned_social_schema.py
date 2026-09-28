"""Additive owned-social schema for approved D-012–D-015.

This revision creates storage only. It does not:
- migrate/quarantine legacy social rows beyond leaving them untouched;
- switch any HTTP/socket/client behavior;
- enable SQLite foreign-key enforcement globally;
- authorize production rollout.
"""

from pathlib import Path


REVISION = "20260928_02_owned_social_schema"
DOWN_REVISION = "20260928_01_pre_migrations"
SCHEMA_MANIFEST_PATH = Path(__file__).with_name(
    "20260928_02_owned_social_schema.json"
)

OWNED_SOCIAL_TABLES = (
    "network_edge",
    "endorsement",
    "direct_conversation",
    "conversation_member",
    "direct_message",
    "ownership_event",
)

OWNED_SOCIAL_TRIGGERS = (
    "trg_conversation_member_endpoint_insert",
    "trg_conversation_member_endpoint_update",
)

UPGRADE_SQL = (
    """
    CREATE TABLE network_edge (
        id INTEGER NOT NULL PRIMARY KEY,
        user_low_id INTEGER NOT NULL,
        user_high_id INTEGER NOT NULL,
        requester_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        state TEXT NOT NULL,
        version INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        requested_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        accepted_at DATETIME,
        ended_at DATETIME,
        changed_by_user_id INTEGER NOT NULL,

        CONSTRAINT uq_network_edge_pair
            UNIQUE (user_low_id, user_high_id),

        CONSTRAINT ck_network_edge_order
            CHECK (user_low_id < user_high_id),

        CONSTRAINT ck_network_edge_parties
            CHECK (
                (
                    requester_id = user_low_id
                    AND recipient_id = user_high_id
                )
                OR
                (
                    requester_id = user_high_id
                    AND recipient_id = user_low_id
                )
            ),

        CONSTRAINT ck_network_edge_state
            CHECK (
                state IN (
                    'pending',
                    'accepted',
                    'ignored',
                    'cancelled',
                    'disconnected'
                )
            ),

        CONSTRAINT ck_network_edge_version
            CHECK (version >= 1),

        FOREIGN KEY(user_low_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(user_high_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(requester_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(recipient_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(changed_by_user_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX ix_network_edge_low_state
    ON network_edge(user_low_id, state)
    """,
    """
    CREATE INDEX ix_network_edge_high_state
    ON network_edge(user_high_id, state)
    """,
    """
    CREATE INDEX ix_network_edge_recipient_state
    ON network_edge(recipient_id, state)
    """,
    """
    CREATE INDEX ix_network_edge_requester_state
    ON network_edge(requester_id, state)
    """,

    """
    CREATE TABLE endorsement (
        id INTEGER NOT NULL PRIMARY KEY,
        network_edge_id INTEGER NOT NULL,
        endorser_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        skill_key TEXT NOT NULL,
        skill_label TEXT,
        version INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        revoked_at DATETIME,

        CONSTRAINT uq_endorsement_actor_recipient_skill
            UNIQUE (endorser_id, recipient_id, skill_key),

        CONSTRAINT ck_endorsement_distinct_users
            CHECK (endorser_id <> recipient_id),

        CONSTRAINT ck_endorsement_version
            CHECK (version >= 1),

        FOREIGN KEY(network_edge_id)
            REFERENCES network_edge(id) ON DELETE RESTRICT,
        FOREIGN KEY(endorser_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(recipient_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX ix_endorsement_recipient_skill_active
    ON endorsement(recipient_id, skill_key)
    WHERE revoked_at IS NULL
    """,

    """
    CREATE TABLE direct_conversation (
        id INTEGER NOT NULL PRIMARY KEY,
        public_id TEXT NOT NULL,
        user_low_id INTEGER NOT NULL,
        user_high_id INTEGER NOT NULL,
        created_by_user_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        last_seq INTEGER NOT NULL DEFAULT 0,

        CONSTRAINT uq_direct_conversation_public_id
            UNIQUE (public_id),

        CONSTRAINT uq_direct_conversation_pair
            UNIQUE (user_low_id, user_high_id),

        CONSTRAINT ck_direct_conversation_order
            CHECK (user_low_id < user_high_id),

        CONSTRAINT ck_direct_conversation_creator
            CHECK (
                created_by_user_id = user_low_id
                OR created_by_user_id = user_high_id
            ),

        CONSTRAINT ck_direct_conversation_last_seq
            CHECK (last_seq >= 0),

        FOREIGN KEY(user_low_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(user_high_id)
            REFERENCES user(id) ON DELETE RESTRICT,
        FOREIGN KEY(created_by_user_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX ix_direct_conversation_high_low
    ON direct_conversation(user_high_id, user_low_id)
    """,

    """
    CREATE TABLE conversation_member (
        conversation_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at DATETIME NOT NULL,
        last_read_seq INTEGER NOT NULL DEFAULT 0,
        read_at DATETIME,

        PRIMARY KEY (conversation_id, user_id),

        CONSTRAINT ck_conversation_member_last_read
            CHECK (last_read_seq >= 0),

        FOREIGN KEY(conversation_id)
            REFERENCES direct_conversation(id) ON DELETE RESTRICT,
        FOREIGN KEY(user_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX ix_conversation_member_user_conversation
    ON conversation_member(user_id, conversation_id)
    """,

    """
    CREATE TRIGGER trg_conversation_member_endpoint_insert
    BEFORE INSERT ON conversation_member
    FOR EACH ROW
    WHEN NOT EXISTS (
        SELECT 1
        FROM direct_conversation AS c
        WHERE c.id = NEW.conversation_id
          AND (
              NEW.user_id = c.user_low_id
              OR NEW.user_id = c.user_high_id
          )
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'conversation member must be a conversation endpoint'
        );
    END
    """,
    """
    CREATE TRIGGER trg_conversation_member_endpoint_update
    BEFORE UPDATE OF conversation_id, user_id ON conversation_member
    FOR EACH ROW
    WHEN NOT EXISTS (
        SELECT 1
        FROM direct_conversation AS c
        WHERE c.id = NEW.conversation_id
          AND (
              NEW.user_id = c.user_low_id
              OR NEW.user_id = c.user_high_id
          )
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'conversation member must be a conversation endpoint'
        );
    END
    """,

    """
    CREATE TABLE direct_message (
        conversation_id INTEGER NOT NULL,
        seq INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        client_message_id TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at DATETIME NOT NULL,

        PRIMARY KEY (conversation_id, seq),

        CONSTRAINT uq_direct_message_retry
            UNIQUE (
                conversation_id,
                sender_id,
                client_message_id
            ),

        CONSTRAINT ck_direct_message_seq
            CHECK (seq >= 1),

        CONSTRAINT ck_direct_message_text
            CHECK (
                length(trim(text)) >= 1
                AND length(text) <= 4000
            ),

        FOREIGN KEY(conversation_id, sender_id)
            REFERENCES conversation_member(
                conversation_id,
                user_id
            )
            ON DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE ownership_event (
        id INTEGER NOT NULL PRIMARY KEY,
        network_edge_id INTEGER,
        endorsement_id INTEGER,
        conversation_id INTEGER,
        actor_user_id INTEGER NOT NULL,
        entity_version INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        previous_state TEXT,
        next_state TEXT,
        created_at DATETIME NOT NULL,

        CONSTRAINT ck_ownership_event_entity
            CHECK (
                (network_edge_id IS NOT NULL)
                + (endorsement_id IS NOT NULL)
                + (conversation_id IS NOT NULL)
                = 1
            ),

        CONSTRAINT ck_ownership_event_version
            CHECK (entity_version >= 1),

        CONSTRAINT ck_ownership_event_type
            CHECK (length(trim(event_type)) >= 1),

        FOREIGN KEY(network_edge_id)
            REFERENCES network_edge(id) ON DELETE RESTRICT,
        FOREIGN KEY(endorsement_id)
            REFERENCES endorsement(id) ON DELETE RESTRICT,
        FOREIGN KEY(conversation_id)
            REFERENCES direct_conversation(id) ON DELETE RESTRICT,
        FOREIGN KEY(actor_user_id)
            REFERENCES user(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE UNIQUE INDEX ux_ownership_event_network_version_type
    ON ownership_event(
        network_edge_id,
        entity_version,
        event_type
    )
    WHERE network_edge_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX ux_ownership_event_endorsement_version_type
    ON ownership_event(
        endorsement_id,
        entity_version,
        event_type
    )
    WHERE endorsement_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX ux_ownership_event_conversation_version_type
    ON ownership_event(
        conversation_id,
        entity_version,
        event_type
    )
    WHERE conversation_id IS NOT NULL
    """,
)

DOWNGRADE_SQL = (
    "DROP TRIGGER IF EXISTS trg_conversation_member_endpoint_update",
    "DROP TRIGGER IF EXISTS trg_conversation_member_endpoint_insert",
    "DROP TABLE ownership_event",
    "DROP TABLE direct_message",
    "DROP TABLE conversation_member",
    "DROP TABLE direct_conversation",
    "DROP TABLE endorsement",
    "DROP TABLE network_edge",
)

CHECKSUM_PAYLOAD = {
    "revision": REVISION,
    "down_revision": DOWN_REVISION,
    "upgrade_sql": UPGRADE_SQL,
    "downgrade_sql": DOWNGRADE_SQL,
    "tables": OWNED_SOCIAL_TABLES,
    "triggers": OWNED_SOCIAL_TRIGGERS,
}


def upgrade(connection):
    for statement in UPGRADE_SQL:
        connection.exec_driver_sql(statement)


def downgrade(connection):
    for statement in DOWNGRADE_SQL:
        connection.exec_driver_sql(statement)


def nonempty_tables(connection):
    nonempty = []

    for table_name in OWNED_SOCIAL_TABLES:
        count = connection.exec_driver_sql(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).scalar()

        if count:
            nonempty.append((table_name, int(count)))

    return nonempty


def verify(connection):
    """Return committed-data invariant problems for this revision."""
    problems = []

    trigger_rows = connection.exec_driver_sql(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'trigger'
        """
    ).fetchall()
    triggers = {row[0] for row in trigger_rows}

    missing_triggers = sorted(
        set(OWNED_SOCIAL_TRIGGERS) - triggers
    )

    if missing_triggers:
        problems.append(
            "missing triggers: " + ", ".join(missing_triggers)
        )

    invariant_queries = (
        (
            "endorsement endpoint mismatch",
            """
            SELECT COUNT(*)
            FROM endorsement AS e
            JOIN network_edge AS n
              ON n.id = e.network_edge_id
            WHERE NOT (
                (
                    e.endorser_id = n.user_low_id
                    AND e.recipient_id = n.user_high_id
                )
                OR
                (
                    e.endorser_id = n.user_high_id
                    AND e.recipient_id = n.user_low_id
                )
            )
            """,
        ),
        (
            "active endorsement on non-accepted edge",
            """
            SELECT COUNT(*)
            FROM endorsement AS e
            JOIN network_edge AS n
              ON n.id = e.network_edge_id
            WHERE e.revoked_at IS NULL
              AND n.state <> 'accepted'
            """,
        ),
        (
            "conversation member is not endpoint",
            """
            SELECT COUNT(*)
            FROM conversation_member AS m
            JOIN direct_conversation AS c
              ON c.id = m.conversation_id
            WHERE m.user_id NOT IN (
                c.user_low_id,
                c.user_high_id
            )
            """,
        ),
        (
            "conversation does not have exactly two endpoint members",
            """
            SELECT COUNT(*)
            FROM (
                SELECT c.id
                FROM direct_conversation AS c
                LEFT JOIN conversation_member AS m
                  ON m.conversation_id = c.id
                GROUP BY c.id
                HAVING COUNT(m.user_id) <> 2
                   OR SUM(
                       CASE
                           WHEN m.user_id IN (
                               c.user_low_id,
                               c.user_high_id
                           )
                           THEN 1
                           ELSE 0
                       END
                   ) <> 2
            )
            """,
        ),
        (
            "conversation last_seq mismatch",
            """
            SELECT COUNT(*)
            FROM (
                SELECT c.id
                FROM direct_conversation AS c
                LEFT JOIN direct_message AS d
                  ON d.conversation_id = c.id
                GROUP BY c.id
                HAVING c.last_seq <> COALESCE(MAX(d.seq), 0)
                   OR COUNT(d.seq) <> c.last_seq
            )
            """,
        ),
        (
            "member read cursor out of bounds",
            """
            SELECT COUNT(*)
            FROM conversation_member AS m
            JOIN direct_conversation AS c
              ON c.id = m.conversation_id
            WHERE m.last_read_seq < 0
               OR m.last_read_seq > c.last_seq
               OR (
                   m.last_read_seq > 0
                   AND NOT EXISTS (
                       SELECT 1
                       FROM direct_message AS d
                       WHERE d.conversation_id = m.conversation_id
                         AND d.seq = m.last_read_seq
                   )
               )
            """,
        ),
    )

    for label, query in invariant_queries:
        count = int(
            connection.exec_driver_sql(query).scalar() or 0
        )

        if count:
            problems.append(f"{label}: {count}")

    return problems
