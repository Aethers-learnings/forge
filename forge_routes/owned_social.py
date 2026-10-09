"""Ownership-v2 persistence and participant-authorized contact delivery.

The caller supplies a trusted authenticated User object, never an actor ID from
request data. Every mutation obtains SQLite's write reservation before reading
authorization or state. Results are detached dictionaries returned after commit.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import secrets
import logging

from sqlalchemy import and_, func, or_, select


COOLDOWN = timedelta(hours=24)
SOCIAL_NOTIFICATIONS = {
    "owned_request": "You have a connection request.",
    "owned_accepted": "Your connection request was accepted.",
    "owned_message": "You have a new message.",
}
logger = logging.getLogger(__name__)


class SocialError(Exception):
    """Domain failure without an HTTP response or moderation-state disclosure."""


class PreconditionRequired(SocialError):
    pass


class Conflict(SocialError):
    pass


class Forbidden(SocialError):
    pass


class NotFound(SocialError):
    pass


class Invalid(SocialError):
    pass


class OperationUnavailable(SocialError):
    pass


def _utcnow():
    # SQLite/SQLAlchemy DateTime columns persist naive UTC values here.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _pair(a, b):
    if type(a) is not int or type(b) is not int or a < 1 or b < 1:
        raise Invalid("invalid pair")
    if a == b:
        raise Invalid("self interaction")
    return min(a, b), max(a, b)


def _version(expected, current):
    if expected is None:
        raise PreconditionRequired("expected version required")
    if type(expected) is not int or expected != current:
        raise Conflict("stale version")


def _retry_version(expected, current):
    """A no-op may replay the pre-commit version of its last transition."""
    if expected is None:
        raise PreconditionRequired("expected version required")
    if type(expected) is not int or not (
        expected == current or (current > 0 and expected == current - 1)
    ):
        raise Conflict("stale version")


def _row(connection, statement):
    result = connection.execute(statement).mappings().first()
    return dict(result) if result else None


class OwnedSocialService:
    """The serialized write and delivery boundary for migration-owned social rows.

    Pass the existing Flask-SQLAlchemy engine and application model module.
    This module does not import the app (including when it runs as __main__).
    """

    def __init__(self, engine, models, *, emit=None):
        if engine.url.get_backend_name() != "sqlite":
            raise ValueError("owned social write serialization requires SQLite")
        self.engine = engine
        self.user_model = models.User
        self.user = models.User.__table__
        self.edge = models.NetworkEdge.__table__
        self.endorsement = models.Endorsement.__table__
        self.conversation = models.DirectConversation.__table__
        self.member = models.ConversationMember.__table__
        self.message = models.DirectMessage.__table__
        self.event = models.OwnershipEvent.__table__
        self.block = models.UserBlock.__table__
        self.block_event = models.BlockEvent.__table__
        self.notification = models.Notification.__table__
        self.emit = emit

    @contextmanager
    def _write(self):
        intents = []
        with self.engine.connect() as connection:
            # Connection-local only, cleared before returning it to the pool.
            connection.info["owned_social_delivery"] = intents
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.info.pop("owned_social_delivery", None)
        # This line is unreachable on mutation/notification/commit failure.
        # Socket failures cannot change the already committed domain result.
        if self.emit and intents:
            self._deliver(intents)

    def _notify(self, connection, recipient_id, kind, link, now):
        note_id = connection.execute(self.notification.insert().values(
            user_id=recipient_id, type=kind, text=SOCIAL_NOTIFICATIONS[kind],
            link=link, read=False, created_at=now)).inserted_primary_key[0]
        connection.info.setdefault("owned_social_delivery", []).append(
            {"note_id": note_id, "recipients": (recipient_id,)})

    def _active_pair(self, connection, low, high):
        users = connection.execute(select(self.user.c.id).where(
            self.user.c.id.in_((low, high)), self.user.c.suspended.is_(False))).scalars().all()
        return set(users) == {low, high} and not self._pair_blocked(connection, low, high)

    def _contact_conversation(self, connection, conversation):
        if not conversation or not self._active_pair(
                connection, conversation["user_low_id"], conversation["user_high_id"]):
            return False
        edge = self._edge_pair(connection, conversation["user_low_id"], conversation["user_high_id"])
        if not edge or edge["state"] != "accepted":
            return False
        try:
            self._members(connection, conversation)
        except OperationUnavailable:
            return False
        return True

    def _notification_visible(self, connection, note):
        if note["type"] not in SOCIAL_NOTIFICATIONS:
            return True
        # Links identify migration-owned records only; they never grant access.
        parts = (note["link"] or "").split(":")
        if len(parts) != 3 or not parts[2].isdecimal() or int(parts[2]) < 1:
            return False
        version = int(parts[2])
        if note["type"] == "owned_message":
            if parts[0] != "messages":
                return False
            conversation = _row(connection, select(self.conversation).where(
                self.conversation.c.public_id == parts[1]))
            if not self._contact_conversation(connection, conversation):
                return False
            # Do not select a message body for notification authorization.
            sender = connection.execute(select(self.message.c.sender_id).where(
                self.message.c.conversation_id == conversation["id"],
                self.message.c.seq == version)).scalar_one_or_none()
            return sender in (conversation["user_low_id"], conversation["user_high_id"]) and (
                note["user_id"] in (conversation["user_low_id"], conversation["user_high_id"])
                and note["user_id"] != sender)
        if parts[0] != "network" or not parts[1].isdecimal():
            return False
        edge = _row(connection, select(self.edge).where(self.edge.c.id == int(parts[1])))
        if not edge or edge["version"] != version or not self._active_pair(
                connection, edge["user_low_id"], edge["user_high_id"]):
            return False
        if note["type"] == "owned_request":
            return edge["state"] == "pending" and note["user_id"] == edge["recipient_id"]
        return edge["state"] == "accepted" and note["user_id"] == edge["requester_id"]

    @staticmethod
    def _note_dict(note):
        return {"id": note["id"], "type": note["type"], "text": note["text"],
                "link": note["link"], "read": note["read"],
                "createdAt": note["created_at"].isoformat()}

    def notification_state(self, actor, *, limit=50, ascending=False):
        """Filter before the display limit/count, also used by v2 export.

        Historical rows remain stored. Empty owned links are permanent
        suppression markers: unblocking/reconnecting cannot restore contact.
        """
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            statement = select(self.notification).where(self.notification.c.user_id == user["id"])
            statement = statement.order_by(self.notification.c.id if ascending else self.notification.c.id.desc())
            visible = [dict(row) for row in connection.execute(statement).mappings()
                       if self._notification_visible(connection, row)]
            return {"notifications": [self._note_dict(row) for row in
                                      (visible if limit is None else visible[:limit])],
                    "unreadCount": sum(not row["read"] for row in visible)}

    def _suppress_contact(self, connection, low, high):
        # The schema has no delivered flag. Conservatively retire every unread
        # owned contact hint for this pair, preserving its generic durable row.
        edge = self._edge_pair(connection, low, high)
        conversation = _row(connection, select(self.conversation).where(
            self.conversation.c.user_low_id == low, self.conversation.c.user_high_id == high))
        links = []
        if edge:
            links.append(self.notification.c.link.startswith(f"network:{edge['id']}:", autoescape=True))
        if conversation:
            links.append(self.notification.c.link.startswith(f"messages:{conversation['public_id']}:", autoescape=True))
        if links:
            connection.execute(self.notification.update().where(
                self.notification.c.user_id.in_((low, high)),
                self.notification.c.type.in_(SOCIAL_NOTIFICATIONS),
                self.notification.c.read.is_(False), or_(*links)).values(link=""))

    def _delivery_packet(self, connection, intent, recipient_id):
        if "note_id" in intent:
            note = _row(connection, select(self.notification).where(
                self.notification.c.id == intent["note_id"],
                self.notification.c.user_id == recipient_id))
            if note and self._notification_visible(connection, note):
                return "notification", self._note_dict(note)
            return None
        conversation = _row(connection, select(self.conversation).where(
            self.conversation.c.id == intent["conversation_id"]))
        if (not self._contact_conversation(connection, conversation) or
                recipient_id not in (conversation["user_low_id"], conversation["user_high_id"])):
            return None
        sequence = connection.execute(select(self.message.c.seq).where(
            self.message.c.conversation_id == conversation["id"],
            self.message.c.seq == intent["sequence"])).scalar_one_or_none()
        if sequence is not None:
            return "new_message", {"conversationId": conversation["public_id"], "lastSequence": sequence}
        return None

    def _deliver(self, intents):
        for intent in intents:
            for recipient_id in intent["recipients"]:
                try:
                    with self.engine.connect() as connection:
                        # Serialize the final eligibility check AND enqueue
                        # against block/suspension commits. No business writes
                        # occur here; the short reservation is rolled back.
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
                        packet = self._delivery_packet(connection, intent, recipient_id)
                        if packet:
                            self.emit(*packet, room=f"user:{recipient_id}")
                except Exception:
                    # Never log exception/payload contents, and never retry
                    # the mutation. HTTP state is the recovery path.
                    logger.warning("Owned social realtime delivery unavailable")

    def _actor(self, connection, actor):
        # A trusted User instance is the service boundary; never accept a raw ID.
        if not isinstance(actor, self.user_model):
            raise Forbidden("authenticated actor required")
        user = _row(connection, select(self.user).where(self.user.c.id == actor.id))
        if not user or user["suspended"]:
            raise Forbidden("active actor required")
        return user

    def _peer(self, connection, peer_id, *, discoverable=False):
        peer = _row(connection, select(self.user).where(self.user.c.id == peer_id))
        if not peer or peer["suspended"]:
            if discoverable:
                raise NotFound("user unavailable")
            raise OperationUnavailable("operation unavailable")
        if discoverable and not peer["profile_visible"]:
            raise NotFound("user unavailable")
        return peer

    def _edge_pair(self, connection, low, high):
        return _row(connection, select(self.edge).where(
            self.edge.c.user_low_id == low, self.edge.c.user_high_id == high))


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

    def _event(self, connection, actor_id, target, entity_id, version, kind,
               previous, next_state, now):
        connection.execute(self.event.insert().values(
            **{target: entity_id}, actor_user_id=actor_id,
            entity_version=version, event_type=kind, previous_state=previous,
            next_state=next_state, created_at=now))

    def own_edges(self, actor):
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            return [dict(row) for row in connection.execute(select(self.edge).where(or_(
                self.edge.c.user_low_id == user["id"],
                self.edge.c.user_high_id == user["id"]))).mappings()]

    def own_blocks(self, actor, *, after=None, limit=50):
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

    def suggestions(self, actor, *, now=None):
        now = now or _utcnow()
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            peers = connection.execute(select(self.user).where(
                self.user.c.id != user["id"], self.user.c.suspended == False,
                self.user.c.profile_visible == True).order_by(self.user.c.id)).mappings()
            result = []
            for peer in peers:
                low, high = _pair(user["id"], peer["id"])
                if self._pair_blocked(connection, low, high):
                    continue
                edge = self._edge_pair(connection, low, high)
                if edge and (edge["state"] in ("pending", "accepted") or
                             edge["ended_at"] is None or now - edge["ended_at"] < COOLDOWN):
                    continue
                # This projection follows ordinary public profile visibility.
                # Caller-owned block version is included only so stale re-blocks can refresh.
                own_block = self._own_block(connection, user["id"], peer["id"])
                result.append({"id": peer["id"], "name": peer["name"],
                               "role": peer["role"], "color": peer["color"],
                               "headline": peer["headline"],
                               "edge_version": edge["version"] if edge else 0,
                               "block_version": own_block["version"] if own_block else 0})
            return result

    def network_sections(self, actor, *, after=None, limit=None):
        """Filter to the caller before stable per-section keyset pagination."""
        after = after or {}
        limit = limit or {}
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            rows = connection.execute(select(self.edge).where(or_(
                self.edge.c.user_low_id == user["id"],
                self.edge.c.user_high_id == user["id"])).order_by(self.edge.c.id)).mappings().all()
            sections = {"requests": [], "outgoingRequests": [], "connections": []}
            for edge in rows:
                key = ("connections" if edge["state"] == "accepted" else
                       "outgoingRequests" if edge["state"] == "pending" and
                       edge["requester_id"] == user["id"] else
                       "requests" if edge["state"] == "pending" else None)
                if key is not None and edge["id"] > after.get(key, 0):
                    item = dict(edge)
                    peer_id = edge["user_high_id"] if edge["user_low_id"] == user["id"] else edge["user_low_id"]
                    own_block = self._own_block(connection, user["id"], peer_id)
                    item["block_version"] = own_block["version"] if own_block else 0
                    sections[key].append(item)
            return {key: (values[:limit.get(key, 50)], len(values) > limit.get(key, 50))
                    for key, values in sections.items()}

    def set_block(self, actor, target_id, desired, expected_version,
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
                self._suppress_contact(connection, low, high)
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

    def request(self, actor, target_id, expected_version, *, now=None):
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            low, high = _pair(user["id"], target_id)
            self._peer(connection, target_id, discoverable=True)
            self._ensure_pair_available(connection, low, high)
            edge = self._edge_pair(connection, low, high)
            if edge and edge["state"] == "pending":
                if edge["requester_id"] == user["id"]:
                    _retry_version(expected_version, edge["version"])
                    return edge
                _version(expected_version, edge["version"])
                raise Conflict("opposite pending request")
            _version(expected_version, edge["version"] if edge else 0)
            if edge and edge["state"] == "accepted":
                raise Conflict("pair already accepted")
            if edge and (edge["ended_at"] is None or now - edge["ended_at"] < COOLDOWN):
                raise OperationUnavailable("operation unavailable")
            if edge:
                previous, version, edge_id = edge["state"], edge["version"] + 1, edge["id"]
                connection.execute(self.edge.update().where(self.edge.c.id == edge_id).values(
                    requester_id=user["id"], recipient_id=target_id, state="pending",
                    version=version, requested_at=now, updated_at=now,
                    accepted_at=None, ended_at=None, changed_by_user_id=user["id"]))
            else:
                previous, version = None, 1
                edge_id = connection.execute(self.edge.insert().values(
                    user_low_id=low, user_high_id=high, requester_id=user["id"],
                    recipient_id=target_id, state="pending", version=version,
                    created_at=now, requested_at=now, updated_at=now,
                    changed_by_user_id=user["id"])).inserted_primary_key[0]
            self._event(connection, user["id"], "network_edge_id", edge_id,
                        version, "requested", previous, "pending", now)
            self._notify(connection, target_id, "owned_request", f"network:{edge_id}:{version}", now)
            return _row(connection, select(self.edge).where(self.edge.c.id == edge_id))

    def transition(self, actor, edge_id, action, expected_version, *, now=None):
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            edge = _row(connection, select(self.edge).where(self.edge.c.id == edge_id))
            if not edge or user["id"] not in (edge["user_low_id"], edge["user_high_id"]):
                raise NotFound("edge unavailable")
            roles = {"accept": ("pending", edge["recipient_id"], "accepted"),
                     "ignore": ("pending", edge["recipient_id"], "ignored"),
                     "cancel": ("pending", edge["requester_id"], "cancelled"),
                     "disconnect": ("accepted", None, "disconnected")}
            if action not in roles:
                raise Invalid("unknown transition")
            source, required_actor, state = roles[action]
            if required_actor is not None and required_actor != user["id"]:
                raise Forbidden("wrong endpoint")
            if action == "accept":
                self._ensure_pair_available(connection, edge["user_low_id"], edge["user_high_id"])
                self._peer(connection, edge["requester_id"])
            _version(expected_version, edge["version"])
            if edge["state"] != source:
                raise OperationUnavailable("operation unavailable")
            version = edge["version"] + 1
            connection.execute(self.edge.update().where(self.edge.c.id == edge_id).values(
                state=state, version=version, updated_at=now,
                accepted_at=now if state == "accepted" else None,
                ended_at=now if state in ("ignored", "cancelled", "disconnected") else None,
                changed_by_user_id=user["id"]))
            self._event(connection, user["id"], "network_edge_id", edge_id,
                        version, state, edge["state"], state, now)
            if action == "accept":
                self._notify(connection, edge["requester_id"], "owned_accepted",
                             f"network:{edge_id}:{version}", now)
            if action in ("ignore", "cancel", "disconnect"):
                self._suppress_contact(connection, edge["user_low_id"], edge["user_high_id"])
            if action == "disconnect":
                endorsements = connection.execute(select(self.endorsement).where(
                    self.endorsement.c.network_edge_id == edge_id,
                    self.endorsement.c.revoked_at.is_(None))).mappings().all()
                for endorsement in endorsements:
                    next_version = endorsement["version"] + 1
                    connection.execute(self.endorsement.update().where(
                        self.endorsement.c.id == endorsement["id"]).values(
                            revoked_at=now, updated_at=now, version=next_version))
                    self._event(connection, user["id"], "endorsement_id",
                                endorsement["id"], next_version, "revoked",
                                "active", "revoked", now)
            return _row(connection, select(self.edge).where(self.edge.c.id == edge_id))

    def endorse(self, actor, edge_id, desired, expected_version, *, now=None):
        if type(desired) is not bool:
            raise Invalid("desired state must be boolean")
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            edge = _row(connection, select(self.edge).where(self.edge.c.id == edge_id))
            if not edge or user["id"] not in (edge["user_low_id"], edge["user_high_id"]):
                raise NotFound("edge unavailable")
            recipient = edge["user_high_id"] if user["id"] == edge["user_low_id"] else edge["user_low_id"]
            if desired:
                self._ensure_pair_available(connection, edge["user_low_id"], edge["user_high_id"])
            endorsement = _row(connection, select(self.endorsement).where(
                self.endorsement.c.endorser_id == user["id"],
                self.endorsement.c.recipient_id == recipient,
                self.endorsement.c.skill_key == ""))
            active = endorsement is not None and endorsement["revoked_at"] is None
            if active == desired:
                _retry_version(expected_version, endorsement["version"] if endorsement else 0)
                return endorsement
            _version(expected_version, endorsement["version"] if endorsement else 0)
            if desired:
                if edge["state"] != "accepted":
                    raise OperationUnavailable("operation unavailable")
                self._peer(connection, recipient)
            if not endorsement:
                # An absent false request is idempotent with no row/event.
                if not desired:
                    return None
                version = 1
                endorsement_id = connection.execute(self.endorsement.insert().values(
                    network_edge_id=edge_id, endorser_id=user["id"], recipient_id=recipient,
                    skill_key="", version=version, created_at=now, updated_at=now)).inserted_primary_key[0]
            else:
                version, endorsement_id = endorsement["version"] + 1, endorsement["id"]
                connection.execute(self.endorsement.update().where(
                    self.endorsement.c.id == endorsement_id).values(
                        version=version, updated_at=now, revoked_at=None if desired else now))
            self._event(connection, user["id"], "endorsement_id", endorsement_id,
                        version, "activated" if desired else "revoked",
                        "active" if active else "revoked" if endorsement else None,
                        "active" if desired else "revoked", now)
            return _row(connection, select(self.endorsement).where(self.endorsement.c.id == endorsement_id))

    def active_endorsements(self, actor, edge_id):
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            edge = _row(connection, select(self.edge).where(self.edge.c.id == edge_id))
            if not edge or user["id"] not in (edge["user_low_id"], edge["user_high_id"]):
                raise NotFound("edge unavailable")
            peer_id = edge["user_high_id"] if user["id"] == edge["user_low_id"] else edge["user_low_id"]
            peer = _row(connection, select(self.user).where(self.user.c.id == peer_id))
            if (edge["state"] != "accepted" or not peer or peer["suspended"]
                    or self._pair_blocked(connection, edge["user_low_id"], edge["user_high_id"])):
                return []
            return [dict(row) for row in connection.execute(select(self.endorsement).where(
                self.endorsement.c.network_edge_id == edge_id,
                self.endorsement.c.endorser_id == user["id"],
                self.endorsement.c.recipient_id == peer_id,
                self.endorsement.c.skill_key == "",
                self.endorsement.c.revoked_at.is_(None))).mappings()]

    def endorsement_status(self, actor, edge_id):
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            edge = _row(connection, select(self.edge).where(self.edge.c.id == edge_id))
            if not edge or user["id"] not in (edge["user_low_id"], edge["user_high_id"]):
                raise NotFound("edge unavailable")
            peer_id = edge["user_high_id"] if user["id"] == edge["user_low_id"] else edge["user_low_id"]
            row = _row(connection, select(self.endorsement).where(
                self.endorsement.c.endorser_id == user["id"],
                self.endorsement.c.recipient_id == peer_id,
                self.endorsement.c.skill_key == ""))
            blocked = self._pair_blocked(connection, edge["user_low_id"], edge["user_high_id"])
            active = bool(row and row["revoked_at"] is None
                          and edge["state"] == "accepted" and not blocked)
            return {"endorsements": int(active), "endorsedByMe": active,
                    "version": row["version"] if row else 0}

    def _members(self, connection, conversation):
        members = [dict(row) for row in connection.execute(select(self.member).where(
            self.member.c.conversation_id == conversation["id"])).mappings()]
        if {m["user_id"] for m in members} != {
            conversation["user_low_id"], conversation["user_high_id"]} or len(members) != 2:
            raise OperationUnavailable("operation unavailable")
        return members

    def _conversation_for_actor(self, connection, actor, public_id):
        user = self._actor(connection, actor)
        conversation = _row(connection, select(self.conversation).where(
            self.conversation.c.public_id == public_id))
        if not conversation or user["id"] not in (conversation["user_low_id"],
                                                    conversation["user_high_id"]):
            raise NotFound("conversation unavailable")
        members = self._members(connection, conversation)
        return user, conversation, next(m for m in members if m["user_id"] == user["id"])

    def open_conversation(self, actor, peer_id, *, now=None, with_status=False):
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            low, high = _pair(user["id"], peer_id)
            self._peer(connection, peer_id, discoverable=True)
            self._ensure_pair_available(connection, low, high)
            edge = self._edge_pair(connection, low, high)
            if not edge or edge["state"] != "accepted":
                raise OperationUnavailable("operation unavailable")
            conversation = _row(connection, select(self.conversation).where(
                self.conversation.c.user_low_id == low, self.conversation.c.user_high_id == high))
            if conversation:
                self._members(connection, conversation)
                return (conversation, False) if with_status else conversation
            conversation_id = connection.execute(self.conversation.insert().values(
                public_id=secrets.token_urlsafe(24), user_low_id=low, user_high_id=high,
                created_by_user_id=user["id"], created_at=now, updated_at=now,
                last_seq=0)).inserted_primary_key[0]
            connection.execute(self.member.insert(), [
                {"conversation_id": conversation_id, "user_id": endpoint,
                 "joined_at": now, "last_read_seq": 0}
                for endpoint in (low, high)])
            self._event(connection, user["id"], "conversation_id", conversation_id,
                        1, "created", None, "active", now)
            conversation = _row(connection, select(self.conversation).where(
                self.conversation.c.id == conversation_id))
            self._members(connection, conversation)
            return (conversation, True) if with_status else conversation

    def history(self, actor, public_id, *, before=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise Invalid("invalid limit")
        with self.engine.connect() as connection:
            user, conversation, member = self._conversation_for_actor(connection, actor, public_id)
            statement = select(self.message).where(self.message.c.conversation_id == conversation["id"])
            if before is not None:
                if type(before) is not int or before < 1:
                    raise Invalid("invalid cursor")
                statement = statement.where(self.message.c.seq < before)
            messages = [{key: row[key] for key in ("seq", "sender_id", "text", "created_at")}
                        for row in connection.execute(statement.order_by(
                            self.message.c.seq.desc()).limit(limit + 1)).mappings()]
            has_more = len(messages) > limit
            messages = messages[:limit]
            unread = connection.execute(select(func.count()).select_from(self.message).where(
                self.message.c.conversation_id == conversation["id"],
                self.message.c.sender_id != user["id"],
                self.message.c.seq > member["last_read_seq"])).scalar_one()
            return {"public_id": public_id, "last_seq": conversation["last_seq"],
                    "last_read_seq": member["last_read_seq"], "unread_count": unread,
                    "messages": list(reversed(messages)), "has_more": has_more}

    def send(self, actor, public_id, text, client_message_id, *, now=None, with_status=False):
        now = now or _utcnow()
        with self._write() as connection:
            user, conversation, _ = self._conversation_for_actor(connection, actor, public_id)
            if not isinstance(client_message_id, str) or not client_message_id.strip():
                raise Invalid("client message ID required")
            if not isinstance(text, str) or not text.strip() or len(text.strip()) > 4000:
                raise Invalid("message must contain 1 to 4000 characters")
            normalized = text.strip()
            prior = _row(connection, select(self.message).where(
                self.message.c.conversation_id == conversation["id"],
                self.message.c.sender_id == user["id"],
                self.message.c.client_message_id == client_message_id))
            if prior:
                if prior["text"] != normalized:
                    raise Conflict("retry key already used")
                return (prior, False) if with_status else prior
            self._ensure_pair_available(connection, conversation["user_low_id"], conversation["user_high_id"])
            peer_id = (conversation["user_high_id"] if user["id"] == conversation["user_low_id"]
                       else conversation["user_low_id"])
            edge = self._edge_pair(connection, conversation["user_low_id"], conversation["user_high_id"])
            if not edge or edge["state"] != "accepted":
                raise OperationUnavailable("operation unavailable")
            self._peer(connection, peer_id)
            seq = conversation["last_seq"] + 1
            connection.execute(self.message.insert().values(
                conversation_id=conversation["id"], seq=seq, sender_id=user["id"],
                client_message_id=client_message_id, text=normalized, created_at=now))
            connection.execute(self.conversation.update().where(
                self.conversation.c.id == conversation["id"]).values(last_seq=seq, updated_at=now))
            self._notify(connection, peer_id, "owned_message", f"messages:{public_id}:{seq}", now)
            connection.info.setdefault("owned_social_delivery", []).append({
                "conversation_id": conversation["id"], "sequence": seq,
                "recipients": (user["id"], peer_id)})
            result = _row(connection, select(self.message).where(
                self.message.c.conversation_id == conversation["id"], self.message.c.seq == seq))
            return (result, True) if with_status else result

    def conversation_info(self, actor, public_id):
        with self.engine.connect() as connection:
            user, conversation, member = self._conversation_for_actor(connection, actor, public_id)
            peer_id = (conversation["user_high_id"] if user["id"] == conversation["user_low_id"]
                       else conversation["user_low_id"])
            peer = _row(connection, select(self.user).where(self.user.c.id == peer_id))
            edge = self._edge_pair(connection, conversation["user_low_id"], conversation["user_high_id"])
            blocked = self._pair_blocked(connection, conversation["user_low_id"], conversation["user_high_id"])
            return {"peer_id": peer_id, "name": peer["name"] if peer else "Member",
                    "color": peer["color"] if peer else "", "read_only": not (
                        peer and not peer["suspended"] and edge and
                        edge["state"] == "accepted" and not blocked),
                    "last_seq": conversation["last_seq"]}

    def list_conversations(self, actor, *, after=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 50 or (
                after is not None and (type(after) is not int or after < 0)):
            raise Invalid("invalid cursor or limit")
        with self.engine.connect() as connection:
            user = self._actor(connection, actor)
            statement = select(self.conversation.c.public_id, self.conversation.c.id).join(
                self.member, self.member.c.conversation_id == self.conversation.c.id).where(
                self.member.c.user_id == user["id"])
            if after is not None:
                statement = statement.where(self.conversation.c.id > after)
            rows = connection.execute(statement.order_by(self.conversation.c.id).limit(limit + 1)).mappings().all()
            return [dict(row) for row in rows[:limit]], len(rows) > limit

    def mark_read(self, actor, public_id, observed_seq, *, now=None):
        now = now or _utcnow()
        with self._write() as connection:
            user, conversation, member = self._conversation_for_actor(connection, actor, public_id)
            if type(observed_seq) is not int or not 0 <= observed_seq <= conversation["last_seq"]:
                raise Invalid("invalid observed sequence")
            if observed_seq > 0 and not _row(connection, select(self.message).where(
                self.message.c.conversation_id == conversation["id"],
                self.message.c.seq == observed_seq)):
                raise Invalid("sequence does not belong to conversation")
            if observed_seq > member["last_read_seq"]:
                connection.execute(self.member.update().where(
                    self.member.c.conversation_id == conversation["id"],
                    self.member.c.user_id == user["id"]).values(
                        last_read_seq=observed_seq, read_at=now))
            return max(member["last_read_seq"], observed_seq)
