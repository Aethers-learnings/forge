"""Real independent authenticated sockets and HTTP in the fixed v2 process."""
import pytest
from sqlalchemy import select, event

import forge_backend as forge
from test_owned_social_delivery import delivery, notes, thread
from _v2_contract import auth, post


def sockets(app, users):
    clients, sockets = [], []
    for user in users:
        client = app.test_client()
        auth(client, user.id)
        socket = forge.socketio.test_client(app, flask_test_client=client)
        assert socket.is_connected()
        # Actor-controlled subscriptions cannot redirect server delivery.
        socket.emit("join", {"userId": users[1].id, "role": "admin", "room": "role:trade"})
        clients.append(client); sockets.append(socket)
    return clients, sockets


def received(sockets):
    return [socket.get_received() if socket.is_connected() else [] for socket in sockets]


def test_http_message_delivery_independent_users_devices_and_role_isolation(app, delivery):
    svc, (a, b, c, admin), _ = delivery
    _, slug = thread(svc, a, b)
    clients, live = sockets(app, (a, b, c, admin, a))
    try:
        path = f"/api/conversations/{slug}/messages"
        h = auth(clients[0], a.id)
        body = {"text": "private socket body", "clientMessageId": "real-client-key"}
        assert post(clients[0], path, body, h).status_code == 201
        packets = received(live)
        for index in (0, 1, 4):
            messages = [p for p in packets[index] if p["name"] == "new_message"]
            assert len(messages) == 1
            assert messages[0]["args"] == [{"conversationId": slug, "lastSequence": 1}]
        assert packets[2] == packets[3] == []
        assert all(p["name"] != "notification" for i in (0, 4) for p in packets[i])
        assert sum(p["name"] == "notification" for p in packets[1]) == 1
        assert "private socket body" not in repr(packets) and "block" not in repr(packets)
        before = len(notes(svc))
        assert post(clients[0], path, body, h).status_code == 200
        assert received(live) == [[], [], [], [], []] and len(notes(svc)) == before
        assert post(clients[0], path, {**body, "text": "changed"}, h).status_code == 409
        for extra in ({"room": "user:3"}, {"senderId": c.id}, {"role": "admin"}):
            assert post(clients[0], path, {**body, **extra}, h).status_code == 400
        for index in (2, 3):
            assert post(clients[index], path, body, auth(clients[index], (c, admin)[index-2].id)).status_code == 404
        assert received(live) == [[], [], [], [], []]
        response = clients[1].get("/api/notifications")
        assert response.headers["Cache-Control"] == "no-store"
        message_notes = [n for n in response.json["notifications"] if n["type"] == "owned_message"]
        assert len(message_notes) == 1 and message_notes[0]["text"] == "You have a new message."
        assert set(message_notes[0]) == {"id", "type", "text", "link", "read", "createdAt"}
    finally:
        for socket in live:
            if socket.is_connected(): socket.disconnect()


def test_http_request_accept_actual_recipient_and_noop_packets(app, delivery):
    svc, users, _ = delivery
    a, b, c, admin = users
    clients, live = sockets(app, users)
    try:
        h = auth(clients[0], a.id)
        path = f"/api/network/suggested/{b.id}/connect"
        first = post(clients[0], path, {"expectedVersion": 0}, h)
        assert first.status_code == 200
        packets = received(live)
        assert packets[0] == packets[2] == packets[3] == []
        assert len(packets[1]) == 1 and packets[1][0]["name"] == "notification"
        assert post(clients[0], path, {"expectedVersion": 0}, h).json == first.json
        assert received(live) == [[], [], [], []] and len(notes(svc)) == 1
        edge = first.json["requestId"]
        accept = f"/api/network/requests/{edge}/accept"
        assert post(clients[1], accept, {"expectedVersion": 1}, auth(clients[1], b.id)).status_code == 200
        packets = received(live)
        assert len(packets[0]) == 1 and packets[1] == packets[2] == packets[3] == []
        assert post(clients[1], accept, {"expectedVersion": 1}, auth(clients[1], b.id)).status_code == 409
        assert received(live) == [[], [], [], []] and len(notes(svc)) == 2
    finally:
        for socket in live: socket.disconnect()


@pytest.mark.parametrize("action", ["suspend", "remove"])
def test_moderation_retires_only_target_sockets_and_rejects_rejoin(app, delivery, action):
    svc, users, _ = delivery
    a, b, c, admin = users
    clients, live = sockets(app, users)
    try:
        response = post(clients[3], f"/api/admin/users/{b.id}/{action}", {}, auth(clients[3], admin.id))
        assert response.status_code == 200
        assert not live[1].is_connected()
        assert all(live[i].is_connected() for i in (0, 2, 3))
        rejected = forge.socketio.test_client(app, flask_test_client=clients[1])
        assert not rejected.is_connected()
        anonymous = forge.socketio.test_client(app, flask_test_client=app.test_client())
        assert not anonymous.is_connected()
    finally:
        for socket in live:
            if socket.is_connected(): socket.disconnect()


def test_suspended_connected_client_join_is_disconnected(app, delivery):
    svc, users, _ = delivery
    clients, live = sockets(app, users)
    try:
        with svc.engine.begin() as connection:
            connection.execute(svc.user.update().where(svc.user.c.id == users[1].id).values(suspended=True))
        live[1].emit("join", {"userId": users[0].id, "role": "admin"})
        assert not live[1].is_connected()
    finally:
        for socket in live:
            if socket.is_connected(): socket.disconnect()


def test_block_filters_notifications_counts_exports_links_and_preserves_member_history(app, delivery):
    svc, (a, b, c, admin), _ = delivery
    _, slug = thread(svc, a, b)
    svc.send(a, slug, "private history", "history")
    client = app.test_client(); auth(client, b.id)
    assert client.get("/api/notifications").json["unreadCount"] == 1
    svc.set_block(a, b.id, True, 0)
    assert client.get("/api/notifications").json == {"notifications": [], "unreadCount": 0}
    export = client.get("/api/profile/export")
    assert export.json["notifications"] == [] and export.headers["Cache-Control"] == "no-store"
    assert "block" not in repr(notes(svc)) and "private history" not in repr(notes(svc))
    assert len(notes(svc)) == 3
    assert client.get(f"/api/conversations/{slug}", headers=auth(client, b.id)).json["messages"][0]["text"] == "private history"
    svc.set_block(a, b.id, False, 1)
    assert client.get("/api/notifications").json["unreadCount"] == 0


def test_http_commit_failure_returns_no_success_or_packet(app, delivery):
    svc, users, _ = delivery
    a, b, _, _ = users
    clients, live = sockets(app, users)
    def fail_social_commit(connection):
        # require_login's separate last_seen commit is intentionally retained.
        if "owned_social_delivery" in connection.info:
            raise OSError("injected domain commit failure")
    event.listen(svc.engine, "commit", fail_social_commit)
    try:
        with pytest.raises(OSError):
            post(clients[0], f"/api/network/suggested/{b.id}/connect",
                 {"expectedVersion": 0}, auth(clients[0], a.id))
        assert notes(svc) == [] and svc.own_edges(a) == []
        assert received(live) == [[], [], [], []]
    finally:
        event.remove(svc.engine, "commit", fail_social_commit)
        for socket in live: socket.disconnect()


def test_http_emit_failure_still_returns_commit_and_refresh_recovers(app, delivery, monkeypatch):
    svc, (a, b, _, _), _ = delivery
    _, slug = thread(svc, a, b)
    client = app.test_client(); h = auth(client, a.id); attempts = []
    def fail(*args, **kwargs):
        attempts.append(args[0]); raise OSError("socket unavailable")
    monkeypatch.setattr(forge.socketio, "emit", fail)
    body = {"text": "Recovered over authorized HTTP", "clientMessageId": "lost-packet"}
    response = post(client, f"/api/conversations/{slug}/messages", body, h)
    assert response.status_code == 201 and len(attempts) == 3
    assert len(notes(svc)) == 3
    assert client.get(f"/api/conversations/{slug}", headers=h).json["messages"][0]["text"] == body["text"]
    assert post(client, f"/api/conversations/{slug}/messages", body, h).status_code == 200
    assert len(attempts) == 3 and len(notes(svc)) == 3


@pytest.mark.parametrize("action,actor_index", [("ignore", 1), ("cancel", 0)])
def test_terminal_requests_create_no_extra_contact(app, delivery, action, actor_index):
    svc, users, packets = delivery
    a, b, _, _ = users
    edge = svc.request(a, b.id, 0); packets.clear()
    client = app.test_client()
    response = post(client, f"/api/network/requests/{edge['id']}/{action}",
                    {"expectedVersion": 1}, auth(client, users[actor_index].id))
    assert response.status_code == 200 and len(notes(svc)) == 1 and packets == []
    assert svc.notification_state(b)["notifications"] == []
