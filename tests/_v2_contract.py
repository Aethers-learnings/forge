"""Runs in a fresh process with FORGE_SOCIAL_MODE=v2."""
import pytest
from sqlalchemy import event, select
import forge_backend as forge
from forge_routes.owned_social import OwnedSocialService


@pytest.fixture
def world(app):
    assert app.config["FORGE_SOCIAL_MODE"] == "v2"
    users = [forge.User(username=f"v2_{i}", name=f"User {i}", role="admin" if i == 3 else "trade",
                        password_hash="unused", color="#123456") for i in range(4)]
    forge.db.session.add_all(users)
    forge.db.session.commit()
    ids = [u.id for u in users]
    return ids, OwnedSocialService(forge.db.engine, forge)


def auth(client, uid, *, cap="2", csrf=True):
    with client.session_transaction() as session:
        session["user_id"] = uid
        session["csrf_user_id"] = uid
        session["csrf_token"] = "valid"
    headers = {"Origin": "http://localhost", "X-CSRF-Token": "valid" if csrf else "bad"}
    if cap is not None:
        headers["X-Forge-Ownership-Version"] = cap
    return headers


def post(client, path, data, headers):
    return client.post(path, json=data, headers=headers)


def test_gate_order_and_absent_object(client, world):
    (a, b, c, admin), svc = world
    assert client.get('/api/network').status_code == 401
    h = auth(client, a, cap=None, csrf=False)
    assert post(client, '/api/network/suggested/999/connect', {"expectedVersion": 0}, h).status_code == 403
    h = auth(client, a, cap=None)
    response = post(client, '/api/network/suggested/999/connect', {"expectedVersion": 0}, h)
    assert response.status_code == 426 and response.json == {"error": "ownership client update required"}
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/conversations/not-real', headers=h).status_code == 426
    h = auth(client, a)
    assert client.get('/api/conversations/not-real', headers=h).status_code == 404
    assert post(client, '/api/network/suggested/999/connect', {"expectedVersion": 0}, h).status_code == 404
    assert post(client, '/api/network/suggested/1/connect', {}, h).status_code == 428
    assert post(client, '/api/network/suggested/1/connect', {"expectedVersion": 0, "actorId": b}, h).status_code == 400
    assert svc.own_edges(forge.db.session.get(forge.User, a)) == []


def test_network_transitions_endorsements_privacy(client, world):
    (a, b, c, admin), svc = world
    h = auth(client, a)
    path = f'/api/network/suggested/{b}/connect'
    created = post(client, path, {"expectedVersion": 0}, h)
    assert created.status_code == 200
    edge = created.json['requestId']
    assert post(client, path, {"expectedVersion": 0}, h).json == created.json
    assert post(client, f'/api/network/suggested/{a}/connect', {"expectedVersion": 1}, auth(client, b)).status_code == 409
    listed = client.get('/api/network', headers=auth(client, a)).json
    assert listed['requests'] == [] and listed['outgoingRequests'][0]['id'] == edge
    assert client.get('/api/network', headers=auth(client, c)).json['connections'] == []
    assert post(client, f'/api/network/requests/{edge}/accept', {"expectedVersion": 1}, auth(client, a)).status_code == 403
    assert post(client, f'/api/network/requests/{edge}/accept', {"expectedVersion": 1}, auth(client, c)).status_code == 404
    assert post(client, f'/api/network/requests/{edge}/accept', {"expectedVersion": 1}, auth(client, b)).json['version'] == 2
    assert post(client, f'/api/network/requests/{edge}/accept', {"expectedVersion": 1}, auth(client, b)).status_code == 409
    epath = f'/api/network/connections/{edge}/endorse'
    assert post(client, epath, {"endorsed": True, "expectedVersion": 0}, auth(client, a)).json['version'] == 1
    assert post(client, epath, {"endorsed": True, "expectedVersion": 0}, auth(client, a)).json['version'] == 1
    assert client.get('/api/network', headers=auth(client, b)).json['connections'][0]['endorsements'] == 0
    assert client.get('/api/network', headers=auth(client, admin)).json['connections'] == []
    assert post(client, epath, {"endorsed": False, "expectedVersion": 1}, auth(client, a)).json['version'] == 2
    assert post(client, epath, {"endorsed": False, "expectedVersion": 1}, auth(client, a)).json['version'] == 2
    assert post(client, f'/api/network/requests/{edge}/disconnect', {"expectedVersion": 2}, auth(client, b)).json['version'] == 3


def test_conversation_creation_history_read_retry_and_isolation(client, world):
    (a, b, c, admin), svc = world
    actor, peer = (forge.db.session.get(forge.User, n) for n in (a, b))
    edge = svc.request(actor, b, 0)
    svc.transition(peer, edge['id'], 'accept', 1)
    h = auth(client, a)
    opened = post(client, '/api/conversations', {"targetUserId": b}, h)
    assert opened.status_code == 201, opened.json
    slug = opened.json['id']
    assert post(client, '/api/conversations', {"targetUserId": b}, h).status_code == 200
    assert post(client, '/api/conversations', {"targetUserId": b, "senderId": c}, h).status_code == 400
    missing = client.get('/api/conversations/missing', headers=auth(client, c))
    foreign = client.get(f'/api/conversations/{slug}', headers=auth(client, c))
    assert foreign.status_code == missing.status_code == 404 and foreign.json == missing.json
    assert client.get('/api/conversations', headers=auth(client, admin)).json == []
    send_path = f'/api/conversations/{slug}/messages'
    h = auth(client, a)
    for i in range(55):
        payload = {"text": f' message {i} ', "clientMessageId": f'key-{i}'}
        result = post(client, send_path, payload, h)
        assert result.status_code == 201, result.json
    retry = post(client, send_path, {"text": 'message 54', "clientMessageId": 'key-54'}, h)
    assert retry.status_code == 200 and retry.json['message']['sequence'] == 55
    assert post(client, send_path, {"text": 'changed', "clientMessageId": 'key-54'}, h).status_code == 409
    assert post(client, send_path, {"text": 'x', "clientMessageId": 'x', "who": 'them'}, h).status_code == 400
    detail = client.get(f'/api/conversations/{slug}', headers=auth(client, b))
    assert detail.status_code == 200 and len(detail.json['messages']) == 50
    assert detail.json['messages'][0]['sequence'] == 6 and detail.json['messages'][-1]['sequence'] == 55
    assert detail.json['messages'][0]['who'] == 'them' and detail.json['unreadCount'] == 55
    assert detail.json['lastReadSequence'] == 0 and detail.json['hasMore']
    older = client.get(f'/api/conversations/{slug}?before={detail.json["nextCursor"]}', headers=auth(client, b))
    assert [m['sequence'] for m in older.json['messages']] == [1, 2, 3, 4, 5]
    assert not older.json['hasMore']
    assert client.get(f'/api/conversations/{slug}?before={detail.json["nextCursor"]}', headers=auth(client, a)).status_code == 400
    assert client.get(f'/api/conversations/{slug}?before={detail.json["nextCursor"]}x', headers=auth(client, b)).status_code == 400
    assert post(client, f'/api/conversations/{slug}/read', {"upToSequence": 20}, auth(client, b)).json == {"lastReadSequence": 20, "unreadCount": 35}
    assert post(client, f'/api/conversations/{slug}/read', {"upToSequence": 10}, auth(client, b)).json['lastReadSequence'] == 20
    assert post(client, f'/api/conversations/{slug}/read', {"upToSequence": 56}, auth(client, b)).status_code == 400
    assert client.get(f'/api/conversations/{slug}', headers=auth(client, b)).json['lastReadSequence'] == 20
    svc.transition(peer, edge['id'], 'disconnect', 2)
    assert client.get(f'/api/conversations/{slug}', headers=auth(client, b)).json['readOnly']
    assert post(client, send_path, {"text": 'new', "clientMessageId": 'new'}, auth(client, a)).status_code == 409
    assert post(client, send_path, {"text": 'message 54', "clientMessageId": 'key-54'}, auth(client, a)).status_code == 200


def test_network_cursor_and_legacy_sql_quarantine(client, world):
    (a, b, c, admin), svc = world
    h = auth(client, a)
    traced = []
    def trace(connection, cursor, statement, parameters, context, executemany):
        traced.append(statement.lower())
    event.listen(forge.db.engine, 'before_cursor_execute', trace)
    try:
        first = client.get('/api/network?suggestedLimit=1', headers=h)
        assert first.status_code == 200 and len(first.json['suggested']) == 1
        token = first.json['nextCursors']['suggested']
        second = client.get('/api/network?suggestedLimit=1&suggestedCursor=' + token, headers=h)
        assert second.status_code == 200 and second.json['suggested'][0]['id'] != first.json['suggested'][0]['id']
        assert client.get('/api/network?suggestedCursor=' + token, headers=auth(client, b)).status_code == 400
        assert client.get('/api/network?suggestedCursor=' + token + 'x', headers=h).status_code == 400
        assert client.get('/api/network?limit=51', headers=h).status_code == 400
        assert client.get('/api/network?limit=1&limit=2', headers=h).status_code == 400
        assert post(client, f'/api/network/suggested/{b}/connect', {"expectedVersion": 0}, auth(client, a)).status_code == 200
        assert client.get('/api/conversations', headers=auth(client, a)).status_code == 200
    finally:
        event.remove(forge.db.engine, 'before_cursor_execute', trace)
    import re
    assert not any(re.search(r'\b(?:from|into|update|join)\s+(?:network_request|suggested|connection_npc|conversation|message)\b', s) for s in traced)


def test_all_unsafe_families_auth_csrf_capability_order(client, world):
    (a, b, c, admin), svc = world
    paths = [f'/api/network/suggested/{b}/connect', '/api/network/requests/999/accept',
             '/api/network/connections/999/endorse', '/api/conversations',
             '/api/conversations/absent/messages', '/api/conversations/absent/read']
    for path in paths:
        with client.session_transaction() as session:
            session.clear()
        assert post(client, path, {}, {}).status_code == 401
        assert post(client, path, {}, auth(client, a, cap=None, csrf=False)).status_code == 403
        for capability in (None, '1', '2,1'):
            assert post(client, path, {}, auth(client, a, cap=capability)).status_code == 426
    with forge.db.engine.begin() as connection:
        connection.execute(svc.user.update().where(svc.user.c.id == a).values(suspended=True))
    assert client.get('/api/network', headers=auth(client, a)).status_code == 403


def test_conversation_list_cursor_scope_and_no_delivery(client, world, monkeypatch):
    (a, b, c, admin), svc = world
    def forbidden(*args, **kwargs):
        raise AssertionError('delivery side effect')
    monkeypatch.setattr(forge, 'notify_user', forbidden)
    monkeypatch.setattr(forge, 'push_notification', forbidden)
    actor = forge.db.session.get(forge.User, a)
    peers = [forge.User(username=f'extra_{i}', name=f'Extra {i}', role='trade',
                        color='#000000', password_hash='unused') for i in range(51)]
    forge.db.session.add_all(peers)
    forge.db.session.commit()
    for peer in peers:
        edge = svc.request(actor, peer.id, 0)
        svc.transition(peer, edge['id'], 'accept', 1)
        svc.open_conversation(actor, peer.id)
    h = auth(client, a)
    first = client.get('/api/conversations?limit=50', headers=h)
    assert first.status_code == 200 and len(first.json) == 50
    token = first.headers['X-Next-Cursor']
    second = client.get('/api/conversations?cursor=' + token, headers=h)
    assert second.status_code == 200 and len(second.json) == 1
    assert second.json[0]['id'] not in {row['id'] for row in first.json}
    assert client.get('/api/conversations?cursor=' + token, headers=auth(client, b)).status_code == 400
    assert client.get('/api/conversations?cursor=' + token + 'x', headers=auth(client, a)).status_code == 400
    assert client.get('/api/conversations?limit=0', headers=auth(client, a)).status_code == 400
    slug = first.json[0]['id']
    assert client.get('/api/conversations/' + slug + '?before=' + token,
                      headers=auth(client, a)).status_code == 400
    send = post(client, f'/api/conversations/{slug}/messages',
                {'text': 'Hi', 'clientMessageId': 'opaque-1'}, auth(client, a))
    assert send.status_code == 201 and send.json['message']['who'] == 'me'
    assert len(client.get('/api/conversations', headers=auth(client, a)).json[0]['messages']) <= 1


def test_sql_trace_all_v2_operations_and_capability_before_lookup(client, world, monkeypatch):
    (a, b, c, admin), svc = world
    monkeypatch.setattr(forge.socketio, 'emit', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('socket delivery')))
    monkeypatch.setattr(forge, 'push_notification', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('notification')))
    monkeypatch.setattr(forge, 'notify_user', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('delivery')))
    sql = []
    def trace(connection, cursor, statement, parameters, context, executemany):
        sql.append(statement.lower())
    event.listen(forge.db.engine, 'before_cursor_execute', trace)
    try:
        assert post(client, '/api/network/requests/999/accept', {}, auth(client, a, cap=None)).status_code == 426
        assert not any('network_edge' in statement for statement in sql)
        created = post(client, f'/api/network/suggested/{b}/connect', {'expectedVersion': 0}, auth(client, a))
        edge = created.json['requestId']
        assert client.get('/api/network', headers=auth(client, b)).status_code == 200
        assert post(client, f'/api/network/requests/{edge}/accept', {'expectedVersion': 1}, auth(client, b)).status_code == 200
        assert post(client, f'/api/network/connections/{edge}/endorse', {'endorsed': True, 'expectedVersion': 0}, auth(client, a)).status_code == 200
        convo = post(client, '/api/conversations', {'targetUserId': b}, auth(client, a))
        assert convo.status_code == 201
        slug = convo.json['id']
        assert client.get('/api/conversations', headers=auth(client, a)).status_code == 200
        assert client.get('/api/conversations/' + slug, headers=auth(client, b)).status_code == 200
        assert post(client, f'/api/conversations/{slug}/messages',
                    {'text': 'one', 'clientMessageId': 'one'}, auth(client, a)).status_code == 201
        assert post(client, f'/api/conversations/{slug}/read',
                    {'upToSequence': 1}, auth(client, b)).status_code == 200
        assert post(client, f'/api/network/requests/{edge}/disconnect',
                    {'expectedVersion': 2}, auth(client, a)).status_code == 200
    finally:
        event.remove(forge.db.engine, 'before_cursor_execute', trace)
    import re
    assert not any(re.search(r'\b(?:from|into|update|join)\s+(?:network_request|suggested|connection_npc|conversation|message)\b', statement) for statement in sql)


def test_v2_public_config(client):
    response = client.get('/api/social-config')
    assert response.json == {'mode': 'v2'}
    assert response.headers['Cache-Control'] == 'no-store'
