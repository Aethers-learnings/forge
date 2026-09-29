"""Internal ownership-v2 persistence service; no route or delivery cutover.

The caller supplies a trusted authenticated User object, never an actor ID from
request data. Every mutation obtains SQLite's write reservation before reading
authorization or state. Results are detached dictionaries returned after commit.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import func, or_, select


COOLDOWN = timedelta(hours=24)


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
    """The sole future write boundary for migration-owned social rows.

    Pass the existing Flask-SQLAlchemy engine and application model module.
    This module does not import the app (including when it runs as __main__).
    """

    def __init__(self, engine, models):
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

    @contextmanager
    def _write(self):
        with self.engine.connect() as connection:
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

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
            raise OperationUnavailable("operation unavailable")
        if discoverable and not peer["profile_visible"]:
            raise NotFound("user unavailable")
        return peer

    def _edge_pair(self, connection, low, high):
        return _row(connection, select(self.edge).where(
            self.edge.c.user_low_id == low, self.edge.c.user_high_id == high))

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
                edge = self._edge_pair(connection, low, high)
                if edge and (edge["state"] in ("pending", "accepted") or
                             edge["ended_at"] is None or now - edge["ended_at"] < COOLDOWN):
                    continue
                # This projection follows ordinary public profile visibility,
                # without privileged admin inspection or hidden fields.
                result.append({"id": peer["id"], "name": peer["name"],
                               "role": peer["role"], "color": peer["color"],
                               "headline": peer["headline"],
                               "edge_version": edge["version"] if edge else 0})
            return result

    def request(self, actor, target_id, expected_version, *, now=None):
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            low, high = _pair(user["id"], target_id)
            self._peer(connection, target_id, discoverable=True)
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
            return _row(connection, select(self.edge).where(self.edge.c.id == edge_id))

    def transition(self, actor, edge_id, action, expected_version, *, now=None):
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            edge = _row(connection, select(self.edge).where(self.edge.c.id == edge_id))
            if not edge or user["id"] not in (edge["user_low_id"], edge["user_high_id"]):
                raise NotFound("edge unavailable")
            _version(expected_version, edge["version"])
            roles = {"accept": ("pending", edge["recipient_id"], "accepted"),
                     "ignore": ("pending", edge["recipient_id"], "ignored"),
                     "cancel": ("pending", edge["requester_id"], "cancelled"),
                     "disconnect": ("accepted", None, "disconnected")}
            if action not in roles:
                raise Invalid("unknown transition")
            source, required_actor, state = roles[action]
            if edge["state"] != source or (required_actor is not None and
                                            required_actor != user["id"]):
                raise OperationUnavailable("operation unavailable")
            version = edge["version"] + 1
            connection.execute(self.edge.update().where(self.edge.c.id == edge_id).values(
                state=state, version=version, updated_at=now,
                accepted_at=now if state == "accepted" else None,
                ended_at=now if state in ("ignored", "cancelled", "disconnected") else None,
                changed_by_user_id=user["id"]))
            self._event(connection, user["id"], "network_edge_id", edge_id,
                        version, state, edge["state"], state, now)
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
            if edge["state"] != "accepted" or not peer or peer["suspended"]:
                return []
            return [dict(row) for row in connection.execute(select(self.endorsement).where(
                self.endorsement.c.network_edge_id == edge_id,
                self.endorsement.c.endorser_id == user["id"],
                self.endorsement.c.recipient_id == peer_id,
                self.endorsement.c.skill_key == "",
                self.endorsement.c.revoked_at.is_(None))).mappings()]

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

    def open_conversation(self, actor, peer_id, *, now=None):
        now = now or _utcnow()
        with self._write() as connection:
            user = self._actor(connection, actor)
            low, high = _pair(user["id"], peer_id)
            self._peer(connection, peer_id)
            edge = self._edge_pair(connection, low, high)
            if not edge or edge["state"] != "accepted":
                raise OperationUnavailable("operation unavailable")
            conversation = _row(connection, select(self.conversation).where(
                self.conversation.c.user_low_id == low, self.conversation.c.user_high_id == high))
            if conversation:
                self._members(connection, conversation)
                return conversation
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
            return conversation

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
                            self.message.c.seq.desc()).limit(limit)).mappings()]
            unread = connection.execute(select(func.count()).select_from(self.message).where(
                self.message.c.conversation_id == conversation["id"],
                self.message.c.sender_id != user["id"],
                self.message.c.seq > member["last_read_seq"])).scalar_one()
            return {"public_id": public_id, "last_seq": conversation["last_seq"],
                    "last_read_seq": member["last_read_seq"], "unread_count": unread,
                    "messages": list(reversed(messages))}

    def send(self, actor, public_id, text, client_message_id, *, now=None):
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
                return prior
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
            return _row(connection, select(self.message).where(
                self.message.c.conversation_id == conversation["id"], self.message.c.seq == seq))

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
