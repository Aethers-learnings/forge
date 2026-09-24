"""Pin notification/onboarding behavior before the T-203 route extraction."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

import forge_backend as backend


ROUTES = [
    ("GET", "/api/notifications"),
    ("POST", "/api/notifications/1/read"),
    ("POST", "/api/notifications/read-all"),
    ("GET", "/api/onboarding"),
    ("POST", "/api/onboarding/advance"),
    ("POST", "/api/onboarding/skip"),
]
STEPS = {
    "trade": ["welcome", "add-photo", "add-skills", "upload-cv", "explore-feed"],
    "grad": ["welcome", "add-photo", "add-skills", "upload-cv", "explore-feed"],
    "business": ["welcome", "company-profile", "post-listing", "explore-candidates"],
    "admin": ["welcome", "review-queue", "explore-dashboard"],
    "unknown": ["welcome"],
}


def sign_in(client, role="grad"):
    user = backend.User(username="account", name="Account", role=role,
                        password_hash="unused: tests establish the session directly")
    backend.db.session.add(user)
    backend.db.session.commit()
    with client.session_transaction() as session:
        session["user_id"] = user.id
    response = client.get("/api/auth/csrf-token")
    assert response.status_code == 200
    return user, {"Origin": "http://localhost", "X-CSRF-Token": response.json["csrfToken"]}


@pytest.mark.parametrize("method,path", ROUTES)
def test_account_routes_require_login(client, method, path):
    response = client.open(path, method=method)
    assert response.status_code == 401
    assert response.json == {"error": "not authenticated"}


@pytest.mark.parametrize("method,path", ROUTES)
def test_account_routes_reject_suspended_users(client, method, path):
    user, headers = sign_in(client)
    user.suspended = True
    backend.db.session.commit()
    response = client.open(path, method=method, headers=headers)
    assert response.status_code == 403
    assert response.json == {"error": "account suspended — contact the administrator"}


@pytest.mark.parametrize("path", [path for method, path in ROUTES if method == "POST"])
@pytest.mark.parametrize("failure", ["missing-token", "foreign-origin"])
def test_account_mutations_keep_global_csrf_guard(client, path, failure):
    user, headers = sign_in(client)
    note = backend.Notification(user_id=user.id, type="test", text="Unread")
    backend.db.session.add(note)
    backend.db.session.commit()
    if failure == "missing-token":
        headers.pop("X-CSRF-Token")
    else:
        headers["Origin"] = "https://foreign.example"
    response = client.post(path, headers=headers)
    assert response.status_code == 403
    assert response.json["code"] == "csrf_failed"
    backend.db.session.refresh(user)
    backend.db.session.refresh(note)
    assert (user.onboarding_step, user.onboarding_complete, note.read) == (0, False, False)


@pytest.mark.parametrize("role", STEPS)
def test_onboarding_progress_persists_and_clamps_at_last_step(client, role):
    user, headers = sign_in(client, role)
    steps = STEPS[role]
    response = client.get("/api/onboarding")
    assert response.status_code == 200
    assert response.json == {"steps": steps, "step": 0, "complete": False}
    for advance in range(1, len(steps) + 2):
        step = min(advance, len(steps) - 1)
        response = client.post("/api/onboarding/advance", headers=headers)
        assert response.status_code == 200
        assert response.json == {"steps": steps, "step": step, "complete": step == len(steps) - 1}
        backend.db.session.refresh(user)
        assert user.onboarding_step == step
        assert user.onboarding_complete == response.json["complete"]
        assert client.get("/api/onboarding").json == response.json


def test_skip_keeps_current_step_and_later_advance_keeps_completion(client):
    user, headers = sign_in(client)
    client.post("/api/onboarding/advance", headers=headers)
    response = client.post("/api/onboarding/skip", headers=headers)
    assert response.status_code == 200
    assert response.json == {"steps": STEPS["grad"], "step": 1, "complete": True}
    assert client.post("/api/onboarding/skip", headers=headers).json == response.json
    advanced = client.post("/api/onboarding/advance", headers=headers)
    assert advanced.json == {"steps": STEPS["grad"], "step": 2, "complete": True}
    backend.db.session.refresh(user)
    assert (user.onboarding_step, user.onboarding_complete) == (2, True)


def test_notification_window_is_newest_first_but_unread_count_is_unbounded(client):
    user, headers = sign_in(client)
    notes = [backend.Notification(user_id=user.id, type="test", text=str(i), read=i == 51)
             for i in range(52)]
    backend.db.session.add_all(notes)
    backend.db.session.commit()
    response = client.get("/api/notifications")
    assert response.status_code == 200
    assert set(response.json) == {"notifications", "unreadCount"}
    assert [n["id"] for n in response.json["notifications"]] == [n.id for n in reversed(notes[2:])]
    assert response.json["unreadCount"] == 51
    for _ in range(2):
        marked = client.post(f"/api/notifications/{notes[0].id}/read", headers=headers)
        assert marked.status_code == 200
        assert marked.json == {"ok": True}
    assert client.get("/api/notifications").json["unreadCount"] == 50
    assert client.post("/api/notifications/read-all", headers=headers).json == {"ok": True}
    assert client.get("/api/notifications").json["unreadCount"] == 0


def test_missing_notification_keeps_flask_404_response(client):
    _, headers = sign_in(client)
    response = client.post("/api/notifications/999/read", headers=headers)
    assert response.status_code == 404
    assert response.mimetype == "text/html"


def test_account_route_methods_include_existing_head_and_options(app):
    expected = {
        "/api/notifications": {"GET", "HEAD", "OPTIONS"},
        "/api/notifications/<int:note_id>/read": {"POST", "OPTIONS"},
        "/api/notifications/read-all": {"POST", "OPTIONS"},
        "/api/onboarding": {"GET", "HEAD", "OPTIONS"},
        "/api/onboarding/advance": {"POST", "OPTIONS"},
        "/api/onboarding/skip": {"POST", "OPTIONS"},
    }
    actual = [(rule.rule, rule.methods) for rule in app.url_map.iter_rules() if rule.rule in expected]
    assert len(actual) == len(expected)
    assert dict(actual) == expected


def test_script_entrypoint_registers_routes_without_importing_a_second_app():
    """A blueprint must also work when the monolith is executed as __main__."""
    script = """
import runpy
import sys
from flask_socketio import SocketIO

calls = []
def inspect_startup(self, app, **kwargs):
    rules = [rule.rule for rule in app.url_map.iter_rules()]
    for path in ('/api/onboarding', '/api/onboarding/advance', '/api/onboarding/skip',
                 '/api/notifications', '/api/notifications/<int:note_id>/read',
                 '/api/notifications/read-all'):
        assert rules.count(path) == 1, path
    calls.append(app)

SocketIO.run = inspect_startup
runpy.run_path('forge_backend.py', run_name='__main__')
assert len(calls) == 1
assert 'forge_backend' not in sys.modules, 'The entrypoint was imported a second time'
"""
    env = dict(os.environ, FORGE_DATABASE_URI="sqlite://", FORGE_ENV="test",
               FORGE_DEBUG="0", FORGE_DEMO_MODE="0")
    result = subprocess.run([sys.executable, "-c", script], env=env,
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
