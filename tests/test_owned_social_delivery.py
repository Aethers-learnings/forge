"""Durable contact delivery on disposable migration-HEAD SQLite fixtures."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Thread

import pytest
from sqlalchemy import event, select, func

import forge_backend as forge
from forge_routes.owned_social import Conflict, OperationUnavailable, OwnedSocialService


@pytest.fixture
def delivery(app):
    users = [forge.User(username=f"delivery_{i}", name="Same Name",
                        role="admin" if i == 3 else "trade", password_hash="unused")
             for i in range(4)]
    forge.db.session.add_all(users)
    forge.db.session.commit()
    for user in users:
        _ = user.id
    forge.db.session.expunge_all()
    packets = []
    service = OwnedSocialService(forge.db.engine, forge,
                                emit=lambda *args, **kwargs: packets.append((args, kwargs)))
    return service, users, packets


def notes(service):
    with service.engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(service.notification)).mappings()]


def thread(service, a, b):
    edge = service.request(a, b.id, 0)
    service.transition(b, edge["id"], "accept", 1)
    return edge, service.open_conversation(a, b.id)["public_id"]


def test_message_commit_retry_and_minimal_participant_packets(delivery):
    svc, (a, b, c, admin), packets = delivery
    _, slug = thread(svc, a, b)
    before = len(notes(svc)); packets.clear()
    message = svc.send(a, slug, " private body ", "key")
    added = notes(svc)[before:]
    assert len(added) == 1 and added[0]["user_id"] == b.id
    assert added[0]["text"] == "You have a new message."
    invalidations = [(args, kw) for args, kw in packets if args[0] == "new_message"]
    assert {kw["room"] for _, kw in invalidations} == {f"user:{a.id}", f"user:{b.id}"}
    assert all(args[1] == {"conversationId": slug, "lastSequence": 1}
               for args, _ in invalidations)
    assert "private body" not in repr(packets) and "block" not in repr(packets)
    assert all(kw["room"].startswith("user:") for _, kw in packets)
    snapshot = list(packets)
    assert svc.send(a, slug, "private body", "key") == message
    with pytest.raises(Conflict):
        svc.send(a, slug, "changed", "key")
    assert packets == snapshot and len(notes(svc)) == before + 1


def test_request_accept_retries_and_non_contact_operations(delivery):
    svc, (a, b, _, _), packets = delivery
    edge = svc.request(a, b.id, 0)
    assert [n["user_id"] for n in notes(svc)] == [b.id]
    snapshot = list(packets)
    assert svc.request(a, b.id, 0) == edge
    assert packets == snapshot and len(notes(svc)) == 1
    svc.transition(b, edge["id"], "accept", 1)
    assert [n["user_id"] for n in notes(svc)] == [b.id, a.id]
    snapshot = list(packets)
    with pytest.raises(Conflict):
        svc.transition(b, edge["id"], "accept", 1)
    slug = svc.open_conversation(a, b.id)["public_id"]
    svc.mark_read(a, slug, 0)
    svc.endorse(a, edge["id"], True, 0)
    svc.transition(a, edge["id"], "disconnect", 2)
    assert len(notes(svc)) == 2 and packets == snapshot


@pytest.mark.parametrize("operation", ["request", "accept", "send"])
@pytest.mark.parametrize("failure", ["notification", "commit"])
def test_persistence_and_commit_failures_roll_back_everything(delivery, operation, failure):
    svc, (a, b, _, _), packets = delivery
    if operation == "accept":
        edge = svc.request(a, b.id, 0)
    elif operation == "send":
        edge, slug = thread(svc, a, b)
    packets.clear()
    tables = (svc.edge, svc.message, svc.event, svc.notification)
    def snapshot():
        with svc.engine.connect() as conn:
            return [list(conn.execute(select(table)).mappings()) for table in tables]
    before = snapshot()
    def fail(conn, *args):
        if failure == "commit" or args[1].lower().startswith("insert into notification"):
            raise OSError("injected persistence failure")
    hook = "commit" if failure == "commit" else "after_cursor_execute"
    event.listen(svc.engine, hook, fail)
    try:
        with pytest.raises(OSError):
            if operation == "request": svc.request(a, b.id, 0)
            elif operation == "accept": svc.transition(b, edge["id"], "accept", 1)
            else: svc.send(a, slug, "rollback body", "failure")
    finally:
        event.remove(svc.engine, hook, fail)
    assert snapshot() == before and packets == []


def test_emission_failure_is_after_commit_and_never_replays_mutation(delivery, monkeypatch):
    svc, (a, b, _, _), packets = delivery
    _, slug = thread(svc, a, b)
    before = len(notes(svc)); attempts = []
    def fail(*args, **kwargs):
        with svc.engine.connect() as connection:
            assert connection.execute(select(func.count()).select_from(svc.message)).scalar_one() == 1
            assert len(notes(svc)) == before + 1
        attempts.append(args[0])
        raise OSError("sensitive details must not be logged")
    monkeypatch.setattr(svc, "emit", fail)
    result = svc.send(a, slug, "committed body", "emission-failure")
    assert result["seq"] == 1 and len(attempts) == 3
    svc.send(a, slug, "committed body", "emission-failure")
    assert len(attempts) == 3


@pytest.mark.parametrize("change", ["block", "disconnect", "suspend", "delete", "membership"])
def test_commit_then_ineligibility_suppresses_delivery(delivery, monkeypatch, change):
    svc, (a, b, _, _), packets = delivery
    edge, slug = thread(svc, a, b)
    packets.clear(); original = svc._deliver
    def interleave(intents):
        other = OwnedSocialService(svc.engine, forge)
        if change == "block": other.set_block(b, a.id, True, 0)
        elif change == "disconnect": other.transition(b, edge["id"], "disconnect", 2)
        else:
            with svc.engine.begin() as connection:
                if change == "suspend":
                    connection.execute(svc.user.update().where(svc.user.c.id == b.id).values(suspended=True))
                elif change == "delete":
                    connection.execute(svc.user.delete().where(svc.user.c.id == b.id))
                else:
                    connection.execute(svc.member.delete().where(svc.member.c.user_id == b.id))
        original(intents)
    monkeypatch.setattr(svc, "_deliver", interleave)
    assert svc.send(a, slug, "historical", "race")["seq"] == 1
    assert packets == [] and len(notes(svc)) == 3
    if change != "membership":
        assert svc.history(a, slug)["messages"][0]["text"] == "historical"
    assert svc.notification_state(a)["unreadCount"] == (1 if change == "membership" else 0)
    if change not in ("suspend", "delete"):
        assert svc.notification_state(b)["unreadCount"] == 0


def test_block_suppression_survives_unblock_reconnect(delivery):
    svc, (a, b, c, _), packets = delivery
    edge, slug = thread(svc, a, b)
    svc.send(a, slug, "historical", "history")
    unrelated = svc.request(c, b.id, 0)
    svc.set_block(a, b.id, True, 0)
    visible = svc.notification_state(b)
    assert visible["unreadCount"] == 1 and len(visible["notifications"]) == 1
    assert visible["notifications"][0]["link"].startswith(f"network:{unrelated['id']}:")
    svc.set_block(a, b.id, False, 1)
    from datetime import timedelta
    ended = svc.own_edges(a)[0]
    fresh = svc.request(b, a.id, ended["version"], now=ended["ended_at"] + timedelta(hours=25))
    svc.transition(a, edge["id"], "accept", fresh["version"])
    assert svc.notification_state(b)["unreadCount"] == 2
    assert len(notes(svc)) == 6  # retain suppressed rows, never delete history
    svc.send(a, slug, "historical", "history")  # historical retry does not redeliver


@pytest.mark.parametrize("operation", ["request", "accept", "send"])
def test_block_commit_before_authorization_denies_contact(delivery, operation):
    svc, (a, b, _, _), packets = delivery
    if operation == "accept": edge = svc.request(a, b.id, 0)
    elif operation == "send": edge, slug = thread(svc, a, b)
    # Hold the block's independent write connection while the operation starts.
    entered, release = Event(), Event(); original = svc._block_event
    def pause(*args):
        original(*args); entered.set(); assert release.wait(5)
    svc._block_event = pause
    with ThreadPoolExecutor(max_workers=2) as executor:
        blocked = executor.submit(svc.set_block, b, a.id, True, 0)
        assert entered.wait(5)
        if operation == "request": future = executor.submit(svc.request, a, b.id, 0)
        elif operation == "accept": future = executor.submit(svc.transition, b, edge["id"], "accept", 1)
        else: future = executor.submit(svc.send, a, slug, "denied", "denied")
        release.set(); blocked.result(); packets.clear(); before = len(notes(svc))
        with pytest.raises(OperationUnavailable): future.result()
    assert len(notes(svc)) == before and packets == []


@pytest.mark.parametrize("operation", ["request", "accept"])
def test_request_and_accept_commit_then_block_suppresses_packet(delivery, monkeypatch, operation):
    svc, (a, b, _, _), packets = delivery
    if operation == "accept": edge = svc.request(a, b.id, 0)
    packets.clear(); original = svc._deliver
    def interleave(intents):
        OwnedSocialService(svc.engine, forge).set_block(b, a.id, True, 0)
        original(intents)
    monkeypatch.setattr(svc, "_deliver", interleave)
    if operation == "request": svc.request(a, b.id, 0)
    else: svc.transition(b, edge["id"], "accept", 1)
    assert len(notes(svc)) == (1 if operation == "request" else 2)
    assert packets == [] and svc.notification_state(a)["unreadCount"] == 0
    assert svc.notification_state(b)["unreadCount"] == 0


def test_concurrent_same_key_message_has_one_notification_and_invalidation(delivery):
    svc, (a, b, _, _), packets = delivery
    _, slug = thread(svc, a, b); packets.clear(); before = len(notes(svc))
    gate = Barrier(3)
    def send():
        gate.wait()
        return svc.send(a, slug, " same body ", "shared-retry")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send) for _ in range(2)]
        gate.wait()
        assert futures[0].result() == futures[1].result()
    assert len(notes(svc)) == before + 1 and len(packets) == 3


def test_failed_block_rolls_back_notification_hint_suppression(delivery, monkeypatch):
    svc, (a, b, _, _), packets = delivery
    _, slug = thread(svc, a, b); svc.send(a, slug, "retained", "retained")
    before = notes(svc); packets.clear()
    def fail(*args): raise OSError("block audit failure")
    monkeypatch.setattr(svc, "_block_event", fail)
    with pytest.raises(OSError): svc.set_block(a, b.id, True, 0)
    assert notes(svc) == before and packets == []
    assert svc.notification_state(b)["unreadCount"] == 1


def test_emit_failure_logs_no_payload_exception_or_identity(delivery, monkeypatch, caplog):
    svc, (a, b, _, _), _ = delivery
    _, slug = thread(svc, a, b)
    def fail(*args, **kwargs): raise OSError("SECRET EVIDENCE user:123 block reason")
    monkeypatch.setattr(svc, "emit", fail)
    svc.send(a, slug, "MESSAGE SECRET", "sensitive-error")
    assert "Owned social realtime delivery unavailable" in caplog.text
    assert all(secret not in caplog.text for secret in ("SECRET", "user:123", "block", slug))


def test_final_delivery_reservation_serializes_against_block_commit(delivery, monkeypatch):
    svc, (a, b, _, _), packets = delivery
    _, slug = thread(svc, a, b); packets.clear()
    entered, release, block_started, block_committed = (Event() for _ in range(4))
    order = []
    def emit(*args, **kwargs):
        if not entered.is_set():
            entered.set(); assert release.wait(5)
            assert not block_committed.is_set()
        order.append("packet")
    monkeypatch.setattr(svc, "emit", emit)
    other = OwnedSocialService(svc.engine, forge)
    def block():
        block_started.set(); other.set_block(b, a.id, True, 0)
        order.append("block"); block_committed.set()
    with ThreadPoolExecutor(max_workers=2) as executor:
        sending = executor.submit(svc.send, a, slug, "committed first", "reservation")
        assert entered.wait(5)
        blocking = executor.submit(block); assert block_started.wait(5)
        release.set(); sending.result(); blocking.result()
    assert order[0] == "packet" and "packet" not in order[order.index("block") + 1:]
    assert svc.history(a, slug)["messages"][0]["text"] == "committed first"
