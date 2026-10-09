"""Pure caller-owned acceptance projection on migration-managed fixtures."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from test_owned_social_service import social
from forge_routes.owned_social import Forbidden, OperationUnavailable


def connect(service, a, b, when):
    edge = service.request(a, b.id, 0, now=when - timedelta(days=30))
    return service.transition(b, edge['id'], 'accept', 1, now=when)


def test_acceptance_projection_caller_dates_and_read_only(social):
    service, (a, b, c, admin) = social
    today = datetime(2026, 10, 9, 12)
    connect(service, a, b, today)
    connect(service, b, c, today - timedelta(days=3))
    service.request(a, c.id, 0)
    connect(service, admin, c, today - timedelta(days=20))
    statements, packets = [], []
    service.emit = lambda *args, **kwargs: packets.append(args)
    def trace(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(service.engine, 'before_cursor_execute', trace)
    try:
        assert service.accepted_connection_dates(a) == [today]
        assert sorted(service.accepted_connection_dates(b)) == [today - timedelta(days=3), today]
        assert sorted(service.accepted_connection_dates(c)) == [today - timedelta(days=20), today - timedelta(days=3)]
        assert service.accepted_connection_dates(admin) == [today - timedelta(days=20)]
    finally:
        event.remove(service.engine, 'before_cursor_execute', trace)
    assert packets == []
    assert all(s.lstrip().startswith('select ') for s in statements)
    assert not any(name in s for s in statements for name in (
        'network_request', 'connection_npc', 'suggested', 'conversation', 'message',
        'ownership_event', 'notification', 'block_event'))
    edge_queries = [s for s in statements if 'from network_edge' in s]
    assert len(edge_queries) == 4
    assert all(s.startswith('select network_edge.accepted_at ') for s in edge_queries)


@pytest.mark.parametrize('action', ['pending', 'ignore', 'cancel', 'disconnect'])
def test_acceptance_projection_excludes_other_states(social, action):
    service, (a, b, _, _) = social
    edge = service.request(a, b.id, 0)
    if action == 'disconnect':
        service.transition(b, edge['id'], 'accept', 1)
        service.transition(a, edge['id'], action, 2)
    elif action != 'pending':
        service.transition(b if action == 'ignore' else a, edge['id'], action, 1)
    assert service.accepted_connection_dates(a) == []
    assert service.accepted_connection_dates(b) == []


@pytest.mark.parametrize('invalid_actor', ['raw_id', 'suspended', 'missing'])
def test_acceptance_projection_rechecks_actor(social, invalid_actor):
    service, (a, _, _, _) = social
    actor = a
    if invalid_actor == 'raw_id':
        actor = a.id
    else:
        with service.engine.begin() as connection:
            statement = service.user.delete() if invalid_actor == 'missing' else service.user.update().values(suspended=True)
            connection.execute(statement.where(service.user.c.id == a.id))
    with pytest.raises(Forbidden):
        service.accepted_connection_dates(actor)


def test_acceptance_projection_missing_timestamp_fails_closed(social):
    service, (a, b, c, _) = social
    edge = connect(service, a, b, datetime(2026, 10, 9))
    with service.engine.begin() as connection:
        connection.execute(service.edge.update().where(service.edge.c.id == edge['id']).values(accepted_at=None))
    with pytest.raises(OperationUnavailable):
        service.accepted_connection_dates(a)
    assert service.accepted_connection_dates(c) == []  # unrelated corruption does not broaden scope


def test_acceptance_projection_block_unblock_does_not_restore(social):
    service, (a, b, _, _) = social
    connect(service, a, b, datetime(2026, 10, 9))
    service.set_block(b, a.id, True, 0)
    assert service.accepted_connection_dates(a) == []
    service.set_block(b, a.id, False, 1)
    assert service.accepted_connection_dates(a) == []
