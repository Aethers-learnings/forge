#!/usr/bin/env python3
"""Apply the T-107 blocking-core backend increment to a clean Forge checkout.

Temporary developer helper. It uses only repository files plus an in-memory SQLite
engine to generate the revision manifest. It never opens instance/forge.db.
Run from the repository root with the project's Python environment.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path.cwd().resolve()
REAL_DB = ROOT / "instance" / "forge.db"


def fail(message: str) -> None:
    raise SystemExit(message)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and new in text:
        print(f"{label}: already applied")
        return text
    fail(f"{label}: expected exactly one source match, found {count}")


def ensure_clean_target() -> None:
    if not (ROOT / ".git").exists():
        fail("Run this helper from the Forge repository root.")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], text=True
    ).strip()
    if branch != "manual/t107-blocking-core":
        fail(f"Refusing to edit branch {branch!r}; expected manual/t107-blocking-core")
    status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    allowed = {"?? scripts/t107_apply_backend.py"}
    dirty = {line for line in status.splitlines() if line not in allowed}
    if dirty:
        fail("Working tree has unexpected changes:\n" + "\n".join(sorted(dirty)))
    if REAL_DB.exists():
        print("Real instance database exists; helper will not open or modify it.")


ensure_clean_target()

# ---------------------------------------------------------------------------
# 1. Add additive migration revision 03.
# ---------------------------------------------------------------------------

migration_path = ROOT / "migrations" / "r20260929_03_blocking_core.py"
migration_source = textwrap.dedent(
    r'''
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
    '''
).lstrip()
migration_path.write_text(migration_source)

# Generate the new committed schema manifest from a disposable in-memory DB
# while forge_migrations still knows only revision 02.
import forge_migrations  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from migrations import r20260929_03_blocking_core as block_migration  # noqa: E402

engine = create_engine("sqlite://")
try:
    forge_migrations.initialize_fresh_database(engine)
    with forge_migrations._sqlite_write_transaction(engine) as connection:
        block_migration.upgrade(connection)
    manifest = {
        "revision": block_migration.REVISION,
        "schema": forge_migrations.schema_snapshot(engine),
    }
    (ROOT / "migrations" / "20260929_03_blocking_core.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
finally:
    engine.dispose()

# ---------------------------------------------------------------------------
# 2. Register revision 03.
# ---------------------------------------------------------------------------

path = ROOT / "forge_migrations.py"
src = path.read_text()
src = replace_once(
    src,
    """from migrations import (\n    r20260928_02_owned_social_schema as owned_social_schema,\n)\n""",
    """from migrations import (\n    r20260928_02_owned_social_schema as owned_social_schema,\n    r20260929_03_blocking_core as blocking_core,\n)\n""",
    "migration import",
)
src = replace_once(
    src,
    """MIGRATION_MODULES = (\n    owned_social_schema,\n)\n""",
    """MIGRATION_MODULES = (\n    owned_social_schema,\n    blocking_core,\n)\n""",
    "migration registry",
)
path.write_text(src)

# ---------------------------------------------------------------------------
# 3. Add ORM mappings beside the existing owned-social mappings.
# ---------------------------------------------------------------------------

path = ROOT / "forge_backend.py"
src = path.read_text()
marker = "\n\nclass AlumniVerification(db.Model):"
models = r'''

class UserBlock(db.Model):
    __tablename__ = "user_block"
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    active = db.Column(db.Boolean, nullable=False)
    version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
    unblocked_at = db.Column(db.DateTime)
    __table_args__ = (
        db.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_direction"),
        db.CheckConstraint("blocker_id <> blocked_id", name="ck_user_block_distinct"),
        db.CheckConstraint("active IN (0, 1)", name="ck_user_block_active"),
        db.CheckConstraint("version >= 1", name="ck_user_block_version"),
        db.CheckConstraint(
            "((active = 1 AND unblocked_at IS NULL) OR "
            "(active = 0 AND unblocked_at IS NOT NULL))",
            name="ck_user_block_unblocked_timestamp",
        ),
        db.Index("ix_user_block_blocker_active", "blocker_id", "active"),
        db.Index("ix_user_block_blocked_active", "blocked_id", "active"),
    )


class BlockEvent(db.Model):
    __tablename__ = "block_event"
    id = db.Column(db.Integer, primary_key=True)
    user_block_id = db.Column(db.Integer, db.ForeignKey("user_block.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    block_version = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.Text, nullable=False)
    previous_state = db.Column(db.Text, nullable=False)
    next_state = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("user_block_id", "block_version", name="uq_block_event_version"),
        db.CheckConstraint("block_version >= 1", name="ck_block_event_version"),
        db.CheckConstraint("event_type IN ('blocked', 'unblocked')", name="ck_block_event_type"),
        db.CheckConstraint("previous_state IN ('blocked', 'unblocked')", name="ck_block_event_previous_state"),
        db.CheckConstraint("next_state IN ('blocked', 'unblocked')", name="ck_block_event_next_state"),
        db.CheckConstraint("previous_state <> next_state", name="ck_block_event_effective_change"),
        db.CheckConstraint(
            "((event_type = 'blocked' AND next_state = 'blocked') OR "
            "(event_type = 'unblocked' AND next_state = 'unblocked'))",
            name="ck_block_event_type_matches_state",
        ),
        db.Index("ix_block_event_block_created", "user_block_id", "created_at"),
    )
'''
if "class UserBlock(db.Model):" not in src:
    if marker not in src:
        fail("ORM insertion marker not found")
    src = src.replace(marker, models + marker, 1)
path.write_text(src)

# ---------------------------------------------------------------------------
# 4. Extend the serialized owned-social service.
# ---------------------------------------------------------------------------

path = ROOT / "forge_routes" / "owned_social.py"
src = path.read_text()
src = replace_once(
    src,
    "from sqlalchemy import func, or_, select\n",
    "from sqlalchemy import and_, func, or_, select\n",
    "SQLAlchemy imports",
)
src = replace_once(
    src,
    """        self.event = models.OwnershipEvent.__table__\n""",
    """        self.event = models.OwnershipEvent.__table__\n        self.block = models.UserBlock.__table__\n        self.block_event = models.BlockEvent.__table__\n""",
    "blocking table registration",
)
edge_helper = """    def _edge_pair(self, connection, low, high):\n        return _row(connection, select(self.edge).where(\n            self.edge.c.user_low_id == low, self.edge.c.user_high_id == high))\n"""
helpers = edge_helper + r'''

    def _own_block(self, connection, blocker_id, blocked_id):
        return _row(connection, select(self.block).where(
            self.block.c.blocker_id == blocker_id,
            self.block.c.blocked_id == blocked_id))

    def _pair_blocked(self, connection, first_id, second_id):
        return _row(connection, select(self.block.c.id).where(
            self.block.c.active.is_(True),
            or_(
                and_(self.block.c.blocker_id == first_id,
                     self.block.c.blocked_id == second_id),
                and_(self.block.c.blocker_id == second_id,
                     self.block.c.blocked_id == first_id),
            )).limit(1)) is not None

    def _ensure_pair_available(self, connection, first_id, second_id):
        if self._pair_blocked(connection, first_id, second_id):
            raise OperationUnavailable("operation unavailable")

    def _block_event(self, connection, actor_id, block_id, version,
                     previous_state, next_state, now):
        connection.execute(self.block_event.insert().values(
            user_block_id=block_id,
            actor_user_id=actor_id,
            block_version=version,
            event_type=next_state,
            previous_state=previous_state,
            next_state=next_state,
            created_at=now,
        ))
'''
src = replace_once(src, edge_helper, helpers, "blocking helpers")

suggestions_marker = """    def suggestions(self, actor, *, now=None):\n"""
own_blocks = r'''    def own_blocks(self, actor, *, after=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 50 or (
                after is not None and (type(after) is not int or after < 0)):
            raise Invalid("invalid cursor or limit")
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            statement = select(self.block).where(
                self.block.c.blocker_id == user["id"],
                self.block.c.active.is_(True))
            if after is not None:
                statement = statement.where(self.block.c.id > after)
            rows = connection.execute(statement.order_by(
                self.block.c.id).limit(limit + 1)).mappings().all()
            return [dict(row) for row in rows[:limit]], len(rows) > limit

'''
src = replace_once(src, suggestions_marker, own_blocks + suggestions_marker, "own block list")
src = replace_once(
    src,
    """                low, high = _pair(user[\"id\"], peer[\"id\"])\n                edge = self._edge_pair(connection, low, high)\n""",
    """                low, high = _pair(user[\"id\"], peer[\"id\"])\n                if self._pair_blocked(connection, low, high):\n                    continue\n                edge = self._edge_pair(connection, low, high)\n""",
    "suggestion blocking",
)
request_marker = """    def request(self, actor, target_id, expected_version, *, now=None):\n"""
set_block = r'''    def set_block(self, actor, target_id, desired, expected_version,
                  *, now=None, with_status=False):
        if type(desired) is not bool:
            raise Invalid("desired state must be boolean")
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            if type(target_id) is not int or target_id < 1 or target_id == user["id"]:
                raise NotFound("user unavailable")
            existing = self._own_block(connection, user["id"], target_id)
            if existing is None:
                self._peer(connection, target_id, discoverable=True)
            current = bool(existing and existing["active"])
            current_version = existing["version"] if existing else 0
            if current == desired:
                _retry_version(expected_version, current_version)
                return (existing, False) if with_status else existing
            _version(expected_version, current_version)
            previous_state = "blocked" if current else "unblocked"
            next_state = "blocked" if desired else "unblocked"
            created = existing is None
            if existing is None:
                version = 1
                block_id = connection.execute(self.block.insert().values(
                    blocker_id=user["id"], blocked_id=target_id, active=True,
                    version=version, created_at=now, updated_at=now,
                    unblocked_at=None)).inserted_primary_key[0]
            else:
                version = existing["version"] + 1
                block_id = existing["id"]
                connection.execute(self.block.update().where(
                    self.block.c.id == block_id).values(
                        active=desired, version=version, updated_at=now,
                        unblocked_at=None if desired else now))
            if desired:
                low, high = _pair(user["id"], target_id)
                edge = self._edge_pair(connection, low, high)
                if edge and edge["state"] in ("pending", "accepted"):
                    edge_state = "cancelled" if edge["state"] == "pending" else "disconnected"
                    edge_version = edge["version"] + 1
                    connection.execute(self.edge.update().where(
                        self.edge.c.id == edge["id"]).values(
                            state=edge_state, version=edge_version,
                            updated_at=now, accepted_at=None, ended_at=now,
                            changed_by_user_id=user["id"]))
                    self._event(connection, user["id"], "network_edge_id",
                                edge["id"], edge_version, edge_state,
                                edge["state"], edge_state, now)
                if edge:
                    endorsements = connection.execute(select(self.endorsement).where(
                        self.endorsement.c.network_edge_id == edge["id"],
                        self.endorsement.c.revoked_at.is_(None))).mappings().all()
                    for endorsement in endorsements:
                        endorsement_version = endorsement["version"] + 1
                        connection.execute(self.endorsement.update().where(
                            self.endorsement.c.id == endorsement["id"]).values(
                                revoked_at=now, updated_at=now,
                                version=endorsement_version))
                        self._event(connection, user["id"], "endorsement_id",
                                    endorsement["id"], endorsement_version,
                                    "revoked", "active", "revoked", now)
            self._block_event(connection, user["id"], block_id, version,
                              previous_state, next_state, now)
            result = _row(connection, select(self.block).where(
                self.block.c.id == block_id))
            return (result, created) if with_status else result

'''
src = replace_once(src, request_marker, set_block + request_marker, "block mutation")
src = replace_once(
    src,
    """            self._peer(connection, target_id, discoverable=True)\n            edge = self._edge_pair(connection, low, high)\n""",
    """            self._peer(connection, target_id, discoverable=True)\n            self._ensure_pair_available(connection, low, high)\n            edge = self._edge_pair(connection, low, high)\n""",
    "request block enforcement",
)
src = replace_once(
    src,
    """            if required_actor is not None and required_actor != user[\"id\"]:\n                raise Forbidden(\"wrong endpoint\")\n            _version(expected_version, edge[\"version\"])\n""",
    """            if required_actor is not None and required_actor != user[\"id\"]:\n                raise Forbidden(\"wrong endpoint\")\n            if action == \"accept\":\n                self._ensure_pair_available(connection, edge[\"user_low_id\"], edge[\"user_high_id\"])\n            _version(expected_version, edge[\"version\"])\n""",
    "accept block enforcement",
)
src = replace_once(
    src,
    """            recipient = edge[\"user_high_id\"] if user[\"id\"] == edge[\"user_low_id\"] else edge[\"user_low_id\"]\n            endorsement = _row(connection, select(self.endorsement).where(\n""",
    """            recipient = edge[\"user_high_id\"] if user[\"id\"] == edge[\"user_low_id\"] else edge[\"user_low_id\"]\n            if desired:\n                self._ensure_pair_available(connection, edge[\"user_low_id\"], edge[\"user_high_id\"])\n            endorsement = _row(connection, select(self.endorsement).where(\n""",
    "endorsement block enforcement",
)
src = replace_once(
    src,
    """            self._peer(connection, peer_id, discoverable=True)\n            edge = self._edge_pair(connection, low, high)\n""",
    """            self._peer(connection, peer_id, discoverable=True)\n            self._ensure_pair_available(connection, low, high)\n            edge = self._edge_pair(connection, low, high)\n""",
    "conversation block enforcement",
)
src = replace_once(
    src,
    """            if prior:\n                if prior[\"text\"] != normalized:\n                    raise Conflict(\"retry key already used\")\n                return (prior, False) if with_status else prior\n            peer_id = (conversation[\"user_high_id\"] if user[\"id\"] == conversation[\"user_low_id\"]\n""",
    """            if prior:\n                if prior[\"text\"] != normalized:\n                    raise Conflict(\"retry key already used\")\n                return (prior, False) if with_status else prior\n            self._ensure_pair_available(connection, conversation[\"user_low_id\"], conversation[\"user_high_id\"])\n            peer_id = (conversation[\"user_high_id\"] if user[\"id\"] == conversation[\"user_low_id\"]\n""",
    "send block enforcement",
)
src = replace_once(
    src,
    """            if edge[\"state\"] != \"accepted\" or not peer or peer[\"suspended\"]:\n                return []\n""",
    """            if (edge[\"state\"] != \"accepted\" or not peer or peer[\"suspended\"]\n                    or self._pair_blocked(connection, edge[\"user_low_id\"], edge[\"user_high_id\"])):\n                return []\n""",
    "active endorsement projection",
)
src = replace_once(
    src,
    """            active = bool(row and row[\"revoked_at\"] is None and edge[\"state\"] == \"accepted\")\n""",
    """            blocked = self._pair_blocked(connection, edge[\"user_low_id\"], edge[\"user_high_id\"])\n            active = bool(row and row[\"revoked_at\"] is None\n                          and edge[\"state\"] == \"accepted\" and not blocked)\n""",
    "endorsement status projection",
)
src = replace_once(
    src,
    """            edge = self._edge_pair(connection, conversation[\"user_low_id\"], conversation[\"user_high_id\"])\n            return {\"peer_id\": peer_id, \"name\": peer[\"name\"] if peer else \"Member\",\n                    \"color\": peer[\"color\"] if peer else \"\", \"read_only\": not (\n                        peer and not peer[\"suspended\"] and edge and edge[\"state\"] == \"accepted\"),\n                    \"last_seq\": conversation[\"last_seq\"]}\n""",
    """            edge = self._edge_pair(connection, conversation[\"user_low_id\"], conversation[\"user_high_id\"])\n            blocked = self._pair_blocked(connection, conversation[\"user_low_id\"], conversation[\"user_high_id\"])\n            return {\"peer_id\": peer_id, \"name\": peer[\"name\"] if peer else \"Member\",\n                    \"color\": peer[\"color\"] if peer else \"\", \"read_only\": not (\n                        peer and not peer[\"suspended\"] and edge and\n                        edge[\"state\"] == \"accepted\" and not blocked),\n                    \"last_seq\": conversation[\"last_seq\"]}\n""",
    "conversation read-only projection",
)
path.write_text(src)

# ---------------------------------------------------------------------------
# 5. Add ownership-v2 block HTTP contract.
# ---------------------------------------------------------------------------

path = ROOT / "forge_routes" / "owned_social_http.py"
src = path.read_text()
conversations_marker = """    @safe\n    def conversations(svc, user):\n"""
block_handlers = r'''    @safe
    def blocks(svc, user):
        if set(request.args) - {"limit", "cursor"}:
            raise Invalid("unknown query parameter")
        after = cursor(request.args["cursor"], user, "blocks") if "cursor" in request.args else None
        rows, more = svc.own_blocks(user, after=after, limit=page_limit("limit"))
        output = []
        for row in rows:
            peer = db.session.get(models.User, row["blocked_id"])
            output.append({
                "targetUserId": row["blocked_id"],
                "name": peer.name if peer else "Member",
                "color": peer.color if peer else "",
                "version": row["version"],
            })
        response = jsonify(blocks=output,
                           nextCursor=encode(user, "blocks", rows[-1]["id"])
                           if more and rows else None)
        return response

    @safe
    def set_block(svc, user, target_id):
        data = body({"blocked", "expectedVersion"})
        if type(data["blocked"]) is not bool:
            raise Invalid("invalid desired state")
        row, created = svc.set_block(
            user, positive(target_id), data["blocked"],
            version(data["expectedVersion"]), with_status=True)
        return jsonify(ok=True, blocked=data["blocked"],
                       version=row["version"] if row else 0), 201 if created else 200

'''
src = replace_once(src, conversations_marker, block_handlers + conversations_marker, "block HTTP handlers")
src = replace_once(
    src,
    """    patterns = [\n        (\"GET\", re.compile(r\"/api/network\"), network),\n""",
    """    patterns = [\n        (\"GET\", re.compile(r\"/api/network/blocks\"), blocks),\n        (\"PUT\", re.compile(r\"/api/network/blocks/(\\d+)\"), set_block),\n        (\"GET\", re.compile(r\"/api/network\"), network),\n""",
    "block HTTP dispatch",
)
path.write_text(src)

# ---------------------------------------------------------------------------
# 6. Update migration/model regressions and add focused block tests.
# ---------------------------------------------------------------------------

path = ROOT / "tests" / "test_owned_social_models.py"
src = path.read_text()
src = replace_once(
    src,
    "from migrations.r20260928_02_owned_social_schema import OWNED_SOCIAL_TABLES\n",
    "from migrations.r20260928_02_owned_social_schema import OWNED_SOCIAL_TABLES\nfrom migrations.r20260929_03_blocking_core import BLOCK_TABLES\n",
    "model test migration import",
)
src = replace_once(
    src,
    """    forge.OwnershipEvent,\n)\n""",
    """    forge.OwnershipEvent,\n    forge.UserBlock,\n    forge.BlockEvent,\n)\n""",
    "model test list",
)
src = replace_once(
    src,
    """        assert {model.__tablename__ for model in MODELS} == set(OWNED_SOCIAL_TABLES)\n""",
    """        assert {model.__tablename__ for model in MODELS} == (\n            set(OWNED_SOCIAL_TABLES) | set(BLOCK_TABLES)\n        )\n""",
    "model table assertion",
)
path.write_text(src)

path = ROOT / "tests" / "test_migration_tooling.py"
src = path.read_text()
src = replace_once(
    src,
    """from migrations import (\n    r20260928_02_owned_social_schema as owned_social,\n)\n""",
    """from migrations import (\n    r20260928_02_owned_social_schema as owned_social,\n    r20260929_03_blocking_core as blocking,\n)\n""",
    "migration test import",
)
src = replace_once(
    src,
    """    assert status[\"pendingRevisions\"] == [\n        owned_social.REVISION\n    ]\n""",
    """    assert status[\"pendingRevisions\"] == [\n        owned_social.REVISION,\n        blocking.REVISION,\n    ]\n""",
    "pending revision assertion",
)
src = replace_once(
    src,
    """    assert applied == [owned_social.REVISION]\n""",
    """    assert applied == [owned_social.REVISION, blocking.REVISION]\n""",
    "upgrade assertion",
)
src = replace_once(
    src,
    """    assert verified[\"revision\"] == owned_social.REVISION\n""",
    """    assert verified[\"revision\"] == blocking.REVISION\n""",
    "verified head assertion",
)
src = replace_once(
    src,
    """    assert removed == [owned_social.REVISION]\n""",
    """    assert removed == [blocking.REVISION, owned_social.REVISION]\n""",
    "downgrade assertion",
)
first_loop = """    for table_name in owned_social.OWNED_SOCIAL_TABLES:\n        assert inspector.has_table(table_name)\n"""
src = replace_once(
    src,
    first_loop,
    first_loop + "\n    for table_name in blocking.BLOCK_TABLES:\n        assert inspector.has_table(table_name)\n",
    "blocking tables after upgrade",
)
second_loop = """    for table_name in owned_social.OWNED_SOCIAL_TABLES:\n        assert not inspector.has_table(table_name)\n"""
src = replace_once(
    src,
    second_loop,
    second_loop + "\n    for table_name in blocking.BLOCK_TABLES:\n        assert not inspector.has_table(table_name)\n",
    "blocking tables after downgrade",
)
path.write_text(src)

(ROOT / "tests" / "test_blocking_core_service.py").write_text(textwrap.dedent(r'''
    """Focused T-107 blocking-core service coverage."""

    from datetime import timedelta
    from threading import Barrier
    from concurrent.futures import ThreadPoolExecutor

    import pytest
    from sqlalchemy import select

    import forge_backend as forge
    from forge_routes.owned_social import (
        Conflict, NotFound, OperationUnavailable, OwnedSocialService,
    )


    @pytest.fixture
    def blocking_social(app):
        with app.app_context():
            users = [forge.User(username=f"blocking_{i}", password_hash="unused",
                                role="admin" if i == 3 else "trade",
                                name=f"Blocking {i}") for i in range(4)]
            forge.db.session.add_all(users)
            forge.db.session.commit()
            for user in users:
                _ = user.id
            forge.db.session.expunge_all()
            service = OwnedSocialService(forge.db.engine, forge)
            yield service, users
            forge.db.session.remove()


    def accepted(service, a, b):
        edge = service.request(a, b.id, 0)
        return service.transition(b, edge["id"], "accept", edge["version"])


    def test_pending_block_cancels_and_unblock_restores_nothing(blocking_social):
        service, (a, b, _, _) = blocking_social
        edge = service.request(a, b.id, 0)
        blocked = service.set_block(a, b.id, True, 0)
        assert blocked["active"] is True and blocked["version"] == 1
        with service.engine.connect() as connection:
            ended = connection.execute(select(service.edge).where(
                service.edge.c.id == edge["id"])).mappings().one()
        assert ended["state"] == "cancelled" and ended["version"] == 2
        assert [row["blocked_id"] for row in service.own_blocks(a)[0]] == [b.id]
        assert service.own_blocks(b)[0] == []
        with pytest.raises(OperationUnavailable):
            service.request(b, a.id, ended["version"])
        unblocked = service.set_block(a, b.id, False, 1)
        assert unblocked["active"] is False and unblocked["version"] == 2
        with pytest.raises(OperationUnavailable):
            service.request(b, a.id, ended["version"])
        fresh = service.request(b, a.id, ended["version"],
                                now=ended["ended_at"] + timedelta(hours=25))
        assert fresh["state"] == "pending" and fresh["requester_id"] == b.id


    def test_accepted_block_revokes_endorsements_and_retains_history(blocking_social):
        service, (a, b, c, _) = blocking_social
        edge = accepted(service, a, b)
        one = service.endorse(a, edge["id"], True, 0)
        two = service.endorse(b, edge["id"], True, 0)
        slug = service.open_conversation(a, b.id)["public_id"]
        sent = service.send(a, slug, "before block", "before-block")
        service.set_block(a, b.id, True, 0)
        with service.engine.connect() as connection:
            ended = connection.execute(select(service.edge).where(
                service.edge.c.id == edge["id"])).mappings().one()
            endorsements = connection.execute(select(service.endorsement)).mappings().all()
        assert ended["state"] == "disconnected"
        assert {row["id"] for row in endorsements} == {one["id"], two["id"]}
        assert all(row["revoked_at"] is not None for row in endorsements)
        assert service.conversation_info(a, slug)["read_only"]
        assert service.conversation_info(b, slug)["read_only"]
        assert service.history(b, slug)["messages"][0]["text"] == "before block"
        assert service.mark_read(b, slug, sent["seq"]) == sent["seq"]
        with pytest.raises(NotFound):
            service.history(c, slug)
        assert service.send(a, slug, "before block", "before-block") == sent
        with pytest.raises(OperationUnavailable):
            service.send(a, slug, "after block", "after-block")
        with pytest.raises(OperationUnavailable):
            service.open_conversation(b, a.id)
        service.set_block(a, b.id, False, 1)
        with pytest.raises(OperationUnavailable):
            service.send(a, slug, "still disconnected", "after-unblock")


    def test_opposite_direction_blocks_are_independent_but_pair_wide(blocking_social):
        service, (a, b, _, _) = blocking_social
        service.set_block(a, b.id, True, 0)
        service.set_block(b, a.id, True, 0)
        assert [row["blocked_id"] for row in service.own_blocks(a)[0]] == [b.id]
        assert [row["blocked_id"] for row in service.own_blocks(b)[0]] == [a.id]
        service.set_block(a, b.id, False, 1)
        with pytest.raises(OperationUnavailable):
            service.request(a, b.id, 0)
        service.set_block(b, a.id, False, 1)
        assert service.request(a, b.id, 0)["state"] == "pending"


    def test_block_retries_are_idempotent_and_stale_changes_conflict(blocking_social):
        service, (a, b, _, _) = blocking_social
        first = service.set_block(a, b.id, True, 0)
        assert service.set_block(a, b.id, True, 0) == first
        assert service.set_block(a, b.id, True, 1) == first
        with pytest.raises(Conflict):
            service.set_block(a, b.id, False, 0)
        second = service.set_block(a, b.id, False, 1)
        assert service.set_block(a, b.id, False, 2) == second
        third = service.set_block(a, b.id, True, 2)
        with service.engine.connect() as connection:
            events = connection.execute(select(service.block_event).where(
                service.block_event.c.user_block_id == third["id"]).order_by(
                    service.block_event.c.block_version)).mappings().all()
        assert [(event["block_version"], event["event_type"]) for event in events] == [
            (1, "blocked"), (2, "unblocked"), (3, "blocked")]


    def test_blocked_pair_removed_from_suggestions(blocking_social):
        service, (a, b, _, _) = blocking_social
        assert b.id in {row["id"] for row in service.suggestions(a)}
        service.set_block(a, b.id, True, 0)
        assert b.id not in {row["id"] for row in service.suggestions(a)}
        assert a.id not in {row["id"] for row in service.suggestions(b)}


    def test_block_racing_accept_has_serialized_commit_order(blocking_social):
        service, (a, b, _, _) = blocking_social
        edge = service.request(a, b.id, 0)
        gate = Barrier(3)

        def accept():
            gate.wait()
            try:
                return service.transition(b, edge["id"], "accept", 1)["state"]
            except (OperationUnavailable, Conflict):
                return "denied"

        def block():
            gate.wait()
            return bool(service.set_block(a, b.id, True, 0)["active"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(accept)
            second = executor.submit(block)
            gate.wait()
            assert second.result() is True
            assert first.result() in {"accepted", "denied"}

        with service.engine.connect() as connection:
            final = connection.execute(select(service.edge).where(
                service.edge.c.id == edge["id"])).mappings().one()
        assert final["state"] in {"cancelled", "disconnected"}
    '''
).lstrip())

(ROOT / "tests" / "test_blocking_core_migration.py").write_text(textwrap.dedent(r'''
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
    '''
).lstrip())

# Extend the v2 subprocess contract with block API/privacy coverage.
path = ROOT / "tests" / "_v2_contract.py"
src = path.read_text()
if "def test_block_api_pair_wide_privacy_and_history" not in src:
    src += r'''


def test_block_api_pair_wide_privacy_and_history(client, world):
    (a, b, c, admin), svc = world
    actor = forge.db.session.get(forge.User, a)
    peer = forge.db.session.get(forge.User, b)
    edge = svc.request(actor, b, 0)
    svc.transition(peer, edge['id'], 'accept', 1)
    slug = svc.open_conversation(actor, b)['public_id']
    svc.send(actor, slug, 'historical', 'history-1')

    path = f'/api/network/blocks/{b}'
    assert client.put(path, json={'blocked': True}, headers=auth(client, a)).status_code == 428
    assert client.put(path, json={'blocked': True, 'expectedVersion': 0, 'blockerId': a},
                      headers=auth(client, a)).status_code == 400
    created = client.put(path, json={'blocked': True, 'expectedVersion': 0},
                         headers=auth(client, a))
    assert created.status_code == 201 and created.json == {'ok': True, 'blocked': True, 'version': 1}
    retry = client.put(path, json={'blocked': True, 'expectedVersion': 0},
                       headers=auth(client, a))
    assert retry.status_code == 200 and retry.json['version'] == 1
    assert client.put(path, json={'blocked': False, 'expectedVersion': 0},
                      headers=auth(client, a)).status_code == 409

    own = client.get('/api/network/blocks', headers=auth(client, a))
    assert own.status_code == 200
    assert own.headers['Cache-Control'] == 'no-store'
    assert own.json['blocks'][0]['targetUserId'] == b
    assert client.get('/api/network/blocks', headers=auth(client, b)).json['blocks'] == []
    assert client.get('/api/network/blocks', headers=auth(client, c)).json['blocks'] == []
    assert client.get('/api/network/blocks', headers=auth(client, admin)).json['blocks'] == []

    network_b = client.get('/api/network', headers=auth(client, b)).json
    assert network_b['requests'] == [] and network_b['connections'] == []
    assert a not in {row['id'] for row in network_b['suggested']}
    assert post(client, f'/api/network/suggested/{a}/connect', {'expectedVersion': 3},
                auth(client, b)).status_code == 409
    assert post(client, '/api/conversations', {'targetUserId': a},
                auth(client, b)).status_code == 409
    assert post(client, f'/api/conversations/{slug}/messages',
                {'text': 'new', 'clientMessageId': 'blocked-send'},
                auth(client, b)).status_code == 409

    detail = client.get(f'/api/conversations/{slug}', headers=auth(client, b))
    assert detail.status_code == 200 and detail.json['readOnly'] is True
    assert detail.json['messages'][0]['text'] == 'historical'
    assert post(client, f'/api/conversations/{slug}/read', {'upToSequence': 1},
                auth(client, b)).status_code == 200

    unblocked = client.put(path, json={'blocked': False, 'expectedVersion': 1},
                           headers=auth(client, a))
    assert unblocked.status_code == 200 and unblocked.json['version'] == 2
    assert client.get('/api/network/blocks', headers=auth(client, a)).json['blocks'] == []
    assert post(client, f'/api/conversations/{slug}/messages',
                {'text': 'still disconnected', 'clientMessageId': 'after-unblock'},
                auth(client, a)).status_code == 409


def test_block_endpoint_gate_order_and_concealment(client, world):
    (a, b, c, admin), svc = world
    path = f'/api/network/blocks/{b}'
    with client.session_transaction() as session:
        session.clear()
    assert client.put(path, json={}, headers={}).status_code == 401
    assert client.put(path, json={}, headers=auth(client, a, cap=None, csrf=False)).status_code == 403
    assert client.put(path, json={}, headers=auth(client, a, cap=None)).status_code == 426
    assert client.put('/api/network/blocks/999999',
                      json={'blocked': True, 'expectedVersion': 0},
                      headers=auth(client, a)).status_code == 404
    assert client.put(f'/api/network/blocks/{a}',
                      json={'blocked': True, 'expectedVersion': 0},
                      headers=auth(client, a)).status_code == 404
'''
path.write_text(src)

# ---------------------------------------------------------------------------
# 7. Compile-only safety check before handing control back.
# ---------------------------------------------------------------------------

for relative in (
    "forge_migrations.py",
    "forge_backend.py",
    "forge_routes/owned_social.py",
    "forge_routes/owned_social_http.py",
    "migrations/r20260929_03_blocking_core.py",
    "tests/test_blocking_core_service.py",
    "tests/test_blocking_core_migration.py",
    "tests/_v2_contract.py",
):
    subprocess.run([sys.executable, "-m", "py_compile", relative], check=True)

subprocess.run(["git", "diff", "--check"], check=True)
print("T-107 backend/core patch applied and syntax-checked.")
print("No real Forge instance database was opened or modified by this helper.")
print("Next run the focused pytest command supplied in chat before committing.")
