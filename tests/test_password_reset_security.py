"""Regression coverage for password-reset token secrecy and delivery."""
import hashlib

from werkzeug.security import generate_password_hash

import forge_backend as backend


def make_user(username="alice", email="alice@example.edu"):
    user = backend.User(
        username=username,
        name=username,
        email=email,
        role="grad",
        password_hash=generate_password_hash("password123"),
    )
    backend.db.session.add(user)
    backend.db.session.commit()
    return user


def test_reset_token_is_hashed_and_can_be_redeemed(client, monkeypatch):
    user = make_user()
    monkeypatch.setattr(backend.app, "debug", True)

    response = client.post("/api/auth/forgot-password", json={"username": user.username})

    assert response.status_code == 200
    token = response.json["devResetToken"]
    stored_user = backend.db.session.get(backend.User, user.id)
    assert stored_user.reset_token == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert stored_user.reset_token != token
    assert client.post(
        "/api/auth/reset-password",
        json={"token": token, "newPassword": "changed123"},
    ).status_code == 200
    assert backend.db.session.get(backend.User, user.id).reset_token is None


def test_non_debug_reset_never_returns_or_logs_token(client, monkeypatch, capsys):
    user = make_user(email="")
    monkeypatch.setattr(backend.app, "debug", False)

    response = client.post("/api/auth/forgot-password", json={"username": user.username})

    assert response.status_code == 200
    assert "devResetToken" not in response.json
    assert capsys.readouterr().out == ""


def test_unconfigured_email_logs_no_recipient_subject_or_body(monkeypatch, capsys):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert backend.send_email("secret@example.edu", "private subject", "reset-token-secret") is False

    output = capsys.readouterr().out
    assert "email:not-configured" in output
    assert "secret@example.edu" not in output
    assert "private subject" not in output
    assert "reset-token-secret" not in output
