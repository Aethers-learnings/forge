"""Owned-only service invariants on migration-HEAD fixture databases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier, Event, Thread

import pytest
from sqlalchemy import event, select, text

import forge_backend as forge
from forge_routes.owned_social import (
    Conflict, Forbidden, Invalid, NotFound, OperationUnavailable,
    OwnedSocialService, PreconditionRequired,
)


@pytest.fixture
def social(app):
    with app.app_context():
        users = [forge.User(username=f"social_{i}", password_hash="unused",
                            role="admin" if i == 3 else "trade", name="Same Name")
                 for i in range(4)]
        forge.db.session.add_all(users)
        forge.db.session.commit()
        for user in users:
            _ = user.id  # load IDs before detaching for independent-connection tests
        forge.db.session.expunge_all()
        actors = users
        service = OwnedSocialService(forge.db.engine, forge)
        yield service, actors
        forge.db.session.remove()


def accepted(service, a, b):
    edge = service.request(a, b.id, 0)
    return service.transition(b, edge["id"], "accept", 1)


def counts(service):
    with service.engine.connect() as connection:
        return tuple(connection.execute(select(text("count(*)")).select_from(table)).scalar_one()
                     for table in (service.edge, service.endorsement, service.conversation,
                                   service.member, service.message, service.event))


def test_discovery_own_graph_and_cooldown(social):
    service, (a, b, c, d) = social
    with service.engine.begin() as connection:
        connection.execute(service.user.update().where(service.user.c.id == c.id).values(profile_visible=False))
    assert {p["id"] for p in service.suggestions(a)} == {b.id, d.id}
    edge = service.request(a, b.id, 0)
    assert b.id not in {p["id"] for p in service.suggestions(a)}
    assert [e["id"] for e in service.own_edges(b)] == [edge["id"]]
    assert service.own_edges(c) == []
    service.transition(a, edge["id"], "cancel", 1)
    assert b.id not in {p["id"] for p in service.suggestions(a)}
    future = datetime.utcnow() + timedelta(hours=25)
    assert b.id in {p["id"] for p in service.suggestions(a, now=future)}
    with pytest.raises(NotFound):
        service.request(a, c.id, 0)
    with pytest.raises(Invalid):
        service.request(a, a.id, 0)


def test_direction_versions_roles_and_terminal_re_request(social):
    service, (a, b, c, _) = social
    with pytest.raises(PreconditionRequired):
        service.request(a, b.id, None)
    with pytest.raises(Conflict):
        service.request(a, b.id, 2)
    edge = service.request(a, b.id, 0)
    before_retry = counts(service)
    assert service.request(a, b.id, 0) == edge
    assert service.request(a, b.id, 1) == edge
    assert counts(service) == before_retry
    with pytest.raises(Conflict):
        service.request(a, b.id, -1)
    with pytest.raises(PreconditionRequired):
        service.request(a, b.id, None)
    with pytest.raises(Conflict):
        service.request(b, a.id, 1)
    with pytest.raises(NotFound):
        service.transition(c, edge["id"], "accept", 1)
    with pytest.raises(Forbidden):
        service.transition(a, edge["id"], "accept", 1)
    with pytest.raises(PreconditionRequired):
        service.transition(b, edge["id"], "accept", None)
    ignored = service.transition(b, edge["id"], "ignore", 1)
    assert ignored["version"] == 2
    with pytest.raises(Conflict):
        service.transition(b, edge["id"], "ignore", 1)
    with pytest.raises(OperationUnavailable):
        service.request(b, a.id, 2)
    new = service.request(b, a.id, 2, now=ignored["ended_at"] + timedelta(hours=24))
    assert (new["id"], new["requester_id"], new["recipient_id"], new["version"]) == (
        edge["id"], b.id, a.id, 3)
    assert new["created_at"] == edge["created_at"]
    assert new["accepted_at"] is None and new["ended_at"] is None
    before_retry = counts(service)
    assert service.request(b, a.id, 2, now=new["requested_at"]) == new
    assert counts(service) == before_retry
    with pytest.raises(Conflict):
        service.request(b, a.id, 0)
    with pytest.raises(Forbidden):
        service.transition(a, edge["id"], "cancel", 3)
    service.transition(b, edge["id"], "cancel", 3)
    with service.engine.connect() as connection:
        audit = connection.execute(select(service.event).where(
            service.event.c.network_edge_id == edge["id"]).order_by(service.event.c.id)).mappings().all()
    assert [(e["entity_version"], e["event_type"], e["previous_state"], e["next_state"])
            for e in audit] == [(1, "requested", None, "pending"), (2, "ignored", "pending", "ignored"),
                               (3, "requested", "ignored", "pending"), (4, "cancelled", "pending", "cancelled")]


def test_endorsement_desired_state_disconnect_revokes_both(social):
    service, (a, b, c, _) = social
    edge = accepted(service, a, b)
    with pytest.raises(NotFound):
        service.endorse(c, edge["id"], True, 0)
    one = service.endorse(a, edge["id"], True, 0)
    two = service.endorse(b, edge["id"], True, 0)
    before_retry = counts(service)
    assert service.endorse(a, edge["id"], True, 0) == one
    assert service.endorse(a, edge["id"], True, 1) == one
    assert counts(service) == before_retry
    with pytest.raises(PreconditionRequired):
        service.endorse(a, edge["id"], True, None)
    assert [row["id"] for row in service.active_endorsements(a, edge["id"])] == [one["id"]]
    assert [row["id"] for row in service.active_endorsements(b, edge["id"])] == [two["id"]]
    with pytest.raises(Conflict):
        service.endorse(a, edge["id"], False, 0)
    ended = service.transition(a, edge["id"], "disconnect", 2)
    assert ended["version"] == 3
    assert service.active_endorsements(a, edge["id"]) == []
    with service.engine.connect() as connection:
        revoked = connection.execute(select(service.endorsement)).mappings().all()
        events = connection.execute(select(service.event).where(
            service.event.c.endorsement_id.is_not(None))).mappings().all()
    assert {r["id"] for r in revoked} == {one["id"], two["id"]}
    assert all(r["version"] == 2 and r["revoked_at"] for r in revoked)
    assert sorted((e["entity_version"], e["event_type"]) for e in events) == [
        (1, "activated"), (1, "activated"), (2, "revoked"), (2, "revoked")]
    with pytest.raises(OperationUnavailable):
        service.endorse(a, edge["id"], True, 2)


def test_conversation_membership_history_admin_and_suspension(social):
    service, (a, b, c, admin) = social
    accepted(service, a, b)
    conversation = service.open_conversation(a, b.id)
    assert service.open_conversation(b, a.id)["id"] == conversation["id"]
    with service.engine.connect() as connection:
        members = connection.execute(select(service.member)).mappings().all()
    assert {m["user_id"] for m in members} == {a.id, b.id}
    for stranger in (c, admin):
        with pytest.raises(NotFound):
            service.history(stranger, conversation["public_id"])
    with service.engine.begin() as connection:
        connection.execute(service.user.update().where(service.user.c.id == b.id).values(suspended=True))
    assert service.history(a, conversation["public_id"])["messages"] == []
    with pytest.raises(Forbidden):
        service.history(b, conversation["public_id"])
    with pytest.raises(OperationUnavailable):
        service.open_conversation(a, c.id)


def test_messages_retry_history_and_read_cursor(social):
    service, (a, b, c, _) = social
    edge = accepted(service, a, b)
    conversation = service.open_conversation(a, b.id)
    slug = conversation["public_id"]
    for value in ("   ", "x" * 4001):
        with pytest.raises(Invalid):
            service.send(a, slug, value, "invalid")
    with pytest.raises(Invalid):
        service.send(a, slug, "hello", "")
    first = service.send(a, slug, " hello ", "key-1")
    assert (first["sender_id"], first["text"], first["seq"]) == (a.id, "hello", 1)
    assert service.history(b, slug)["unread_count"] == 1
    assert service.history(b, slug)["last_read_seq"] == 0
    with pytest.raises(NotFound):
        service.send(c, slug, "spoof", "key-x")
    with pytest.raises(Invalid):
        service.mark_read(b, slug, 2)
    assert service.mark_read(b, slug, 1) == 1
    assert service.mark_read(b, slug, 0) == 1
    assert service.history(b, slug)["unread_count"] == 0
    service.transition(b, edge["id"], "disconnect", 2)
    assert service.send(a, slug, "hello", "key-1") == first
    with pytest.raises(Conflict):
        service.send(a, slug, "different", "key-1")
    with pytest.raises(OperationUnavailable):
        service.send(a, slug, "new", "key-2")
    assert service.history(a, slug)["messages"][0]["text"] == "hello"
    assert counts(service)[4] == 1


def test_fails_closed_on_corrupt_membership(social):
    service, (a, b, _, _) = social
    accepted(service, a, b)
    conversation = service.open_conversation(a, b.id)
    with service.engine.begin() as connection:
        connection.execute(service.member.delete().where(service.member.c.user_id == b.id))
    with pytest.raises(OperationUnavailable):
        service.history(a, conversation["public_id"])
    with pytest.raises(OperationUnavailable):
        service.send(a, conversation["public_id"], "hi", "k")
    with pytest.raises(OperationUnavailable):
        service.open_conversation(a, b.id)


def test_legacy_tables_never_queried_or_changed(social):
    service, (a, b, _, _) = social
    legacy = {"network_request", "suggested", "connection_npc", "conversation", "message"}
    before = {}
    with service.engine.connect() as connection:
        for name in legacy:
            before[name] = connection.exec_driver_sql(f"SELECT count(*) FROM {name}").scalar_one()
    statements = []
    from sqlalchemy import event
    def trace(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(service.engine, "before_cursor_execute", trace)
    try:
        edge = accepted(service, a, b)
        conversation = service.open_conversation(a, b.id)
        service.send(a, conversation["public_id"], "owned", "retry")
        service.transition(a, edge["id"], "disconnect", 2)
        service.suggestions(a)
    finally:
        event.remove(service.engine, "before_cursor_execute", trace)
    assert not any(f" {name} " in f" {statement} " for statement in statements for name in legacy)
    with service.engine.connect() as connection:
        assert before == {name: connection.exec_driver_sql(
            f"SELECT count(*) FROM {name}").scalar_one() for name in legacy}


def test_concurrent_pair_request_and_opposite_direction(social):
    service, (a, b, _, _) = social
    gate = Barrier(3)
    def worker(actor, target):
        gate.wait()
        try:
            return service.request(actor, target.id, 0)
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, a, b)
        second = executor.submit(worker, b, a)
        gate.wait()
        results = [first.result(), second.result()]
    assert sum(isinstance(r, dict) for r in results) == 1
    assert results.count("conflict") == 1
    assert counts(service)[0] == 1 and counts(service)[5] == 1


def test_concurrent_duplicate_same_direction_request_is_idempotent(social):
    service, (a, b, _, _) = social
    gate = Barrier(3)
    def worker():
        gate.wait()
        return service.request(a, b.id, 0)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        gate.wait()
        results = [f.result() for f in futures]
    assert results[0] == results[1]
    assert counts(service)[0] == 1 and counts(service)[5] == 1


def test_endorsement_revoked_retry_is_noop_and_stale_change_conflicts(social):
    service, (a, b, _, _) = social
    edge = accepted(service, a, b)
    assert service.endorse(a, edge["id"], False, 0) is None
    assert counts(service)[1] == 0
    active = service.endorse(a, edge["id"], True, 0)
    revoked = service.endorse(a, edge["id"], False, active["version"])
    before_retry = counts(service)
    assert service.endorse(a, edge["id"], False, active["version"]) == revoked
    assert service.endorse(a, edge["id"], False, revoked["version"]) == revoked
    assert counts(service) == before_retry
    with pytest.raises(Conflict):
        service.endorse(a, edge["id"], False, 0)
    with pytest.raises(Conflict):
        service.endorse(a, edge["id"], True, active["version"])


def test_concurrent_conversation_create_converges(social):
    service, (a, b, _, _) = social
    accepted(service, a, b)
    gate = Barrier(3)
    def worker(actor, peer):
        gate.wait()
        return service.open_conversation(actor, peer.id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, a, b)
        second = executor.submit(worker, b, a)
        gate.wait()
        assert first.result()["id"] == second.result()["id"]
    assert counts(service)[2:4] == (1, 2)
    assert counts(service)[5] == 3  # request, accept, conversation create


def test_concurrent_sends_dense_sequences(social):
    service, (a, b, _, _) = social
    accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    gate = Barrier(3)
    def worker(actor, key):
        gate.wait()
        return service.send(actor, slug, "hello", key)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, a, "a")
        second = executor.submit(worker, b, "b")
        gate.wait()
        assert {first.result()["seq"], second.result()["seq"]} == {1, 2}
    assert service.history(a, slug)["last_seq"] == 2
    assert counts(service)[4] == 2


def test_disconnect_racing_send_serializes_commit_order(social):
    service, (a, b, _, _) = social
    edge = accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    entered, release = Event(), Event()
    original = service._event
    def pause(*args):
        result = original(*args)
        if args[5] == "disconnected":
            entered.set()
            assert release.wait(5)
        return result
    service._event = pause
    outcome = []
    def disconnect():
        outcome.append(service.transition(a, edge["id"], "disconnect", 2))
    thread = Thread(target=disconnect)
    thread.start()
    assert entered.wait(5)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.send, b, slug, "later", "late")
        release.set()
        with pytest.raises(OperationUnavailable):
            future.result()
    thread.join(5)
    assert not thread.is_alive() and len(outcome) == 1
    assert counts(service)[4] == 0


def test_send_committed_before_disconnect_is_retained(social):
    service, (a, b, _, _) = social
    edge = accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    inserted, release = Event(), Event()
    def pause_after_message(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("insert into direct_message"):
            inserted.set()
            assert release.wait(5)
    event.listen(service.engine, "after_cursor_execute", pause_after_message)
    sent, disconnected = [], []
    sender = Thread(target=lambda: sent.append(service.send(a, slug, "earlier", "early")))
    sender.start()
    assert inserted.wait(5)
    disconnect_started = Event()
    def disconnect():
        disconnect_started.set()
        disconnected.append(service.transition(b, edge["id"], "disconnect", 2))
    closer = Thread(target=disconnect)
    closer.start()
    assert disconnect_started.wait(5)
    release.set()
    sender.join(5)
    closer.join(5)
    event.remove(service.engine, "after_cursor_execute", pause_after_message)
    assert not sender.is_alive() and not closer.is_alive()
    assert sent[0]["seq"] == 1 and disconnected[0]["state"] == "disconnected"
    assert service.history(b, slug)["messages"][0]["text"] == "earlier"


def test_rollback_edge_and_endorsement_revocation(social):
    service, (a, b, _, _) = social
    baseline = counts(service)
    original = service._event
    def fail_event(*args):
        original(*args)
        raise RuntimeError("injected after insert")
    service._event = fail_event
    with pytest.raises(RuntimeError):
        service.request(a, b.id, 0)
    assert counts(service) == baseline
    service._event = original
    edge = accepted(service, a, b)
    service.endorse(a, edge["id"], True, 0)
    service.endorse(b, edge["id"], True, 0)
    baseline = counts(service)
    def fail_revoke(*args):
        original(*args)
        if args[2] == "endorsement_id":
            raise RuntimeError("after one revocation and event")
    service._event = fail_revoke
    with pytest.raises(RuntimeError):
        service.transition(a, edge["id"], "disconnect", 2)
    assert counts(service) == baseline
    with service.engine.connect() as connection:
        assert _state(connection, service, edge["id"]) == "accepted"
        assert all(r[0] is None for r in connection.execute(select(
            service.endorsement.c.revoked_at)).all())


def _state(connection, service, edge_id):
    return connection.execute(select(service.edge.c.state).where(service.edge.c.id == edge_id)).scalar_one()


def test_commit_failure_cannot_return_success(social):
    service, (a, b, _, _) = social
    baseline = counts(service)
    def fail_commit(connection):
        raise OSError("injected commit failure")
    event.listen(service.engine, "commit", fail_commit)
    try:
        with pytest.raises(OSError):
            service.request(a, b.id, 0)
    finally:
        event.remove(service.engine, "commit", fail_commit)
    assert counts(service) == baseline


def test_peer_suspension_allows_disconnect_and_retained_history(social):
    service, (a, b, _, _) = social
    edge = accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    service.send(a, slug, "before suspension", "key")
    with service.engine.begin() as connection:
        connection.execute(service.user.update().where(service.user.c.id == b.id).values(suspended=True))
    with pytest.raises(OperationUnavailable):
        service.send(a, slug, "after suspension", "new-key")
    with pytest.raises(OperationUnavailable):
        service.endorse(a, edge["id"], True, 0)
    assert service.history(a, slug)["messages"][0]["text"] == "before suspension"
    assert service.transition(a, edge["id"], "disconnect", 2)["state"] == "disconnected"
    with pytest.raises(Forbidden):
        service.transition(b, edge["id"], "disconnect", 3)


def test_suspended_peer_endorsement_hidden_without_revocation(social):
    service, (a, b, _, _) = social
    edge = accepted(service, a, b)
    endorsement = service.endorse(a, edge["id"], True, 0)
    with service.engine.begin() as connection:
        connection.execute(service.user.update().where(service.user.c.id == b.id).values(suspended=True))
    assert service.active_endorsements(a, edge["id"]) == []
    with service.engine.connect() as connection:
        assert connection.execute(select(service.endorsement.c.revoked_at).where(
            service.endorsement.c.id == endorsement["id"])).scalar_one() is None


def test_service_persists_generic_notifications_without_legacy_delivery(social, monkeypatch):
    service, (a, b, _, _) = social
    def forbidden_delivery(*args, **kwargs):
        raise AssertionError("service must not emit or notify")
    monkeypatch.setattr(forge, "push_notification", forbidden_delivery)
    monkeypatch.setattr(forge.socketio, "emit", forbidden_delivery)
    edge = accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    service.endorse(a, edge["id"], True, 0)
    service.send(a, slug, "hello", "key")
    service.mark_read(b, slug, 1)
    service.transition(b, edge["id"], "disconnect", 2)
    with service.engine.connect() as connection:
        assert connection.execute(select(text("count(*)")).select_from(
            forge.Notification.__table__)).scalar_one() == 3
    assert service.notification_state(b)["notifications"] == []  # disconnected contact suppressed


def test_reconnection_reuses_history_and_no_synthetic_reply(social):
    service, (a, b, _, _) = social
    edge = accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    service.send(a, slug, "one", "1")
    ended = service.transition(a, edge["id"], "disconnect", 2)
    rerequest = service.request(b, a.id, 3, now=ended["ended_at"] + timedelta(hours=24))
    service.transition(a, edge["id"], "accept", rerequest["version"])
    assert service.open_conversation(b, a.id)["public_id"] == slug
    assert [m["seq"] for m in service.history(b, slug)["messages"]] == [1]
    assert counts(service)[4] == 1 and counts(service)[2:4] == (1, 2)


def test_concurrent_identical_retry_produces_one_message(social):
    service, (a, b, _, _) = social
    accepted(service, a, b)
    slug = service.open_conversation(a, b.id)["public_id"]
    gate = Barrier(3)
    def worker():
        gate.wait()
        return service.send(a, slug, " same text ", "same-key")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        gate.wait()
        assert futures[0].result() == futures[1].result()
    assert counts(service)[4] == 1 and service.history(b, slug)["unread_count"] == 1


def test_rollback_partial_conversation_and_message(social):
    service, (a, b, _, _) = social
    accepted(service, a, b)
    baseline = counts(service)
    original = service._event
    def fail_after_members(*args):
        original(*args)
        if args[2] == "conversation_id":
            raise RuntimeError("injected conversation audit failure")
    service._event = fail_after_members
    with pytest.raises(RuntimeError):
        service.open_conversation(a, b.id)
    assert counts(service) == baseline
    service._event = original
    slug = service.open_conversation(a, b.id)["public_id"]
    original_write = service._write
    # Fail after the message and last_seq update but before the commit.
    from contextlib import contextmanager
    @contextmanager
    def fail_before_commit():
        with service.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
                raise RuntimeError("injected after message write")
            finally:
                connection.rollback()
    service._write = fail_before_commit
    with pytest.raises(RuntimeError):
        service.send(a, slug, "not committed", "key")
    service._write = original_write
    assert service.history(a, slug)["last_seq"] == 0
    assert counts(service)[4] == 0
