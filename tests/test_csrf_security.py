"""Exercise CSRF through Flask requests and real isolated database mutations."""
from io import BytesIO

import pytest
from werkzeug.security import generate_password_hash

import forge_backend as backend


def make_user(username="alice", role="grad", suspended=False):
    user = backend.User(username=username, name=username, role=role,
                        password_hash=generate_password_hash("password123"), suspended=suspended)
    backend.db.session.add(user)
    backend.db.session.commit()
    return user.id


@pytest.fixture
def signed_in(client):
    uid = make_user()
    with client.session_transaction() as session:
        session["user_id"] = uid
    return client


def token(client):
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.json["csrfToken"]


def headers(client):
    return {"X-CSRF-Token": token(client), "Origin": "http://localhost"}


def test_authenticated_token_is_stable_random_and_session_bound(signed_in, app):
    first = token(signed_in)
    assert len(first) >= 43
    assert token(signed_in) == first
    second = app.test_client()
    with signed_in.session_transaction() as original, second.session_transaction() as session:
        session["user_id"] = original["user_id"]
    assert token(second) != first
    response = second.post("/api/posts", json={"body": "forged"},
                           headers={"Origin": "http://localhost", "X-CSRF-Token": first})
    assert response.status_code == 403
    assert backend.Post.query.count() == 0


def test_token_endpoint_requires_active_user(client):
    assert client.get("/api/auth/csrf-token").status_code == 401
    uid = make_user(suspended=True)
    with client.session_transaction() as session:
        session["user_id"] = uid
    assert client.get("/api/auth/csrf-token").status_code == 403


def test_valid_token_permits_real_mutation(signed_in):
    response = signed_in.post("/api/posts", json={"body": "allowed"}, headers=headers(signed_in))
    assert response.status_code == 201
    assert backend.Post.query.one().body == "allowed"


@pytest.mark.parametrize("supplied", [None, "", "wrong", "é"])
def test_missing_or_wrong_token_blocks_mutation(signed_in, supplied):
    token(signed_in)
    h = {"Origin": "http://localhost"}
    if supplied is not None:
        h["X-CSRF-Token"] = supplied
    response = signed_in.post("/api/posts", json={"body": "blocked"}, headers=h)
    assert response.status_code == 403
    assert response.json["code"] == "csrf_failed"
    assert backend.Post.query.count() == 0


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost.evil.example",
    "https://localhost", "http://localhost:81", "null", "", "http://localhost/path",
    "http://localhost?query", "http://evil@localhost", "http://localhost:invalid",
    "http://localhost https://evil.example", "http://localhost\\@evil.example"])
def test_foreign_or_malformed_origin_rejected_even_with_valid_referer(signed_in, origin):
    h = headers(signed_in)
    h.update(Origin=origin, Referer="http://localhost/page")
    response = signed_in.post("/api/posts", json={"body": "blocked"}, headers=h)
    assert response.status_code == 403
    assert backend.Post.query.count() == 0


@pytest.mark.parametrize("source", [{"Origin": "http://LOCALHOST:80"},
    {"Referer": "http://localhost/page?view=feed"}])
def test_same_origin_and_referer_fallback(signed_in, source):
    response = signed_in.post("/api/posts", json={"body": "allowed"},
                             headers={"X-CSRF-Token": token(signed_in), **source})
    assert response.status_code == 201


@pytest.mark.parametrize("source", [{}, {"Referer": "https://evil.example/page"},
    {"Referer": "/relative"}, {"Referer": "null"}])
def test_missing_or_foreign_referer_rejected(signed_in, source):
    response = signed_in.post("/api/posts", json={"body": "blocked"},
                             headers={"X-CSRF-Token": token(signed_in), **source})
    assert response.status_code == 403


def test_forwarded_headers_do_not_change_target_origin(signed_in):
    h = headers(signed_in)
    h.update({"Origin": "https://public.example", "X-Forwarded-Host": "public.example",
              "X-Forwarded-Proto": "https", "Forwarded": "host=public.example;proto=https"})
    assert signed_in.post("/api/posts", json={"body": "blocked"}, headers=h).status_code == 403
    h["Origin"] = "http://localhost"
    assert signed_in.post("/api/posts", json={"body": "allowed"}, headers=h).status_code == 201


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_need_no_csrf(signed_in, method):
    assert signed_in.open("/api/feed", method=method).status_code == 200


@pytest.mark.parametrize("method,path,payload,allowed_status", [
    ("POST", "/api/posts", {"body": "allowed"}, 201),
    ("PATCH", "/api/profile/skills", {"action": "add", "skill": "Python"}, 200),
    ("DELETE", "/api/posts/999999", {}, 404),
    # No current PUT route: a valid request reaches normal method routing.
    ("PUT", "/api/posts", {}, 405),
])
def test_all_relevant_unsafe_methods_are_guarded(signed_in, method, path, payload, allowed_status):
    if method == "DELETE":
        # Deletion is admin-only; reach object lookup rather than a role denial.
        with signed_in.session_transaction() as session:
            user = backend.db.session.get(backend.User, session["user_id"])
        user.role = "admin"
        backend.db.session.commit()
    h = headers(signed_in)
    bad = signed_in.open(path, method=method, json=payload, headers={"Origin": h["Origin"]})
    assert bad.status_code == 403
    assert bad.json["code"] == "csrf_failed"
    good = signed_in.open(path, method=method, json=payload, headers=h)
    assert good.status_code == allowed_status


def test_multipart_video_is_guarded_before_route_processing(signed_in):
    def data():
        return {"video": (BytesIO(b"test"), "invalid.txt")}
    h = headers(signed_in)
    assert signed_in.post("/api/posts/video", data=data()).status_code == 403
    response = signed_in.post("/api/posts/video", data=data(), headers=h)
    # Valid CSRF reaches existing extension validation without saving a video.
    assert response.status_code == 400
    assert response.json.get("code") != "csrf_failed"


def test_anonymous_login_and_registration_need_no_csrf(client):
    response = client.post("/api/auth/register", json={"username": "new", "password": "password123"})
    assert response.status_code == 201
    first = token(client)
    assert client.post("/api/auth/logout", headers=headers(client)).status_code == 200
    response = client.post("/api/auth/login", json={"username": "new", "password": "password123"})
    assert response.status_code == 200
    assert token(client) != first


def test_anonymous_password_reset_flows_need_no_csrf(client):
    uid = make_user()
    response = client.post("/api/auth/forgot-password", json={"username": "alice"})
    assert response.status_code == 200
    user = backend.db.session.get(backend.User, uid)
    reset_token = user.reset_token
    assert reset_token
    response = client.post("/api/auth/reset-password", json={"token": reset_token, "newPassword": "changed123"})
    assert response.status_code == 200
    assert client.post("/api/auth/login", json={"username": "alice", "password": "changed123"}).status_code == 200


def test_anonymous_demo_login_rotates_token(client, monkeypatch):
    make_user(username="demo_grad")
    monkeypatch.setattr(backend.app, "debug", True)
    assert client.post("/api/auth/demo-login", json={"role": "grad"}).status_code == 200
    first = token(client)
    assert client.post("/api/auth/demo-login", json={"role": "grad"}, headers=headers(client)).status_code == 200
    assert token(client) != first


def test_logout_requires_protection_and_clears_csrf(signed_in):
    h = headers(signed_in)
    assert signed_in.post("/api/auth/logout").status_code == 403
    assert signed_in.get("/api/auth/me").json is not None
    assert signed_in.post("/api/auth/logout", headers=h).status_code == 200
    with signed_in.session_transaction() as session:
        assert "user_id" not in session
        assert "csrf_token" not in session
        assert "csrf_user_id" not in session
    assert signed_in.get("/api/auth/csrf-token").status_code == 401
    assert signed_in.post("/api/posts", json={"body": "blocked"}, headers=h).status_code == 401
    assert signed_in.post("/api/auth/logout").status_code == 200


def test_authenticated_auth_routes_are_not_exempt_and_rotate_identity(signed_in):
    make_user(username="bob")
    payload = {"username": "bob", "password": "password123"}
    h = headers(signed_in)
    assert signed_in.post("/api/auth/login", json=payload).status_code == 403
    assert signed_in.post("/api/auth/login", json=payload, headers=h).status_code == 200
    assert token(signed_in) != h["X-CSRF-Token"]
    assert signed_in.post("/api/posts", json={"body": "blocked"}, headers=h).status_code == 403


def test_token_bound_to_identity_even_if_session_identity_changes(signed_in):
    h = headers(signed_in)
    uid = make_user(username="bob")
    with signed_in.session_transaction() as session:
        session["user_id"] = uid
    assert signed_in.post("/api/posts", json={"body": "blocked"}, headers=h).status_code == 403
    assert token(signed_in) != h["X-CSRF-Token"]
