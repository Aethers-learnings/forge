"""Regression tests for authenticated Socket.IO room membership."""

import forge_backend


def _make_user(*, username, role, suspended=False):
    user = forge_backend.User(
        username=username,
        password_hash="not-used-by-socket-tests",
        role=role,
        name=username,
        suspended=suspended,
    )
    forge_backend.db.session.add(user)
    forge_backend.db.session.commit()
    return user


def _authenticated_socket(app, user_id):
    flask_client = app.test_client()
    with flask_client.session_transaction() as session:
        session["user_id"] = user_id
    socket_client = forge_backend.socketio.test_client(
        app,
        flask_test_client=flask_client,
    )
    return socket_client


def _event_names(socket_client):
    return [event["name"] for event in socket_client.get_received()]


def test_anonymous_socket_connection_is_rejected(app):
    socket_client = forge_backend.socketio.test_client(app)

    assert socket_client.is_connected() is False


def test_suspended_socket_connection_is_rejected(app):
    with app.app_context():
        user = _make_user(username="suspended-user", role="grad", suspended=True)
        user_id = user.id

    socket_client = _authenticated_socket(app, user_id)

    assert socket_client.is_connected() is False


def test_authenticated_socket_receives_only_its_own_user_room(app):
    with app.app_context():
        alice = _make_user(username="alice", role="grad")
        bob = _make_user(username="bob", role="grad")
        alice_id, bob_id = alice.id, bob.id

    alice_socket = _authenticated_socket(app, alice_id)
    bob_socket = _authenticated_socket(app, bob_id)

    assert alice_socket.is_connected()
    assert bob_socket.is_connected()

    with app.app_context():
        forge_backend.notify_user(bob_id, "private_probe", {"for": "bob"})

    assert "private_probe" not in _event_names(alice_socket)
    assert "private_probe" in _event_names(bob_socket)


def test_client_cannot_join_another_user_or_role_room(app):
    with app.app_context():
        alice = _make_user(username="alice", role="grad")
        bob = _make_user(username="bob", role="trade")
        admin = _make_user(username="admin-user", role="admin")
        alice_id, bob_id, admin_id = alice.id, bob.id, admin.id

    alice_socket = _authenticated_socket(app, alice_id)
    bob_socket = _authenticated_socket(app, bob_id)
    admin_socket = _authenticated_socket(app, admin_id)

    alice_socket.emit("join", {"userId": bob_id, "role": "admin"})

    with app.app_context():
        forge_backend.notify_user(bob_id, "bob_probe", {"for": "bob"})
        forge_backend.notify_role("admin", "admin_probe", {"for": "admin"})

    alice_events = _event_names(alice_socket)
    bob_events = _event_names(bob_socket)
    admin_events = _event_names(admin_socket)

    assert "bob_probe" not in alice_events
    assert "admin_probe" not in alice_events
    assert "bob_probe" in bob_events
    assert "admin_probe" in admin_events


def test_authenticated_socket_receives_its_actual_role_room(app):
    with app.app_context():
        grad = _make_user(username="grad-user", role="grad")
        business = _make_user(username="business-user", role="business")
        grad_id, business_id = grad.id, business.id

    grad_socket = _authenticated_socket(app, grad_id)
    business_socket = _authenticated_socket(app, business_id)

    with app.app_context():
        forge_backend.notify_role("grad", "role_probe", {"role": "grad"})

    assert "role_probe" in _event_names(grad_socket)
    assert "role_probe" not in _event_names(business_socket)


def test_socketio_does_not_allow_wildcard_origins():
    assert forge_backend.socketio.server.eio.cors_allowed_origins != "*"
