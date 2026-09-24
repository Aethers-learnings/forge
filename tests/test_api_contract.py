"""Request/response compatibility tests for the stable API baseline."""

from werkzeug.security import generate_password_hash

import forge_backend as backend


USER_FIELDS = {
    "id", "username", "role", "name", "color", "avatarUrl", "completion",
    "cvUploaded", "skills", "alumniVerified", "bio", "headline", "programme",
    "year", "campus", "businessApproved", "company", "portfolio", "visibility",
    "onboarding",
}
POST_FIELDS = {
    "id", "name", "role", "color", "body", "media", "videoUrl", "thumbUrl",
    "pick", "flagged", "likeCount", "likedByMe", "comments",
}
OPPORTUNITY_FIELDS = {
    "id", "title", "co", "match", "matchIsFallback", "tags", "applied",
}


def assert_user_shape(payload):
    assert set(payload) == USER_FIELDS
    assert isinstance(payload["id"], int)
    assert isinstance(payload["username"], str)
    assert isinstance(payload["role"], str)
    assert isinstance(payload["name"], str)
    assert isinstance(payload["color"], str)
    assert isinstance(payload["avatarUrl"], str)
    assert isinstance(payload["completion"], int)
    assert isinstance(payload["cvUploaded"], bool)
    assert isinstance(payload["skills"], list)
    assert isinstance(payload["alumniVerified"], bool)
    assert isinstance(payload["company"], dict)
    assert isinstance(payload["portfolio"], dict)
    assert isinstance(payload["visibility"], dict)
    assert isinstance(payload["onboarding"], dict)


def assert_post_shape(payload):
    assert set(payload) == POST_FIELDS
    assert isinstance(payload["id"], int)
    assert isinstance(payload["name"], str)
    assert isinstance(payload["role"], str)
    assert isinstance(payload["color"], str)
    assert isinstance(payload["body"], str)
    assert isinstance(payload["media"], bool)
    assert payload["videoUrl"] is None or isinstance(payload["videoUrl"], str)
    assert payload["thumbUrl"] is None or isinstance(payload["thumbUrl"], str)
    assert isinstance(payload["pick"], bool)
    assert isinstance(payload["flagged"], bool)
    assert isinstance(payload["likeCount"], int)
    assert isinstance(payload["likedByMe"], bool)
    assert isinstance(payload["comments"], list)


def assert_opportunity_shape(payload):
    assert set(payload) == OPPORTUNITY_FIELDS
    assert isinstance(payload["id"], int)
    assert isinstance(payload["title"], str)
    assert isinstance(payload["co"], str)
    assert isinstance(payload["match"], int)
    assert isinstance(payload["matchIsFallback"], bool)
    assert isinstance(payload["tags"], list)
    assert isinstance(payload["applied"], bool)


def make_user(username="sam", role="trade", **kwargs):
    user = backend.User(
        username=username,
        password_hash=generate_password_hash("password123"),
        role=role,
        name=kwargs.pop("name", username),
        **kwargs,
    )
    backend.db.session.add(user)
    backend.db.session.commit()
    return user


def sign_in(client, user):
    with client.session_transaction() as session:
        session["user_id"] = user.id


def csrf_headers(client):
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    return {"Origin": "http://localhost", "X-CSRF-Token": response.json["csrfToken"]}


def test_auth_contract_covers_registration_session_and_csrf(client):
    created = client.post(
        "/api/auth/register",
        json={"username": "new-user", "password": "password123", "role": "trade", "name": "New User"},
    )

    assert created.status_code == 201
    assert_user_shape(created.json)
    assert created.json["role"] == "trade"
    assert isinstance(created.json["skills"], list)
    assert set(created.json["company"]) == {"industry", "description", "location", "talentSought"}
    assert set(created.json["portfolio"]) == {"github", "linkedin", "credly", "website"}
    assert set(created.json["visibility"]) == {"profileVisible", "showEmail", "showSkills"}

    me = client.get("/api/auth/me")
    token = client.get("/api/auth/csrf-token")
    assert me.status_code == 200
    assert me.json == created.json
    assert token.status_code == 200
    assert set(token.json) == {"csrfToken"}
    assert isinstance(token.json["csrfToken"], str) and token.json["csrfToken"]
    assert token.headers["Cache-Control"] == "no-store"

    logged_out = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert logged_out.status_code == 200
    assert logged_out.json == {"ok": True}
    assert client.get("/api/auth/me").json is None


def test_authenticated_unsafe_requests_require_documented_csrf_shape(client):
    user = make_user()
    sign_in(client, user)

    rejected = client.post("/api/posts", json={"body": "Missing token"})

    assert rejected.status_code == 403
    assert rejected.json == {
        "error": "same-origin request required",
        "code": "csrf_failed",
    }


def test_content_contract_covers_post_request_response_and_validation(client):
    user = make_user()
    sign_in(client, user)
    headers = csrf_headers(client)

    invalid = client.post("/api/posts", json={"body": "   "}, headers=headers)
    created = client.post("/api/posts", json={"body": "A stable post"}, headers=headers)
    liked = client.post(f"/api/posts/{created.json['id']}/like", headers=headers)
    unliked = client.post(f"/api/posts/{created.json['id']}/like", headers=headers)
    commented = client.post(
        f"/api/posts/{created.json['id']}/comments", json={"text": "A comment"}, headers=headers,
    )
    feed = client.get("/api/feed")

    assert invalid.status_code == 400
    assert invalid.json == {"error": "body required"}
    assert created.status_code == 201
    assert_post_shape(created.json)
    assert created.json["body"] == "A stable post"
    assert created.json["media"] is False
    assert created.json["videoUrl"] is None
    assert created.json["thumbUrl"] is None
    assert liked.status_code == 200
    assert set(liked.json) == POST_FIELDS
    assert liked.json["likedByMe"] is True
    assert unliked.status_code == 200
    assert set(unliked.json) == POST_FIELDS
    assert unliked.json["likedByMe"] is False
    assert commented.status_code == 200
    assert commented.json["comments"] == [{"who": user.name, "text": "A comment"}]
    assert feed.status_code == 200
    assert feed.json == [commented.json]


def test_opportunity_and_notification_contracts_include_toggle_and_summary_shapes(client):
    user = make_user()
    opportunity = backend.Opportunity(title="Junior developer", co="Forge", tags="Python")
    notification = backend.Notification(user_id=user.id, type="event", text="Welcome")
    backend.db.session.add_all([opportunity, notification])
    backend.db.session.commit()
    sign_in(client, user)
    headers = csrf_headers(client)

    opportunities = client.get("/api/opportunities")
    applied = client.post(f"/api/opportunities/{opportunity.id}/apply", headers=headers)
    unapplied = client.post(f"/api/opportunities/{opportunity.id}/apply", headers=headers)
    notifications = client.get("/api/notifications")
    read = client.post(f"/api/notifications/{notification.id}/read", headers=headers)

    assert opportunities.status_code == 200
    assert len(opportunities.json) == 1
    assert_opportunity_shape(opportunities.json[0])
    assert opportunities.json[0]["applied"] is False
    assert applied.status_code == 200
    assert_opportunity_shape(applied.json)
    assert applied.json["applied"] is True
    assert unapplied.status_code == 200
    assert_opportunity_shape(unapplied.json)
    assert unapplied.json["applied"] is False
    assert notifications.status_code == 200
    assert set(notifications.json) == {"notifications", "unreadCount"}
    assert notifications.json["unreadCount"] == 1
    assert set(notifications.json["notifications"][0]) == {
        "id", "type", "text", "link", "read", "createdAt",
    }
    assert read.status_code == 200
    assert read.json == {"ok": True}


def test_profile_skills_contract_preserves_request_validation_and_user_response(client):
    user = make_user()
    sign_in(client, user)
    headers = csrf_headers(client)

    invalid = client.patch("/api/profile/skills", json={"action": "rename", "skill": "Python"}, headers=headers)
    updated = client.patch("/api/profile/skills", json={"action": "add", "skill": "Python"}, headers=headers)

    assert invalid.status_code == 400
    assert invalid.json == {"error": "action ('add'/'remove') and skill are required"}
    assert updated.status_code == 200
    assert_user_shape(updated.json)
    assert updated.json["skills"] == ["Python"]

def test_auth_error_status_contract(client):
    created = client.post(
        "/api/auth/register",
        json={
            "username": "contract-user",
            "password": "password123",
            "role": "trade",
        },
    )
    assert created.status_code == 201

    # Registration establishes an authenticated session. Log out first so the
    # duplicate-registration contract is exercised as the public anonymous flow
    # rather than being intercepted by authenticated-session CSRF protection.
    logged_out = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert logged_out.status_code == 200

    duplicate = client.post(
        "/api/auth/register",
        json={
            "username": "contract-user",
            "password": "password123",
            "role": "trade",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json == {"error": "username already taken"}

    bad = client.post(
        "/api/auth/login",
        json={"username": "contract-user", "password": "wrong"},
    )
    assert bad.status_code == 401
    assert bad.json == {"error": "invalid credentials"}

    user = backend.User.query.filter_by(username="contract-user").one()
    user.suspended = True
    backend.db.session.commit()

    suspended = client.post(
        "/api/auth/login",
        json={"username": "contract-user", "password": "password123"},
    )
    assert suspended.status_code == 403
    assert suspended.json == {"error": "this account has been suspended"}

    backend._failed_logins.clear()
    for _ in range(backend.LOGIN_MAX_ATTEMPTS):
        response = client.post(
            "/api/auth/login",
            json={"username": "missing-user", "password": "wrong"},
        )
        assert response.status_code == 401

    throttled = client.post(
        "/api/auth/login",
        json={"username": "missing-user", "password": "wrong"},
    )
    assert throttled.status_code == 429
    assert throttled.json == {
        "error": "too many attempts — try again in a few minutes"
    }


def test_unauthenticated_contract_and_notification_ownership(client):
    assert client.get("/api/auth/csrf-token").status_code == 401
    assert client.get("/api/feed").status_code == 401
    assert client.get("/api/opportunities").status_code == 401

    unauthenticated_skills = client.patch(
        "/api/profile/skills",
        json={"action": "add", "skill": "Python"},
    )
    assert unauthenticated_skills.status_code == 401

    owner = make_user("owner")
    other = make_user("other")
    note = backend.Notification(user_id=other.id, type="event", text="Private")
    backend.db.session.add(note)
    backend.db.session.commit()

    sign_in(client, owner)
    forbidden = client.post(
        f"/api/notifications/{note.id}/read",
        headers=csrf_headers(client),
    )
    assert forbidden.status_code == 403
    assert forbidden.json == {"error": "not yours"}

