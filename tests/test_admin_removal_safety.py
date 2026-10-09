"""The removal safety contract is independent of unenforced FK exceptions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event

import forge_backend as forge
import forge_integrity
from forge_integrity import foreign_key_violations, user_reference_exists
from fk_review_fixtures import ROWS, populate, snapshot
from test_whole_schema_fks import FKS, fk_id


def auth(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
    token = client.get("/api/auth/csrf-token").json["csrfToken"]
    return {"Origin": "http://localhost", "X-CSRF-Token": token}


def test_linked_remove_suspends_and_preserves_every_child(app, client):
    with forge.db.engine.begin() as connection:
        populate(connection)
        before = snapshot(connection)
    response = client.post("/api/admin/users/1/remove", headers=auth(client, 3))
    assert response.status_code == 200
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=1").scalar() == 1
        assert snapshot(connection) == before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_unreferenced_remove_fails_closed_while_writers_are_fk_off(app, client):
    with forge.db.engine.begin() as connection:
        populate(connection, {"user"})
    response = client.post("/api/admin/users/1/remove", headers=auth(client, 3))
    assert response.status_code == 200
    assert "suspended" in response.json["note"]
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=1").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def ancestors(table):
    required = {table, "user"}
    while True:
        expanded = required | {fk["parent_table"] for fk in FKS if fk["child_table"] in required}
        if expanded == required:
            return required
        required = expanded


@pytest.mark.parametrize("fk", [fk for fk in FKS if fk["parent_table"] == "user"], ids=fk_id)
def test_every_user_identity_reference_is_preserved(fk, app, client):
    target = ROWS[fk["child_table"]][0][fk["child_columns"][0]]
    with forge.db.engine.begin() as connection:
        populate(connection, ancestors(fk["child_table"]))
        assert user_reference_exists(connection, target)
        before = snapshot(connection)
        target_before = connection.exec_driver_sql("SELECT * FROM user WHERE id=?", (target,)).mappings().one()
    response = client.post(f"/api/admin/users/{target}/remove", headers=auth(client, 3))
    assert response.status_code == 200
    assert response.json == {"ok": True, "note": f"Account {target} has linked activity — suspended instead."}
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=?", (target,)).scalar() == 1
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=?", (3-target,)).scalar() == 0
        assert snapshot(connection) == before
        target_after = connection.exec_driver_sql("SELECT * FROM user WHERE id=?", (target,)).mappings().one()
        assert dict(target_after) == {**target_before, "suspended": 1}
        assert foreign_key_violations(connection) == []


@pytest.mark.parametrize("linked", [False, True])
def test_removal_retires_only_target_devices_and_unsuspend_works(linked, app, client):
    with forge.db.engine.begin() as connection:
        populate(connection, None if linked else {"user"})
    peers, live = [], []
    for user_id in (1, 1, 2, 3):
        peer = app.test_client()
        with peer.session_transaction() as session:
            session["user_id"] = user_id
        peers.append(peer)
        live.append(forge.socketio.test_client(app, flask_test_client=peer))
    try:
        headers = auth(client, 3)
        response = client.post("/api/admin/users/1/remove", headers=headers)
        assert response.status_code == 200
        assert [socket.is_connected() for socket in live] == [False, False, True, True]
        rejected = forge.socketio.test_client(app, flask_test_client=peers[0])
        assert not rejected.is_connected()
        assert client.post("/api/admin/users/1/unsuspend", headers=headers).status_code == 200
        restored = forge.socketio.test_client(app, flask_test_client=peers[0])
        assert restored.is_connected()
        restored.disconnect()
    finally:
        for socket in live:
            if socket.is_connected():
                socket.disconnect()


@pytest.mark.parametrize("action", ["remove", "suspend"])
def test_admin_targets_are_protected(action, app, client):
    with forge.db.engine.begin() as connection:
        populate(connection, {"user"})
    response = client.post(f"/api/admin/users/3/{action}", headers=auth(client, 3))
    assert response.status_code == 400
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=3").scalar() == 0


@pytest.mark.parametrize("failure", ["anonymous", "non-admin", "no-token", "foreign-origin", "missing"])
def test_removal_auth_csrf_and_missing_target(failure, app, client):
    with forge.db.engine.begin() as connection:
        populate(connection, {"user"})
    headers = {} if failure == "anonymous" else auth(client, 1 if failure == "non-admin" else 3)
    if failure == "no-token":
        headers.pop("X-CSRF-Token")
    if failure == "foreign-origin":
        headers["Origin"] = "https://foreign.example"
    response = client.post(f"/api/admin/users/{999 if failure == 'missing' else 1}/remove", headers=headers)
    assert response.status_code == {"anonymous": 401, "non-admin": 403, "no-token": 403,
                                    "foreign-origin": 403, "missing": 404}[failure]
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=1").scalar() == 0


@pytest.mark.parametrize("phase", ["begin", "preflight", "update", "commit"])
def test_transaction_failures_rollback_without_success_or_history_loss(phase, app, client, caplog):
    engine = forge.db.engine
    with engine.begin() as connection:
        populate(connection)
        before = snapshot(connection)
    headers = auth(client, 3)
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
    live = forge.socketio.test_client(app, flask_test_client=live_client)
    def fail_sql(connection, cursor, statement, parameters, context, many):
        if statement == "BEGIN IMMEDIATE":
            connection.info["removal_test"] = True
        triggers = {"begin": "BEGIN IMMEDIATE", "preflight": "PRAGMA foreign_key_list",
                    "update": "UPDATE user"}
        if (phase in triggers and statement.startswith(triggers[phase])
                and connection.info.get("removal_test")):
            raise RuntimeError("private fixture must not be logged")
    def fail_commit(connection):
        if connection.info.get("removal_test"):
            raise RuntimeError("private fixture must not be logged")
    event.listen(engine, "before_cursor_execute", fail_sql)
    if phase == "commit":
        event.listen(engine, "commit", fail_commit)
    try:
        response = client.post("/api/admin/users/1/remove", headers=headers)
        assert response.status_code == 503 and response.json == {"error": "operation unavailable"}
        assert "private fixture" not in caplog.text
        assert live.is_connected()
    finally:
        event.remove(engine, "before_cursor_execute", fail_sql)
        if phase == "commit":
            event.remove(engine, "commit", fail_commit)
        live.disconnect()
    with engine.connect() as connection:
        connection.info.pop("removal_test", None)
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=1").scalar() == 0
        assert snapshot(connection) == before
        assert foreign_key_violations(connection) == []
    # Prove the failed reservation did not poison the pool/next request.
    assert client.post("/api/admin/users/1/remove", headers=headers).status_code == 200


def test_preflight_discovers_new_physical_fk_without_a_manual_list(app, client):
    with forge.db.engine.begin() as connection:
        populate(connection, {"user"})
        connection.exec_driver_sql('CREATE TABLE "future quoted table" (actor INTEGER REFERENCES user(id))')
        connection.exec_driver_sql('INSERT INTO "future quoted table" VALUES (1)')
        assert user_reference_exists(connection, 1)
    response = client.post("/api/admin/users/1/remove", headers=auth(client, 3))
    assert response.json["note"] == "Account 1 has linked activity — suspended instead."


def test_remove_reauthorizes_actor_after_reserving_write_lock(app, client, monkeypatch):
    with forge.db.engine.begin() as connection:
        populate(connection, {"user"})
    original = forge.preflight_admin_remove
    def changed_actor(engine, table, actor, target):
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE user SET suspended=1 WHERE id=3")
        return original(engine, table, actor, target)
    monkeypatch.setattr(forge, "preflight_admin_remove", changed_actor)
    assert client.post("/api/admin/users/1/remove", headers=auth(client, 3)).status_code == 403
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=1").scalar() == 0


@pytest.mark.parametrize("first", ["remove", "child"])
def test_remove_vs_independent_fk_off_child_writer_never_orphans(first, app, client):
    engine = forge.db.engine
    with engine.begin() as connection:
        populate(connection, {"user"})
    reserved, release, competing = Event(), Event(), Event()
    def pause_preflight(connection, target):
        reserved.set()
        assert release.wait(5)
        return original(connection, target)
    original = forge_integrity.user_reference_exists
    def removal():
        if first == "child":
            competing.set()
        with app.test_client() as remover:
            with remover.session_transaction() as session:
                session["user_id"] = 3
            actual_headers = auth(remover, 3)
            return remover.post("/api/admin/users/1/remove", headers=actual_headers).status_code
    def child():
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
            connection.rollback()
            if first == "child":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                reserved.set()
                assert release.wait(5)
            else:
                competing.set()
            connection.exec_driver_sql(
                "INSERT INTO notification (user_id,type,text) VALUES (1,'test','private fixture')")
            connection.commit()
    if first == "remove":
        forge_integrity.user_reference_exists = pause_preflight
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            winner = executor.submit(removal if first == "remove" else child)
            assert reserved.wait(5)
            loser = executor.submit(child if first == "remove" else removal)
            assert competing.wait(5)
            release.set()
            results = (winner.result(timeout=10), loser.result(timeout=10))
            assert 200 in results
    finally:
        release.set()
        forge_integrity.user_reference_exists = original
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT suspended FROM user WHERE id=1").scalar() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM notification WHERE user_id=1").scalar() == 1
        assert foreign_key_violations(connection) == []


def test_clean_remove_is_repeatable_and_names_are_not_identity_links(app, client):
    with forge.db.engine.begin() as connection:
        populate(connection, {"user", "post"})
        assert not user_reference_exists(connection, 1)
    headers = auth(client, 3)
    for _ in range(2):
        assert client.post("/api/admin/users/1/remove", headers=headers).json == {
            "ok": True, "note": "Account 1 suspended instead."}
    with forge.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT author_name FROM post").scalar() == "Account 1"
        assert foreign_key_violations(connection) == []
