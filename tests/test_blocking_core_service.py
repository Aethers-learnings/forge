"""Focused T-107 blocking-core service coverage."""

from datetime import timedelta
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

import forge_backend as forge
from forge_routes.owned_social import (
    Conflict, Forbidden, NotFound, OperationUnavailable, OwnedSocialService,
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



def test_block_racing_request_never_leaves_pending_contact(blocking_social):
    service, (a, b, _, _) = blocking_social; gate = Barrier(3)
    def request():
        gate.wait()
        try: return service.request(a, b.id, 0)['state']
        except OperationUnavailable: return 'denied'
    def block(): gate.wait(); return service.set_block(a, b.id, True, 0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(request); two=ex.submit(block); gate.wait(); assert two.result() is True; assert one.result() in {'pending','denied'}
    edges=service.own_edges(a); assert not edges or all(edge['state']=='cancelled' for edge in edges)


def test_block_racing_conversation_creation_is_denied_or_retained_readonly(blocking_social):
    service, (a, b, _, _) = blocking_social; accepted(service,a,b); gate=Barrier(3)
    def create():
        gate.wait()
        try: return service.open_conversation(b,a.id)['public_id']
        except OperationUnavailable: return None
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(create); two=ex.submit(block); gate.wait(); slug=one.result(); assert two.result() is True
    if slug: assert service.conversation_info(b,slug)['read_only'] is True


def test_block_racing_send_allows_only_prior_commit(blocking_social):
    service, (a,b,_,_) = blocking_social; accepted(service,a,b); slug=service.open_conversation(a,b.id)['public_id']; gate=Barrier(3)
    def send():
        gate.wait()
        try: return service.send(b,slug,'raced','race-send')['seq']
        except OperationUnavailable: return None
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(send); two=ex.submit(block); gate.wait(); sent=one.result(); assert two.result() is True
    assert len(service.history(b,slug)['messages']) == (1 if sent else 0); assert service.conversation_info(b,slug)['read_only']


def test_block_racing_endorsement_leaves_no_active_projection(blocking_social):
    service,(a,b,_,_)=blocking_social; edge=accepted(service,a,b); gate=Barrier(3)
    def endorse():
        gate.wait()
        try: return service.endorse(b,edge['id'],True,0)
        except OperationUnavailable: return None
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(endorse); two=ex.submit(block); gate.wait(); one.result(); assert two.result() is True
    assert service.active_endorsements(b,edge['id']) == []


def test_block_racing_read_cursor_remains_allowed(blocking_social):
    service,(a,b,_,_)=blocking_social; accepted(service,a,b); slug=service.open_conversation(a,b.id)['public_id']; msg=service.send(a,slug,'seen','race-read'); gate=Barrier(3)
    def read(): gate.wait(); return service.mark_read(b,slug,msg['seq'])
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(read); two=ex.submit(block); gate.wait(); assert one.result()==msg['seq']; assert two.result() is True
    assert service.history(b,slug)['last_read_seq']==msg['seq']


def test_block_transaction_rolls_back_all_side_effects(monkeypatch, blocking_social):
    service,(a,b,_,_)=blocking_social; edge=accepted(service,a,b); endorsement=service.endorse(a,edge['id'],True,0)
    monkeypatch.setattr(service,'_block_event',lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('injected block audit failure')))
    with pytest.raises(RuntimeError,match='injected block audit failure'): service.set_block(a,b.id,True,0)
    with service.engine.connect() as connection:
        assert connection.execute(select(service.block)).mappings().all()==[]
        stored_edge=connection.execute(select(service.edge).where(service.edge.c.id==edge['id'])).mappings().one()
        stored_endorsement=connection.execute(select(service.endorsement).where(service.endorsement.c.id==endorsement['id'])).mappings().one()
    assert stored_edge['state']=='accepted' and stored_edge['version']==2; assert stored_endorsement['revoked_at'] is None and stored_endorsement['version']==1


def test_suspension_denies_actor_but_existing_own_block_remains_manageable(blocking_social):
    service,(a,b,_,_)=blocking_social; service.set_block(a,b.id,True,0)
    with service.engine.begin() as connection: connection.execute(service.user.update().where(service.user.c.id==b.id).values(suspended=True))
    assert service.set_block(a,b.id,False,1)['active'] is False
    with service.engine.begin() as connection: connection.execute(service.user.update().where(service.user.c.id==a.id).values(suspended=True))
    with pytest.raises(Forbidden): service.set_block(a,b.id,True,2)
